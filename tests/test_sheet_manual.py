"""Tests de src/seleccion/sheet_manual.py — Fase E.2

Suma tests para los filtros nuevos: has_stock y published.
"""
from unittest.mock import patch
from datetime import datetime
import pytest

from src.core.modelo_datos import Producto
from src.seleccion.sheet_manual import (
    SeleccionManualSheet,
    ConfigSeleccionSheet,
)


def _make_producto(
    sku: str, precio: float = 1000.0,
    has_stock: bool = True, published: bool = True,
) -> Producto:
    """Helper: crea Producto con metadata TN para tests."""
    return Producto(
        sku=sku, nombre=f"Producto {sku}", precio_lista=precio,
        actualizado_en=datetime.now(),
        enriquecimiento={
            "tn_has_stock": has_stock,
            "tn_published": published,
        },
    )


@pytest.fixture
def fuente():
    return SeleccionManualSheet(ConfigSeleccionSheet(sheet_id="test123"))


# ============ Tests Fase C (que siguen funcionando) ============

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
    ]
    productos = [_make_producto("ABC"), _make_producto("DEF")]
    decisiones = fuente.seleccionar(productos)
    skus = [d.sku for d in decisiones]
    assert skus == ["ABC"]


# ============ Tests Fase E.2: nuevos filtros ============

@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_sin_stock_se_filtra(mock_leer, fuente):
    """Si un SKU está marcado generar=SI pero sin stock, NO se procesa."""
    mock_leer.return_value = [
        {"sku": "SIN-STOCK", "generar": True, "template": "default"},
        {"sku": "CON-STOCK", "generar": True, "template": "default"},
    ]
    productos = [
        _make_producto("SIN-STOCK", has_stock=False),
        _make_producto("CON-STOCK", has_stock=True),
    ]
    decisiones = fuente.seleccionar(productos)
    skus = [d.sku for d in decisiones]
    assert skus == ["CON-STOCK"]


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_no_publicado_se_filtra(mock_leer, fuente):
    """Si un SKU está marcado pero no está publicado en TN, NO se procesa."""
    mock_leer.return_value = [
        {"sku": "NO-PUB", "generar": True, "template": "default"},
        {"sku": "PUB", "generar": True, "template": "default"},
    ]
    productos = [
        _make_producto("NO-PUB", published=False),
        _make_producto("PUB", published=True),
    ]
    decisiones = fuente.seleccionar(productos)
    skus = [d.sku for d in decisiones]
    assert skus == ["PUB"]


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_sin_stock_Y_no_publicado_se_filtra_doble(mock_leer, fuente):
    """Si falla por ambas razones, se filtra (sin error)."""
    mock_leer.return_value = [
        {"sku": "MAL", "generar": True, "template": "default"},
    ]
    productos = [_make_producto("MAL", has_stock=False, published=False)]
    decisiones = fuente.seleccionar(productos)
    assert decisiones == []


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_producto_sin_metadata_tn_asume_valido(mock_leer, fuente):
    """Si el producto no tiene tn_has_stock ni tn_published en enriquecimiento,
    asumimos que está OK (mejor incluir de más que excluir indebido)."""
    mock_leer.return_value = [
        {"sku": "X", "generar": True, "template": "default"},
    ]
    # Producto sin metadata
    productos = [Producto(sku="X", nombre="X", precio_lista=100.0)]
    decisiones = fuente.seleccionar(productos)
    assert len(decisiones) == 1


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_se_puede_desactivar_filtro_de_stock_published(mock_leer):
    """El filtro es opcional; si se desactiva, vuelve al comportamiento de Fase C."""
    fuente = SeleccionManualSheet(ConfigSeleccionSheet(
        sheet_id="test",
        filtrar_por_stock_y_publicado=False,
    ))
    mock_leer.return_value = [
        {"sku": "SIN-STOCK", "generar": True, "template": "default"},
    ]
    productos = [_make_producto("SIN-STOCK", has_stock=False, published=False)]
    decisiones = fuente.seleccionar(productos)
    # Con filtro desactivado, igual lo procesa
    assert len(decisiones) == 1
