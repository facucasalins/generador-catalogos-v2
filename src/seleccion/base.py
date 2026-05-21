"""Interfaz base para el Bloque 2: Selección.

Una fuente de selección decide, para una lista de productos del Inventario,
cuáles van al feed hoy (generar=SI), con qué template, en qué orden.

Output: lista de DecisionSeleccion (uno por producto seleccionado).
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from src.core.modelo_datos import Producto, DecisionSeleccion


class FuenteSeleccion(ABC):
    """Contrato que toda fuente de selección debe cumplir."""

    @abstractmethod
    def seleccionar(self, productos: list[Producto]) -> list[DecisionSeleccion]:
        """Recibe lista de productos del Bloque 1, devuelve lista de decisiones.

        Reglas:
        - Solo devuelve decisiones con generar=True (los NO se filtran acá)
        - El campo `template` debe corresponder a un archivo existente en el
          directorio templates/ del cliente
        - Si un SKU del input no aparece en el output, equivale a generar=False
        """
        ...

    @abstractmethod
    def nombre(self) -> str:
        """Identificador: 'sheet_manual', 'top_ventas', 'combinado', etc."""
        ...
