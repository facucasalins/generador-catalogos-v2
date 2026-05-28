"""Lógica compartida entre destinos Meta y TikTok (multi-template).

Cambio multi-template:
- Las decisiones llegan como list[DecisionSeleccion] donde un SKU puede
  aparecer N veces con distintos templates.
- Cada template = 1 pestaña individual en el feed (visualización/debug).
- Hay además una pestaña MAESTRA consolidada (Meta_Feed / TikTok_Feed) que
  contiene TODAS las decisiones de la plataforma con id único e item_group_id.

Sobre el id consolidado:
- id            = sku + '__' + template     (ej: "bota-X__Meta_default_4x5")
- item_group_id = sku                        (ej: "bota-X")
- Esto permite que Meta acepte el mismo SKU varias veces (distintas placas)
  y entienda que son VARIANTES del mismo producto físico.
"""
from __future__ import annotations
import logging
from collections import defaultdict

from src.core.modelo_datos import Producto, PlacaSubida, DecisionSeleccion
from src.core.sheets_client import ConfigSheets, SheetsClient
from src.distribucion.destinos.base import ErrorDestino


log = logging.getLogger(__name__)


# ===================== HELPERS GENERALES =====================

def calcular_availability(producto: Producto, calcular_por_stock: bool) -> str:
    if not calcular_por_stock:
        return "in stock"
    if producto.stock is None:
        return "in stock"
    return "in stock" if producto.stock > 0 else "out of stock"


def formatear_precio(valor: float, moneda: str) -> str:
    return f"{valor:.2f} {moneda}"


def agrupar_decisiones_por_template(
    decisiones: list[DecisionSeleccion],
) -> dict[str, list[DecisionSeleccion]]:
    """Agrupa decisiones por template. 1 template = 1 grupo = 1 pestaña individual."""
    grupos: dict[str, list[DecisionSeleccion]] = defaultdict(list)
    for d in decisiones:
        grupos[d.template].append(d)
    return dict(grupos)


# ===================== FILAS: PESTAÑAS INDIVIDUALES =====================

def producto_a_fila_individual(
    producto: Producto,
    url_imagen: str,
    moneda: str,
    calcular_availability_por_stock: bool,
) -> list:
    """Fila para pestaña INDIVIDUAL (1 por template).

    id = SKU directo (sin sufijo). Estas pestañas existen para
    visualización/debug. Si conectás esta pestaña directamente a Meta,
    Meta sigue aceptando porque no hay duplicación de id (cada pestaña
    individual tiene 1 fila por SKU como máximo).
    """
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


# Alias para compatibilidad con código existente
producto_a_fila = producto_a_fila_individual


# ===================== FILAS: PESTAÑA MAESTRA CONSOLIDADA =====================

def producto_a_fila_maestra(
    producto: Producto,
    template: str,
    url_imagen: str,
    moneda: str,
    calcular_availability_por_stock: bool,
) -> list:
    """Fila para pestaña MAESTRA (Meta_Feed / TikTok_Feed).

    id            = sku + '__' + template (ej: "bota-X__Meta_default_4x5")
    item_group_id = sku                    (ej: "bota-X")

    Esto permite que el mismo SKU aparezca N veces (1 por template), y
    Meta/TikTok entienden que son variantes del mismo producto físico.
    """
    enriq = producto.enriquecimiento or {}
    title = enriq.get("titulo_corto") or producto.nombre
    description = (
        enriq.get("descripcion_corta")
        or producto.descripcion
        or producto.nombre
    )

    id_consolidado = f"{producto.sku}__{template}"

    return [
        id_consolidado,              # id (único)
        producto.sku,                # item_group_id (= SKU base)
        title,
        description,
        calcular_availability(producto, calcular_availability_por_stock),
        "new",
        formatear_precio(producto.precio_efectivo, moneda),
        producto.url_producto,
        url_imagen,
        producto.marca or "Agency Nusa",
    ]


# ===================== ESCRITURA =====================

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
    """Escribe UNA pestaña INDIVIDUAL del feed (modo replace).

    Las pestañas individuales tienen 1 fila por SKU (porque cada
    decisión del grupo es de un template único + SKU único).
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
        filas.append(producto_a_fila_individual(
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


def escribir_pestaña_maestra(
    sheet_id: str,
    pestaña: str,
    headers: list[str],
    decisiones_plataforma: list[DecisionSeleccion],
    productos_por_sku: dict[str, Producto],
    placas_por_sku_template: dict[tuple[str, str], PlacaSubida],
    moneda: str,
    calcular_availability_por_stock: bool,
) -> int:
    """Escribe la pestaña MAESTRA consolidada (Meta_Feed o TikTok_Feed).

    Esta pestaña contiene TODAS las decisiones de la plataforma (no agrupadas
    por template). Cada fila tiene id único = sku + '__' + template y
    item_group_id = sku.

    Esta es la pestaña que se conecta a Meta Catalog / TikTok Catalog.
    Las pestañas individuales por template existen además como visualización.
    """
    filas = []
    sin_placa = 0
    sin_producto = 0
    for decision in decisiones_plataforma:
        producto = productos_por_sku.get(decision.sku)
        if not producto:
            sin_producto += 1
            continue
        placa = placas_por_sku_template.get((decision.sku, decision.template))
        if not placa:
            sin_placa += 1
            continue
        filas.append(producto_a_fila_maestra(
            producto, decision.template, placa.url_publica,
            moneda, calcular_availability_por_stock,
        ))

    if sin_placa:
        log.warning(
            "Pestaña maestra '%s': %d decisiones sin placa subida",
            pestaña, sin_placa,
        )
    if sin_producto:
        log.warning(
            "Pestaña maestra '%s': %d decisiones sin producto en inventario",
            pestaña, sin_producto,
        )

    client = SheetsClient(ConfigSheets(sheet_id=sheet_id, pestaña=pestaña))
    try:
        client.escribir_replace(headers, filas)
    except Exception as e:
        raise ErrorDestino(f"Falló escritura pestaña maestra '{pestaña}': {e}") from e

    log.info("Pestaña maestra '%s': %d filas escritas (consolidadas)",
             pestaña, len(filas))
    return len(filas)
