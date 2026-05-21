"""CLI principal del generador de catálogos v2.

Uso:
    python -m src.cli --cliente=morashop [--solo-inventario]

Fase C: implementa Bloques 1 (Inventario) y 2 (Selección).
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("cli")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generador de catálogos v2 (Agency Nusa)")
    parser.add_argument("--cliente", type=str, default=os.environ.get("CLIENTE"))
    parser.add_argument(
        "--solo-inventario", action="store_true",
        help="Corre solo el Bloque 1 (no toca el sheet de Selección).",
    )
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


def correr_pipeline(cliente: str, solo_inventario: bool = False) -> ResultadoRun:
    """Ejecuta el pipeline para un cliente."""
    resultado = ResultadoRun(cliente=cliente, inicio=datetime.now())

    pipeline = cargar_pipeline_yaml(cliente)

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

    # Escribir Inventario al sheet propio
    inv_dest = cfg_inv["config"]["sheet_destino"]
    inv_client = SheetsClient(ConfigSheets(
        sheet_id=inv_dest["id"],
        pestaña=inv_dest["pestaña"],
    ))
    escribir_inventario(inv_client, productos)
    log.info("[Bloque 1] OK")

    if solo_inventario:
        log.info("--solo-inventario: salgo sin tocar Selección")
        resultado.fin = datetime.now()
        return resultado

    # ============ BLOQUE 2: SELECCIÓN ============
    cfg_sel = pipeline.get("seleccion")
    if not cfg_sel:
        log.info("[Bloque 2] No configurado en pipeline.yaml, salteo")
        resultado.fin = datetime.now()
        return resultado

    sheet_sel_id = cfg_sel["config"]["sheet"]["id"]

    # ⚠️ ORDEN IMPORTANTE: primero Templates, después Seleccion (el dropdown
    # de Seleccion referencia la pestaña Templates, así que tiene que existir
    # antes). Después Catalogo (ese no tiene dependencias).
    #
    # 2a) Sync Templates PRIMERO
    templates_dir = Path(__file__).parent.parent / "clients" / cliente / "templates"
    templates_disponibles = sync_templates(
        sheet_id=sheet_sel_id, templates_dir=templates_dir,
    )

    # 2b) Inicializar pestaña Seleccion (con dropdown que apunta a Templates)
    inicializar_pestaña_seleccion(sheet_id=sheet_sel_id)

    # 2c) Sync Catalogo (espejo del inventario)
    sync_catalogo(sheet_id=sheet_sel_id, productos=productos)

    # 2d) Leer pestaña Seleccion y filtrar decisiones
    fuente_sel = SeleccionManualSheet(ConfigSeleccionSheet(
        sheet_id=sheet_sel_id,
        pestaña=cfg_sel["config"]["sheet"].get("pestaña", "Seleccion"),
    ))
    decisiones = fuente_sel.seleccionar(productos)
    resultado.productos_seleccionados = len(decisiones)
    log.info("[Bloque 2] Decisiones generar=SI: %d", len(decisiones))

    # Validar que los templates referenciados existen
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

    log.info("[Bloque 2] Decisiones válidas (con template existente): %d",
             len(decisiones_validas))
    log.info("[Bloque 2] OK")

    resultado.fin = datetime.now()
    return resultado


def main() -> None:
    args = parse_args()
    if not args.cliente:
        log.error("Falta --cliente o env var CLIENTE")
        sys.exit(2)

    log.info("=== Cliente: %s ===", args.cliente)
    resultado = correr_pipeline(args.cliente, solo_inventario=args.solo_inventario)
    log.info(
        "=== Fin: inventario=%d, seleccionados=%d, errores=%d, %.1fs ===",
        resultado.productos_inventario,
        resultado.productos_seleccionados,
        len(resultado.errores),
        resultado.duracion_segundos or 0,
    )


if __name__ == "__main__":
    main()
