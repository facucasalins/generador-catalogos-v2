"""Destino: feed Meta Catalog (refactor Opción B).

Escribe N pestañas en el sheet de Feed-Output, una por template.
Pestañas: Meta_{template}, ej: Meta_default, Meta_electrohogar.

Header del id: 'id' (lo que Meta espera).
"""
from __future__ import annotations
import logging
from dataclasses import dataclass

from src.core.modelo_datos import Producto, PlacaSubida, DecisionSeleccion
from src.distribucion.destinos.base import DestinoFeed, ErrorDestino
from src.distribucion.destinos._common import (
    agrupar_por_template,
    escribir_pestaña_feed,
)


log = logging.getLogger(__name__)


# Headers Meta. Primera columna 'id' (Meta-specific).
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

PREFIJO_PESTAÑA = "Meta"


@dataclass
class ConfigMetaCatalog:
    """Config Meta. Una pestaña por template, prefijo 'Meta_'."""
    sheet_id: str
    moneda: str = "ARS"
    calcular_availability_por_stock: bool = True


class MetaCatalogDestino(DestinoFeed):
    """Escribe feeds Meta Catalog, una pestaña por template."""

    def __init__(self, config: ConfigMetaCatalog):
        if not config.sheet_id:
            raise ErrorDestino("ConfigMetaCatalog.sheet_id es obligatorio")
        self.cfg = config

    def nombre(self) -> str:
        return "meta_catalog"

    def publicar(
        self,
        productos: list[Producto],
        placas_subidas: list[PlacaSubida],
        decisiones: list[DecisionSeleccion],
    ) -> dict[str, int]:
        """Agrupa por template, escribe 1 pestaña por grupo."""
        placas_por_sku = {ps.sku: ps for ps in placas_subidas}
        grupos = agrupar_por_template(productos, decisiones)

        if not grupos:
            log.warning("Meta: no hay productos para publicar")
            return {}

        resultados: dict[str, int] = {}
        errores: list[str] = []

        for template, productos_grupo in grupos.items():
            pestaña = f"{PREFIJO_PESTAÑA}_{template}"
            log.info("Meta: escribiendo pestaña '%s' (%d productos del template '%s')",
                     pestaña, len(productos_grupo), template)
            try:
                n = escribir_pestaña_feed(
                    sheet_id=self.cfg.sheet_id,
                    pestaña=pestaña,
                    headers=HEADERS_META,
                    productos_grupo=productos_grupo,
                    placas_por_sku=placas_por_sku,
                    moneda=self.cfg.moneda,
                    calcular_availability_por_stock=self.cfg.calcular_availability_por_stock,
                )
                resultados[pestaña] = n
            except ErrorDestino as e:
                # No abortamos las otras pestañas
                log.error("Meta: falló pestaña '%s': %s", pestaña, e)
                errores.append(f"{pestaña}: {e}")

        if errores and not resultados:
            # Si TODAS las pestañas fallaron, sí abortamos
            raise ErrorDestino(f"Meta: todas las pestañas fallaron: {errores}")

        return resultados
