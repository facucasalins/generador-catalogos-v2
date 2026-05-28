"""Fuente de selección manual basada en Google Sheet (multi-template).

Cambio importante (multi-template):
- La pestaña Seleccion ahora tiene N columnas de checkbox (una por template
  activo en la pestaña Templates). Cada checkbox marcado = 1 placa a generar.
- Cada fila debe tener `generar=SI` (master switch) Y al menos un template
  marcado para que se procese.
- Un SKU puede aparecer 1 vez con varios templates marcados → genera N
  DecisionSeleccion (una por cada template marcado).

Estructura de la pestaña Seleccion:
    sku | generar | <template_1> | <template_2> | ... | prioridad | notas

Las columnas de templates se autogeneran desde la pestaña Templates con un
Apps Script al abrir el sheet. Si un template tiene activo=NO, su columna
se borra automáticamente.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass

from src.core.modelo_datos import Producto, DecisionSeleccion
from src.core.sheets_helpers import leer_pestaña_como_dicts
from src.seleccion.base import FuenteSeleccion


log = logging.getLogger(__name__)


# Columnas FIJAS (las no-template). El orden de las columnas de templates
# es dinámico y se descubre al leer el header del sheet.
COL_SKU = "sku"
COL_GENERAR = "generar"
COL_PRIORIDAD = "prioridad"
COL_NOTAS = "notas"

COLUMNAS_FIJAS = {COL_SKU, COL_GENERAR, COL_PRIORIDAD, COL_NOTAS}


@dataclass
class ConfigSeleccionSheet:
    sheet_id: str
    pestaña: str = "Seleccion"
    credenciales_json: str | None = None
    # Si False: NO filtrar por stock/published (volver al comportamiento Fase C).
    # Útil para testing o casos donde querés generar placas igual.
    filtrar_por_stock_y_publicado: bool = True
    # Lista de templates activos (viene de la pestaña Templates). Si una
    # columna de template no está en esta lista, se ignora.
    templates_activos: list[str] = None

    def __post_init__(self):
        if self.templates_activos is None:
            self.templates_activos = []


class SeleccionManualSheet(FuenteSeleccion):
    """Lee decisiones de la pestaña Seleccion. 1 fila puede generar N decisiones."""

    def __init__(self, config: ConfigSeleccionSheet):
        if not config.sheet_id:
            raise ValueError("ConfigSeleccionSheet.sheet_id es obligatorio")
        self.cfg = config

    def nombre(self) -> str:
        return "sheet_manual"

    def _es_si(self, valor) -> bool:
        """Normaliza checkbox/string a bool."""
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, (int, float)):
            return bool(valor)
        s = str(valor).strip().upper()
        return s in ("TRUE", "SI", "YES", "X", "1")

    def _tiene_stock(self, producto: Producto) -> bool:
        """Lee tn_has_stock del enriquecimiento. Si no está, asume True."""
        meta = producto.enriquecimiento or {}
        if "tn_has_stock" in meta:
            return bool(meta["tn_has_stock"])
        return True

    def _esta_publicado(self, producto: Producto) -> bool:
        """Idem para tn_published."""
        meta = producto.enriquecimiento or {}
        if "tn_published" in meta:
            return bool(meta["tn_published"])
        return True

    def _columnas_de_template(self, fila: dict) -> list[str]:
        """Detecta qué columnas de la fila son templates (no son fijas)."""
        templates = [
            col for col in fila.keys()
            if col not in COLUMNAS_FIJAS
        ]
        # Filtrar contra templates activos si están configurados
        if self.cfg.templates_activos:
            templates = [t for t in templates if t in self.cfg.templates_activos]
        return templates

    def seleccionar(self, productos: list[Producto]) -> list[DecisionSeleccion]:
        """Lee la pestaña Seleccion y genera N decisiones por fila.

        Reglas:
        - Si generar=NO → fila ignorada completa
        - Si generar=SI pero ningún template marcado → fila ignorada (warning)
        - Si SKU no existe en inventario → fila ignorada (warning)
        - Si SKU sin stock o no publicado → ignorada (info)
        - Cada template marcado con ✓ genera una DecisionSeleccion
        """
        filas = leer_pestaña_como_dicts(
            sheet_id=self.cfg.sheet_id,
            pestaña=self.cfg.pestaña,
            credenciales_json=self.cfg.credenciales_json,
        )

        if not filas:
            log.warning(
                "Pestaña '%s' está vacía. Nadie va a generar placas hoy.",
                self.cfg.pestaña,
            )
            return []

        productos_por_sku = {p.sku: p for p in productos}

        decisiones: list[DecisionSeleccion] = []
        ignorados_no_marcados = 0
        ignorados_sku_no_existe = 0
        ignorados_sin_stock = 0
        ignorados_no_publicado = 0
        ignorados_sin_templates = 0
        skus_procesados = set()

        for i, fila in enumerate(filas, start=2):
            sku = str(fila.get(COL_SKU, "")).strip()
            if not sku:
                continue

            # Master switch
            if not self._es_si(fila.get(COL_GENERAR)):
                ignorados_no_marcados += 1
                continue

            producto = productos_por_sku.get(sku)
            if not producto:
                log.warning(
                    "Fila %d: SKU '%s' marcado pero NO existe en inventario. Ignorado.",
                    i, sku,
                )
                ignorados_sku_no_existe += 1
                continue

            # Filtros stock/publicado
            if self.cfg.filtrar_por_stock_y_publicado:
                if not self._tiene_stock(producto):
                    log.info("Fila %d: SKU '%s' SIN STOCK. Ignorado.", i, sku)
                    ignorados_sin_stock += 1
                    continue
                if not self._esta_publicado(producto):
                    log.info("Fila %d: SKU '%s' NO PUBLICADO. Ignorado.", i, sku)
                    ignorados_no_publicado += 1
                    continue

            # Detectar qué templates están marcados en esta fila
            templates_disponibles = self._columnas_de_template(fila)
            templates_marcados = [
                t for t in templates_disponibles
                if self._es_si(fila.get(t))
            ]

            if not templates_marcados:
                log.warning(
                    "Fila %d: SKU '%s' marcado generar=SI pero ningún template "
                    "marcado. Fila ignorada.", i, sku,
                )
                ignorados_sin_templates += 1
                continue

            # Prioridad y notas: comunes a todas las decisiones de la fila
            try:
                prioridad = int(fila.get(COL_PRIORIDAD) or 100)
            except (TypeError, ValueError):
                prioridad = 100
            notas = str(fila.get(COL_NOTAS, "")).strip()

            # Una decisión por cada template marcado
            for template in templates_marcados:
                decisiones.append(DecisionSeleccion(
                    sku=sku,
                    generar=True,
                    template=template,
                    prioridad=prioridad,
                    notas=notas,
                ))

            skus_procesados.add(sku)

        log.info(
            "Selección: %d decisiones generadas para %d SKUs únicos. "
            "Ignorados: %d sin marcar, %d sin templates, %d SKU inexistente, "
            "%d sin stock, %d no publicados.",
            len(decisiones), len(skus_procesados),
            ignorados_no_marcados, ignorados_sin_templates,
            ignorados_sku_no_existe, ignorados_sin_stock, ignorados_no_publicado,
        )
        return decisiones
