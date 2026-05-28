"""Lógica compartida entre destinos Meta y TikTok (multi-template).

Cambio multi-template:
- Las decisiones llegan como list[DecisionSeleccion] donde un SKU puede
  aparecer N veces con distintos templates.
- Cada template = 1 pestaña en el feed. Se filtra por template, no por SKU.
- Las placas subidas se filtran por (sku, template, aspect_ratio).
"""
from __future__ import annotations
import logging
from collections import defaultdict

from src.core.modelo_datos import Producto, PlacaSubida, DecisionSeleccion
from src.core.sheets_client import ConfigSheets, SheetsClient
from src.distribucion.destinos.base import ErrorDestino


log = logging.getLogger(__name__)


def calcular_availability(producto: Producto, calcular_por_stock: bool) -> str:
    if not calcular_por_stock:
        return "in stock"
    if producto.stock is None:
        return "in stock"
    return "in stock" if producto.stock > 0 else "out of stock"


def formatear_precio(valor: float, moneda: str) -> str:
    return f"{valor:.2f} {moneda}"


def producto_a_fila(
    producto: Producto,
    url_imagen: str,
    moneda: str,
    calcular_availability_por_stock: bool,
) -> list:
    enriq = producto.enriquecimiento or {}
    title = enriq.get("titulo_corto") or producto.nombre
    description = (
        enriq.get("descripcion_corta")
        or producto.descripcion
        or producto.nombre
    )

    return [
        producto.sku,
        title,
        description,
        calcular_availability(producto, calcular_availability_por_stock),
        "new",
        formatear_precio(producto.precio_efectivo, moneda),
        producto.url_producto,
        url_imagen,
        producto.marca or "Agency Nusa",
    ]


def agrupar_decisiones_por_template(
    decisiones: list[DecisionSeleccion],
) -> dict[str, list[DecisionSeleccion]]:
    """Agrupa decisiones por template. 1 template = 1 grupo = 1 pestaña."""
    grupos: dict[str, list[DecisionSeleccion]] = defaultdict(list)
    for d in decisiones:
        grupos[d.template].append(d)
    return dict(grupos)


def escribir_pestaña_feed(
    sheet_id: str,
    pestaña: str,
    headers: list[str],
    decisiones_grupo: list[DecisionSeleccion],
    productos_por_sku: dict[str, Producto],
    placas_por_sku_template: dict[tuple[str, str], PlacaSubida],
    moneda: str,
    calcular_availability_por_stock: bool,
) -> int:
    """Escribe UNA pestaña del feed (modo replace).

    Args:
        decisiones_grupo: decisiones de ESTE template (todas mismo template).
        productos_por_sku: índice de productos del run.
        placas_por_sku_template: índice {(sku, template): PlacaSubida}.

    Returns:
        Cantidad de filas escritas.
    """
    filas = []
    sin_placa = 0
    sin_producto = 0
    for decision in decisiones_grupo:
        producto = productos_por_sku.get(decision.sku)
        if not producto:
            sin_producto += 1
            continue
        placa = placas_por_sku_template.get((decision.sku, decision.template))
        if not placa:
            sin_placa += 1
            continue
        filas.append(producto_a_fila(
            producto, placa.url_publica, moneda, calcular_availability_por_stock,
        ))

    if sin_placa:
        log.warning(
            "Pestaña '%s': %d decisiones sin placa subida",
            pestaña, sin_placa,
        )
    if sin_producto:
        log.warning(
            "Pestaña '%s': %d decisiones sin producto en inventario",
            pestaña, sin_producto,
        )

    client = SheetsClient(ConfigSheets(sheet_id=sheet_id, pestaña=pestaña))
    try:
        client.escribir_replace(headers, filas)
    except Exception as e:
        raise ErrorDestino(f"Falló escritura pestaña '{pestaña}': {e}") from e

    log.info("Pestaña '%s': %d filas escritas", pestaña, len(filas))
    return len(filas)
