"""Fuente de inventario: Tiendanube API v1.

Documentación: https://tiendanube.github.io/api-documentation/resources/product

Conceptos clave:
- Un producto en TN tiene N variantes (talles/colores). Cada variante PUEDE
  tener su propio SKU.
- Hay 2 modos de mapeo a `Producto`, elegibles vía `agrupar_por_producto`:

  MODO 1 (default, False): "1 fila por variante con SKU".
      Cada variante con SKU explícito genera un Producto independiente.
      Variantes sin SKU se descartan con warning.
      Usado por Mora (suplementos): cada SKU = ítem distinto en feed.

  MODO 2 (True): "1 fila por producto del catálogo".
      Cada producto TN genera UN solo Producto, agrupando sus variantes.
      SKU = handle (identificador de URL). Precio = primera variante.
      Stock = suma de todas las variantes (disponible si alguna tiene).
      Usado por Shark (ropa): el link manda a la página del producto donde
      el comprador elige talle/color. Evita duplicados en feed.
- Campos multi-idioma vienen como {"es": "valor"}. Asumimos siempre "es".
- Paginación: ?page=N, hasta `per_page=200` por request.
"""
from __future__ import annotations
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests

from src.core.modelo_datos import Producto
from src.inventario.base import FuenteInventario


log = logging.getLogger(__name__)


# ============ Config ============

@dataclass
class ConfigTiendanube:
    """Config específica de Tiendanube."""
    store_id: str
    access_token: str
    user_agent: str = "AgencyNusa-GeneradorCatalogos (info@agencynusa.com)"
    per_page: int = 200          # máximo permitido por TN
    max_paginas: int = 100       # safeguard contra loops
    timeout_segundos: int = 30
    retraso_entre_paginas: float = 0.3  # ser amable con el rate limit
    # Modo de agrupación opt-in:
    # - False (default): 1 Producto por variante con SKU (Mora). Retrocompat.
    # - True: 1 Producto por producto TN, agrupando variantes. SKU = handle.
    #   Útil para ropa/calzado donde las variantes son talles/colores y el
    #   link manda a la página del producto.
    agrupar_por_producto: bool = False
    # Cantidad de cuotas sin interés que muestra la placa.
    # TN no devuelve cuotas, así que se setea por cliente en el pipeline.yaml.
    # Default 3 = retrocompat con Mora/Shark.
    cuotas_num: int = 3


# ============ Helpers de parseo ============

_RE_HTML = re.compile(r"<[^>]+>")
_RE_WHITESPACE = re.compile(r"\s+")


def limpiar_html(texto: str) -> str:
    """Quita tags HTML y normaliza whitespace. Para `description` de TN."""
    if not texto:
        return ""
    sin_tags = _RE_HTML.sub(" ", texto)
    # Decodificar entidades HTML comunes
    sin_tags = (sin_tags
                .replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
                .replace("&#39;", "'"))
    return _RE_WHITESPACE.sub(" ", sin_tags).strip()


def _campo_es(campo) -> str:
    """TN devuelve algunos campos como {"es": "valor"}. Devuelve el valor o "".
    """
    if campo is None:
        return ""
    if isinstance(campo, dict):
        return str(campo.get("es", "")).strip()
    return str(campo).strip()


def _a_float(valor) -> Optional[float]:
    """Convierte string '23124.00' a float. None si no es parseable o vacío."""
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _a_int(valor) -> Optional[int]:
    if valor is None or valor == "":
        return None
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _sku_desde_handle(handle: str, product_id) -> Optional[str]:
    """Genera SKU a partir del handle (Identificador de URL en TN).

    Caso normal: handle válido → usar tal cual ('remera-oversize-negra').
    Fallback defensivo: si TN no devuelve handle (raro), usar 'tn-{product_id}'.
    Devuelve None si tampoco hay product_id (no podemos generar nada único).
    """
    handle_limpio = (handle or "").strip()
    if handle_limpio:
        return handle_limpio
    if product_id:
        return f"tn-{product_id}"
    return None


# ============ Implementación ============

class TiendanubeInventario(FuenteInventario):
    """Trae el catálogo completo de productos+variantes desde Tiendanube."""

    BASE_URL = "https://api.tiendanube.com/v1"

    def __init__(self, config: ConfigTiendanube):
        if not config.store_id:
            raise ValueError("ConfigTiendanube.store_id es obligatorio")
        if not config.access_token:
            raise ValueError("ConfigTiendanube.access_token es obligatorio")
        self.cfg = config

    def nombre(self) -> str:
        return "tiendanube"

    def _headers(self) -> dict:
        return {
            "Authentication": f"bearer {self.cfg.access_token}",
            "User-Agent": self.cfg.user_agent,
            "Accept": "application/json",
        }

    def _traer_pagina(self, pagina: int) -> list[dict]:
        """Trae UNA página de productos. Lista vacía = no hay más."""
        url = f"{self.BASE_URL}/{self.cfg.store_id}/products"
        params = {
            "per_page": self.cfg.per_page,
            "page": pagina,
            # Por ahora traemos todos. Filtros (published, has_stock) los hacemos
            # localmente porque queremos guardar todo en el sheet.
        }
        resp = requests.get(
            url,
            headers=self._headers(),
            params=params,
            timeout=self.cfg.timeout_segundos,
        )
        # TN devuelve 404 cuando se acabaron las páginas (es así, no es bug)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json()

    def _traer_todos_los_productos_tn(self) -> list[dict]:
        """Trae todas las páginas hasta que TN devuelva vacío o 404."""
        productos_tn: list[dict] = []
        for pagina in range(1, self.cfg.max_paginas + 1):
            log.info("TN: trayendo página %d", pagina)
            try:
                batch = self._traer_pagina(pagina)
            except requests.HTTPError as e:
                log.error("TN: error en página %d: %s", pagina, e)
                raise
            if not batch:
                log.info("TN: página %d vacía, fin de paginación", pagina)
                break
            productos_tn.extend(batch)
            time.sleep(self.cfg.retraso_entre_paginas)
        else:
            log.warning(
                "TN: alcanzado max_paginas=%d sin terminar. ¿Hay más productos?",
                self.cfg.max_paginas,
            )
        log.info("TN: %d productos (con variantes) traídos en total", len(productos_tn))
        return productos_tn

    def _extraer_comunes(self, producto_tn: dict) -> dict:
        """Extrae los campos compartidos entre ambos modos (nombre, marca, etc)."""
        nombre = _campo_es(producto_tn.get("name"))
        descripcion = limpiar_html(_campo_es(producto_tn.get("description")))
        marca = (producto_tn.get("brand") or "").strip()
        url_producto = producto_tn.get("canonical_url") or ""
        handle = _campo_es(producto_tn.get("handle"))

        # Categoría: tomamos la primera (TN permite N pero el caso típico es 1)
        categorias = producto_tn.get("categories") or []
        categoria = _campo_es(categorias[0].get("name")) if categorias else ""

        # Imagen: primera. (Más adelante podemos mapear por variant.image_id.)
        imagenes = producto_tn.get("images") or []
        imagen_url = imagenes[0].get("src", "") if imagenes else ""

        return {
            "nombre": nombre,
            "descripcion": descripcion,
            "marca": marca,
            "url_producto": url_producto,
            "handle": handle,
            "categoria": categoria,
            "imagen_url": imagen_url,
        }

    def _meta_base(self, producto_tn: dict) -> dict:
        """Metadata base del producto TN, sin info de variante."""
        return {
            "tn_product_id": producto_tn.get("id"),
            "tn_published": producto_tn.get("published", False),
            "tn_has_stock": producto_tn.get("has_stock", False),
            "tn_is_kit": producto_tn.get("is_kit", False),
        }

    def _mapear_por_variante(self, producto_tn: dict) -> list[Producto]:
        """MODO 1 (Mora): cada variante con SKU → un Producto separado."""
        productos: list[Producto] = []
        comunes = self._extraer_comunes(producto_tn)
        meta = self._meta_base(producto_tn)

        variantes = producto_tn.get("variants") or []
        if not variantes:
            log.warning("Producto TN %s sin variantes, ignorado", producto_tn.get("id"))
            return []

        for variante in variantes:
            sku = (variante.get("sku") or "").strip()
            if not sku:
                # Sin SKU no podemos trackearlo. Ignoramos.
                log.warning(
                    "Variante sin SKU ignorada: producto_id=%s variant_id=%s",
                    producto_tn.get("id"), variante.get("id"),
                )
                continue

            precio_lista = _a_float(variante.get("price"))
            if precio_lista is None:
                log.warning("SKU %s sin precio_lista, ignorado", sku)
                continue

            precio_promo = _a_float(variante.get("promotional_price"))

            meta_variante = {
                **meta,
                "tn_variant_id": variante.get("id"),
                "tn_compare_at_price": variante.get("compare_at_price"),
            }

            productos.append(Producto(
                sku=sku,
                nombre=comunes["nombre"] or sku,
                descripcion=comunes["descripcion"],
                precio_lista=precio_lista,
                precio_promocional=precio_promo,
                cuotas_num=3,  # default acordado (TN no devuelve cuotas)
                stock=_a_int(variante.get("stock")),
                categoria=comunes["categoria"],
                marca=comunes["marca"],
                imagen_url=comunes["imagen_url"],
                url_producto=comunes["url_producto"],
                fuente="tiendanube",
                enriquecimiento=meta_variante,
            ))

        return productos

    def _mapear_agrupado(self, producto_tn: dict) -> list[Producto]:
        """MODO 2 (Shark): 1 Producto por producto TN, agrupando variantes.

        - SKU = handle (identificador de URL TN), o "tn-{product_id}" si no hay
        - Precio = primera variante (asumimos que todas las variantes valen igual)
        - Stock = suma de variantes (disponible si alguna tiene stock)
        - Imagen, nombre, etc. = del producto padre
        """
        comunes = self._extraer_comunes(producto_tn)
        meta = self._meta_base(producto_tn)

        variantes = producto_tn.get("variants") or []
        if not variantes:
            log.warning(
                "Producto TN %s sin variantes, ignorado",
                producto_tn.get("id"),
            )
            return []

        sku = _sku_desde_handle(comunes["handle"], producto_tn.get("id"))
        if not sku:
            log.warning(
                "Producto TN %s sin handle ni id, ignorado",
                producto_tn.get("id"),
            )
            return []

        # Tomamos la primera variante como referencia de precio.
        # El usuario confirmó que en Shark todas las variantes valen igual;
        # si alguna vez aparece un caso con precios distintos, lo veremos
        # en los logs (precio_min vs precio_max).
        primera = variantes[0]
        precio_lista = _a_float(primera.get("price"))
        if precio_lista is None:
            log.warning("Producto %s sin precio en primera variante, ignorado", sku)
            return []
        precio_promo = _a_float(primera.get("promotional_price"))

        # Stock agregado: suma de variantes con stock numérico.
        # Si todas tienen stock=None, dejamos None (no asumimos nada).
        stocks = [_a_int(v.get("stock")) for v in variantes]
        stocks_validos = [s for s in stocks if s is not None]
        stock_total = sum(stocks_validos) if stocks_validos else None

        # Sanity check: si las variantes tienen precios distintos, lo logueamos
        # como warning para que el usuario lo vea (no abortamos).
        precios_variantes = {_a_float(v.get("price")) for v in variantes}
        precios_variantes.discard(None)
        if len(precios_variantes) > 1:
            log.warning(
                "Producto %s tiene variantes con precios distintos (%s). "
                "Usando el de la primera variante: $%.2f",
                sku, sorted(precios_variantes), precio_lista,
            )

        meta_agrupada = {
            **meta,
            "tn_handle": comunes["handle"],
            "tn_variantes_total": len(variantes),
            "tn_variantes_con_stock": sum(
                1 for s in stocks_validos if s > 0
            ),
            "tn_sku_es_handle": True,  # marca: este SKU es autogenerado del handle
        }

        return [Producto(
            sku=sku,
            nombre=comunes["nombre"] or sku,
            descripcion=comunes["descripcion"],
            precio_lista=precio_lista,
            precio_promocional=precio_promo,
            cuotas_num=3,
            stock=stock_total,
            categoria=comunes["categoria"],
            marca=comunes["marca"],
            imagen_url=comunes["imagen_url"],
            url_producto=comunes["url_producto"],
            fuente="tiendanube",
            enriquecimiento=meta_agrupada,
        )]

    def _producto_tn_a_modelo(self, producto_tn: dict) -> list[Producto]:
        """Convierte 1 producto TN en N Productos según el modo configurado."""
        if self.cfg.agrupar_por_producto:
            return self._mapear_agrupado(producto_tn)
        return self._mapear_por_variante(producto_tn)

    def traer_productos(self) -> list[Producto]:
        """Trae todo el catálogo y lo normaliza a lista de Producto.

        Estrategia:
        - Pagina hasta agotar el catálogo
        - El mapeo a Producto depende del modo (ver `agrupar_por_producto`)
        - Errores HTTP se propagan (no es seguro continuar si falla la API)
        """
        productos_tn = self._traer_todos_los_productos_tn()

        productos: list[Producto] = []
        ignorados = 0

        for p_tn in productos_tn:
            mapeados = self._producto_tn_a_modelo(p_tn)
            if not mapeados:
                ignorados += 1
                continue
            productos.extend(mapeados)

        if self.cfg.agrupar_por_producto:
            log.info(
                "TN: %d Producto generados (modo agrupado, 1 por producto TN). "
                "%d productos TN ignorados (sin variantes válidas).",
                len(productos), ignorados,
            )
        else:
            log.info(
                "TN: %d Producto generados (modo por variante). "
                "%d productos TN sin variantes válidas.",
                len(productos), ignorados,
            )
        return productos
