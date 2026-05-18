"""Modelo de datos central del pipeline.

Estas dataclasses son el CONTRATO entre bloques. Cualquier módulo nuevo
(ej: una fuente de Inventario para Shopify) debe producir/consumir estos
objetos. No se modifican a la ligera.

Diseñado siguiendo §6 de docs/ARCHITECTURE.md.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


# ============================================================
# BLOQUE 1: INVENTARIO
# ============================================================

@dataclass
class Producto:
    """Producto normalizado desde cualquier fuente de inventario.

    Cualquier módulo de inventario (tiendanube, shopify, csv) debe devolver
    una lista de Producto con estos campos.
    """
    sku: str
    nombre: str
    precio_lista: float

    # Opcionales
    descripcion: str = ""
    precio_promocional: Optional[float] = None
    cuotas_num: int = 3
    stock: Optional[int] = None
    categoria: str = ""
    marca: str = ""
    imagen_url: str = ""
    url_producto: str = ""

    # Metadata
    actualizado_en: Optional[datetime] = None
    fuente: str = ""  # qué módulo lo trajo (ej: "tiendanube")

    # Campos que pueden agregarse por enriquecimiento (Bloque 3):
    enriquecimiento: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.actualizado_en is None:
            self.actualizado_en = datetime.now()

    @property
    def tiene_promo(self) -> bool:
        return (
            self.precio_promocional is not None
            and self.precio_promocional > 0
            and self.precio_promocional < self.precio_lista
        )

    @property
    def precio_efectivo(self) -> float:
        """Precio a mostrar al usuario: promo si hay, lista si no."""
        return self.precio_promocional if self.tiene_promo else self.precio_lista


# ============================================================
# BLOQUE 2: SELECCIÓN
# ============================================================

@dataclass
class DecisionSeleccion:
    """Una decisión por SKU: si va al feed hoy y con qué diseño."""
    sku: str
    generar: bool  # True = "SI" en el Sheet
    template: str = "default"  # nombre del template HTML a usar
    prioridad: int = 100  # 1 = alta. Para ordenar el feed.
    notas: str = ""  # texto libre del cliente/Vladimir


# ============================================================
# BLOQUE 3: ENRIQUECIMIENTO
# ============================================================

@dataclass
class Enriquecimiento:
    """Output del bloque de enriquecimiento para un SKU.

    Estos campos se mergean en Producto.enriquecimiento y quedan
    disponibles como variables en los templates HTML del Bloque 4.
    """
    sku: str
    hash_input: str  # hash del input usado, para invalidar cache si cambia
    proveedor: str  # "llm_gemini", "reglas_simples", etc.
    generado_en: datetime

    # Outputs típicos (todos opcionales):
    tips: list[str] = field(default_factory=list)
    titulo_corto: str = ""
    descripcion_corta: str = ""
    slogan: str = ""
    categoria_inferida: str = ""

    # Si el LLM falló y se usó fallback, queda registrado acá:
    fallback_aplicado: bool = False
    error: str = ""


# ============================================================
# BLOQUE 4: ESTILO
# ============================================================

@dataclass
class Placa:
    """Una placa renderizada en disco, lista para subir a storage."""
    sku: str
    template_usado: str  # qué template HTML generó esta placa
    path_local: str  # archivo PNG en disco
    width: int = 1080
    height: int = 1350


# ============================================================
# BLOQUE 5: DISTRIBUCIÓN
# ============================================================

@dataclass
class PlacaSubida:
    """Placa que ya está subida al storage y tiene URL pública."""
    sku: str
    url_publica: str
    storage_backend: str  # "cloudinary", "s3", etc.


@dataclass
class EntradaFeed:
    """Una fila del feed final que va a Meta/TikTok/etc.

    Cada destino sabe cómo serializar esto a su formato específico
    (Meta usa 'id', TikTok usa 'sku_id', etc.)
    """
    sku: str
    title: str
    description: str
    price: float
    moneda: str  # "ARS", "USD"
    link: str
    image_link: str
    brand: str
    availability: Literal["in stock", "out of stock", "preorder"] = "in stock"
    condition: Literal["new", "used", "refurbished"] = "new"


# ============================================================
# RESULTADO DEL PIPELINE
# ============================================================

@dataclass
class ResultadoRun:
    """Resumen de una ejecución completa del pipeline para un cliente."""
    cliente: str
    inicio: datetime
    fin: Optional[datetime] = None

    # Conteos por bloque:
    productos_inventario: int = 0
    productos_seleccionados: int = 0
    productos_enriquecidos: int = 0
    placas_generadas: int = 0
    placas_subidas: int = 0
    feeds_publicados: int = 0

    # Errores
    errores: list[tuple[str, str]] = field(default_factory=list)  # [(sku, mensaje)]

    @property
    def duracion_segundos(self) -> Optional[float]:
        if self.fin is None:
            return None
        return (self.fin - self.inicio).total_seconds()

    @property
    def exito(self) -> bool:
        """Si pasó al menos la mitad del trabajo, consideramos éxito.
        El threshold se puede ajustar por cliente en el pipeline.yaml."""
        if self.productos_seleccionados == 0:
            return True  # no había nada que hacer
        return len(self.errores) < self.productos_seleccionados / 2
