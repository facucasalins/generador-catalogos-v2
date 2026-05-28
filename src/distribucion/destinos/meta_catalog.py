"""Destino: feed Meta Catalog.

El template ya viene con prefijo de plataforma (ej: 'Meta_default_4x5').
Filtra solo los templates 'Meta_*' y usa el nombre tal cual como pestaña.
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

PREFIJO_PLATAFORMA = "Meta_"


@dataclass
class ConfigMetaCatalog:
    """Config Meta. Solo procesa templates que empiezan con 'Meta_'."""
    sheet_id: str
    moneda: str = "ARS"
    calcular_availability_por_stock: bool = True
    aspect_ratios_aceptados: list[str] = field(default_factory=list)


class MetaCatalogDestino(DestinoFeed):

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
        productos_por_sku = {p.sku: p for p in productos}

        # Filtrar solo decisiones de Meta (template empieza con 'Meta_')
        decisiones_meta = [d for d in decisiones if d.template.startswith(PREFIJO_PLATAFORMA)]
        if not decisiones_meta:
            log.warning("Meta: no hay decisiones con prefijo '%s'", PREFIJO_PLATAFORMA)
            return {}

        # Filtrar placas por aspect_ratios aceptados
        placas_filtradas = placas_subidas
        if self.cfg.aspect_ratios_aceptados:
            placas_filtradas = [
                p for p in placas_subidas
                if p.aspect_ratio in self.cfg.aspect_ratios_aceptados
            ]

        # Indexar placas que sean de templates Meta_
        placas_por_sku_template: dict[tuple[str, str], PlacaSubida] = {
            (p.sku, p.template_usado): p
            for p in placas_filtradas
            if p.template_usado.startswith(PREFIJO_PLATAFORMA)
        }

        grupos = agrupar_decisiones_por_template(decisiones_meta)

        resultados: dict[str, int] = {}
        errores: list[str] = []

        for template, decisiones_grupo in grupos.items():
            placas_de_este_template = [
                p for p in placas_filtradas if p.template_usado == template
            ]
            if not placas_de_este_template and self.cfg.aspect_ratios_aceptados:
                log.info(
                    "Meta: template '%s' no tiene placas en aspect_ratios "
                    "aceptados %s. Pestaña omitida.",
                    template, self.cfg.aspect_ratios_aceptados,
                )
                continue

            # El nombre del template YA tiene 'Meta_' al inicio, lo usamos tal cual
            pestaña = template
            log.info("Meta: escribiendo pestaña '%s' (%d decisiones)",
                     pestaña, len(decisiones_grupo))
            try:
                n = escribir_pestaña_feed(
                    sheet_id=self.cfg.sheet_id,
                    pestaña=pestaña,
                    headers=HEADERS_META,
                    decisiones_grupo=decisiones_grupo,
                    productos_por_sku=productos_por_sku,
                    placas_por_sku_template=placas_por_sku_template,
                    moneda=self.cfg.moneda,
                    calcular_availability_por_stock=self.cfg.calcular_availability_por_stock,
                )
                resultados[pestaña] = n
            except ErrorDestino as e:
                log.error("Meta: falló pestaña '%s': %s", pestaña, e)
                errores.append(f"{pestaña}: {e}")

        if errores and not resultados:
            raise ErrorDestino(f"Meta: todas las pestañas fallaron: {errores}")

        return resultados
