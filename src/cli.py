"""CLI principal del generador de catálogos v2.

Uso:
    python -m src.cli --cliente=morashop [--solo-inventario] [--solo-seleccion]

Fase D: implementa Bloques 1 (Inventario), 2 (Selección) y 4 (Estilo).
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
        help="Corre solo el Bloque 1 (no toca Selección ni Estilo).",
    )
    parser.add_argument(
        "--solo-seleccion", action="store_true",
        help="Corre Bloques 1 + 2, sin renderizar placas.",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Override del directorio de placas. Default: temporal.",
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


def correr_pipeline(
    cliente: str,
    solo_inventario: bool = False,
    solo_seleccion: bool = False,
    output_dir: str | None = None,
) -> ResultadoRun:
    """Ejecuta el pipeline para un cliente."""
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
        sheet_id=inv_dest["id"],
        pestaña=inv_dest["pestaña"],
    ))
    escribir_inventario(inv_client, productos)
    log.info("[Bloque 1] OK")

    if solo_inventario:
        log.info("--solo-inventario: salgo sin tocar Selección ni Estilo")
        resultado.fin = datetime.now()
        return resultado

    # ============ BLOQUE 2: SELECCIÓN ============
    cfg_sel = pipeline.get("seleccion")
    if not cfg_sel:
        log.info("[Bloque 2] No configurado en pipeline.yaml, salteo")
        resultado.fin = datetime.now()
        return resultado

    sheet_sel_id = cfg_sel["config"]["sheet"]["id"]
    templates_dir = base_repo / "clients" / cliente / "templates"

    # Orden importante (ver Fase C): Templates → Seleccion → Catalogo
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
    log.info("[Bloque 2] Decisiones generar=SI: %d", len(decisiones))

    # Validar templates referenciados
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

    log.info("[Bloque 2] Decisiones válidas: %d", len(decisiones_validas))
    log.info("[Bloque 2] OK")

    if solo_seleccion:
        log.info("--solo-seleccion: salgo sin renderizar placas")
        resultado.fin = datetime.now()
        return resultado

    # ============ BLOQUE 4: ESTILO ============
    cfg_estilo = pipeline.get("estilo")
    if not cfg_estilo:
        log.info("[Bloque 4] No configurado en pipeline.yaml, salteo")
        resultado.fin = datetime.now()
        return resultado

    motor_tipo = cfg_estilo.get("motor")
    if motor_tipo != "playwright_html":
        log.error("Motor de estilo no soportado: %s", motor_tipo)
        sys.exit(30)

    cfg_estilo_inner = cfg_estilo.get("config", {})

    # Output dir: arg CLI > env > temporal
    if output_dir:
        output_path = Path(output_dir)
    elif os.environ.get("OUTPUT_DIR"):
        output_path = Path(os.environ["OUTPUT_DIR"])
    else:
        output_path = Path(tempfile.gettempdir()) / "placas" / cliente
    output_path.mkdir(parents=True, exist_ok=True)
    log.info("[Bloque 4] Output dir: %s", output_path)

    # Indexar productos por SKU para lookup rápido
    productos_por_sku = {p.sku: p for p in productos}

    # Ordenar decisiones por prioridad (1 = alta) para que las importantes
    # se generen primero. Si falla a mitad, al menos las prioritarias están.
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
    with PlaywrightHtmlEstilo(motor_config) as motor:
        for i, decision in enumerate(decisiones_ordenadas, start=1):
            producto = productos_por_sku.get(decision.sku)
            if not producto:
                # Defensive: ya filtramos en Bloque 2, pero por las dudas
                log.warning("SKU %s no está en inventario. Salteado.", decision.sku)
                resultado.errores.append((decision.sku, "no está en inventario"))
                continue

            try:
                placa = motor.renderizar(producto, decision)
                placas_generadas.append(placa)
                log.info("[%d/%d] %s → %s",
                         i, len(decisiones_ordenadas),
                         producto.sku, placa.path_local)
            except ErrorEstilo as e:
                # Fail-fast (decisión de Faco): propagar y romper el run.
                log.error("Falló render de %s: %s", producto.sku, e)
                resultado.errores.append((producto.sku, str(e)))
                raise

    resultado.placas_generadas = len(placas_generadas)
    log.info("[Bloque 4] %d placas generadas", len(placas_generadas))
    log.info("[Bloque 4] OK")

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
        output_dir=args.output_dir,
    )
    log.info(
        "=== Fin: inventario=%d, seleccionados=%d, placas=%d, errores=%d, %.1fs ===",
        resultado.productos_inventario,
        resultado.productos_seleccionados,
        resultado.placas_generadas,
        len(resultado.errores),
        resultado.duracion_segundos or 0,
    )


if __name__ == "__main__":
    main()
