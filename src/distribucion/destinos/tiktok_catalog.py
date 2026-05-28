"""Destino: feed TikTok Catalog.

El template ya viene con prefijo de plataforma (ej: 'TikTok_default_9x16').
Filtra solo los templates 'TikTok_*' y usa el nombre tal cual como pestaña.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field

from src.core.modelo_datos import Producto, PlacaSubida, DecisionSeleccion
from src.distribucion.destinos.base import DestinoFeed, ErrorDestino
from src.distribucion.destinos._common import (
    agrupar_decisiones_por_template,
    escribir_pestaña_feed,
)


log = logging.getLogger(__name__)


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

PREFIJO_PLATAFORMA = "TikTok_"


@dataclass
class ConfigTikTokCatalog:
    sheet_id: str
    moneda: str = "ARS"
    calcular_availability_por_stock: bool = True
    aspect_ratios_aceptados: list[str] = field(default_factory=list)


class TikTokCatalogDestino(DestinoFeed):

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
        productos_por_sku = {p.sku: p for p in productos}

        decisiones_tt = [d for d in decisiones if d.template.startswith(PREFIJO_PLATAFORMA)]
        if not decisiones_tt:
            log.warning("TikTok: no hay decisiones con prefijo '%s'", PREFIJO_PLATAFORMA)
            return {}

        placas_filtradas = placas_subidas
        if self.cfg.aspect_ratios_aceptados:
            placas_filtradas = [
                p for p in placas_subidas
                if p.aspect_ratio in self.cfg.aspect_ratios_aceptados
            ]

        placas_por_sku_template: dict[tuple[str, str], PlacaSubida] = {
            (p.sku, p.template_usado): p
            for p in placas_filtradas
            if p.template_usado.startswith(PREFIJO_PLATAFORMA)
        }

        grupos = agrupar_decisiones_por_template(decisiones_tt)

        resultados: dict[str, int] = {}
        errores: list[str] = []

        for template, decisiones_grupo in grupos.items():
            placas_de_este_template = [
                p for p in placas_filtradas if p.template_usado == template
            ]
            if not placas_de_este_template and self.cfg.aspect_ratios_aceptados:
                log.info(
                    "TikTok: template '%s' no tiene placas en aspect_ratios "
                    "aceptados %s. Pestaña omitida.",
                    template, self.cfg.aspect_ratios_aceptados,
                )
                continue

            pestaña = template  # YA viene con 'TikTok_'
            log.info("TikTok: escribiendo pestaña '%s' (%d decisiones)",
                     pestaña, len(decisiones_grupo))
            try:
                n = escribir_pestaña_feed(
                    sheet_id=self.cfg.sheet_id,
                    pestaña=pestaña,
                    headers=HEADERS_TIKTOK,
                    decisiones_grupo=decisiones_grupo,
                    productos_por_sku=productos_por_sku,
                    placas_por_sku_template=placas_por_sku_template,
                    moneda=self.cfg.moneda,
                    calcular_availability_por_stock=self.cfg.calcular_availability_por_stock,
                )
                resultados[pestaña] = n
            except ErrorDestino as e:
                log.error("TikTok: falló pestaña '%s': %s", pestaña, e)
                errores.append(f"{pestaña}: {e}")

        if errores and not resultados:
            raise ErrorDestino(f"TikTok: todas las pestañas fallaron: {errores}")

        return resultados
