"""Lógica compartida entre destinos Meta y TikTok.

Ambos destinos:
- Agrupan productos por template
- Escriben 1 pestaña por template ({prefijo}_{template})
- Tienen las mismas 9 columnas (con diferente nombre del id)
- Filtran productos sin placa subida
- Mismo manejo de availability, precio y brand

Diferencias:
- Header del id ('id' en Meta, 'sku_id' en TikTok)
- Prefijo de pestaña ('Meta' vs 'TikTok')
- Posible diferencia futura en otros campos (acá centralizamos para
  cambiarlo fácil)
"""
from __future__ import annotations
import logging
from collections import defaultdict

from src.core.modelo_datos import Producto, PlacaSubida, DecisionSeleccion
from src.core.sheets_client import ConfigSheets, SheetsClient
from src.distribucion.destinos.base import ErrorDestino


log = logging.getLogger(__name__)


def calcular_availability(producto: Producto, calcular_por_stock: bool) -> str:
    """Devuelve 'in stock' o 'out of stock'.

    Si calcular_por_stock=False, siempre 'in stock'.
    Si stock es None, asumimos 'in stock' (mejor incluir de más).
    """
    if not calcular_por_stock:
        return "in stock"
    if producto.stock is None:
        return "in stock"
    return "in stock" if producto.stock > 0 else "out of stock"


def formatear_precio(valor: float, moneda: str) -> str:
    """Formato Meta/TikTok: '1234.00 ARS' (sin separador miles, 2 decimales)."""
    return f"{valor:.2f} {moneda}"


def producto_a_fila(
    producto: Producto,
    url_imagen: str,
    moneda: str,
    calcular_availability_por_stock: bool,
) -> list:
    """Convierte producto + URL placa en fila del feed (9 columnas).

    Orden de columnas fijo: id, title, description, availability, condition,
    price, link, image_link, brand. El header del 'id' cambia (id vs sku_id)
    pero la estructura es la misma para Meta y TikTok.

    Si el producto fue enriquecido (Fase G), usa titulo_corto / descripcion_corta
    del campo .enriquecimiento. Si no, usa nombre / descripcion crudos
    (retrocompat con runs sin Bloque 3).
    """
    enriq = producto.enriquecimiento or {}
    title = enriq.get("titulo_corto") or producto.nombre
    description = (
        enriq.get("descripcion_corta")
        or producto.descripcion
        or producto.nombre
    )

    return [
        producto.sku,                                              # id / sku_id
        title,                                                     # title
        description,                                               # description
        calcular_availability(producto, calcular_availability_por_stock),  # availability
        "new",                                                     # condition
        formatear_precio(producto.precio_efectivo, moneda),        # price
        producto.url_producto,                                     # link
        url_imagen,                                                # image_link
        producto.marca or "MoraShop",                              # brand
    ]


def agrupar_por_template(
    productos: list[Producto],
    decisiones: list[DecisionSeleccion],
) -> dict[str, list[Producto]]:
    """Agrupa productos por el template con el que se renderizaron."""
    template_por_sku = {d.sku: d.template for d in decisiones}

    grupos: dict[str, list[Producto]] = defaultdict(list)
    sin_template = 0
    for p in productos:
        template = template_por_sku.get(p.sku)
        if template is None:
            # Defensive: este producto pasó por Bloque 4 pero no aparece en
            # decisiones (no debería pasar, pero por las dudas)
            log.warning("SKU %s no tiene template asignado, se excluye", p.sku)
            sin_template += 1
            continue
        grupos[template].append(p)

    if sin_template:
        log.warning("%d productos sin template, excluidos del feed", sin_template)
    return dict(grupos)


def escribir_pestaña_feed(
    sheet_id: str,
    pestaña: str,
    headers: list[str],
    productos_grupo: list[Producto],
    placas_subidas: list[PlacaSubida],
    moneda: str,
    calcular_availability_por_stock: bool,
    aspect_ratio_filtrar: str = "4:5",
) -> int:
    """Escribe UNA pestaña del feed (modo replace).

    Si la pestaña no existe, se crea (lo hace SheetsClient automáticamente).
    Si productos_grupo está vacío, escribe solo los headers (limpia data vieja).

    Args:
        placas_subidas: lista de TODAS las placas subidas (4:5 + 9:16).
            Adentro filtramos por aspect_ratio_filtrar.
        aspect_ratio_filtrar: solo se incluyen placas con este aspect ratio.
            "4:5" para feed Meta, "9:16" para feed TikTok.

    Returns:
        Cantidad de filas de datos escritas (sin contar header).
    """
    # Filtrar por aspect ratio e indexar por SKU
    placas_por_sku: dict[str, PlacaSubida] = {
        p.sku: p for p in placas_subidas if p.aspect_ratio == aspect_ratio_filtrar
    }

    filas = []
    sin_placa = 0
    for p in productos_grupo:
        placa = placas_por_sku.get(p.sku)
        if not placa:
            sin_placa += 1
            continue
        filas.append(producto_a_fila(
            p, placa.url_publica, moneda, calcular_availability_por_stock,
        ))

    if sin_placa:
        log.warning(
            "Pestaña '%s' (%s): %d productos excluidos por falta de placa subida",
            pestaña, aspect_ratio_filtrar, sin_placa,
        )

    client = SheetsClient(ConfigSheets(sheet_id=sheet_id, pestaña=pestaña))
    try:
        client.escribir_replace(headers, filas)
    except Exception as e:
        raise ErrorDestino(f"Falló escritura pestaña '{pestaña}': {e}") from e

    log.info("Pestaña '%s': %d filas escritas (aspect_ratio=%s)",
             pestaña, len(filas), aspect_ratio_filtrar)
    return len(filas)
