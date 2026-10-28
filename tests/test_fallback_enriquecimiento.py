"""Tests de src/enriquecimiento/fallback.py."""
from src.core.modelo_datos import Producto
from src.enriquecimiento.base import ErrorEnriquecimiento
from src.enriquecimiento.fallback import (
    PROVEEDOR_FALLBACK, enriquecimiento_desde_tienda, es_falta_de_credito, freno_de_seguridad,
)
from src.enriquecimiento.gemini import ConfigGemini

CFG = ConfigGemini(api_key="x", max_chars_titulo=60, max_chars_titulo_placa=40,
                   max_chars_descripcion=200)


def test_fallback_usa_nombre_y_descripcion_de_tienda():
    p = Producto(sku="a", nombre="Sandalia Alondra Cuero Chocolate", precio_lista=100,
                 descripcion="Sandalia de cuero. Plataforma de 2 cm.")
    e = enriquecimiento_desde_tienda(p, CFG)
    assert e.titulo_corto == "Sandalia Alondra Cuero Chocolate"
    assert e.descripcion_corta == "Sandalia de cuero. Plataforma de 2 cm."
    assert e.proveedor == PROVEEDOR_FALLBACK and e.fallback_aplicado


def test_fallback_recorta_y_sin_descripcion_usa_nombre():
    p = Producto(sku="a", nombre="Bota " + "muy larga " * 10, precio_lista=100)
    e = enriquecimiento_desde_tienda(p, CFG)
    assert len(e.titulo_placa) <= 40 and len(e.titulo_corto) <= 60
    assert e.descripcion_corta


def test_es_falta_de_credito():
    assert es_falta_de_credito(ErrorEnriquecimiento('Gemini HTTP 402: {"status": "RESOURCE_EXHAUSTED"}'))
    assert not es_falta_de_credito(ErrorEnriquecimiento("Gemini HTTP 500: internal"))


def test_freno_de_seguridad():
    assert freno_de_seguridad(4, 698, hubo_errores=True)          # lo que pasó con Juanita
    assert not freno_de_seguridad(4, 698, hubo_errores=False)     # destildaron a propósito
    assert not freno_de_seguridad(600, 698, hubo_errores=True)    # baja chica
    assert not freno_de_seguridad(700, 0, hubo_errores=True)      # primer run
