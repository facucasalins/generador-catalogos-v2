"""Tests de los destinos (Meta + TikTok) post refactor Opción B."""
from unittest.mock import patch, MagicMock
import pytest

from src.core.modelo_datos import Producto, PlacaSubida, DecisionSeleccion
from src.distribucion.destinos.base import ErrorDestino
from src.distribucion.destinos.meta_catalog import (
    ConfigMetaCatalog, MetaCatalogDestino, HEADERS_META,
)
from src.distribucion.destinos.tiktok_catalog import (
    ConfigTikTokCatalog, TikTokCatalogDestino, HEADERS_TIKTOK,
)
from src.distribucion.destinos._common import (
    calcular_availability, formatear_precio, agrupar_por_template,
)


def _producto(sku="A", stock=10, marca="MarcaX", promo=800.0):
    return Producto(
        sku=sku, nombre=f"Producto {sku}", descripcion=f"Desc {sku}",
        precio_lista=1000.0, precio_promocional=promo,
        stock=stock, marca=marca,
        url_producto=f"https://x.com/{sku}", imagen_url="https://x.com/img.jpg",
    )


def _placa(sku="A"):
    return PlacaSubida(
        sku=sku, url_publica=f"https://cdn/{sku}.png", storage_backend="cloudinary",
    )


def _decision(sku="A", template="default"):
    return DecisionSeleccion(sku=sku, generar=True, template=template)


# ============ Helpers comunes ============

def test_formato_precio():
    assert formatear_precio(1234.0, "ARS") == "1234.00 ARS"
    assert formatear_precio(50.0, "USD") == "50.00 USD"


def test_availability_con_stock():
    assert calcular_availability(_producto(stock=10), True) == "in stock"
    assert calcular_availability(_producto(stock=0), True) == "out of stock"
    assert calcular_availability(_producto(stock=None), True) == "in stock"


def test_availability_sin_calcular():
    assert calcular_availability(_producto(stock=0), False) == "in stock"


def test_agrupar_por_template_basico():
    productos = [_producto("A"), _producto("B"), _producto("C")]
    decisiones = [
        _decision("A", "default"),
        _decision("B", "electrohogar"),
        _decision("C", "default"),
    ]
    grupos = agrupar_por_template(productos, decisiones)
    assert set(grupos.keys()) == {"default", "electrohogar"}
    assert len(grupos["default"]) == 2
    assert len(grupos["electrohogar"]) == 1


def test_agrupar_excluye_skus_sin_decision():
    """Si un producto no tiene decisión (caso defensivo), se excluye."""
    productos = [_producto("A"), _producto("B")]
    decisiones = [_decision("A", "default")]  # B sin decisión
    grupos = agrupar_por_template(productos, decisiones)
    assert "default" in grupos
    assert len(grupos["default"]) == 1


# ============ Meta ============

@pytest.fixture
def meta():
    return MetaCatalogDestino(ConfigMetaCatalog(sheet_id="sheet-123"))


def test_meta_config_requiere_sheet_id():
    with pytest.raises(ErrorDestino, match="sheet_id"):
        MetaCatalogDestino(ConfigMetaCatalog(sheet_id=""))


def test_meta_nombre(meta):
    assert meta.nombre() == "meta_catalog"


def test_meta_header_id_no_sku_id():
    """Meta usa 'id', no 'sku_id'."""
    assert HEADERS_META[0] == "id"


@patch("src.distribucion.destinos._common.SheetsClient")
def test_meta_publica_una_pestaña_por_template(mock_sheets_class, meta):
    """2 templates → 2 pestañas escritas."""
    mock_client = MagicMock()
    mock_sheets_class.return_value = mock_client

    productos = [_producto("A"), _producto("B"), _producto("C")]
    placas = [_placa("A"), _placa("B"), _placa("C")]
    decisiones = [
        _decision("A", "default"),
        _decision("B", "electrohogar"),
        _decision("C", "default"),
    ]

    resultados = meta.publicar(productos, placas, decisiones)

    # Esperamos 2 pestañas: Meta_default y Meta_electrohogar
    assert set(resultados.keys()) == {"Meta_default", "Meta_electrohogar"}
    assert resultados["Meta_default"] == 2
    assert resultados["Meta_electrohogar"] == 1

    # Se llamó escribir_replace 2 veces (una por pestaña)
    assert mock_client.escribir_replace.call_count == 2


@patch("src.distribucion.destinos._common.SheetsClient")
def test_meta_excluye_productos_sin_placa(mock_sheets_class, meta):
    mock_client = MagicMock()
    mock_sheets_class.return_value = mock_client

    productos = [_producto("A"), _producto("B")]
    placas = [_placa("A")]  # solo A tiene placa
    decisiones = [_decision("A", "default"), _decision("B", "default")]

    resultados = meta.publicar(productos, placas, decisiones)
    assert resultados["Meta_default"] == 1  # solo A


@patch("src.distribucion.destinos._common.SheetsClient")
def test_meta_sin_productos_no_escribe_nada(mock_sheets_class, meta):
    """Sin productos válidos, no se crea ninguna pestaña (no la del template
    porque no llegó nada)."""
    mock_client = MagicMock()
    mock_sheets_class.return_value = mock_client

    resultados = meta.publicar([], [], [])
    assert resultados == {}
    mock_client.escribir_replace.assert_not_called()


@patch("src.distribucion.destinos._common.SheetsClient")
def test_meta_fila_usa_id_no_sku_id(mock_sheets_class, meta):
    """La primera columna de la fila escrita es el SKU bajo header 'id'."""
    mock_client = MagicMock()
    mock_sheets_class.return_value = mock_client

    meta.publicar(
        [_producto("A")], [_placa("A")], [_decision("A", "default")],
    )

    call = mock_client.escribir_replace.call_args
    headers = call[0][0]
    filas = call[0][1]

    assert headers[0] == "id"
    assert filas[0][0] == "A"  # primera columna = SKU


# ============ TikTok ============

@pytest.fixture
def tiktok():
    return TikTokCatalogDestino(ConfigTikTokCatalog(sheet_id="sheet-123"))


def test_tiktok_config_requiere_sheet_id():
    with pytest.raises(ErrorDestino, match="sheet_id"):
        TikTokCatalogDestino(ConfigTikTokCatalog(sheet_id=""))


def test_tiktok_nombre(tiktok):
    assert tiktok.nombre() == "tiktok_catalog"


def test_tiktok_header_es_sku_id():
    """TikTok usa 'sku_id', no 'id'. Diferencia clave con Meta."""
    assert HEADERS_TIKTOK[0] == "sku_id"


def test_tiktok_y_meta_difieren_solo_en_id():
    """Las otras 8 columnas son idénticas."""
    assert HEADERS_META[1:] == HEADERS_TIKTOK[1:]


@patch("src.distribucion.destinos._common.SheetsClient")
def test_tiktok_publica_con_prefijo_tiktok(mock_sheets_class, tiktok):
    mock_client = MagicMock()
    mock_sheets_class.return_value = mock_client

    productos = [_producto("A")]
    placas = [_placa("A")]
    decisiones = [_decision("A", "electrohogar")]

    resultados = tiktok.publicar(productos, placas, decisiones)
    assert "TikTok_electrohogar" in resultados


@patch("src.distribucion.destinos._common.SheetsClient")
def test_tiktok_fila_usa_sku_id(mock_sheets_class, tiktok):
    """La fila escrita debe tener header 'sku_id' como primera columna."""
    mock_client = MagicMock()
    mock_sheets_class.return_value = mock_client

    tiktok.publicar(
        [_producto("A")], [_placa("A")], [_decision("A", "default")],
    )

    call = mock_client.escribir_replace.call_args
    headers = call[0][0]
    filas = call[0][1]

    assert headers[0] == "sku_id"
    assert filas[0][0] == "A"


# ============ Mismo sheet para ambos destinos ============

@patch("src.distribucion.destinos._common.SheetsClient")
def test_meta_y_tiktok_pueden_compartir_sheet(mock_sheets_class):
    """Apuntando al mismo sheet, no se pisan: prefijos distintos."""
    mock_client = MagicMock()
    mock_sheets_class.return_value = mock_client

    sheet_id = "same-sheet"
    meta = MetaCatalogDestino(ConfigMetaCatalog(sheet_id=sheet_id))
    tiktok = TikTokCatalogDestino(ConfigTikTokCatalog(sheet_id=sheet_id))

    productos = [_producto("A")]
    placas = [_placa("A")]
    decisiones = [_decision("A", "default")]

    r_meta = meta.publicar(productos, placas, decisiones)
    r_tiktok = tiktok.publicar(productos, placas, decisiones)

    # Las pestañas no se solapan
    assert set(r_meta.keys()) == {"Meta_default"}
    assert set(r_tiktok.keys()) == {"TikTok_default"}
