"""Interfaz base para el storage del Bloque 5: Distribución.

Cualquier storage nuevo (s3, google_drive, etc.) debe heredar de StorageBackend
y devolver una PlacaSubida con la URL pública.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

from src.core.modelo_datos import Placa, PlacaSubida


class ErrorStorage(Exception):
    """Cualquier error durante la subida al storage."""


class StorageBackend(ABC):
    """Contrato que todo backend de storage debe cumplir."""

    @abstractmethod
    def subir(self, placa: Placa) -> PlacaSubida:
        """Sube UNA placa al storage y devuelve una PlacaSubida con la URL.

        Reglas:
        - Si el SKU ya existe en el storage, se sobreescribe (overwrite=True).
        - Si la subida falla, tirar ErrorStorage con mensaje claro.
        - El public_id en el storage debe ser determinístico: mismo SKU = misma URL.
        """
        ...

    @abstractmethod
    def nombre(self) -> str:
        """Identificador: 'cloudinary', 's3', 'google_drive', etc."""
        ...
