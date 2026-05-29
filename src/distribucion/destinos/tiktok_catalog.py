"""Destino: feed TikTok Catalog.

El template ya viene con prefijo de plataforma (ej: 'TikTok_default_9x16').
Filtra solo los templates 'TikTok_*'.

Pestaña MAESTRA 'TikTok_Feed':
- Contiene TODAS las decisiones TikTok_* del run.
- Esta es la pestaña que se conecta a TikTok Catalog.
- sku_id = sku + '__' + template (único)
- item_group_id = sku (agrupa variantes)
- Se mueve a posición 1 del sheet (segunda pestaña, después de Meta_Feed).

Pestañas individuales por template:
- Se mantienen como visualización (TikTok_default_9x16, etc.)

Idempotencia:
- Si hay decisiones TikTok: se crea/actualiza TikTok_Feed + individuales.
- Si NO hay decisiones TikTok: se BORRAN todas las pestañas TikTok_*.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field

from src.core.modelo_datos import Producto, PlacaSubida, DecisionSeleccion
from src.core.sheets_client import ConfigSheets, SheetsClient
from src.distribucion.destinos.base import DestinoFeed, ErrorDestino
from src.distribucion.destinos._common import (
    agrupar_decisiones_por_template,
    escribir_pestaña_feed,
    escribir_pestaña_maestra,
    mover_pestaña_a_posicion,
)


log = logging.getLogger(__name__)


HEADERS_TIKTOK_INDIVIDUAL = [
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

HEADERS_TIKTOK_MAESTRA = [
    "sku_id",
    "item_group_id",
    "title",
    "description",
    "availability",
    "condition",
    "price",
    "link",
    "image_link",
    "brand",
    "internal_label",
]

PREFIJO_PLATAFORMA = "TikTok_"
PESTAÑA_MAESTRA = "TikTok_Feed"
POSICION_MAESTRA = 1  # Segunda pestaña (después de Meta_Feed)


@dataclass
class ConfigTikTokCatalog:
    sheet_id: str
    moneda: str = "ARS"
    calcular_availability_por_stock: bool = True
    aspect_ratios_aceptados: list[str] = field(default_factory=list)
    # Marca del cliente (cliente.brand_name). Fallback del campo 'brand' del
    # feed cuando Tiendanube no trae marca en el producto.
    brand_fallback: str = ""
    # Etiqueta fija para filtrar el feed (distingue origen 'placa' del feed
    # nativo de Tiendanube en el mismo catálogo). Configurable por cliente.
    internal_label: str = "nusa_placa"


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
            log.info("TikTok: no hay decisiones marcadas. No se crea TikTok_Feed.")
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

        resultados: dict[str, int] = {}
        errores: list[str] = []

        # ============ 1. ESCRIBIR PESTAÑA MAESTRA ============
        try:
            n_maestra = escribir_pestaña_maestra(
                sheet_id=self.cfg.sheet_id,
                pestaña=PESTAÑA_MAESTRA,
                headers=HEADERS_TIKTOK_MAESTRA,
                decisiones_plataforma=decisiones_tt,
                productos_por_sku=productos_por_sku,
                placas_por_sku_template=placas_por_sku_template,
                moneda=self.cfg.moneda,
                calcular_availability_por_stock=self.cfg.calcular_availability_por_stock,
                brand_fallback=self.cfg.brand_fallback,
                internal_label=self.cfg.internal_label,
            )
            resultados[PESTAÑA_MAESTRA] = n_maestra

            # Mover a posición 1 (después de Meta_Feed)
            mover_pestaña_a_posicion(
                self.cfg.sheet_id, PESTAÑA_MAESTRA, POSICION_MAESTRA,
            )
        except ErrorDestino as e:
            log.error("TikTok: falló pestaña maestra '%s': %s", PESTAÑA_MAESTRA, e)
            errores.append(f"{PESTAÑA_MAESTRA}: {e}")

        # ============ 2. ESCRIBIR PESTAÑAS INDIVIDUALES ============
        grupos = agrupar_decisiones_por_template(decisiones_tt)

        for template, decisiones_grupo in grupos.items():
            placas_de_este_template = [
                p for p in placas_filtradas if p.template_usado == template
            ]
            if not placas_de_este_template and self.cfg.aspect_ratios_aceptados:
                log.info(
                    "TikTok: template '%s' no tiene placas en aspect_ratios "
                    "aceptados %s. Pestaña individual omitida.",
                    template, self.cfg.aspect_ratios_aceptados,
                )
                continue

            pestaña = template
            log.info("TikTok: escribiendo pestaña individual '%s' (%d decisiones)",
                     pestaña, len(decisiones_grupo))
            try:
                n = escribir_pestaña_feed(
                    sheet_id=self.cfg.sheet_id,
                    pestaña=pestaña,
                    headers=HEADERS_TIKTOK_INDIVIDUAL,
                    decisiones_grupo=decisiones_grupo,
                    productos_por_sku=productos_por_sku,
                    placas_por_sku_template=placas_por_sku_template,
                    moneda=self.cfg.moneda,
                    calcular_availability_por_stock=self.cfg.calcular_availability_por_stock,
                    brand_fallback=self.cfg.brand_fallback,
                )
                resultados[pestaña] = n
            except ErrorDestino as e:
                log.error("TikTok: falló pestaña '%s': %s", pestaña, e)
                errores.append(f"{pestaña}: {e}")

        if errores and not resultados:
            raise ErrorDestino(f"TikTok: todas las pestañas fallaron: {errores}")

        return resultados

    def eliminar_pestañas_huerfanas(self, pestañas_activas: set[str]) -> list[str]:
        """Borra del sheet pestañas con prefijo 'TikTok_' que NO están activas.

        Incluye TikTok_Feed si no fue escrita en este run.
        """
        client = SheetsClient(ConfigSheets(
            sheet_id=self.cfg.sheet_id, pestaña="_dummy",
        ))
        sheet = client._abrir_sheet()
        worksheets = sheet.worksheets()

        borradas: list[str] = []
        for ws in worksheets:
            nombre = ws.title
            if not nombre.startswith(PREFIJO_PLATAFORMA):
                continue
            if nombre in pestañas_activas:
                continue
            try:
                sheet.del_worksheet(ws)
                borradas.append(nombre)
                log.info("TikTok: pestaña huérfana borrada → %s", nombre)
            except Exception as e:
                log.warning("TikTok: no pude borrar pestaña '%s': %s", nombre, e)

        if borradas:
            log.info("TikTok: %d pestañas huérfanas borradas", len(borradas))
        return borradas
