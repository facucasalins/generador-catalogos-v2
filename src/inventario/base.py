"""Interfaz base para fuentes de inventario.

Cualquier módulo nuevo (shopify, mercadolibre, csv_manual, etc.)
debe heredar de FuenteInventario e implementar traer_productos().

El output siempre es una lista de objetos `Producto` (ver core/modelo_datos.py).
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.core.modelo_datos import Producto


@dataclass
class ConfigInventarioBase:
    """Configuración común a cualquier fuente de inventario.
    Los módulos concretos extienden esto con sus propios campos.
    """
    # Nada obligatorio por ahora — cada módulo define lo suyo
    pass


class FuenteInventario(ABC):
    """Contrato que toda fuente de inventario debe cumplir.

    El orquestador (src/cli.py) crea instancias de esta clase a partir
    del pipeline.yaml del cliente y llama a traer_productos().
    """

    @abstractmethod
    def traer_productos(self) -> list[Producto]:
        """Trae todos los productos de la tienda y los normaliza al
        formato estándar (lista de `Producto`).

        Reglas de implementación:
        - Una variante = un Producto en la salida (SKU único por producto)
        - Productos sin SKU se IGNORAN (no se pueden trackear)
        - Si hay errores parciales, registrar y continuar (no fallar todo)
        - El campo Producto.fuente debe quedar seteado al nombre del módulo
        """
        ...

    @abstractmethod
    def nombre(self) -> str:
        """Identificador corto: 'tiendanube', 'shopify', etc."""
        ...
