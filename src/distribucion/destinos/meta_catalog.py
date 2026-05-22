"""Destino: feed Meta Catalog.

Escribe un Google Sheet con el formato que Meta espera para catalog ads.
Meta lee este sheet automáticamente (configurable del lado de Meta, una vez).

Columnas del feed Meta (lo define Meta, no nosotros):
https://www.facebook.com/business/help/120325381656392

Las obligatorias son: id, title, description, availability, condition,
price, link, image_link, brand.

Diseño:
- Escribe en modo REPLACE: borra la pestaña y vuelve a escribir todo cada run.
  Esto es lo que decidimos en DECISIONES sección #11 ("Replace vs Update").
- Mergea Producto + PlacaSubida por SKU para llenar image_link.
- Si un Producto NO tiene su PlacaSubida correspondiente, NO se incluye en el feed
  (sin imagen no tiene sentido publicar).
- Availability: in stock si stock>0, out of stock si no.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass

from src.core.modelo_datos import Producto, PlacaSubida
from src.core.sheets_client import ConfigSheets, SheetsClient
from src.distribucion.destinos.base import DestinoFeed, ErrorDestino


log = logging.getLogger(__name__)


# Headers del feed Meta. ORDEN IMPORTA (Meta espera estos nombres exactos).
HEADERS_META = [
    "id",
    "title",
    "description",
    "availability",
    "condition",
    "price",
    "link",
    "image_link",
    "brand",
]


@dataclass
class ConfigMetaCatalog:
    """Config para escribir el feed Meta a un Google Sheet."""
    sheet_id: str
    pestaña: str = "Meta"
    moneda: str = "ARS"

    # Si True (default): availability se calcula del stock real de TN.
    # Si False: todo va como "in stock" (útil si confiás en el filtro de Bloque 2).
    calcular_availability_por_stock: bool = True


class MetaCatalogDestino(DestinoFeed):
    """Escribe feed Meta Catalog en un Google Sheet."""

    def __init__(self, config: ConfigMetaCatalog):
        if not config.sheet_id:
            raise ErrorDestino("ConfigMetaCatalog.sheet_id es obligatorio")
        self.cfg = config

    def nombre(self) -> str:
        return "meta_catalog"

    def _formatear_precio(self, valor: float) -> str:
        """Meta espera precio con formato '1234.00 ARS' (1 decimal, espacio, moneda).

        Ojo: NO usa separador de miles. '1234.00' no '1.234,00'.
        """
        return f"{valor:.2f} {self.cfg.moneda}"

    def _calcular_availability(self, producto: Producto) -> str:
        """Devuelve 'in stock' o 'out of stock' según las reglas configuradas."""
        if not self.cfg.calcular_availability_por_stock:
            return "in stock"
        # Si stock es None (no informado), asumimos in stock (mejor mostrar
        # de más que ocultar productos válidos)
        if producto.stock is None:
            return "in stock"
        return "in stock" if producto.stock > 0 else "out of stock"

    def _producto_a_fila(
        self, producto: Producto, url_imagen: str
    ) -> list:
        """Convierte un producto + URL de placa en una fila del feed Meta."""
        return [
            producto.sku,                                                    # id
            producto.nombre,                                                 # title
            producto.descripcion or producto.nombre,                         # description
            self._calcular_availability(producto),                           # availability
            "new",                                                           # condition (siempre new)
            self._formatear_precio(producto.precio_efectivo),                # price (efectivo = promo si hay, sino lista)
            producto.url_producto,                                           # link
            url_imagen,                                                      # image_link
            producto.marca or "MoraShop",                                    # brand (fallback si TN no tiene marca)
        ]

    def publicar(
        self,
        productos: list[Producto],
        placas_subidas: list[PlacaSubida],
    ) -> int:
        """Escribe el feed completo al sheet (modo replace)."""
        # Indexar placas por SKU para lookup rápido
        placas_por_sku = {ps.sku: ps for ps in placas_subidas}

        filas = []
        sin_placa = 0
        for p in productos:
            placa = placas_por_sku.get(p.sku)
            if not placa:
                # El producto pasó los filtros pero su placa no se subió a Cloudinary
                # (puede haber fallado el render o la subida). Sin imagen no va al feed.
                log.warning(
                    "SKU %s pasó filtros pero no tiene placa subida. "
                    "Se excluye del feed Meta.", p.sku,
                )
                sin_placa += 1
                continue

            filas.append(self._producto_a_fila(p, placa.url_publica))

        log.info(
            "Meta feed: %d productos a publicar, %d excluidos por falta de placa",
            len(filas), sin_placa,
        )

        if not filas:
            log.warning("Feed Meta vacío. Escribo solo headers para no dejar el sheet inconsistente.")

        # Escribir al sheet (replace)
        client = SheetsClient(ConfigSheets(
            sheet_id=self.cfg.sheet_id,
            pestaña=self.cfg.pestaña,
        ))
        try:
            client.escribir_replace(HEADERS_META, filas)
        except Exception as e:
            raise ErrorDestino(f"Falló escritura del feed Meta: {e}") from e

        log.info("Meta feed: %d filas escritas en sheet/%s", len(filas), self.cfg.pestaña)
        return len(filas)
