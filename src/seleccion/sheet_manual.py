"""Fuente de selección manual basada en Google Sheet.

Diseño (decidido en Fase C):
- Sheet 'MoraShop V2 - Selección' tiene 3 pestañas:
  - `Catalogo`: espejo del Inventario, read-only desde la perspectiva del usuario.
    Se regenera cada vez que corre el bloque.
  - `Seleccion`: lo único editable. El usuario agrega SKUs, marca checkboxes,
    elige template del dropdown. Esta función lee SOLO esta pestaña.
  - `Templates`: lista de templates disponibles (source del dropdown). Se
    regenera escaneando archivos HTML del cliente.

Esta clase implementa el PASO C del flujo: leer Seleccion y devolver decisiones.
Los pasos A (sync Catalogo) y B (sync Templates) están en sync.py.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass

from src.core.modelo_datos import Producto, DecisionSeleccion
from src.core.sheets_helpers import leer_pestaña_como_dicts
from src.seleccion.base import FuenteSeleccion


log = logging.getLogger(__name__)


# Headers esperados en la pestaña Seleccion. Si el usuario los cambia se rompe;
# el código loguea warning pero sigue con defaults.
COL_SKU = "sku"
COL_GENERAR = "generar"
COL_TEMPLATE = "template"
COL_PRIORIDAD = "prioridad"
COL_NOTAS = "notas"


@dataclass
class ConfigSeleccionSheet:
    sheet_id: str
    pestaña: str = "Seleccion"
    template_default: str = "default"
    credenciales_json: str | None = None


class SeleccionManualSheet(FuenteSeleccion):
    """Lee decisiones de la pestaña Seleccion del sheet de un cliente."""

    def __init__(self, config: ConfigSeleccionSheet):
        if not config.sheet_id:
            raise ValueError("ConfigSeleccionSheet.sheet_id es obligatorio")
        self.cfg = config

    def nombre(self) -> str:
        return "sheet_manual"

    def _es_si(self, valor) -> bool:
        """Normaliza checkbox/string a bool.

        En Sheets, los checkboxes devuelven True/False como bool, pero si la
        celda es string puede ser "TRUE", "SI", "FALSE", "NO", o vacío.
        """
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, (int, float)):
            return bool(valor)
        s = str(valor).strip().upper()
        return s in ("TRUE", "SI", "YES", "X", "1")

    def seleccionar(self, productos: list[Producto]) -> list[DecisionSeleccion]:
        """Lee la pestaña Seleccion, filtra los que tienen generar=SI,
        y devuelve DecisionSeleccion solo para los SKUs que existen en
        el inventario actual.
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

        # Índice rápido por SKU del inventario actual
        skus_validos = {p.sku for p in productos}

        decisiones: list[DecisionSeleccion] = []
        ignorados_no_marcados = 0
        ignorados_sku_no_existe = 0

        for i, fila in enumerate(filas, start=2):  # start=2 porque fila 1 es header
            sku = str(fila.get(COL_SKU, "")).strip()
            if not sku:
                continue

            if not self._es_si(fila.get(COL_GENERAR)):
                ignorados_no_marcados += 1
                continue

            if sku not in skus_validos:
                log.warning(
                    "Fila %d: SKU '%s' marcado para generar pero NO existe en "
                    "el inventario actual. Ignorado.", i, sku,
                )
                ignorados_sku_no_existe += 1
                continue

            template = str(fila.get(COL_TEMPLATE, "")).strip() or self.cfg.template_default

            # Prioridad: si no es número, usamos 100
            try:
                prioridad = int(fila.get(COL_PRIORIDAD) or 100)
            except (TypeError, ValueError):
                prioridad = 100

            decisiones.append(DecisionSeleccion(
                sku=sku,
                generar=True,
                template=template,
                prioridad=prioridad,
                notas=str(fila.get(COL_NOTAS, "")).strip(),
            ))

        log.info(
            "Selección: %d decisiones generadas. "
            "Ignorados: %d sin marcar, %d con SKU inexistente.",
            len(decisiones), ignorados_no_marcados, ignorados_sku_no_existe,
        )
        return decisiones
