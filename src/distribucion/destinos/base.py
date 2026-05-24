"""Interfaz base para destinos del Bloque 5.2: feeds de catálogo.

Cualquier destino nuevo (meta_catalog, tiktok_catalog, google_shopping)
debe heredar de DestinoFeed y escribir el feed en el formato que ese
destino necesita.

Fase E.2 (refactor Opción B): un destino genera N pestañas, una por
template usado. La pestaña destino se autoinfiere del template:
    pestaña = f"{prefijo}_{template}"
    Ej: Meta_default, Meta_electrohogar, TikTok_default, etc.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from src.core.modelo_datos import Producto, PlacaSubida, DecisionSeleccion


class ErrorDestino(Exception):
    """Cualquier error escribiendo el feed."""


class DestinoFeed(ABC):
    """Contrato que todo destino debe cumplir."""

    @abstractmethod
    def publicar(
        self,
        productos: list[Producto],
        placas_subidas: list[PlacaSubida],
        decisiones: list[DecisionSeleccion],
    ) -> dict[str, int]:
        """Publica el feed, agrupando por template en pestañas separadas.

        Args:
            productos: productos del inventario YA FILTRADOS (cumplen
                generar=SI + has_stock + published).
            placas_subidas: las placas subidas a Cloudinary (con URL pública).
                Se mergea con productos por SKU.
            decisiones: para saber qué template usó cada SKU.

        Returns:
            Dict {nombre_pestaña: filas_escritas}. Permite logear por destino
            cuántos productos cayeron en cada pestaña.

        Raises:
            ErrorDestino si una pestaña falla. Por defecto seguimos con
            las otras pestañas (no abortamos todo el destino).
        """
        ...

    @abstractmethod
    def nombre(self) -> str:
        """Identificador: 'meta_catalog', 'tiktok_catalog', etc."""
        ...
