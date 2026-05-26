"""Destino: feed TikTok Catalog.

Igual que Meta pero con:
- Header del id: 'sku_id' (TikTok-specific, no 'id')
- Prefijo de pestaña: 'TikTok_'

Las demás 8 columnas son idénticas a Meta. Si en el futuro TikTok cambia
algún campo, se ajusta acá sin tocar Meta.

Limpieza de huérfanas (Fase I): igual que en Meta. Ver meta_catalog.py.
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


# Headers TikTok. La diferencia con Meta: 'sku_id' en vez de 'id'.
HEADERS_TIKTOK = [
    "sku_id",
    "title",
    "description",
    "availability",
    "condition",
    "price",
    "link",
    "image_link",
    "brand",
]

PREFIJO_PESTAÑA = "TikTok"


@dataclass
class ConfigTikTokCatalog:
    """Config TikTok. Una pestaña por template, prefijo 'TikTok_'."""
    sheet_id: str
    moneda: str = "ARS"
    calcular_availability_por_stock: bool = True


class TikTokCatalogDestino(DestinoFeed):
    """Escribe feeds TikTok Catalog, una pestaña por template."""

    def __init__(self, config: ConfigTikTokCatalog):
        if not config.sheet_id:
            raise ErrorDestino("ConfigTikTokCatalog.sheet_id es obligatorio")
        self.cfg = config

    def nombre(self) -> str:
        return "tiktok_catalog"

    def publicar(
        self,
        productos: list[Producto],
        placas_subidas: list[PlacaSubida],
        decisiones: list[DecisionSeleccion],
    ) -> dict[str, int]:
        """Agrupa por template, escribe 1 pestaña por grupo, limpia huérfanas.

        TikTok usa las placas 9:16 (Fase H: filtra del set total de placas).
        Si todavía no hay placas 9:16 para los SKUs, la pestaña queda vacía
        con warning.
        """
        grupos = agrupar_por_template(productos, decisiones)

        resultados: dict[str, int] = {}
        errores: list[str] = []

        if not grupos:
            log.warning("TikTok: no hay productos para publicar")
        else:
            for template, productos_grupo in grupos.items():
                pestaña = f"{PREFIJO_PESTAÑA}_{template}"
                log.info("TikTok: escribiendo pestaña '%s' (%d productos del template '%s')",
                         pestaña, len(productos_grupo), template)
                try:
                    n = escribir_pestaña_feed(
                        sheet_id=self.cfg.sheet_id,
                        pestaña=pestaña,
                        headers=HEADERS_TIKTOK,
                        productos_grupo=productos_grupo,
                        placas_subidas=placas_subidas,
                        moneda=self.cfg.moneda,
                        calcular_availability_por_stock=self.cfg.calcular_availability_por_stock,
                        aspect_ratio_filtrar="9:16",
                    )
                    resultados[pestaña] = n
                except ErrorDestino as e:
                    log.error("TikTok: falló pestaña '%s': %s", pestaña, e)
                    errores.append(f"{pestaña}: {e}")

            if errores and not resultados:
                raise ErrorDestino(f"TikTok: todas las pestañas fallaron: {errores}")

        # Limpieza de huérfanas (ver doc en meta_catalog.py)
        vaciadas = limpiar_pestañas_huerfanas(
            sheet_id=self.cfg.sheet_id,
            prefijo=PREFIJO_PESTAÑA,
            headers=HEADERS_TIKTOK,
            pestañas_activas=set(resultados.keys()),
        )
        for nombre in vaciadas:
            resultados[nombre] = 0

        return resultados
