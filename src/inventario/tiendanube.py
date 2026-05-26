"""Fuente de inventario: Tiendanube API v1.

Documentación: https://tiendanube.github.io/api-documentation/resources/product

Conceptos clave:
- Un producto en TN tiene N variantes. Cada variante tiene su propio SKU.
- En nuestro modelo, cada variante = un `Producto` separado (1 fila por SKU).
- Campos multi-idioma vienen como {"es": "valor"}. Asumimos siempre "es".
- Paginación: ?page=N, hasta `per_page=200` por request.

Fallback de SKU (opt-in):
- Tiendas que NO cargan SKU explícito en variantes (típico en ropa) pueden
  activar `sku_fallback_handle_variant=True` en la config. Si una variante
  no tiene SKU, se genera automáticamente como "{handle}-{variant_id}".
- Por defecto está apagado: variantes sin SKU se ignoran (comportamiento
  histórico, retrocompat con Mora y otras tiendas que sí cargan SKU).
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
    # Fallback opt-in: si la variante no tiene SKU, generar "{handle}-{variant_id}".
    # Útil para tiendas (típicamente ropa) que no cargan SKU explícito en TN.
    # Default False = comportamiento histórico (ignorar variantes sin SKU).
    sku_fallback_handle_variant: bool = False


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


def _construir_sku_fallback(handle: str, variant_id) -> Optional[str]:
    """Genera SKU como "{handle}-{variant_id}" para variantes sin SKU explícito.

    - El handle es el 'Identificador de URL' de TN (slug del producto).
    - Incluir variant_id garantiza unicidad cuando un producto tiene varias
      variantes (talles/colores) sin SKU propio.
    - Devuelve None si falta cualquiera de los dos (no podemos generar).
    """
    if not variant_id:
        return None
    handle_limpio = (handle or "").strip()
    if not handle_limpio:
        # Sin handle no podemos generar SKU legible; usar solo variant_id.
        return f"tn-{variant_id}"
    return f"{handle_limpio}-{variant_id}"


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

    def _producto_tn_a_modelo(self, producto_tn: dict) -> list[Producto]:
        """Convierte 1 producto TN en N Productos (uno por variante)."""
        productos: list[Producto] = []

        nombre = _campo_es(producto_tn.get("name"))
        descripcion = limpiar_html(_campo_es(producto_tn.get("description")))
        marca = (producto_tn.get("brand") or "").strip()
        url_producto = producto_tn.get("canonical_url") or ""
        # El handle (Identificador de URL en TN) lo usamos como fallback de SKU.
        handle = _campo_es(producto_tn.get("handle"))

        # Categoría: tomamos la primera (TN permite N pero el caso típico es 1)
        categorias = producto_tn.get("categories") or []
        categoria = _campo_es(categorias[0].get("name")) if categorias else ""

        # Imagen: primera. (Más adelante podemos mapear por variant.image_id.)
        imagenes = producto_tn.get("images") or []
        imagen_url = imagenes[0].get("src", "") if imagenes else ""

        # Metadata extra a guardar en `enriquecimiento` para no perderla
        # (lo usamos como "campo libre" del modelo).
        meta = {
            "tn_product_id": producto_tn.get("id"),
            "tn_published": producto_tn.get("published", False),
            "tn_has_stock": producto_tn.get("has_stock", False),
            "tn_is_kit": producto_tn.get("is_kit", False),
        }

        variantes = producto_tn.get("variants") or []
        if not variantes:
            log.warning("Producto TN %s sin variantes, ignorado", producto_tn.get("id"))
            return []

        for variante in variantes:
            sku = (variante.get("sku") or "").strip()
            sku_es_fallback = False
            if not sku:
                # Sin SKU explícito: intentar fallback si está habilitado.
                if self.cfg.sku_fallback_handle_variant:
                    sku = _construir_sku_fallback(handle, variante.get("id")) or ""
                    sku_es_fallback = bool(sku)
                    if sku:
                        log.debug(
                            "SKU fallback generado para producto_id=%s variant_id=%s: %s",
                            producto_tn.get("id"), variante.get("id"), sku,
                        )
                if not sku:
                    # Ni SKU explícito ni fallback disponible: ignorar.
                    log.warning(
                        "Variante sin SKU ignorada: producto_id=%s variant_id=%s",
                        producto_tn.get("id"), variante.get("id"),
                    )
                    continue

            precio_lista = _a_float(variante.get("price"))
            if precio_lista is None:
                log.warning("SKU %s sin precio_lista, ignorado", sku)
                continue

            # En TN: `promotional_price` < `price` = está en promo.
            # `compare_at_price` es el precio tachado (>price) para mostrar ahorro.
            # Nuestro modelo es más simple: precio_lista + opcional precio_promocional.
            precio_promo = _a_float(variante.get("promotional_price"))

            meta_variante = {
                **meta,
                "tn_variant_id": variante.get("id"),
                "tn_compare_at_price": variante.get("compare_at_price"),
                "tn_sku_es_fallback": sku_es_fallback,
            }

            productos.append(Producto(
                sku=sku,
                nombre=nombre or sku,
                descripcion=descripcion,
                precio_lista=precio_lista,
                precio_promocional=precio_promo,
                cuotas_num=3,  # default acordado (TN no devuelve cuotas)
                stock=_a_int(variante.get("stock")),
                categoria=categoria,
                marca=marca,
                imagen_url=imagen_url,
                url_producto=url_producto,
                fuente="tiendanube",
                enriquecimiento=meta_variante,
            ))

        return productos

    def traer_productos(self) -> list[Producto]:
        """Trae todo el catálogo y lo normaliza a lista de Producto.

        Estrategia:
        - Pagina hasta agotar el catálogo
        - Cada producto TN puede generar N Productos (1 por variante con SKU)
        - Productos/variantes sin SKU o sin precio se ignoran con warning
          (a menos que sku_fallback_handle_variant esté activo)
        - Errores HTTP se propagan (no es seguro continuar si falla la API)
        """
        productos_tn = self._traer_todos_los_productos_tn()

        productos: list[Producto] = []
        ignorados_sin_variantes = 0

        for p_tn in productos_tn:
            variantes_modelo = self._producto_tn_a_modelo(p_tn)
            if not variantes_modelo:
                ignorados_sin_variantes += 1
                continue
            productos.extend(variantes_modelo)

        # Contar cuántos usaron fallback (útil para diagnóstico).
        con_fallback = sum(
            1 for p in productos
            if p.enriquecimiento and p.enriquecimiento.get("tn_sku_es_fallback")
        )
        if con_fallback:
            log.info(
                "TN: %d Producto generados (de %d productos TN). "
                "%d productos sin variantes válidas. %d con SKU fallback (handle-variant_id).",
                len(productos), len(productos_tn), ignorados_sin_variantes, con_fallback,
            )
        else:
            log.info(
                "TN: %d Producto generados (de %d productos TN). %d productos sin variantes válidas.",
                len(productos), len(productos_tn), ignorados_sin_variantes,
            )
        return productos
