"""Lógica compartida entre destinos Meta y TikTok (multi-template).

Estructura de salida por destino:
- 1 pestaña MAESTRA consolidada (Meta_Feed / TikTok_Feed) con TODAS las
  decisiones de la plataforma. Cada fila tiene id único e item_group_id
  con el SKU base. Se conecta a Meta/TikTok Catalog Manager.
- N pestañas INDIVIDUALES (1 por template) para visualización/debug.

Sobre el id consolidado:
- id (Meta) / sku_id (TikTok) = sku + '__' + template
- item_group_id = sku
- Esto permite que Meta/TikTok acepte el mismo SKU varias veces (distintas
  placas) y entienda que son VARIANTES del mismo producto físico.
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
    brand_fallback: str = "",
) -> list:
    """Fila para pestaña INDIVIDUAL (1 por template).

    Identificador = SKU directo (sin sufijo). Estas pestañas existen para
    visualización/debug. No tienen duplicados (cada pestaña individual tiene
    1 fila por SKU como máximo).

    brand_fallback: marca del cliente (cliente.brand_name) que se usa cuando
    Tiendanube no trae marca en el producto. Meta rechaza productos sin
    brand/gtin/mpn, así que el brand no puede quedar vacío.
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
        producto.marca or brand_fallback,
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
    brand_fallback: str = "",
) -> list:
    """Fila para pestaña MAESTRA (Meta_Feed / TikTok_Feed).

    Identificador consolidado = sku + '__' + template (único)
    item_group_id            = sku                    (agrupa variantes)

    Funciona para Meta (columna 'id') y TikTok (columna 'sku_id'): la
    función devuelve los VALORES, los nombres de columnas los define
    cada destino en sus HEADERS.
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
        id_consolidado,              # id (Meta) / sku_id (TikTok)
        producto.sku,                # item_group_id (= SKU base)
        title,
        description,
        calcular_availability(producto, calcular_availability_por_stock),
        "new",
        formatear_precio(producto.precio_efectivo, moneda),
        producto.url_producto,
        url_imagen,
        producto.marca or brand_fallback,
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
    brand_fallback: str = "",
) -> int:
    """Escribe UNA pestaña INDIVIDUAL del feed (modo replace).

    Las pestañas individuales tienen 1 fila por SKU.
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
            brand_fallback=brand_fallback,
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
    brand_fallback: str = "",
) -> int:
    """Escribe la pestaña MAESTRA consolidada (Meta_Feed o TikTok_Feed).

    Esta pestaña contiene TODAS las decisiones de la plataforma. Esta es la
    pestaña que se conecta a Meta Catalog / TikTok Catalog.
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
            brand_fallback=brand_fallback,
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


def mover_pestaña_a_posicion(sheet_id: str, pestaña: str, posicion: int) -> bool:
    """Mueve una pestaña a una posición específica del sheet.

    Args:
        sheet_id: ID del Google Sheet.
        pestaña: nombre de la pestaña a mover.
        posicion: índice destino (0-based). 0 = primera pestaña.

    Returns:
        True si se movió OK, False si la pestaña no existía o falló.
    """
    try:
        client = SheetsClient(ConfigSheets(sheet_id=sheet_id, pestaña="_dummy"))
        sheet = client._abrir_sheet()
        ws = None
        for w in sheet.worksheets():
            if w.title == pestaña:
                ws = w
                break
        if ws is None:
            return False
        # gspread expone update_index() para reordenar
        ws.update_index(posicion)
        return True
    except Exception as e:
        log.warning("No pude reordenar pestaña '%s' a posición %d: %s",
                    pestaña, posicion, e)
        return False


def borrar_pestaña_si_existe(sheet_id: str, pestaña: str) -> bool:
    """Borra una pestaña del sheet si existe.

    Returns:
        True si la borró, False si no existía o falló.
    """
    try:
        client = SheetsClient(ConfigSheets(sheet_id=sheet_id, pestaña="_dummy"))
        sheet = client._abrir_sheet()
        for w in sheet.worksheets():
            if w.title == pestaña:
                sheet.del_worksheet(w)
                log.info("Pestaña '%s' borrada", pestaña)
                return True
        return False
    except Exception as e:
        log.warning("No pude borrar pestaña '%s': %s", pestaña, e)
        return False
