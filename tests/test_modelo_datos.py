"""Tests del modelo de datos central. Validan el CONTRATO entre bloques.

Si estos tests fallan, es señal de que cambiaron interfaces que afectan
a múltiples bloques. Tratar con cuidado.
"""
from datetime import datetime

from src.core.modelo_datos import (
    Producto,
    DecisionSeleccion,
    Enriquecimiento,
    Placa,
    PlacaSubida,
    EntradaFeed,
    ResultadoRun,
)


def test_producto_minimo():
    """Un Producto necesita al menos sku + nombre + precio_lista."""
    p = Producto(sku="ABC123", nombre="Test", precio_lista=1000.0)
    assert p.sku == "ABC123"
    assert p.tiene_promo is False
    assert p.precio_efectivo == 1000.0
    assert p.actualizado_en is not None


def test_producto_con_promo():
    p = Producto(
        sku="ABC123",
        nombre="Test",
        precio_lista=1000.0,
        precio_promocional=800.0,
    )
    assert p.tiene_promo is True
    assert p.precio_efectivo == 800.0


def test_producto_promo_invalida_se_ignora():
    """Si precio_promocional >= precio_lista, no es realmente una promo."""
    p = Producto(
        sku="ABC123",
        nombre="Test",
        precio_lista=1000.0,
        precio_promocional=1200.0,
    )
    assert p.tiene_promo is False


def test_decision_seleccion_default():
    d = DecisionSeleccion(sku="ABC", generar=True)
    assert d.template == "default"
    assert d.prioridad == 100


def test_resultado_run_exito():
    """Sin errores y con decisiones, exito=True."""
    r = ResultadoRun(cliente="morashop", inicio=datetime.now())
    r.decisiones_totales = 10
    r.errores = []
    assert r.exito is True


def test_resultado_run_muchos_errores():
    """Si los errores superan la mitad de decisiones_totales, exito=False.

    Nota: la lógica de .exito se basa en decisiones_totales (no en
    productos_seleccionados), porque 1 producto puede generar N placas
    (1 por template) y queremos medir errores contra placas, no productos.
    """
    r = ResultadoRun(cliente="morashop", inicio=datetime.now())
    r.decisiones_totales = 10
    r.errores = [("sku1", "err"), ("sku2", "err"), ("sku3", "err"),
                 ("sku4", "err"), ("sku5", "err"), ("sku6", "err")]
    assert r.exito is False


def test_resultado_run_nada_que_hacer():
    """Si no había decisiones, no es un fallo."""
    r = ResultadoRun(cliente="morashop", inicio=datetime.now())
    assert r.exito is True


def test_entrada_feed_defaults():
    """Verificar defaults sensibles de EntradaFeed."""
    e = EntradaFeed(
        sku="ABC", title="Test", description="Desc",
        price=1000.0, moneda="ARS",
        link="https://example.com", image_link="https://example.com/img.png",
        brand="MoraShop",
    )
    assert e.availability == "in stock"
    assert e.condition == "new"
