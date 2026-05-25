"""CLI principal del generador de catálogos v2.

Uso:
    python -m src.cli --cliente=morashop [flags]

Fase F: diff inteligente (solo regenera placas con cambios) + Telegram.
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
    parser = argparse.ArgumentParser(description="Generador de catálogos v2 (Agency Nusa)")
    parser.add_argument("--cliente", type=str, default=os.environ.get("CLIENTE"))
    parser.add_argument("--solo-inventario", action="store_true")
    parser.add_argument("--solo-seleccion", action="store_true")
    parser.add_argument("--sin-storage", action="store_true")
    parser.add_argument("--sin-feeds", action="store_true")
    parser.add_argument("--sin-telegram", action="store_true",
                        help="No mandar mensaje a Telegram al final")
    parser.add_argument("--sin-enriquecimiento", action="store_true",
                        help="Skipear Bloque 3 (usar nombre/desc crudos de TN)")
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
        store_id_secret = cfg_inv["config"]["store_id_secret"]
        token_secret = cfg_inv["config"]["access_token_secret"]
        store_id = os.environ.get(store_id_secret)
        token = os.environ.get(token_secret)
        if not store_id:
            log.error("Falta env var %s", store_id_secret)
            sys.exit(10)
        if not token:
            log.error("Falta env var %s", token_secret)
            sys.exit(11)
        return TiendanubeInventario(ConfigTiendanube(
            store_id=str(store_id), access_token=str(token),
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


def construir_destino(destino_config: dict):
    tipo = destino_config.get("tipo")
    inner = destino_config.get("config", {})
    if tipo == "meta_catalog":
        return MetaCatalogDestino(ConfigMetaCatalog(
            sheet_id=inner.get("sheet_id", ""),
            moneda=inner.get("moneda", "ARS"),
            calcular_availability_por_stock=inner.get(
                "calcular_availability_por_stock", True
            ),
        ))
    if tipo == "tiktok_catalog":
        return TikTokCatalogDestino(ConfigTikTokCatalog(
            sheet_id=inner.get("sheet_id", ""),
            moneda=inner.get("moneda", "ARS"),
            calcular_availability_por_stock=inner.get(
                "calcular_availability_por_stock", True
            ),
        ))
    log.error("Destino no soportado: %s", tipo)
    sys.exit(50)


def _resumir_cambio_precio(p: Producto, anterior: EntradaHistorial | None) -> str:
    """Helper: arma un texto breve describiendo qué cambió, para Telegram."""
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
    """Corre el pipeline. Devuelve resultado + métricas extra para Telegram."""
    resultado = ResultadoRun(cliente=cliente, inicio=datetime.now())
    pipeline = cargar_pipeline_yaml(cliente)
    base_repo = Path(__file__).parent.parent

    # Métricas extra que devolvemos para que el resumen de Telegram las use
    metricas = {
        "placas_regeneradas": 0,
        "placas_reusadas": 0,
        "skus_regenerados": [],       # lista de SKUs que se re-renderizaron
        "motivos_regeneracion": {},   # {sku: "precio: $X → $Y"}
        "feeds_resumen": {},          # {nombre_pestaña: filas}
        "enriquecimientos_nuevos": 0,
        "enriquecimientos_reusados": 0,
        "enriquecimientos_fallidos": 0,
        "skus_huerfanos_borrados": [],   # SKUs que salieron y limpiamos
        "skus_huerfanos_fallidos": [],   # SKUs que intentamos borrar pero falló
    }

    # ============ BLOQUE 1: INVENTARIO ============
    cfg_inv = pipeline.get("inventario")
    if not cfg_inv:
        log.error("pipeline.yaml no tiene sección 'inventario'")
        sys.exit(4)

    log.info("[Bloque 1] Inventario")
    fuente = construir_fuente_inventario(cfg_inv)

    # Reintento: 1 reintento con 30s de espera. TN a veces tira blip de red.
    # Si falla DOS veces seguidas, Telegram avisa con alerta clara (main()).
    productos = None
    ultimo_error = None
    for intento in range(2):
        try:
            productos = fuente.traer_productos()
            break  # éxito
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
        # Los 2 intentos fallaron. Tiramos excepción para que main() la capture
        # y mande alerta a Telegram con el formato de falla.
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

    templates_disponibles = sync_templates(
        sheet_id=sheet_sel_id, templates_dir=templates_dir,
    )
    inicializar_pestaña_seleccion(sheet_id=sheet_sel_id)
    sync_catalogo(sheet_id=sheet_sel_id, productos=productos)

    fuente_sel = SeleccionManualSheet(ConfigSeleccionSheet(
        sheet_id=sheet_sel_id,
        pestaña=cfg_sel["config"]["sheet"].get("pestaña", "Seleccion"),
    ))
    decisiones = fuente_sel.seleccionar(productos)
    resultado.productos_seleccionados = len(decisiones)
    log.info("[Bloque 2] Decisiones válidas: %d", len(decisiones))

    templates_set = set(templates_disponibles)
    decisiones_validas = []
    for d in decisiones:
        if d.template not in templates_set:
            log.warning(
                "SKU %s referencia template '%s' que no existe. Ignorado.",
                d.sku, d.template,
            )
            resultado.errores.append(
                (d.sku, f"template '{d.template}' no existe")
            )
            continue
        decisiones_validas.append(d)

    log.info("[Bloque 2] OK")
    if solo_seleccion:
        resultado.fin = datetime.now()
        return resultado, metricas

    # ============ BLOQUE 3: ENRIQUECIMIENTO ============
    # Mergea titulo_corto / descripcion_corta / tips dentro de
    # producto.enriquecimiento. Si Gemini falla en un SKU, ese SKU se quita
    # de las decisiones (no entra al feed).
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

        # Cache: lee la pestaña Enriquecimiento del sheet de Inventario
        cache = CacheEnriquecimiento(sheet_id=inv_dest["id"])
        cache_actual = cache.leer_todo()

        productos_por_sku_para_enriq = {p.sku: p for p in productos}
        cache_nuevo = dict(cache_actual)  # copia para mutar

        decisiones_post_enriq = []
        for decision in decisiones_validas:
            producto = productos_por_sku_para_enriq.get(decision.sku)
            if not producto:
                continue

            hash_actual = calcular_hash_input(producto, proveedor.nombre())
            entrada_vieja = cache_actual.get(decision.sku)

            if entrada_vieja and entrada_vieja.hash_input == hash_actual and not entrada_vieja.error:
                # Cache hit: reusar
                enr = entrada_vieja.a_enriquecimiento()
                metricas["enriquecimientos_reusados"] += 1
            else:
                # Cache miss: llamar a Gemini
                try:
                    enr = proveedor.enriquecer(producto)
                    enr.hash_input = hash_actual
                    cache_nuevo[decision.sku] = enriquecimiento_a_entrada_cache(
                        enr, hash_actual,
                    )
                    metricas["enriquecimientos_nuevos"] += 1
                    log.info("[Bloque 3] %s enriquecido: %s",
                             decision.sku, enr.titulo_corto)
                except ErrorEnriquecimiento as e:
                    log.error("[Bloque 3] Falló %s: %s", decision.sku, e)
                    resultado.errores.append((decision.sku, f"enriquecimiento: {e}"))
                    metricas["enriquecimientos_fallidos"] += 1
                    # Decisión del usuario: SKU NO entra al feed
                    continue

            # Mergear enriquecimiento en producto.enriquecimiento (dict)
            producto.enriquecimiento = {
                "titulo_corto": enr.titulo_corto,
                "descripcion_corta": enr.descripcion_corta,
                "tips": enr.tips,
                "proveedor": enr.proveedor,
            }
            decisiones_post_enriq.append(decision)

        # Reemplazamos decisiones_validas con las que sí pasaron Bloque 3
        decisiones_validas = decisiones_post_enriq

        # Guardamos cache (incluso si algunos SKUs fallaron, los exitosos se guardan)
        try:
            cache.escribir_todo(cache_nuevo)
        except Exception as e:
            log.error("[Bloque 3] No pude guardar el cache: %s", e)
            resultado.errores.append(("cache_enriquecimiento", str(e)))

        log.info(
            "[Bloque 3] OK: %d nuevos, %d reusados, %d fallidos",
            metricas["enriquecimientos_nuevos"],
            metricas["enriquecimientos_reusados"],
            metricas["enriquecimientos_fallidos"],
        )
    else:
        log.info("[Bloque 3] Skipeado (sin_enriquecimiento=%s, cfg=%s)",
                 sin_enriquecimiento, bool(cfg_enriq))

    # ============ HISTORIAL: cargar antes de Bloque 4 ============
    historial = HistorialPlacas(sheet_id=inv_dest["id"])
    historial_actual = historial.leer_todo()
    skus_unicos_historial = len({sku for (sku, _) in historial_actual.keys()})
    log.info("[Historial] %d entradas (%d SKUs únicos)",
             len(historial_actual), skus_unicos_historial)

    # ============ BLOQUE 4 + 5.1: ESTILO + STORAGE (multi-aspect-ratio) ============
    # Fase H activada: cada SKU genera N placas según `aspect_ratios` del yaml.
    # 4:5 → Meta, 9:16 → TikTok. El diff inteligente trackea cada uno por separado.
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
    decisiones_ordenadas = sorted(decisiones_validas, key=lambda d: d.prioridad)

    # Aspect ratios a procesar. Si el yaml define la sección 'aspect_ratios',
    # se itera; si no, default a una sola pasada 4:5 (retrocompat).
    aspect_ratios_cfg = cfg_estilo_inner.get("aspect_ratios") or [{
        "label": "4:5",
        "width": cfg_estilo_inner.get("placa_width", 1080),
        "height": cfg_estilo_inner.get("placa_height", 1350),
        "template_suffix": "",
    }]
    log.info("[Bloque 4] Procesando %d aspect_ratios: %s",
             len(aspect_ratios_cfg),
             [ar.get("label", "?") for ar in aspect_ratios_cfg])

    # Storage: construir una sola vez, lo reusamos en cada pasada
    cfg_dist = pipeline.get("distribucion", {})
    cfg_storage = cfg_dist.get("storage")
    storage = None
    if not sin_storage and cfg_storage:
        storage = construir_storage(cfg_storage)
        log.info("[Bloque 5.1] Storage: %s", storage.nombre())

    # Acumuladores GLOBALES a través de todos los aspect_ratios.
    # Los feeds reciben TODAS las placas subidas y filtran por aspect_ratio.
    placas_subidas_total: list[PlacaSubida] = []
    historial_nuevo: dict[tuple[str, str], EntradaHistorial] = {}
    # Productos/decisiones para los feeds (dedup por SKU, agnóstico de aspect_ratio)
    productos_renderizados_set: dict[str, Producto] = {}
    decisiones_renderizadas_set: dict[str, DecisionSeleccion] = {}
    total_regeneradas = 0
    total_reusadas = 0
    fecha_render_ahora = ahora_iso()

    # ----- LOOP sobre aspect_ratios -----
    for ar_cfg in aspect_ratios_cfg:
        ar_label = ar_cfg.get("label", "4:5")
        ar_width = ar_cfg.get("width", 1080)
        ar_height = ar_cfg.get("height", 1350)
        # template_suffix: "" para 4:5 (template tal cual), "_tiktok" para 9:16
        template_suffix = ar_cfg.get("template_suffix", "")

        log.info("[Bloque 4][%s] Procesando aspect_ratio %s (%dx%d, suffix='%s')",
                 ar_label, ar_label, ar_width, ar_height, template_suffix)

        motor_config = ConfigPlaywrightHtml(
            templates_dir=templates_dir,
            output_dir=output_path,
            placa_width=ar_width,
            placa_height=ar_height,
            variables_globales=cfg_estilo_inner.get("variables_globales", {}),
            hotsale_discount_factor=cfg_estilo_inner.get("hotsale_discount_factor", 1.0),
        )

        # Para este aspect_ratio: separar regenerar vs reusar
        a_regenerar: list[tuple[Producto, DecisionSeleccion, str]] = []
        a_reusar: list[tuple[Producto, DecisionSeleccion, EntradaHistorial]] = []

        for decision in decisiones_ordenadas:
            producto = productos_por_sku.get(decision.sku)
            if not producto:
                if ar_label == aspect_ratios_cfg[0].get("label"):
                    # Solo log una vez (en la primera pasada) para no duplicar
                    log.warning("SKU %s no está en inventario. Salteado.", decision.sku)
                    resultado.errores.append((decision.sku, "no está en inventario"))
                continue

            # Construir el nombre del template aplicado para este aspect_ratio
            template_a_usar = decision.template + template_suffix
            template_path = templates_dir / f"{template_a_usar}.html"
            if not template_path.exists():
                log.warning(
                    "[%s] Template '%s' no existe (esperado en %s). "
                    "SKU %s salteado en este aspect_ratio.",
                    ar_label, template_a_usar, template_path, decision.sku,
                )
                continue

            # Decision con el template ajustado (para que renderizar() use el correcto
            # y el hash se calcule con el HTML correcto)
            decision_ajustada = DecisionSeleccion(
                sku=decision.sku,
                generar=decision.generar,
                template=template_a_usar,
                prioridad=decision.prioridad,
                notas=decision.notas,
            )

            hash_nuevo = calcular_hash(
                producto, decision_ajustada, templates_dir,
                template_name=template_a_usar,
                aspect_ratio=ar_label,
            )
            entrada_vieja = historial_actual.get((decision.sku, ar_label))

            if entrada_vieja and entrada_vieja.hash_render == hash_nuevo and entrada_vieja.url_cloudinary:
                a_reusar.append((producto, decision_ajustada, entrada_vieja))
            else:
                a_regenerar.append((producto, decision_ajustada, hash_nuevo))

        log.info("[Bloque 4][%s] %d a regenerar, %d a reusar",
                 ar_label, len(a_regenerar), len(a_reusar))

        # Render: solo si hay algo que regenerar
        placas_generadas: list[Placa] = []
        if a_regenerar:
            with PlaywrightHtmlEstilo(motor_config) as motor:
                for i, (producto, decision_ajustada, hash_nuevo) in enumerate(a_regenerar, start=1):
                    try:
                        placa = motor.renderizar(producto, decision_ajustada)
                        placas_generadas.append(placa)

                        # Métricas Telegram: solo el primer aspect_ratio popula
                        # skus_regenerados (evita duplicados visuales en el mensaje).
                        # Las 9:16 son visibles en el log pero no en la lista resumen.
                        if ar_label == aspect_ratios_cfg[0].get("label"):
                            motivo = _resumir_cambio_precio(
                                producto, historial_actual.get((producto.sku, ar_label)),
                            )
                            if producto.sku not in metricas["skus_regenerados"]:
                                metricas["skus_regenerados"].append(producto.sku)
                                metricas["motivos_regeneracion"][producto.sku] = motivo

                        log.info("[%s][%d/%d] %s → %s",
                                 ar_label, i, len(a_regenerar),
                                 producto.sku, placa.path_local)
                    except ErrorEstilo as e:
                        log.error("Falló render de %s [%s]: %s", producto.sku, ar_label, e)
                        resultado.errores.append((producto.sku, f"{ar_label}: {e}"))
                        raise

        total_regeneradas += len(placas_generadas)
        total_reusadas += len(a_reusar)

        # Subida a storage de las nuevas (en este aspect_ratio)
        placas_subidas_nuevas: list[PlacaSubida] = []
        if storage and placas_generadas:
            for i, placa in enumerate(placas_generadas, start=1):
                try:
                    subida = storage.subir(placa)
                    placas_subidas_nuevas.append(subida)
                    log.info("[%s][%d/%d] Subido: %s → %s",
                             ar_label, i, len(placas_generadas),
                             subida.sku, subida.url_publica)
                except ErrorStorage as e:
                    log.error("Falló subida de %s [%s]: %s", placa.sku, ar_label, e)
                    resultado.errores.append((placa.sku, f"storage {ar_label}: {e}"))

        # Reusadas: armar PlacaSubida virtual con la URL del historial
        placas_subidas_reusadas: list[PlacaSubida] = [
            PlacaSubida(
                sku=p.sku,
                url_publica=entrada.url_cloudinary,
                storage_backend="cloudinary",
                aspect_ratio=ar_label,
            )
            for (p, _, entrada) in a_reusar
        ]

        # Acumular para los feeds (todas las pasadas juntas)
        placas_subidas_total.extend(placas_subidas_nuevas)
        placas_subidas_total.extend(placas_subidas_reusadas)

        # Productos/decisiones (dedup por SKU; usamos la decision original sin sufijo
        # para que el feed agrupe por template lógico, no por template_tiktok)
        def _quitar_suffix(template_name: str, suffix: str) -> str:
            """Quita el sufijo SOLO si está al final del nombre."""
            if suffix and template_name.endswith(suffix):
                return template_name[:-len(suffix)]
            return template_name

        for p, d, _ in a_reusar:
            productos_renderizados_set[p.sku] = p
            decision_para_feed = DecisionSeleccion(
                sku=d.sku,
                generar=d.generar,
                template=_quitar_suffix(d.template, template_suffix),
                prioridad=d.prioridad,
                notas=d.notas,
            )
            decisiones_renderizadas_set[p.sku] = decision_para_feed
        for p, d, _ in a_regenerar:
            productos_renderizados_set[p.sku] = p
            decision_para_feed = DecisionSeleccion(
                sku=d.sku,
                generar=d.generar,
                template=_quitar_suffix(d.template, template_suffix),
                prioridad=d.prioridad,
                notas=d.notas,
            )
            decisiones_renderizadas_set[p.sku] = decision_para_feed

        # Actualizar historial para este aspect_ratio
        skus_subidos_ok = {s.sku for s in placas_subidas_nuevas}
        for producto, decision_ajustada, hash_nuevo in a_regenerar:
            if producto.sku not in skus_subidos_ok:
                # Falló la subida: NO actualizamos el historial para este SKU/ar
                # (queremos reintentar mañana solo este aspect_ratio)
                continue
            url = next(s.url_publica for s in placas_subidas_nuevas if s.sku == producto.sku)
            historial_nuevo[(producto.sku, ar_label)] = EntradaHistorial(
                sku=producto.sku,
                template=decision_ajustada.template,  # template REAL usado (con sufijo)
                precio_lista=producto.precio_lista,
                precio_promo=producto.precio_promocional or 0.0,
                url_cloudinary=url,
                fecha_render=fecha_render_ahora,
                hash_render=hash_nuevo,
                aspect_ratio=ar_label,
            )
        for producto, decision_ajustada, entrada_vieja in a_reusar:
            historial_nuevo[(producto.sku, ar_label)] = entrada_vieja

    # ----- Fin del loop aspect_ratios -----

    # Métricas globales (suma de todos los aspect_ratios)
    metricas["placas_regeneradas"] = total_regeneradas
    metricas["placas_reusadas"] = total_reusadas
    resultado.placas_generadas = total_regeneradas
    resultado.placas_subidas = len(placas_subidas_total)
    log.info("[Bloque 4+5.1] OK: %d regen, %d reus, %d en storage final",
             total_regeneradas, total_reusadas, len(placas_subidas_total))

    # Listas para feeds
    productos_para_feeds = list(productos_renderizados_set.values())
    decisiones_para_feeds = list(decisiones_renderizadas_set.values())

    # ============ LIMPIEZA DE SKUs HUÉRFANOS ============
    # Un SKU es huérfano si NINGUNA entrada (en ningún aspect_ratio) está en
    # historial_nuevo. Si el 4:5 está OK pero el 9:16 falló, NO es huérfano.
    skus_activos = {sku for (sku, _) in historial_nuevo.keys()}
    skus_historial_anterior = {sku for (sku, _) in historial_actual.keys()}
    skus_huerfanos = skus_historial_anterior - skus_activos
    if skus_huerfanos and storage:
        log.info("[Limpieza] %d SKUs huérfanos detectados", len(skus_huerfanos))
        borrados_ok = []
        borrados_falla = []
        for sku in skus_huerfanos:
            if storage.borrar(sku):
                borrados_ok.append(sku)
                log.info("[Limpieza] Borrado de Cloudinary: %s", sku)
            else:
                borrados_falla.append(sku)
                log.warning("[Limpieza] No pude borrar de Cloudinary: %s", sku)
        metricas["skus_huerfanos_borrados"] = borrados_ok
        metricas["skus_huerfanos_fallidos"] = borrados_falla
        log.info("[Limpieza] OK: %d borrados, %d fallidos",
                 len(borrados_ok), len(borrados_falla))
    else:
        metricas["skus_huerfanos_borrados"] = []
        metricas["skus_huerfanos_fallidos"] = []

    # Guardar historial completo (todos los aspect_ratios juntos)
    try:
        historial.escribir_todo(historial_nuevo)
        log.info("[Historial] Actualizado: %d entradas", len(historial_nuevo))
    except Exception as e:
        log.error("[Historial] Falló actualizar: %s", e)
        resultado.errores.append(("historial", str(e)))

    # Si no hay storage, salimos antes de los feeds
    if sin_storage:
        resultado.fin = datetime.now()
        return resultado, metricas

    if not cfg_storage:
        log.info("[Bloque 5.1] Storage no configurado")
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

    feeds_publicados = 0
    for destino_config in destinos_cfg:
        destino = construir_destino(destino_config)
        log.info("[Bloque 5.2] Destino: %s", destino.nombre())
        try:
            resultados = destino.publicar(
                productos_para_feeds,
                placas_subidas_total,
                decisiones_para_feeds,
            )
            total_filas = sum(resultados.values())
            log.info("[Bloque 5.2] %s: %d pestañas, %d filas",
                     destino.nombre(), len(resultados), total_filas)
            for pestaña, n in resultados.items():
                log.info("[Bloque 5.2]   - %s: %d filas", pestaña, n)
                metricas["feeds_resumen"][pestaña] = n
            feeds_publicados += 1
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

    # URL del run (GitHub Actions lo expone como env var)
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
        # Capturamos cualquier excepción no manejada para mandar a Telegram
        tb = traceback.format_exc()
        log.error("Pipeline falló: %s\n%s", e, tb)
        if not args.sin_telegram:
            # Intentar deducir el bloque que rompió a partir del mensaje
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
        raise  # re-raisear para que GitHub Actions marque rojo

    log.info(
        "=== Fin: inventario=%d, seleccionados=%d, "
        "enriq=%d nuevos/%d reusados/%d fallidos, "
        "placas=%d regen/%d reus, subidas=%d, feeds=%d, errores=%d, %.1fs ===",
        resultado.productos_inventario,
        resultado.productos_seleccionados,
        metricas["enriquecimientos_nuevos"],
        metricas["enriquecimientos_reusados"],
        metricas["enriquecimientos_fallidos"],
        metricas["placas_regeneradas"],
        metricas["placas_reusadas"],
        resultado.placas_subidas,
        resultado.feeds_publicados,
        len(resultado.errores),
        resultado.duracion_segundos or 0,
    )

    # Telegram (solo si hubo éxito; si hubo excepción, ya se manejó arriba)
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
            skus_huerfanos_borrados=metricas.get("skus_huerfanos_borrados", []),
            skus_huerfanos_fallidos=metricas.get("skus_huerfanos_fallidos", []),
        )
        telegram_notifier.notificar(msg)


if __name__ == "__main__":
    main()
