"""CLI principal del generador de catálogos v2.

Uso:
    python -m src.cli --cliente=morashop

En esta fase (B) implementa solo el Bloque 1: Inventario.
Lee config de clients/{cliente}/pipeline.yaml, trae productos de la fuente
configurada, y los escribe al Sheet de Inventario.
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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("cli")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generador de catálogos v2 (Agency Nusa)")
    parser.add_argument(
        "--cliente", type=str, default=os.environ.get("CLIENTE"),
        help="Nombre del cliente (carpeta dentro de clients/).",
    )
    parser.add_argument(
        "--solo-inventario", action="store_true",
        help="Corre solo el Bloque 1 (Inventario). Default en Fase B.",
    )
    return parser.parse_args()


def cargar_pipeline_yaml(cliente: str) -> dict:
    """Lee y parsea el pipeline.yaml del cliente."""
    base = Path(__file__).parent.parent
    path = base / "clients" / cliente / "pipeline.yaml"
    if not path.exists():
        log.error("No existe %s", path)
        sys.exit(3)
    with open(path) as f:
        return yaml.safe_load(f)


def construir_fuente_inventario(cfg_inv: dict):
    """Instancia la fuente de inventario según la config."""
    fuente_tipo = cfg_inv.get("fuente")

    if fuente_tipo == "tiendanube":
        store_id_secret = cfg_inv["config"]["store_id_secret"]
        token_secret = cfg_inv["config"]["access_token_secret"]

        store_id = os.environ.get(store_id_secret)
        token = os.environ.get(token_secret)

        if not store_id:
            log.error("Falta env var %s (store_id de Tiendanube)", store_id_secret)
            sys.exit(10)
        if not token:
            log.error("Falta env var %s (access_token de Tiendanube)", token_secret)
            sys.exit(11)

        return TiendanubeInventario(ConfigTiendanube(
            store_id=str(store_id),
            access_token=str(token),
        ))

    log.error("Fuente de inventario no soportada: %s", fuente_tipo)
    sys.exit(20)


def construir_sheets_client(cfg_inv: dict) -> SheetsClient:
    """Instancia el cliente de Sheets para escribir el inventario."""
    dest = cfg_inv["config"]["sheet_destino"]
    return SheetsClient(ConfigSheets(
        sheet_id=dest["id"],
        pestaña=dest["pestaña"],
        # credenciales se leen de env var GOOGLE_SERVICE_ACCOUNT_JSON automáticamente
    ))


def correr_inventario(cliente: str) -> ResultadoRun:
    """Ejecuta Bloque 1: trae productos de la fuente y los escribe al sheet."""
    resultado = ResultadoRun(cliente=cliente, inicio=datetime.now())

    pipeline = cargar_pipeline_yaml(cliente)
    cfg_inv = pipeline.get("inventario")
    if not cfg_inv:
        log.error("pipeline.yaml no tiene sección 'inventario'")
        sys.exit(4)

    fuente = construir_fuente_inventario(cfg_inv)
    log.info("Fuente de inventario: %s", fuente.nombre())

    productos = fuente.traer_productos()
    resultado.productos_inventario = len(productos)
    log.info("Productos traídos: %d", len(productos))

    if not productos:
        log.warning("Cero productos traídos. ¿Hay catálogo en la tienda?")
        resultado.fin = datetime.now()
        return resultado

    client = construir_sheets_client(cfg_inv)
    n_escritos = escribir_inventario(client, productos)
    log.info("Escritos %d productos al sheet", n_escritos)

    resultado.fin = datetime.now()
    return resultado


def main() -> None:
    args = parse_args()
    if not args.cliente:
        log.error("Falta --cliente o env var CLIENTE")
        sys.exit(2)

    log.info("=== Cliente: %s ===", args.cliente)
    resultado = correr_inventario(args.cliente)

    log.info(
        "=== Fin: %d productos, %.1fs ===",
        resultado.productos_inventario,
        resultado.duracion_segundos or 0,
    )


if __name__ == "__main__":
    main()
