"""CLI principal del generador de catálogos v2 (multi-template).

Uso:
    python -m src.cli --cliente=morashop [flags]

Cambio multi-template:
- Cada DecisionSeleccion = 1 placa a renderizar (1 SKU + 1 template).
- Las dimensiones vienen del template, no del config.
- Un SKU puede tener N decisiones (una por template marcado en el sheet).

Cambio idempotencia total:
- Pestañas del feed-output: las que no tienen decisiones activas se BORRAN.
- Placas de Cloudinary huérfanas: se BORRAN.
- El sheet de Selección es la única fuente de verdad.
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

import yaml

from src.core.modelo_datos import (
    ResultadoRun, Producto, Placa, PlacaSubida, DecisionSeleccion,
)
from src.core.sheets_client import ConfigSheets, SheetsClient
from src.inventario.tiendanube import ConfigTiendanube, TiendanubeInventario
from src.inventario.sheet_sink import escribir_inventario
from src.seleccion.sync import (
    sync_catalogo, sync_templates, inicializar_pestaña_seleccion,
)
from src.seleccion.sheet_manual import (
    ConfigSeleccionSheet, SeleccionManualSheet,
)
from src.estilo.playwright_html import (
    ConfigPlaywrightHtml, PlaywrightHtmlEstilo,
)
from src.estilo.base import ErrorEstilo
from src.distribucion.storage.cloudinary import (
    ConfigCloudinary, CloudinaryStorage,
)
from src.distribucion.storage.base import ErrorStorage
from src.distribucion.destinos.meta_catalog import (
    ConfigMetaCatalog, MetaCatalogDestino,
)
from src.distribucion.destinos.tiktok_catalog import (
    ConfigTikTokCatalog, TikTokCatalogDestino,
)
from src.distribucion.destinos.base import ErrorDestino
from src.distribucion.historial import (
    HistorialPlacas, EntradaHistorial, calcular_hash, ahora_iso,
)
from src.distribucion import telegram_notifier
from src.enriquecimiento.base import ErrorEnriquecimiento
from src.enriquecimiento.gemini import ConfigGemini, GeminiEnriquecimiento
from src.enriquecimiento.sheet_cache import (
    CacheEnriquecimiento, calcular_hash_input,
    enriquecimiento_a_entrada_cache,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("cli")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generador de catálogos v2")
    parser.add_argument("--cliente", type=str, default=os.environ.get("CLIENTE"))
    parser.add_argument("--solo-inventario", action="store_true")
    parser.add_argument("--solo-seleccion", action="store_true")
    parser.add_argument("--sin-storage", action="store_true")
    parser.add_argument("--sin-feeds", action="store_true")
    parser.add_argument("--sin-telegram", action="store_true")
    parser.add_argument("--sin-enriquecimiento", action="store_true")
    parser.add_argument("--output-dir", type=str, default=None)
    return parser.parse_args()


def cargar_pipeline_yaml(cliente: str) -> dict:
    base = Path(__file__).parent.parent
    path = base / "clients" / cliente / "pipeline.yaml"
    if not path.exists():
        log.error("No existe %s", path)
        sys.exit(3)
    with open(path) as f:
        return yaml.safe_load(f)


def construir_fuente_inventario(cfg_inv: dict):
    fuente_tipo = cfg_inv.get("fuente")
    if fuente_tipo == "tiendanube":
        inner = cfg_inv.get("config", {})
        store_id_secret = inner["store_id_secret"]
        token_secret = inner["access_token_secret"]
        store_id = os.environ.get(store_id_secret)
        token = os.environ.get(token_secret)
        if not store_id:
            log.error("Falta env var %s", store_id_secret)
            sys.exit(10)
        if not token:
            log.error("Falta env var %s", token_secret)
            sys.exit(11)
        agrupar = inner.get("agrupar_por_producto", False)
        if agrupar:
            log.info(
                "[TN] agrupar_por_producto=True: 1 fila por producto TN "
                "(SKU = handle, agrupa variantes de talle/color)."
            )
        return TiendanubeInventario(ConfigTiendanube(
            store_id=str(store_id),
            access_token=str(token),
            agrupar_por_producto=bool(agrupar),
            cuotas_num=int(inner.get("cuotas_num", 3)),
        ))
    log.error("Fuente de inventario no soportada: %s", fuente_tipo)
    sys.exit(20)


def construir_storage(cfg_storage: dict):
    backend = cfg_storage.get("backend")
    if backend != "cloudinary":
        log.error("Storage backend no soportado: %s", backend)
        sys.exit(40)
    inner = cfg_storage.get("config", {})
    cloud_name = os.environ.get(inner.get("cloud_name_secret", "CLOUDINARY_CLOUD_NAME"))
    api_key = os.environ.get(inner.get("api_key_secret", "CLOUDINARY_API_KEY"))
    api_secret = os.environ.get(inner.get("api_secret_secret", "CLOUDINARY_API_SECRET"))
    if not cloud_name or not api_key or not api_secret:
        log.error("Faltan credenciales de Cloudinary")
        sys.exit(41)
    folder = inner.get("folder")
    if not folder:
        log.error("Falta 'folder' en config de storage")
        sys.exit(42)
    return CloudinaryStorage(ConfigCloudinary(
        cloud_name=str(cloud_name), api_key=str(api_key),
        api_secret=str(api_secret), folder=folder,
    ))


def construir_destino(
    destino_config: dict, brand_fallback: str = "", internal_label: str = "nusa_placa",
):
    tipo = destino_config.get("tipo")
    inner = destino_config.get("config", {})
    if tipo == "meta_catalog":
        return MetaCatalogDestino(ConfigMetaCatalog(
            sheet_id=inner.get("sheet_id", ""),
            moneda=inner.get("moneda", "ARS"),
            calcular_availability_por_stock=inner.get(
                "calcular_availability_por_stock", True
            ),
            aspect_ratios_aceptados=inner.get("aspect_ratios_aceptados", []),
            brand_fallback=brand_fallback,
            internal_label=internal_label,
        ))
    if tipo == "tiktok_catalog":
        return TikTokCatalogDestino(ConfigTikTokCatalog(
            sheet_id=inner.get("sheet_id", ""),
            moneda=inner.get("moneda", "ARS"),
            calcular_availability_por_stock=inner.get(
                "calcular_availability_por_stock", True
            ),
            aspect_ratios_aceptados=inner.get("aspect_ratios_aceptados", []),
            brand_fallback=brand_fallback,
            internal_label=internal_label,
        ))
    log.error("Destino no soportado: %s", tipo)
    sys.exit(50)


def _resumir_cambio_precio(p: Producto, anterior: EntradaHistorial | None) -> str:
    if anterior is None:
        return "nuevo"
    cambios = []
    if abs(p.precio_lista - anterior.precio_lista) > 0.01:
        cambios.append(f"precio: ${anterior.precio_lista:.0f} → ${p.precio_lista:.0f}")
    promo_actual = p.precio_promocional or 0
    if abs(promo_actual - anterior.precio_promo) > 0.01:
        cambios.append(f"promo: ${anterior.precio_promo:.0f} → ${promo_actual:.0f}")
    if not cambios:
        return "otros cambios (imagen, template, etc.)"
    return ", ".join(cambios)


def correr_pipeline(
    cliente: str,
    solo_inventario: bool = False,
    solo_seleccion: bool = False,
    sin_storage: bool = False,
    sin_feeds: bool = False,
    sin_enriquecimiento: bool = False,
    output_dir: str | None = None,
) -> tuple[ResultadoRun, dict]:
    resultado = ResultadoRun(cliente=cliente, inicio=datetime.now())
    pipeline = cargar_pipeline_yaml(cliente)
    base_repo = Path(__file__).parent.parent

    metricas = {
        "placas_regeneradas": 0,
        "placas_reusadas": 0,
        "skus_regenerados": [],
        "motivos_regeneracion": {},
        "feeds_resumen": {},
        "enriquecimientos_nuevos": 0,
        "enriquecimientos_reusados": 0,
        "enriquecimientos_fallidos": 0,
        "skus_huerfanos_borrados": [],
        "skus_huerfanos_fallidos": [],
        "pestañas_huerfanas_borradas": [],
    }

    # ============ BLOQUE 1: INVENTARIO ============
    cfg_inv = pipeline.get("inventario")
    if not cfg_inv:
        log.error("pipeline.yaml no tiene sección 'inventario'")
        sys.exit(4)

    log.info("[Bloque 1] Inventario")
    fuente = construir_fuente_inventario(cfg_inv)

    productos = None
    ultimo_error = None
    for intento in range(2):
        try:
            productos = fuente.traer_productos()
            break
        except Exception as e:
            ultimo_error = e
            if intento == 0:
                log.warning(
                    "[Bloque 1] Falló traer productos (intento 1/2): %s. "
                    "Esperando 30s antes de reintentar...", e,
                )
                time.sleep(30)
            else:
                log.error("[Bloque 1] Falló traer productos (intento 2/2): %s", e)

    if productos is None:
        raise RuntimeError(
            f"TN no respondió después de 2 intentos (30s de espera). "
            f"Último error: {ultimo_error}"
        )

    resultado.productos_inventario = len(productos)
    log.info("[Bloque 1] Productos: %d", len(productos))

    if not productos:
        log.warning("Cero productos. Aborto.")
        resultado.fin = datetime.now()
        return resultado, metricas

    inv_dest = cfg_inv["config"]["sheet_destino"]
    inv_client = SheetsClient(ConfigSheets(
        sheet_id=inv_dest["id"], pestaña=inv_dest["pestaña"],
    ))
    escribir_inventario(inv_client, productos)
    log.info("[Bloque 1] OK")

    if solo_inventario:
        resultado.fin = datetime.now()
        return resultado, metricas

    # ============ BLOQUE 2: SELECCIÓN ============
    cfg_sel = pipeline.get("seleccion")
    if not cfg_sel:
        log.info("[Bloque 2] No configurado")
        resultado.fin = datetime.now()
        return resultado, metricas

    sheet_sel_id = cfg_sel["config"]["sheet"]["id"]
    templates_dir = base_repo / "clients" / cliente / "templates"

    # Sync de Templates (devuelve TemplateMetadata)
    templates_metadata = sync_templates(
        sheet_id=sheet_sel_id, templates_dir=templates_dir,
    )
    templates_activos = [t.nombre for t in templates_metadata]
    templates_por_nombre = {t.nombre: t for t in templates_metadata}

    inicializar_pestaña_seleccion(sheet_id=sheet_sel_id)
    sync_catalogo(sheet_id=sheet_sel_id, productos=productos)

    fuente_sel = SeleccionManualSheet(ConfigSeleccionSheet(
        sheet_id=sheet_sel_id,
        pestaña=cfg_sel["config"]["sheet"].get("pestaña", "Seleccion"),
        templates_activos=templates_activos,
    ))
    decisiones = fuente_sel.seleccionar(productos)
    skus_unicos = {d.sku for d in decisiones}
    resultado.productos_seleccionados = len(skus_unicos)
    resultado.decisiones_totales = len(decisiones)
    log.info("[Bloque 2] %d decisiones (%d SKUs únicos × N templates)",
             len(decisiones), len(skus_unicos))

    # Validar que todos los templates referenciados existen
    decisiones_validas = []
    for d in decisiones:
        if d.template not in templates_por_nombre:
            log.warning(
                "SKU %s referencia template '%s' que no existe. Ignorado.",
                d.sku, d.template,
            )
            resultado.errores.append(
                (d.sku, f"template '{d.template}' no existe")
            )
            continue
        decisiones_validas.append(d)

    log.info("[Bloque 2] OK (%d decisiones válidas)", len(decisiones_validas))
    if solo_seleccion:
        resultado.fin = datetime.now()
        return resultado, metricas

    # ============ BLOQUE 3: ENRIQUECIMIENTO ============
    cfg_enriq = pipeline.get("enriquecimiento")
    if cfg_enriq and not sin_enriquecimiento:
        proveedor_tipo = cfg_enriq.get("proveedor")
        inner = cfg_enriq.get("config", {})

        if proveedor_tipo != "gemini":
            log.error("Proveedor de enriquecimiento no soportado: %s", proveedor_tipo)
            sys.exit(60)

        api_key_secret = inner.get("api_key_secret", "GEMINI_API_KEY")
        api_key = os.environ.get(api_key_secret)
        if not api_key:
            log.error("Falta env var %s para Gemini", api_key_secret)
            sys.exit(61)

        proveedor = GeminiEnriquecimiento(ConfigGemini(
            api_key=str(api_key),
            modelo=inner.get("modelo", "gemini-2.0-flash"),
            max_chars_titulo=inner.get("max_chars_titulo", 60),
            max_chars_descripcion=inner.get("max_chars_descripcion", 200),
            cantidad_tips=inner.get("cantidad_tips", 3),
            max_chars_tip=inner.get("max_chars_tip", 40),
            tono=inner.get("tono", ConfigGemini.__dataclass_fields__["tono"].default),
        ))
        log.info("[Bloque 3] Proveedor: %s", proveedor.nombre())

        cache = CacheEnriquecimiento(sheet_id=inv_dest["id"])
        cache_actual = cache.leer_todo()

        productos_por_sku_para_enriq = {p.sku: p for p in productos}
        cache_nuevo = dict(cache_actual)

        skus_a_enriquecer = {d.sku for d in decisiones_validas}
        skus_enriquecidos_ok = set()

        for sku in skus_a_enriquecer:
            producto = productos_por_sku_para_enriq.get(sku)
            if not producto:
                continue

            hash_actual = calcular_hash_input(producto, proveedor.nombre())
            entrada_vieja = cache_actual.get(sku)

            if entrada_vieja and entrada_vieja.hash_input == hash_actual and not entrada_vieja.error:
                enr = entrada_vieja.a_enriquecimiento()
                metricas["enriquecimientos_reusados"] += 1
            else:
                try:
                    enr = proveedor.enriquecer(producto)
                    enr.hash_input = hash_actual
                    cache_nuevo[sku] = enriquecimiento_a_entrada_cache(
                        enr, hash_actual,
                    )
                    metricas["enriquecimientos_nuevos"] += 1
                    log.info("[Bloque 3] %s enriquecido: %s", sku, enr.titulo_corto)
                except ErrorEnriquecimiento as e:
                    log.error("[Bloque 3] Falló %s: %s", sku, e)
                    resultado.errores.append((sku, f"enriquecimiento: {e}"))
                    metricas["enriquecimientos_fallidos"] += 1
                    continue

            producto.enriquecimiento = {
                **(producto.enriquecimiento or {}),
                "titulo_corto": enr.titulo_corto,
                "descripcion_corta": enr.descripcion_corta,
                "tips": enr.tips,
                "proveedor": enr.proveedor,
            }
            skus_enriquecidos_ok.add(sku)

        decisiones_validas = [
            d for d in decisiones_validas if d.sku in skus_enriquecidos_ok
        ]

        try:
            cache.escribir_todo(cache_nuevo)
        except Exception as e:
            log.error("[Bloque 3] No pude guardar el cache: %s", e)
            resultado.errores.append(("cache_enriquecimiento", str(e)))

        log.info(
            "[Bloque 3] OK: %d nuevos, %d reusados, %d fallidos. %d decisiones válidas",
            metricas["enriquecimientos_nuevos"],
            metricas["enriquecimientos_reusados"],
            metricas["enriquecimientos_fallidos"],
            len(decisiones_validas),
        )
    else:
        log.info("[Bloque 3] Skipeado (sin_enriquecimiento=%s, cfg=%s)",
                 sin_enriquecimiento, bool(cfg_enriq))

    # ============ HISTORIAL ============
    historial = HistorialPlacas(sheet_id=inv_dest["id"])
    historial_actual = historial.leer_todo()
    log.info("[Historial] %d entradas (SKU × template)", len(historial_actual))

    # ============ BLOQUE 4 + 5.1: ESTILO + STORAGE ============
    cfg_estilo = pipeline.get("estilo")
    if not cfg_estilo:
        log.info("[Bloque 4] No configurado")
        resultado.fin = datetime.now()
        return resultado, metricas

    cfg_estilo_inner = cfg_estilo.get("config", {})

    if output_dir:
        output_path = Path(output_dir)
    elif os.environ.get("OUTPUT_DIR"):
        output_path = Path(os.environ["OUTPUT_DIR"])
    else:
        output_path = Path(tempfile.gettempdir()) / "placas" / cliente
    output_path.mkdir(parents=True, exist_ok=True)

    productos_por_sku = {p.sku: p for p in productos}
    decisiones_ordenadas = sorted(
        decisiones_validas, key=lambda d: (d.prioridad, d.sku, d.template)
    )

    motor_config = ConfigPlaywrightHtml(
        templates_dir=templates_dir,
        output_dir=output_path,
        variables_globales=cfg_estilo_inner.get("variables_globales", {}),
        hotsale_discount_factor=cfg_estilo_inner.get("hotsale_discount_factor", 1.0),
        descuento_efectivo_factor=cfg_estilo_inner.get("descuento_efectivo_factor"),
        cuotas_sobre_promocional=cfg_estilo_inner.get("cuotas_sobre_promocional", False),
    )

    cfg_dist = pipeline.get("distribucion", {})
    cfg_storage = cfg_dist.get("storage")
    storage = None
    if not sin_storage and cfg_storage:
        storage = construir_storage(cfg_storage)
        log.info("[Bloque 5.1] Storage: %s", storage.nombre())

    a_regenerar: list[tuple[Producto, DecisionSeleccion, str]] = []
    a_reusar: list[tuple[Producto, DecisionSeleccion, EntradaHistorial]] = []

    for decision in decisiones_ordenadas:
        producto = productos_por_sku.get(decision.sku)
        if not producto:
            log.warning("SKU %s no está en inventario. Salteado.", decision.sku)
            resultado.errores.append((decision.sku, "no está en inventario"))
            continue

        hash_nuevo = calcular_hash(producto, decision, templates_dir)
        entrada_vieja = historial_actual.get((decision.sku, decision.template))

        if entrada_vieja and entrada_vieja.hash_render == hash_nuevo and entrada_vieja.url_cloudinary:
            a_reusar.append((producto, decision, entrada_vieja))
        else:
            a_regenerar.append((producto, decision, hash_nuevo))

    log.info("[Bloque 4] %d a regenerar, %d a reusar",
             len(a_regenerar), len(a_reusar))

    placas_generadas: list[Placa] = []
    decision_por_placa: dict[tuple[str, str], DecisionSeleccion] = {}
    if a_regenerar:
        with PlaywrightHtmlEstilo(motor_config) as motor:
            for i, (producto, decision, hash_nuevo) in enumerate(a_regenerar, start=1):
                try:
                    placa = motor.renderizar(producto, decision)
                    placas_generadas.append(placa)
                    decision_por_placa[(producto.sku, decision.template)] = decision

                    motivo = _resumir_cambio_precio(
                        producto, historial_actual.get((producto.sku, decision.template)),
                    )
                    if producto.sku not in metricas["skus_regenerados"]:
                        metricas["skus_regenerados"].append(producto.sku)
                        metricas["motivos_regeneracion"][producto.sku] = motivo

                    log.info("[%d/%d] %s [%s] → %s",
                             i, len(a_regenerar),
                             producto.sku, decision.template, placa.path_local)
                except ErrorEstilo as e:
                    # Fallo de ITEM (imagen 404, template inválido, etc.):
                    # se saltea esta placa y la corrida sigue con el resto.
                    # Los errores sistémicos (browser de Playwright caído,
                    # timeout de página) NO son ErrorEstilo: propagan crudos
                    # y abortan la corrida (fail-fast), que es lo deseado.
                    log.error("Falló render de %s [%s]: %s. Se saltea esta placa.",
                              producto.sku, decision.template, e)
                    resultado.errores.append(
                        (producto.sku, f"{decision.template}: {e}")
                    )
                    continue

    placas_subidas_nuevas: list[PlacaSubida] = []
    if storage and placas_generadas:
        for i, placa in enumerate(placas_generadas, start=1):
            try:
                subida = storage.subir(placa)
                subida.template_usado = placa.template_usado
                subida.aspect_ratio = placa.aspect_ratio
                placas_subidas_nuevas.append(subida)
                log.info("[%d/%d] Subido: %s [%s] → %s",
                         i, len(placas_generadas),
                         subida.sku, placa.template_usado, subida.url_publica)
            except ErrorStorage as e:
                log.error("Falló subida de %s [%s]: %s",
                          placa.sku, placa.template_usado, e)
                resultado.errores.append(
                    (placa.sku, f"storage {placa.template_usado}: {e}")
                )

    placas_subidas_reusadas: list[PlacaSubida] = []
    for producto, decision, entrada in a_reusar:
        aspect_ratio_template = templates_por_nombre.get(decision.template)
        ar = aspect_ratio_template.aspect_ratio if aspect_ratio_template else entrada.aspect_ratio
        placas_subidas_reusadas.append(PlacaSubida(
            sku=producto.sku,
            template_usado=decision.template,
            url_publica=entrada.url_cloudinary,
            storage_backend="cloudinary",
            aspect_ratio=ar,
        ))

    placas_subidas_total = placas_subidas_nuevas + placas_subidas_reusadas

    metricas["placas_regeneradas"] = len(placas_generadas)
    metricas["placas_reusadas"] = len(a_reusar)
    resultado.placas_generadas = len(placas_generadas)
    resultado.placas_subidas = len(placas_subidas_total)
    log.info("[Bloque 4+5.1] OK: %d regen, %d reus, %d en storage",
             len(placas_generadas), len(a_reusar), len(placas_subidas_total))

    # ============ ACTUALIZAR HISTORIAL ============
    fecha_render_ahora = ahora_iso()
    historial_nuevo: dict[tuple[str, str], EntradaHistorial] = {}

    skus_template_subidos_ok = {
        (s.sku, s.template_usado) for s in placas_subidas_nuevas
    }
    url_por_sku_template = {
        (s.sku, s.template_usado): s.url_publica for s in placas_subidas_nuevas
    }
    aspect_por_template = {t.nombre: t.aspect_ratio for t in templates_metadata}

    for producto, decision, hash_nuevo in a_regenerar:
        key = (producto.sku, decision.template)
        if key not in skus_template_subidos_ok:
            continue
        historial_nuevo[key] = EntradaHistorial(
            sku=producto.sku,
            template=decision.template,
            precio_lista=producto.precio_lista,
            precio_promo=producto.precio_promocional or 0.0,
            url_cloudinary=url_por_sku_template[key],
            fecha_render=fecha_render_ahora,
            hash_render=hash_nuevo,
            aspect_ratio=aspect_por_template.get(decision.template, "4:5"),
        )
    for producto, decision, entrada_vieja in a_reusar:
        historial_nuevo[(producto.sku, decision.template)] = entrada_vieja

    # ============ LIMPIEZA DE HUÉRFANOS EN CLOUDINARY ============
    keys_activas = set(historial_nuevo.keys())
    keys_anteriores = set(historial_actual.keys())
    huerfanas = keys_anteriores - keys_activas

    if huerfanas and storage:
        log.info("[Limpieza Cloudinary] %d placas huérfanas detectadas", len(huerfanas))
        borrados_ok = []
        borrados_falla = []
        for (sku, template) in huerfanas:
            public_id = f"{sku}__{template}"
            if storage.borrar(public_id):
                borrados_ok.append(f"{sku}/{template}")
                log.info("[Limpieza Cloudinary] Borrado: %s/%s", sku, template)
            else:
                borrados_falla.append(f"{sku}/{template}")
                log.warning("[Limpieza Cloudinary] No pude borrar: %s/%s", sku, template)
        metricas["skus_huerfanos_borrados"] = borrados_ok
        metricas["skus_huerfanos_fallidos"] = borrados_falla

    try:
        historial.escribir_todo(historial_nuevo)
        log.info("[Historial] Actualizado: %d entradas", len(historial_nuevo))
    except Exception as e:
        log.error("[Historial] Falló actualizar: %s", e)
        resultado.errores.append(("historial", str(e)))

    if sin_storage or not cfg_storage:
        resultado.fin = datetime.now()
        return resultado, metricas

    # ============ BLOQUE 5.2: DESTINOS ============
    if sin_feeds:
        resultado.fin = datetime.now()
        return resultado, metricas

    destinos_cfg = cfg_dist.get("destinos", [])
    if not destinos_cfg:
        log.info("[Bloque 5.2] No hay destinos configurados")
        resultado.fin = datetime.now()
        return resultado, metricas

    # Marca del cliente: fallback del campo 'brand' del feed cuando Tiendanube
    # no trae marca. Meta exige brand/gtin/mpn, así que no puede quedar vacío.
    brand_fallback = pipeline.get("cliente", {}).get("brand_name", "")
    # Etiqueta fija para distinguir el origen 'placa' del feed nativo de TN
    # en el mismo catálogo. Configurable a nivel distribucion; default nusa_placa.
    internal_label = cfg_dist.get("internal_label", "nusa_placa")

    feeds_publicados = 0
    for destino_config in destinos_cfg:
        destino = construir_destino(
            destino_config, brand_fallback=brand_fallback, internal_label=internal_label,
        )
        log.info("[Bloque 5.2] Destino: %s", destino.nombre())
        try:
            resultados = destino.publicar(
                productos, placas_subidas_total, decisiones_validas,
            )
            total_filas = sum(resultados.values())
            log.info("[Bloque 5.2] %s: %d pestañas, %d filas",
                     destino.nombre(), len(resultados), total_filas)
            for pestaña, n in resultados.items():
                log.info("[Bloque 5.2]   - %s: %d filas", pestaña, n)
                metricas["feeds_resumen"][pestaña] = n
            feeds_publicados += 1

            # ============ LIMPIEZA DE PESTAÑAS HUÉRFANAS ============
            # Borrar pestañas del feed-output que NO se escribieron este run.
            # Esto convierte al sheet en un espejo idempotente del Seleccion.
            try:
                pestañas_activas = set(resultados.keys())
                borradas = destino.eliminar_pestañas_huerfanas(pestañas_activas)
                if borradas:
                    log.info("[Bloque 5.2] %s: %d pestañas huérfanas borradas: %s",
                             destino.nombre(), len(borradas), borradas)
                    metricas["pestañas_huerfanas_borradas"].extend(borradas)
            except Exception as e:
                log.warning("[Bloque 5.2] %s: falló limpieza de pestañas huérfanas: %s",
                            destino.nombre(), e)

        except ErrorDestino as e:
            log.error("Falló destino %s: %s", destino.nombre(), e)
            resultado.errores.append((destino.nombre(), str(e)))

    resultado.feeds_publicados = feeds_publicados
    log.info("[Bloque 5.2] OK (%d destinos)", feeds_publicados)

    resultado.fin = datetime.now()
    return resultado, metricas


def main() -> None:
    args = parse_args()
    if not args.cliente:
        log.error("Falta --cliente o env var CLIENTE")
        sys.exit(2)

    log.info("=== Cliente: %s ===", args.cliente)

    url_run = ""
    if os.environ.get("GITHUB_RUN_ID") and os.environ.get("GITHUB_REPOSITORY"):
        url_run = (
            f"https://github.com/{os.environ['GITHUB_REPOSITORY']}"
            f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        )

    try:
        resultado, metricas = correr_pipeline(
            args.cliente,
            solo_inventario=args.solo_inventario,
            solo_seleccion=args.solo_seleccion,
            sin_storage=args.sin_storage,
            sin_feeds=args.sin_feeds,
            sin_enriquecimiento=args.sin_enriquecimiento,
            output_dir=args.output_dir,
        )
    except Exception as e:
        tb = traceback.format_exc()
        log.error("Pipeline falló: %s\n%s", e, tb)
        if not args.sin_telegram:
            error_str = str(e)
            if "TN no respondió" in error_str:
                bloque = "Bloque 1 (Inventario - TN no responde)"
            elif "Cloudinary" in error_str:
                bloque = "Bloque 5.1 (Storage Cloudinary)"
            elif "Gemini" in error_str:
                bloque = "Bloque 3 (Enriquecimiento Gemini)"
            elif "sheet" in error_str.lower() or "Sheets" in error_str:
                bloque = "Sheets API"
            else:
                bloque = "ver logs"

            msg = telegram_notifier.formatear_resumen_falla(
                cliente=args.cliente,
                fecha_iso=datetime.now().strftime("%Y-%m-%d %H:%M ART"),
                error_msg=str(e),
                bloque=bloque,
                url_run=url_run,
            )
            telegram_notifier.notificar(msg)
        raise

    log.info(
        "=== Fin: inventario=%d, seleccionados=%d, decisiones=%d, "
        "enriq=%d nuevos/%d reusados/%d fallidos, "
        "placas=%d regen/%d reus, subidas=%d, feeds=%d, "
        "pestañas_huerf=%d, errores=%d, %.1fs ===",
        resultado.productos_inventario,
        resultado.productos_seleccionados,
        resultado.decisiones_totales,
        metricas["enriquecimientos_nuevos"],
        metricas["enriquecimientos_reusados"],
        metricas["enriquecimientos_fallidos"],
        metricas["placas_regeneradas"],
        metricas["placas_reusadas"],
        resultado.placas_subidas,
        resultado.feeds_publicados,
        len(metricas.get("pestañas_huerfanas_borradas", [])),
        len(resultado.errores),
        resultado.duracion_segundos or 0,
    )

    if not args.sin_telegram:
        msg = telegram_notifier.formatear_resumen_exito(
            cliente=args.cliente,
            fecha_iso=datetime.now().strftime("%Y-%m-%d %H:%M ART"),
            duracion_segundos=resultado.duracion_segundos or 0,
            inventario=resultado.productos_inventario,
            seleccionados=resultado.productos_seleccionados,
            placas_regeneradas=metricas["placas_regeneradas"],
            placas_reusadas=metricas["placas_reusadas"],
            feeds_resumen=metricas["feeds_resumen"],
            skus_regenerados=metricas["skus_regenerados"],
            motivos_regeneracion=metricas["motivos_regeneracion"],
            enriq_nuevos=metricas["enriquecimientos_nuevos"],
            enriq_reusados=metricas["enriquecimientos_reusados"],
            enriq_fallidos=metricas["enriquecimientos_fallidos"],
            skus_huerfanos_borrados=metricas["skus_huerfanos_borrados"],
            skus_huerfanos_fallidos=metricas["skus_huerfanos_fallidos"],
            errores=resultado.errores,
        )
        telegram_notifier.notificar(msg)


if __name__ == "__main__":
    main()
