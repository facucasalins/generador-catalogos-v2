"""Fuente de selección manual basada en Google Sheet.

Diseño (Fase C):
- Sheet 'MoraShop V2 - Selección' tiene 3 pestañas:
  - `Catalogo`: espejo del Inventario, read-only desde la perspectiva del usuario.
  - `Seleccion`: lo único editable. El usuario agrega SKUs, marca checkboxes,
    elige template del dropdown.
  - `Templates`: lista de templates disponibles (source del dropdown).

Fase E.2: además de generar=SI, ahora filtramos por has_stock y published.
Si el equipo marcó un SKU pero el producto NO tiene stock o NO está publicado
en TN, se saltea (con log). Esto evita generar placas y feed de productos
que no se pueden vender.

La data de stock/published viene del Producto (Bloque 1 ya la trae de TN).
"""
from __future__ import annotations
import logging
from dataclasses import dataclass

from src.core.modelo_datos import Producto, DecisionSeleccion
from src.core.sheets_helpers import leer_pestaña_como_dicts
from src.seleccion.base import FuenteSeleccion


log = logging.getLogger(__name__)


# Headers esperados en la pestaña Seleccion
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
    # Si False: NO filtrar por stock/published (volver al comportamiento Fase C).
    # Útil para testing o casos donde querés generar placas igual.
    filtrar_por_stock_y_publicado: bool = True


class SeleccionManualSheet(FuenteSeleccion):
    """Lee decisiones de la pestaña Seleccion del sheet de un cliente."""

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
        """Lee tn_has_stock del enriquecimiento. Si no está, asume True
        (mejor incluir de más que excluir indebido)."""
        meta = producto.enriquecimiento or {}
        # tn_has_stock se setea explícitamente en tiendanube.py
        if "tn_has_stock" in meta:
            return bool(meta["tn_has_stock"])
        return True

    def _esta_publicado(self, producto: Producto) -> bool:
        """Idem para tn_published."""
        meta = producto.enriquecimiento or {}
        if "tn_published" in meta:
            return bool(meta["tn_published"])
        return True

    def seleccionar(self, productos: list[Producto]) -> list[DecisionSeleccion]:
        """Lee la pestaña Seleccion, filtra por generar=SI + has_stock + published,
        y devuelve DecisionSeleccion solo para los SKUs que pasan todos los filtros.
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

        # Índice rápido por SKU
        productos_por_sku = {p.sku: p for p in productos}

        decisiones: list[DecisionSeleccion] = []
        ignorados_no_marcados = 0
        ignorados_sku_no_existe = 0
        ignorados_sin_stock = 0
        ignorados_no_publicado = 0

        for i, fila in enumerate(filas, start=2):  # start=2: fila 1 es header
            sku = str(fila.get(COL_SKU, "")).strip()
            if not sku:
                continue

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

            # NUEVO en Fase E.2: filtrar por stock y published
            if self.cfg.filtrar_por_stock_y_publicado:
                if not self._tiene_stock(producto):
                    log.info(
                        "Fila %d: SKU '%s' marcado pero SIN STOCK en TN. "
                        "No se genera placa ni va al feed.", i, sku,
                    )
                    ignorados_sin_stock += 1
                    continue

                if not self._esta_publicado(producto):
                    log.info(
                        "Fila %d: SKU '%s' marcado pero NO PUBLICADO en TN. "
                        "No se genera placa ni va al feed.", i, sku,
                    )
                    ignorados_no_publicado += 1
                    continue

            template = str(fila.get(COL_TEMPLATE, "")).strip() or self.cfg.template_default

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
            "Selección: %d decisiones generadas. Ignorados: %d sin marcar, "
            "%d con SKU inexistente, %d sin stock, %d no publicados.",
            len(decisiones), ignorados_no_marcados, ignorados_sku_no_existe,
            ignorados_sin_stock, ignorados_no_publicado,
        )
        return decisiones
