"""Interfaz base para destinos del Bloque 5.2: feeds de catálogo.

Cualquier destino nuevo (meta_catalog, tiktok_catalog, google_shopping)
debe heredar de DestinoFeed y escribir el feed en el formato que ese
destino necesita.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from src.core.modelo_datos import Producto, PlacaSubida


class ErrorDestino(Exception):
    """Cualquier error escribiendo el feed."""


class DestinoFeed(ABC):
    """Contrato que todo destino debe cumplir."""

    @abstractmethod
    def publicar(
        self,
        productos: list[Producto],
        placas_subidas: list[PlacaSubida],
    ) -> int:
        """Publica el feed.

        Args:
            productos: productos del inventario YA FILTRADOS (solo los que
                cumplen las 3 condiciones: generar=SI, has_stock, published)
            placas_subidas: las placas que se subieron a Cloudinary, con URL
                pública. Se mergean con productos por SKU.

        Returns:
            Cantidad de filas escritas al feed.

        Raises:
            ErrorDestino si la escritura falla.
        """
        ...

    @abstractmethod
    def nombre(self) -> str:
        """Identificador: 'meta_catalog', 'tiktok_catalog', etc."""
        ...
