"""Destino: feed Meta Catalog (refactor Opción B).

Escribe N pestañas en el sheet de Feed-Output, una por template.
Pestañas: Meta_{template}, ej: Meta_default, Meta_electrohogar.

Header del id: 'id' (lo que Meta espera).

Limpieza de huérfanas (Fase I):
Al final del run, busca pestañas con prefijo 'Meta_' que NO se escribieron
en este run y las vacía (deja headers solos). Caso típico: usuario quita
todos los SKUs de un template de la selección.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass

from src.core.modelo_datos import Producto, PlacaSubida, DecisionSeleccion
from src.distribucion.destinos.base import DestinoFeed, ErrorDestino
from src.distribucion.destinos._common import (
    agrupar_por_template,
    escribir_pestaña_feed,
    limpiar_pestañas_huerfanas,
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
        """Agrupa por template, escribe 1 pestaña por grupo, limpia huérfanas.

        Meta usa las placas 4:5 (Fase H: filtra del set total de placas).
        """
        grupos = agrupar_por_template(productos, decisiones)

        resultados: dict[str, int] = {}
        errores: list[str] = []

        if not grupos:
            log.warning("Meta: no hay productos para publicar")
        else:
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
                        placas_subidas=placas_subidas,
                        moneda=self.cfg.moneda,
                        calcular_availability_por_stock=self.cfg.calcular_availability_por_stock,
                        aspect_ratio_filtrar="4:5",
                    )
                    resultados[pestaña] = n
                except ErrorDestino as e:
                    log.error("Meta: falló pestaña '%s': %s", pestaña, e)
                    errores.append(f"{pestaña}: {e}")

            if errores and not resultados:
                raise ErrorDestino(f"Meta: todas las pestañas fallaron: {errores}")

        # Limpieza de huérfanas: pestañas Meta_X que no se escribieron en este run.
        # Se ejecuta SIEMPRE, incluso si no hubo grupos (caso: vaciaste selección
        # entera, hay que limpiar todas las Meta_ viejas).
        vaciadas = limpiar_pestañas_huerfanas(
            sheet_id=self.cfg.sheet_id,
            prefijo=PREFIJO_PESTAÑA,
            headers=HEADERS_META,
            pestañas_activas=set(resultados.keys()),
        )
        for nombre in vaciadas:
            # Reportamos en resultados con 0 filas, para que el log/Telegram
            # muestre que se vació.
            resultados[nombre] = 0

        return resultados
