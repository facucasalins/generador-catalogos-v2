"""Tests de src/seleccion/sheet_manual.py

Mockean leer_pestaña_como_dicts para no llamar a la API real.
"""
from unittest.mock import patch
from datetime import datetime
import pytest

from src.core.modelo_datos import Producto
from src.seleccion.sheet_manual import (
    SeleccionManualSheet,
    ConfigSeleccionSheet,
)


def _make_producto(sku: str, precio: float = 1000.0) -> Producto:
    return Producto(
        sku=sku, nombre=f"Producto {sku}", precio_lista=precio,
        actualizado_en=datetime.now(),
    )


@pytest.fixture
def fuente():
    return SeleccionManualSheet(ConfigSeleccionSheet(sheet_id="test123"))


def test_config_requiere_sheet_id():
    with pytest.raises(ValueError, match="sheet_id"):
        SeleccionManualSheet(ConfigSeleccionSheet(sheet_id=""))


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_pestaña_vacia_devuelve_lista_vacia(mock_leer, fuente):
    mock_leer.return_value = []
    productos = [_make_producto("ABC")]
    assert fuente.seleccionar(productos) == []


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_filas_marcadas_si_se_devuelven(mock_leer, fuente):
    mock_leer.return_value = [
        {"sku": "ABC", "generar": True, "template": "default", "prioridad": "10", "notas": ""},
        {"sku": "DEF", "generar": False, "template": "promo", "prioridad": "20", "notas": ""},
        {"sku": "GHI", "generar": "SI", "template": "default", "prioridad": "", "notas": ""},
    ]
    productos = [_make_producto("ABC"), _make_producto("DEF"), _make_producto("GHI")]
    decisiones = fuente.seleccionar(productos)
    skus = [d.sku for d in decisiones]
    assert skus == ["ABC", "GHI"]
    # Verificar prioridades parseadas
    by_sku = {d.sku: d for d in decisiones}
    assert by_sku["ABC"].prioridad == 10
    assert by_sku["GHI"].prioridad == 100  # default cuando vacío


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_sku_inexistente_se_ignora_con_warning(mock_leer, fuente):
    mock_leer.return_value = [
        {"sku": "FANTASMA", "generar": True, "template": "default"},
    ]
    productos = [_make_producto("REAL")]
    decisiones = fuente.seleccionar(productos)
    assert decisiones == []


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_template_vacio_usa_default(mock_leer, fuente):
    mock_leer.return_value = [
        {"sku": "ABC", "generar": True, "template": "", "prioridad": "", "notas": ""},
    ]
    productos = [_make_producto("ABC")]
    decisiones = fuente.seleccionar(productos)
    assert len(decisiones) == 1
    assert decisiones[0].template == "default"


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_sku_vacio_se_ignora(mock_leer, fuente):
    """Si una fila tiene sku='' (fila vacía), se ignora sin warning."""
    mock_leer.return_value = [
        {"sku": "", "generar": True, "template": "default"},
        {"sku": "ABC", "generar": True, "template": "default"},
    ]
    productos = [_make_producto("ABC")]
    decisiones = fuente.seleccionar(productos)
    assert len(decisiones) == 1
    assert decisiones[0].sku == "ABC"


@pytest.mark.parametrize("valor,esperado", [
    (True, True),
    (False, False),
    ("TRUE", True),
    ("true", True),
    ("SI", True),
    ("Si", True),
    ("NO", False),
    ("", False),
    (None, False),
    (1, True),
    (0, False),
    ("x", True),
    ("X", True),
])
def test_es_si_normalizacion(fuente, valor, esperado):
    assert fuente._es_si(valor) is esperado


def test_nombre_modulo(fuente):
    assert fuente.nombre() == "sheet_manual"
