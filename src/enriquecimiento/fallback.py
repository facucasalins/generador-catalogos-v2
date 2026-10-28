"""Plan B cuando Gemini no responde (sin crédito, caído, etc.).

Un producto NUNCA se cae del catálogo porque falló el enriquecimiento:
1. Si hay un enriquecimiento anterior en el cache (aunque el hash ya no
   coincida), se reusa. Un texto un poco viejo es mejor que no publicar.
2. Si no hay nada, se arma uno básico con el nombre y la descripción de
   Tiendanube.

Ninguno de los dos se guarda en el cache, así el próximo run con Gemini
funcionando los regenera.
"""
from __future__ import annotations
from datetime import datetime

from src.core.modelo_datos import Enriquecimiento, Producto
from src.enriquecimiento.gemini import ConfigGemini, _recortar

PROVEEDOR_FALLBACK = "fallback_tiendanube"


def enriquecimiento_desde_tienda(producto: Producto, cfg: ConfigGemini) -> Enriquecimiento:
    nombre = (producto.nombre or producto.sku).strip()
    descripcion = (producto.descripcion or "").strip() or nombre
    return Enriquecimiento(
        sku=producto.sku,
        hash_input="",
        proveedor=PROVEEDOR_FALLBACK,
        generado_en=datetime.now(),
        titulo_corto=_recortar(nombre, cfg.max_chars_titulo),
        titulo_placa=_recortar(nombre, cfg.max_chars_titulo_placa),
        descripcion_corta=_recortar(descripcion, cfg.max_chars_descripcion),
        tips=[],
        fallback_aplicado=True,
        error="",
    )


def es_falta_de_credito(error: Exception) -> bool:
    """True si Gemini rechazó por crédito/cuota agotada: no tiene sentido reintentar en este run."""
    texto = str(error)
    return "402" in texto or "RESOURCE_EXHAUSTED" in texto


def freno_de_seguridad(n_activas: int, n_anteriores: int, hubo_errores: bool,
                       umbral: float = 0.5) -> bool:
    """True si el run quiere dejar el catálogo a menos de la mitad Y hubo errores.

    En ese caso no se borra nada ni se publica el feed: queda el del run
    anterior. Una baja grande sin errores (ej. se destildaron productos en
    Selección) sigue funcionando normal.
    """
    if not hubo_errores or n_anteriores == 0:
        return False
    return n_activas < n_anteriores * umbral
