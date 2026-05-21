"""Sink: escribe Productos del Bloque 1 (Inventario) al Sheet.

Toma una lista de Producto (formato normalizado) y la vuelca al Sheet
configurado para el cliente, con las columnas estándar.

Las columnas se definen acá, no por cliente, para mantener un formato
consistente entre clientes (y simplificar el Bloque 2 de Selección).
"""
from __future__ import annotations
import logging
from datetime import datetime

from src.core.modelo_datos import Producto
from src.core.sheets_client import SheetsClient


log = logging.getLogger(__name__)


# Columnas del Sheet Inventario. ORDEN ES PARTE DEL CONTRATO con Bloque 2.
# Si cambia, hay que migrar los sheets existentes de clientes.
HEADERS_INVENTARIO = [
    "sku",
    "nombre",
    "descripcion",
    "precio_lista",
    "precio_promocional",
    "tiene_promo",
    "stock",
    "categoria",
    "marca",
    "imagen_url",
    "url_producto",
    "cuotas_num",
    # Metadata de fuente
    "fuente",
    "actualizado_en",
    # Metadata específica de Tiendanube (vacía si la fuente es otra)
    "tn_product_id",
    "tn_variant_id",
    "tn_published",
    "tn_has_stock",
    "tn_is_kit",
    "tn_compare_at_price",
]


def _producto_a_fila(p: Producto) -> list:
    """Convierte un Producto a una fila (lista de valores) según HEADERS_INVENTARIO."""
    meta = p.enriquecimiento or {}
    return [
        p.sku,
        p.nombre,
        p.descripcion,
        p.precio_lista,
        p.precio_promocional if p.precio_promocional is not None else "",
        "SI" if p.tiene_promo else "NO",
        p.stock if p.stock is not None else "",
        p.categoria,
        p.marca,
        p.imagen_url,
        p.url_producto,
        p.cuotas_num,
        p.fuente,
        p.actualizado_en.isoformat() if p.actualizado_en else "",
        meta.get("tn_product_id", ""),
        meta.get("tn_variant_id", ""),
        "SI" if meta.get("tn_published") else "NO",
        "SI" if meta.get("tn_has_stock") else "NO",
        "SI" if meta.get("tn_is_kit") else "NO",
        meta.get("tn_compare_at_price", ""),
    ]


def escribir_inventario(client: SheetsClient, productos: list[Producto]) -> int:
    """Escribe la lista completa de productos al sheet (modo replace).

    Returns:
        Cantidad de productos escritos.
    """
    log.info("Escribiendo %d productos al sheet '%s'/'%s'",
             len(productos), client.cfg.sheet_id, client.cfg.pestaña)

    filas = [_producto_a_fila(p) for p in productos]
    return client.escribir_replace(HEADERS_INVENTARIO, filas)
