"""Interfaz base para el Bloque 3: Enriquecimiento.

Cualquier proveedor (Gemini, OpenAI, reglas simples) debe heredar de
FuenteEnriquecimiento. El cli orquesta llamando a .enriquecer(producto)
para cada SKU seleccionado, y obtiene un objeto Enriquecimiento.

Diseño:
- 1 producto entra, 1 Enriquecimiento sale (sin batch, simple)
- Si Gemini falla → ErrorEnriquecimiento → el cli lo captura y descarta
  el SKU del feed (decisión del usuario)
- El hash_input se calcula afuera (en sheet_cache.py) para que esté
  desacoplado del proveedor
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from src.core.modelo_datos import Producto, Enriquecimiento


class ErrorEnriquecimiento(Exception):
    """Cualquier error al enriquecer: timeout, rate limit, parseo, etc."""


class FuenteEnriquecimiento(ABC):
    """Contrato que toda fuente de enriquecimiento debe cumplir."""

    @abstractmethod
    def enriquecer(self, producto: Producto) -> Enriquecimiento:
        """Genera el enriquecimiento para un producto.

        Args:
            producto: el producto a enriquecer (con nombre + descripción TN)

        Returns:
            Enriquecimiento con titulo_corto, descripcion_corta, tips poblados.

        Raises:
            ErrorEnriquecimiento si falla (timeout, formato inválido, etc.)
        """
        ...

    @abstractmethod
    def nombre(self) -> str:
        """Identificador del proveedor: 'gemini_flash', 'openai_gpt4o', etc."""
        ...
