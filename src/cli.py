"""CLI principal del generador de catálogos v2.

Uso:
    python -m src.cli --cliente=morashop [flags]

Fase E.2 refactor + E.3: Meta + TikTok, 1 pestaña por template.
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

from src.core.modelo_datos import ResultadoRun
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
    """Construye un destino concreto según su tipo."""
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


def correr_pipeline(
    cliente: str,
    solo_inventario: bool = False,
    solo_seleccion: bool = False,
    sin_storage: bool = False,
    sin_feeds: bool = False,
    output_dir: str | None = None,
) -> ResultadoRun:
    resultado = ResultadoRun(cliente=cliente, inicio=datetime.now())
    pipeline = cargar_pipeline_yaml(cliente)
    base_repo = Path(__file__).parent.parent

    # ============ BLOQUE 1: INVENTARIO ============
    cfg_inv = pipeline.get("inventario")
    if not cfg_inv:
        log.error("pipeline.yaml no tiene sección 'inventario'")
        sys.exit(4)

    fuente = construir_fuente_inventario(cfg_inv)
    log.info("[Bloque 1] Fuente: %s", fuente.nombre())
    productos = fuente.traer_productos()
    resultado.productos_inventario = len(productos)
    log.info("[Bloque 1] Productos: %d", len(productos))

    if not productos:
        log.warning("Cero productos. Aborto.")
        resultado.fin = datetime.now()
        return resultado

    inv_dest = cfg_inv["config"]["sheet_destino"]
    inv_client = SheetsClient(ConfigSheets(
        sheet_id=inv_dest["id"], pestaña=inv_dest["pestaña"],
    ))
    escribir_inventario(inv_client, productos)
    log.info("[Bloque 1] OK")

    if solo_inventario:
        resultado.fin = datetime.now()
        return resultado

    # ============ BLOQUE 2: SELECCIÓN ============
    cfg_sel = pipeline.get("seleccion")
    if not cfg_sel:
        log.info("[Bloque 2] No configurado")
        resultado.fin = datetime.now()
        return resultado

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
        return resultado

    # ============ BLOQUE 4: ESTILO ============
    cfg_estilo = pipeline.get("estilo")
    if not cfg_estilo:
        log.info("[Bloque 4] No configurado")
        resultado.fin = datetime.now()
        return resultado

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

    motor_config = ConfigPlaywrightHtml(
        templates_dir=templates_dir,
        output_dir=output_path,
        placa_width=cfg_estilo_inner.get("placa_width", 1080),
        placa_height=cfg_estilo_inner.get("placa_height", 1350),
        variables_globales=cfg_estilo_inner.get("variables_globales", {}),
        hotsale_discount_factor=cfg_estilo_inner.get("hotsale_discount_factor", 1.0),
    )

    placas_generadas = []
    productos_renderizados = []
    decisiones_renderizadas = []  # paralelo a productos_renderizados
    with PlaywrightHtmlEstilo(motor_config) as motor:
        for i, decision in enumerate(decisiones_ordenadas, start=1):
            producto = productos_por_sku.get(decision.sku)
            if not producto:
                log.warning("SKU %s no está en inventario. Salteado.", decision.sku)
                resultado.errores.append((decision.sku, "no está en inventario"))
                continue

            try:
                placa = motor.renderizar(producto, decision)
                placas_generadas.append(placa)
                productos_renderizados.append(producto)
                decisiones_renderizadas.append(decision)
                log.info("[%d/%d] %s → %s",
                         i, len(decisiones_ordenadas),
                         producto.sku, placa.path_local)
            except ErrorEstilo as e:
                log.error("Falló render de %s: %s", producto.sku, e)
                resultado.errores.append((producto.sku, str(e)))
                raise

    resultado.placas_generadas = len(placas_generadas)
    log.info("[Bloque 4] %d placas generadas", len(placas_generadas))

    # ============ BLOQUE 5.1: STORAGE ============
    if sin_storage:
        resultado.fin = datetime.now()
        return resultado

    cfg_dist = pipeline.get("distribucion", {})
    cfg_storage = cfg_dist.get("storage")
    if not cfg_storage:
        log.info("[Bloque 5.1] Storage no configurado")
        resultado.fin = datetime.now()
        return resultado

    storage = construir_storage(cfg_storage)
    log.info("[Bloque 5.1] Storage: %s", storage.nombre())

    placas_subidas = []
    for i, placa in enumerate(placas_generadas, start=1):
        try:
            subida = storage.subir(placa)
            placas_subidas.append(subida)
            log.info("[%d/%d] Subido: %s → %s",
                     i, len(placas_generadas), subida.sku, subida.url_publica)
        except ErrorStorage as e:
            log.error("Falló subida de %s: %s", placa.sku, e)
            resultado.errores.append((placa.sku, f"storage: {e}"))

    resultado.placas_subidas = len(placas_subidas)
    log.info("[Bloque 5.1] %d placas subidas", len(placas_subidas))

    # ============ BLOQUE 5.2: DESTINOS ============
    if sin_feeds:
        resultado.fin = datetime.now()
        return resultado

    destinos_cfg = cfg_dist.get("destinos", [])
    if not destinos_cfg:
        log.info("[Bloque 5.2] No hay destinos configurados")
        resultado.fin = datetime.now()
        return resultado

    feeds_publicados = 0
    for destino_config in destinos_cfg:
        destino = construir_destino(destino_config)
        log.info("[Bloque 5.2] Destino: %s", destino.nombre())
        try:
            # Refactor: ahora pasamos decisiones para que el destino agrupe
            # por template
            resultados = destino.publicar(
                productos_renderizados,
                placas_subidas,
                decisiones_renderizadas,
            )
            total_filas = sum(resultados.values())
            log.info("[Bloque 5.2] %s: %d pestañas, %d filas totales",
                     destino.nombre(), len(resultados), total_filas)
            for pestaña, n in resultados.items():
                log.info("[Bloque 5.2]   - %s: %d filas", pestaña, n)
            feeds_publicados += 1
        except ErrorDestino as e:
            log.error("Falló destino %s: %s", destino.nombre(), e)
            resultado.errores.append((destino.nombre(), str(e)))

    resultado.feeds_publicados = feeds_publicados
    log.info("[Bloque 5.2] OK (%d destinos publicados)", feeds_publicados)

    resultado.fin = datetime.now()
    return resultado


def main() -> None:
    args = parse_args()
    if not args.cliente:
        log.error("Falta --cliente o env var CLIENTE")
        sys.exit(2)

    log.info("=== Cliente: %s ===", args.cliente)
    resultado = correr_pipeline(
        args.cliente,
        solo_inventario=args.solo_inventario,
        solo_seleccion=args.solo_seleccion,
        sin_storage=args.sin_storage,
        sin_feeds=args.sin_feeds,
        output_dir=args.output_dir,
    )
    log.info(
        "=== Fin: inventario=%d, seleccionados=%d, placas=%d, subidas=%d, feeds=%d, errores=%d, %.1fs ===",
        resultado.productos_inventario,
        resultado.productos_seleccionados,
        resultado.placas_generadas,
        resultado.placas_subidas,
        resultado.feeds_publicados,
        len(resultado.errores),
        resultado.duracion_segundos or 0,
    )


if __name__ == "__main__":
    main()
