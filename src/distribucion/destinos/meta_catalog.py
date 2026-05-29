"""Destino: feed Meta Catalog.

El template ya viene con prefijo de plataforma (ej: 'Meta_default_4x5').
Filtra solo los templates 'Meta_*'.

Pestaña MAESTRA 'Meta_Feed':
- Contiene TODAS las decisiones Meta_* del run.
- Esta es la pestaña que se conecta a Meta Catalog.
- id = sku + '__' + template (único)
- item_group_id = sku (agrupa variantes)
- Se mueve a posición 0 del sheet (primera pestaña).

Pestañas individuales por template:
- Se mantienen como visualización (Meta_default_4x5, Meta_cuotas_4x5, etc.)

Idempotencia:
- Si hay decisiones Meta: se crea/actualiza Meta_Feed + individuales.
- Si NO hay decisiones Meta: se BORRAN todas las pestañas Meta_* (incluida
  Meta_Feed). El sheet refleja 1:1 lo marcado en Selección.
- Las individuales sin decisiones también se borran.
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
    borrar_pestaña_si_existe,
)


log = logging.getLogger(__name__)


HEADERS_META_INDIVIDUAL = [
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

HEADERS_META_MAESTRA = [
    "id",
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

PREFIJO_PLATAFORMA = "Meta_"
PESTAÑA_MAESTRA = "Meta_Feed"
POSICION_MAESTRA = 0  # Primera pestaña del sheet


@dataclass
class ConfigMetaCatalog:
    """Config Meta. Solo procesa templates que empiezan con 'Meta_'."""
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

        decisiones_meta = [d for d in decisiones if d.template.startswith(PREFIJO_PLATAFORMA)]

        # Si NO hay decisiones Meta → no creamos nada (idempotencia total).
        # La pestaña maestra y las individuales se borran después en
        # eliminar_pestañas_huerfanas() al no estar en el set activo.
        if not decisiones_meta:
            log.info("Meta: no hay decisiones marcadas. No se crea Meta_Feed.")
            return {}

        # Filtrar placas por aspect_ratios aceptados
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
                headers=HEADERS_META_MAESTRA,
                decisiones_plataforma=decisiones_meta,
                productos_por_sku=productos_por_sku,
                placas_por_sku_template=placas_por_sku_template,
                moneda=self.cfg.moneda,
                calcular_availability_por_stock=self.cfg.calcular_availability_por_stock,
                brand_fallback=self.cfg.brand_fallback,
                internal_label=self.cfg.internal_label,
            )
            resultados[PESTAÑA_MAESTRA] = n_maestra

            # Mover a posición 0 (primera pestaña del sheet)
            mover_pestaña_a_posicion(
                self.cfg.sheet_id, PESTAÑA_MAESTRA, POSICION_MAESTRA,
            )
        except ErrorDestino as e:
            log.error("Meta: falló pestaña maestra '%s': %s", PESTAÑA_MAESTRA, e)
            errores.append(f"{PESTAÑA_MAESTRA}: {e}")

        # ============ 2. ESCRIBIR PESTAÑAS INDIVIDUALES ============
        grupos = agrupar_decisiones_por_template(decisiones_meta)

        for template, decisiones_grupo in grupos.items():
            placas_de_este_template = [
                p for p in placas_filtradas if p.template_usado == template
            ]
            if not placas_de_este_template and self.cfg.aspect_ratios_aceptados:
                log.info(
                    "Meta: template '%s' no tiene placas en aspect_ratios "
                    "aceptados %s. Pestaña individual omitida.",
                    template, self.cfg.aspect_ratios_aceptados,
                )
                continue

            pestaña = template
            log.info("Meta: escribiendo pestaña individual '%s' (%d decisiones)",
                     pestaña, len(decisiones_grupo))
            try:
                n = escribir_pestaña_feed(
                    sheet_id=self.cfg.sheet_id,
                    pestaña=pestaña,
                    headers=HEADERS_META_INDIVIDUAL,
                    decisiones_grupo=decisiones_grupo,
                    productos_por_sku=productos_por_sku,
                    placas_por_sku_template=placas_por_sku_template,
                    moneda=self.cfg.moneda,
                    calcular_availability_por_stock=self.cfg.calcular_availability_por_stock,
                    brand_fallback=self.cfg.brand_fallback,
                )
                resultados[pestaña] = n
            except ErrorDestino as e:
                log.error("Meta: falló pestaña '%s': %s", pestaña, e)
                errores.append(f"{pestaña}: {e}")

        if errores and not resultados:
            raise ErrorDestino(f"Meta: todas las pestañas fallaron: {errores}")

        return resultados

    def eliminar_pestañas_huerfanas(self, pestañas_activas: set[str]) -> list[str]:
        """Borra del sheet pestañas con prefijo 'Meta_' que NO están activas.

        IMPORTANTE: incluye Meta_Feed si no fue escrita en este run.
        Esto es deseable: si nadie marcó nada, Meta_Feed también se borra.

        Args:
            pestañas_activas: set con los nombres de pestañas que SÍ se
                acaban de escribir en este run.

        Returns:
            Lista de nombres de pestañas borradas.
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
                log.info("Meta: pestaña huérfana borrada → %s", nombre)
            except Exception as e:
                log.warning("Meta: no pude borrar pestaña '%s': %s", nombre, e)

        if borradas:
            log.info("Meta: %d pestañas huérfanas borradas", len(borradas))
        return borradas
