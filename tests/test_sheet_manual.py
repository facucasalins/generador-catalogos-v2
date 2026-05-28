"""Tests de src/seleccion/sheet_manual.py (multi-template).

Modelo nuevo: cada template es 1 COLUMNA en el sheet (no un valor en una
columna 'template'). El template marcado con True genera una decisión.
Un SKU con varios templates marcados genera N decisiones.
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
    """Fuente con templates 'default' y 'promo' activos.

    En el modelo multi-template, las columnas del sheet que no son fijas
    (sku, generar, prioridad, notas) se interpretan como templates. La
    config templates_activos filtra solo los que están habilitados.
    """
    return SeleccionManualSheet(ConfigSeleccionSheet(
        sheet_id="test123",
        templates_activos=["default", "promo"],
    ))


def test_config_requiere_sheet_id():
    with pytest.raises(ValueError, match="sheet_id"):
        SeleccionManualSheet(ConfigSeleccionSheet(sheet_id=""))


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_pestaña_vacia_devuelve_lista_vacia(mock_leer, fuente):
    mock_leer.return_value = []
    productos = [_make_producto("ABC")]
    assert fuente.seleccionar(productos) == []


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_fila_con_template_marcado_genera_decision(mock_leer, fuente):
    """ABC tiene generar=True y default=True → 1 decision con template='default'.
    DEF tiene generar=False → ignorada aunque tenga templates marcados."""
    mock_leer.return_value = [
        {"sku": "ABC", "generar": True, "default": True, "promo": False,
         "prioridad": "10", "notas": ""},
        {"sku": "DEF", "generar": False, "default": True, "promo": False,
         "prioridad": "20", "notas": ""},
    ]
    productos = [_make_producto("ABC"), _make_producto("DEF")]
    decisiones = fuente.seleccionar(productos)
    assert len(decisiones) == 1
    assert decisiones[0].sku == "ABC"
    assert decisiones[0].template == "default"


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_fila_sin_templates_marcados_se_ignora(mock_leer, fuente):
    """generar=True pero ningún template marcado → fila ignorada."""
    mock_leer.return_value = [
        {"sku": "ABC", "generar": True, "default": False, "promo": False},
    ]
    productos = [_make_producto("ABC")]
    decisiones = fuente.seleccionar(productos)
    assert decisiones == []


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_fila_multi_template_genera_n_decisiones(mock_leer, fuente):
    """Un SKU con 2 templates marcados genera 2 decisiones (1 por template)."""
    mock_leer.return_value = [
        {"sku": "ABC", "generar": True, "default": True, "promo": True},
    ]
    productos = [_make_producto("ABC")]
    decisiones = fuente.seleccionar(productos)
    assert len(decisiones) == 2
    templates = {d.template for d in decisiones}
    assert templates == {"default", "promo"}


# ============ Filtros stock + publicado ============

@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_sin_stock_se_filtra(mock_leer, fuente):
    """generar=SI + template marcado + sin stock → NO se procesa."""
    mock_leer.return_value = [
        {"sku": "SIN-STOCK", "generar": True, "default": True},
        {"sku": "CON-STOCK", "generar": True, "default": True},
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
    """generar=SI + template marcado + no publicado en TN → NO se procesa."""
    mock_leer.return_value = [
        {"sku": "NO-PUB", "generar": True, "default": True},
        {"sku": "PUB", "generar": True, "default": True},
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
        {"sku": "MAL", "generar": True, "default": True},
    ]
    productos = [_make_producto("MAL", has_stock=False, published=False)]
    decisiones = fuente.seleccionar(productos)
    assert decisiones == []


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_producto_sin_metadata_tn_asume_valido(mock_leer, fuente):
    """Sin metadata tn_has_stock/tn_published, asumimos OK (incluir de más)."""
    mock_leer.return_value = [
        {"sku": "X", "generar": True, "default": True},
    ]
    productos = [Producto(sku="X", nombre="X", precio_lista=100.0)]
    decisiones = fuente.seleccionar(productos)
    assert len(decisiones) == 1
    assert decisiones[0].template == "default"


@patch("src.seleccion.sheet_manual.leer_pestaña_como_dicts")
def test_se_puede_desactivar_filtro_de_stock_published(mock_leer):
    """Con filtrar_por_stock_y_publicado=False, no filtra por stock/publicado."""
    fuente = SeleccionManualSheet(ConfigSeleccionSheet(
        sheet_id="test",
        templates_activos=["default"],
        filtrar_por_stock_y_publicado=False,
    ))
    mock_leer.return_value = [
        {"sku": "SIN-STOCK", "generar": True, "default": True},
    ]
    productos = [_make_producto("SIN-STOCK", has_stock=False, published=False)]
    decisiones = fuente.seleccionar(productos)
    assert len(decisiones) == 1
