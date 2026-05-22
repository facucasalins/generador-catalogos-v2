"""Tests de src/distribucion/destinos/meta_catalog.py

Mockean SheetsClient para no tocar Google Sheets real.
"""
from unittest.mock import patch, MagicMock
import pytest

from src.core.modelo_datos import Producto, PlacaSubida
from src.distribucion.destinos.base import ErrorDestino
from src.distribucion.destinos.meta_catalog import (
    ConfigMetaCatalog,
    MetaCatalogDestino,
    HEADERS_META,
)


@pytest.fixture
def destino():
    return MetaCatalogDestino(ConfigMetaCatalog(
        sheet_id="test-sheet-id",
        pestaña="Meta",
    ))


def _producto(sku="TEST-1", precio=1000.0, promo=800.0, stock=10, marca="MarcaX"):
    return Producto(
        sku=sku, nombre=f"Producto {sku}",
        descripcion=f"Descripción {sku}",
        precio_lista=precio,
        precio_promocional=promo,
        stock=stock,
        marca=marca,
        url_producto=f"https://morashop.ar/p/{sku}",
        imagen_url="https://tn.com/img.jpg",
    )


def _placa(sku="TEST-1"):
    return PlacaSubida(
        sku=sku,
        url_publica=f"https://res.cloudinary.com/morashop-v2/{sku}.png",
        storage_backend="cloudinary",
    )


# ============ Config ============

def test_config_requiere_sheet_id():
    with pytest.raises(ErrorDestino, match="sheet_id"):
        MetaCatalogDestino(ConfigMetaCatalog(sheet_id=""))


def test_nombre_destino(destino):
    assert destino.nombre() == "meta_catalog"


# ============ Formato de precio ============

def test_formato_precio_meta(destino):
    """Meta espera '1234.00 ARS' (1 decimal, espacio, moneda)."""
    assert destino._formatear_precio(1234.0) == "1234.00 ARS"
    assert destino._formatear_precio(97656.5) == "97656.50 ARS"
    assert destino._formatear_precio(100.0) == "100.00 ARS"


def test_formato_precio_otra_moneda():
    d = MetaCatalogDestino(ConfigMetaCatalog(sheet_id="x", moneda="USD"))
    assert d._formatear_precio(50.0) == "50.00 USD"


# ============ Availability ============

def test_availability_stock_positivo_es_in_stock(destino):
    p = _producto(stock=10)
    assert destino._calcular_availability(p) == "in stock"


def test_availability_stock_cero_es_out_of_stock(destino):
    p = _producto(stock=0)
    assert destino._calcular_availability(p) == "out of stock"


def test_availability_stock_none_asume_in_stock(destino):
    p = _producto(stock=None)
    assert destino._calcular_availability(p) == "in stock"


def test_availability_desactivado_siempre_in_stock():
    d = MetaCatalogDestino(ConfigMetaCatalog(
        sheet_id="x",
        calcular_availability_por_stock=False,
    ))
    p = _producto(stock=0)
    assert d._calcular_availability(p) == "in stock"


# ============ Mapeo de producto a fila ============

def test_fila_tiene_9_columnas(destino):
    fila = destino._producto_a_fila(_producto(), "https://x/img.png")
    assert len(fila) == 9
    assert len(HEADERS_META) == 9


def test_fila_usa_precio_efectivo_no_lista(destino):
    """Si hay precio promocional, el feed usa el promo (no el lista)."""
    p = _producto(precio=1000.0, promo=800.0)
    fila = destino._producto_a_fila(p, "https://x/img.png")
    # price es la 6ta columna (índice 5)
    assert fila[5] == "800.00 ARS"


def test_fila_sin_promo_usa_precio_lista(destino):
    p = Producto(
        sku="X", nombre="X", precio_lista=500.0,
        precio_promocional=None,
        url_producto="", imagen_url="",
    )
    fila = destino._producto_a_fila(p, "https://x/img.png")
    assert fila[5] == "500.00 ARS"


def test_fila_brand_fallback_morashop_si_vacia(destino):
    p = _producto(marca="")
    fila = destino._producto_a_fila(p, "https://x/img.png")
    assert fila[8] == "MoraShop"


def test_fila_descripcion_fallback_a_nombre_si_vacia(destino):
    p = Producto(
        sku="X", nombre="Nombre del producto", precio_lista=100.0,
        descripcion="",  # vacía
        url_producto="", imagen_url="",
    )
    fila = destino._producto_a_fila(p, "https://x/img.png")
    assert fila[2] == "Nombre del producto"  # description = nombre


# ============ Publicar ============

@patch("src.distribucion.destinos.meta_catalog.SheetsClient")
def test_publicar_escribe_solo_productos_con_placa_subida(
    mock_sheets_class, destino
):
    """Si un producto pasó los filtros pero su placa no se subió,
    NO va al feed (no tiene image_link)."""
    mock_client = MagicMock()
    mock_sheets_class.return_value = mock_client

    productos = [_producto("A"), _producto("B"), _producto("C")]
    # Solo se subieron A y C; B falló en Cloudinary
    placas = [_placa("A"), _placa("C")]

    n = destino.publicar(productos, placas)

    assert n == 2  # solo 2 filas

    # Verificar las filas escritas
    call_args = mock_client.escribir_replace.call_args
    headers_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("headers")
    filas_arg = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get("filas")
    # En este caso vienen como positional args
    headers_arg = call_args[0][0]
    filas_arg = call_args[0][1]

    assert headers_arg == HEADERS_META
    skus_escritos = [f[0] for f in filas_arg]
    assert skus_escritos == ["A", "C"]


@patch("src.distribucion.destinos.meta_catalog.SheetsClient")
def test_publicar_lista_vacia_escribe_solo_headers(mock_sheets_class, destino):
    """Si no hay productos válidos, escribe solo los headers para no dejar
    el sheet inconsistente."""
    mock_client = MagicMock()
    mock_sheets_class.return_value = mock_client

    n = destino.publicar([], [])
    assert n == 0
    # Debe haber escrito (con filas vacías pero headers presentes)
    mock_client.escribir_replace.assert_called_once()
    filas_arg = mock_client.escribir_replace.call_args[0][1]
    assert filas_arg == []


@patch("src.distribucion.destinos.meta_catalog.SheetsClient")
def test_publicar_propaga_error_de_sheets_como_errordestino(
    mock_sheets_class, destino
):
    mock_client = MagicMock()
    mock_client.escribir_replace.side_effect = Exception("API error")
    mock_sheets_class.return_value = mock_client

    with pytest.raises(ErrorDestino, match="Falló escritura"):
        destino.publicar([_producto()], [_placa()])
