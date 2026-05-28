"""Destino: feed Meta Catalog (multi-template).

Cambios:
- 1 pestaña por template (ej: Meta_default_4x5, Meta_cuotas_4x5).
- Acepta cualquier aspect ratio (Meta soporta 4:5, 1:1, 9:16 para Reels).
- Si querés restringir a ciertos aspect ratios, configurá `aspect_ratios_aceptados`.
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

PREFIJO_PESTAÑA = "Meta"


@dataclass
class ConfigMetaCatalog:
    """Config Meta. Una pestaña por template, prefijo 'Meta_'."""
    sheet_id: str
    moneda: str = "ARS"
    calcular_availability_por_stock: bool = True
    # Si está vacío: acepta todos los aspect ratios. Si tiene valores,
    # filtra placas que NO estén en la lista.
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
        # Indexar productos y placas para lookup rápido
        productos_por_sku = {p.sku: p for p in productos}

        # Filtrar placas por aspect_ratios aceptados (si está configurado)
        placas_filtradas = placas_subidas
        if self.cfg.aspect_ratios_aceptados:
            placas_filtradas = [
                p for p in placas_subidas
                if p.aspect_ratio in self.cfg.aspect_ratios_aceptados
            ]

        placas_por_sku_template: dict[tuple[str, str], PlacaSubida] = {
            (p.sku, p.template_usado): p for p in placas_filtradas
        }

        # Filtrar decisiones también por aspect ratio (vía placa subida)
        grupos = agrupar_decisiones_por_template(decisiones)

        if not grupos:
            log.warning("Meta: no hay decisiones para publicar")
            return {}

        resultados: dict[str, int] = {}
        errores: list[str] = []

        for template, decisiones_grupo in grupos.items():
            # Saltar templates cuyo aspect_ratio no es aceptado por este destino
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

            pestaña = f"{PREFIJO_PESTAÑA}_{template}"
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
