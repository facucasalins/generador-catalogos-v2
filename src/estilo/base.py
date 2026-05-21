"""Interfaz base para el Bloque 4: Estilo (render de placas).

Cualquier motor de estilo nuevo (figma_api, canva_api, ia_generativa)
debe heredar de MotorEstilo y devolver una Placa.

El orquestador (src/cli.py) le pasa de a uno: un Producto + una DecisionSeleccion
(que dice qué template usar), y espera de vuelta una Placa con el PNG en disco.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from src.core.modelo_datos import Producto, DecisionSeleccion, Placa


class ErrorEstilo(Exception):
    """Cualquier error durante el render."""


class MotorEstilo(ABC):
    """Contrato que todo motor de estilo debe cumplir."""

    @abstractmethod
    def renderizar(self, producto: Producto, decision: DecisionSeleccion) -> Placa:
        """Renderiza UNA placa para un producto, usando el template de la decisión.

        Reglas:
        - El template referenciado en `decision.template` debe existir (validar arriba)
        - Si el render falla (imagen rota, etc.), tirar ErrorEstilo
        - Devolver Placa con path_local apuntando al PNG generado
        """
        ...

    @abstractmethod
    def nombre(self) -> str:
        """Identificador: 'playwright_html', 'figma_api', etc."""
        ...
