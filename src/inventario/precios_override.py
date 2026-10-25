"""Override de precios desde una planilla (eventos: Cyber, Hot Sale, etc.).

Caso de uso: el cliente define precios de evento en una planilla propia
(ej: "Cyber 2027" de Juanita) que NO están cargados en Tiendanube. El
pipeline sigue tomando nombre, imagen, stock, etc. de Tiendanube, pero
reemplaza precio_lista y precio_promocional por los de la planilla.

Se aplica sobre la lista de Producto DESPUÉS de escribir la pestaña
Inventario (que queda como espejo fiel de TN) y ANTES de Selección,
Estilo y Feeds. Así la placa y el feed de Meta/TikTok muestran el mismo
precio.

Opt-in por cliente en pipeline.yaml:

    inventario:
      precios_override:
        sheet_id: "..."
        pestaña: "MAESTRA CYBER"
        # opcionales (defaults):
        col_sku: "URL (handle TN)"
        col_precio_lista: "Precio full"
        col_precio_promo: "Precio Cyber"

Si un SKU no está en la planilla, conserva los precios de Tiendanube.
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from typing import Callable, Optional

from src.core.modelo_datos import Producto
from src.core.sheets_client import ConfigSheets, SheetsClient


log = logging.getLogger(__name__)


@dataclass
class ConfigPreciosOverride:
    sheet_id: str
    pestaña: str
    col_sku: str = "URL (handle TN)"
    col_precio_lista: str = "Precio full"
    col_precio_promo: str = "Precio Cyber"


def parsear_precio(valor) -> Optional[float]:
    """Convierte lo que devuelve Sheets a float.

    Acepta: 153600 · "153600" · "$153.600" · "$ 153,600.00" · "153.600,50".
    Devuelve None si está vacío o no es un número.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    s = re.sub(r"[^0-9.,]", "", str(valor))
    if not s:
        return None
    if "." in s and "," in s:
        # El último separador es el decimal.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        partes = s.split(sep)
        # "153.600" / "1,234,567" → miles; "153600,5" → decimal
        if len(partes) > 2 or len(partes[-1]) == 3:
            s = s.replace(sep, "")
        else:
            s = s.replace(sep, ".")
    try:
        return float(s)
    except ValueError:
        return None


def construir_mapa(
    filas: list[list[str]], cfg: ConfigPreciosOverride,
) -> dict[str, tuple[float, float]]:
    """Filas crudas (con header) → {sku: (precio_lista, precio_promo)}.

    Ignora filas sin sku o con precios inválidos (precio_lista <= 0, o promo
    <= 0, o promo > lista).
    """
    if not filas:
        return {}
    headers = [h.strip() for h in filas[0]]
    faltantes = [
        c for c in (cfg.col_sku, cfg.col_precio_lista, cfg.col_precio_promo)
        if c not in headers
    ]
    if faltantes:
        raise ValueError(
            f"Pestaña '{cfg.pestaña}' no tiene las columnas {faltantes}. "
            f"Headers encontrados: {headers}"
        )
    i_sku = headers.index(cfg.col_sku)
    i_lista = headers.index(cfg.col_precio_lista)
    i_promo = headers.index(cfg.col_precio_promo)

    mapa: dict[str, tuple[float, float]] = {}
    invalidas = 0
    for fila in filas[1:]:
        celda = lambda i: fila[i] if i < len(fila) else ""
        sku = str(celda(i_sku)).strip()
        if not sku:
            continue
        lista = parsear_precio(celda(i_lista))
        promo = parsear_precio(celda(i_promo))
        if not lista or not promo or lista <= 0 or promo <= 0 or promo > lista:
            invalidas += 1
            log.warning("[Precios override] Fila inválida para %s: lista=%r promo=%r",
                        sku, celda(i_lista), celda(i_promo))
            continue
        if sku in mapa:
            log.warning("[Precios override] SKU duplicado en la planilla: %s (uso la última)", sku)
        mapa[sku] = (lista, promo)
    log.info("[Precios override] %d SKUs con precio, %d filas inválidas", len(mapa), invalidas)
    return mapa


def leer_precios_override(
    cfg: ConfigPreciosOverride,
    leer_filas: Optional[Callable[[], list[list[str]]]] = None,
) -> dict[str, tuple[float, float]]:
    """Lee la planilla y devuelve el mapa de precios. `leer_filas` es inyectable para tests."""
    if leer_filas is None:
        client = SheetsClient(ConfigSheets(sheet_id=cfg.sheet_id, pestaña=cfg.pestaña))
        leer_filas = client.leer_todas_las_filas
    return construir_mapa(leer_filas(), cfg)


def aplicar_precios_override(
    productos: list[Producto], mapa: dict[str, tuple[float, float]],
) -> int:
    """Pisa precio_lista y precio_promocional de los productos que están en el mapa.

    Modifica los objetos in place. Devuelve cuántos productos se actualizaron.
    """
    aplicados = 0
    for p in productos:
        precios = mapa.get(p.sku)
        if precios is None:
            continue
        p.precio_lista, p.precio_promocional = precios
        aplicados += 1
    skus_inventario = {p.sku for p in productos}
    no_encontrados = [s for s in mapa if s not in skus_inventario]
    if no_encontrados:
        log.warning("[Precios override] %d SKUs de la planilla no están en el inventario: %s",
                    len(no_encontrados), no_encontrados[:20])
    log.info("[Precios override] Aplicado a %d de %d productos", aplicados, len(productos))
    return aplicados
