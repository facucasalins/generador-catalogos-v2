"""Tests de destinos Meta + TikTok (multi-template + pestaña maestra)."""
from unittest.mock import patch, MagicMock
import pytest

from src.core.modelo_datos import Producto, PlacaSubida, DecisionSeleccion
from src.distribucion.destinos.base import ErrorDestino
from src.distribucion.destinos.meta_catalog import (
    ConfigMetaCatalog, MetaCatalogDestino,
    HEADERS_META_INDIVIDUAL, HEADERS_META_MAESTRA,
    PESTAÑA_MAESTRA as META_MAESTRA,
)
from src.distribucion.destinos.tiktok_catalog import (
    ConfigTikTokCatalog, TikTokCatalogDestino,
    HEADERS_TIKTOK_INDIVIDUAL, HEADERS_TIKTOK_MAESTRA,
    PESTAÑA_MAESTRA as TIKTOK_MAESTRA,
)
from src.distribucion.destinos._common import (
    calcular_availability, formatear_precio, agrupar_decisiones_por_template,
    producto_a_fila_individual, producto_a_fila_maestra,
)


def _producto(sku="A", stock=10, marca="MarcaX", promo=800.0):
    return Producto(
        sku=sku, nombre=f"Producto {sku}", descripcion=f"Desc {sku}",
        precio_lista=1000.0, precio_promocional=promo,
        stock=stock, marca=marca,
        url_producto=f"https://x.com/{sku}", imagen_url="https://x.com/img.jpg",
    )


def _placa(sku="A", template="Meta_default_4x5", aspect="4:5"):
    return PlacaSubida(
        sku=sku, template_usado=template,
        url_publica=f"https://cdn/{sku}__{template}.png",
        storage_backend="cloudinary", aspect_ratio=aspect,
    )


def _decision(sku="A", template="Meta_default_4x5"):
    return DecisionSeleccion(sku=sku, generar=True, template=template)


def test_formato_precio():
    assert formatear_precio(1234.0, "ARS") == "1234.00 ARS"
    assert formatear_precio(50.0, "USD") == "50.00 USD"


def test_availability_con_stock():
    assert calcular_availability(_producto(stock=10), True) == "in stock"
    assert calcular_availability(_producto(stock=0), True) == "out of stock"
    assert calcular_availability(_producto(stock=None), True) == "in stock"


def test_availability_sin_calcular():
    assert calcular_availability(_producto(stock=0), False) == "in stock"


def test_agrupar_decisiones_por_template():
    decisiones = [
        _decision("A", "Meta_default_4x5"),
        _decision("B", "Meta_cuotas_4x5"),
        _decision("C", "Meta_default_4x5"),
    ]
    grupos = agrupar_decisiones_por_template(decisiones)
    assert set(grupos.keys()) == {"Meta_default_4x5", "Meta_cuotas_4x5"}
    assert len(grupos["Meta_default_4x5"]) == 2
    assert len(grupos["Meta_cuotas_4x5"]) == 1


def test_headers_meta_individual_empieza_con_id():
    assert HEADERS_META_INDIVIDUAL[0] == "id"
    assert "item_group_id" not in HEADERS_META_INDIVIDUAL


def test_headers_meta_maestra_incluye_item_group_id():
    assert HEADERS_META_MAESTRA[0] == "id"
    assert HEADERS_META_MAESTRA[1] == "item_group_id"


def test_headers_tiktok_individual_usa_sku_id():
    assert HEADERS_TIKTOK_INDIVIDUAL[0] == "sku_id"


def test_headers_tiktok_maestra_usa_sku_id_y_item_group():
    assert HEADERS_TIKTOK_MAESTRA[0] == "sku_id"
    assert HEADERS_TIKTOK_MAESTRA[1] == "item_group_id"


def test_fila_individual_no_lleva_item_group():
    p = _producto("A")
    fila = producto_a_fila_individual(p, "https://cdn/x.png", "ARS", True)
    assert fila[0] == "A"
    assert len(fila) == len(HEADERS_META_INDIVIDUAL)


def test_fila_maestra_lleva_id_consolidado():
    p = _producto("A")
    fila = producto_a_fila_maestra(p, "Meta_default_4x5", "https://cdn/x.png", "ARS", True)
    assert fila[0] == "A__Meta_default_4x5"
    assert fila[1] == "A"
    assert len(fila) == len(HEADERS_META_MAESTRA)


def test_fila_maestra_dos_templates_mismo_sku_difieren_solo_en_id():
    p = _producto("A")
    f1 = producto_a_fila_maestra(p, "Meta_default_4x5", "u1", "ARS", True)
    f2 = producto_a_fila_maestra(p, "Meta_cuotas_4x5", "u2", "ARS", True)
    assert f1[0] != f2[0]
    assert f1[1] == f2[1] == "A"


def test_fila_usa_titulo_corto_si_hay_enriquecimiento():
    p = _producto("A")
    p.nombre = "Nombre LARGO aburrido"
    p.descripcion = "Descripción larga aburrida"
    p.enriquecimiento = {
        "titulo_corto": "Título Punchy",
        "descripcion_corta": "Desc 200ch",
    }
    fila = producto_a_fila_individual(p, "https://cdn/x.png", "ARS", True)
    assert fila[1] == "Título Punchy"
    assert fila[2] == "Desc 200ch"


def test_fila_fallback_a_nombre_si_no_hay_enriquecimiento():
    p = _producto("A")
    p.nombre = "Producto Original"
    p.descripcion = "Desc Original"
    p.enriquecimiento = {}
    fila = producto_a_fila_individual(p, "https://cdn/x.png", "ARS", True)
    assert fila[1] == "Producto Original"
    assert fila[2] == "Desc Original"


# ===================== brand: marca TN vs fallback del cliente =====================

def test_brand_individual_respeta_marca_de_tiendanube():
    # Si Tiendanube trae marca, se usa esa (aunque haya brand_fallback).
    p = _producto("A", marca="MarcaReal")
    fila = producto_a_fila_individual(
        p, "https://cdn/x.png", "ARS", True, brand_fallback="Juanita Shoes",
    )
    assert fila[-1] == "MarcaReal"


def test_brand_individual_cae_a_brand_fallback_si_no_hay_marca():
    # Sin marca de TN → usa el brand_name del cliente (no "Agency Nusa").
    p = _producto("A", marca="")
    fila = producto_a_fila_individual(
        p, "https://cdn/x.png", "ARS", True, brand_fallback="Juanita Shoes",
    )
    assert fila[-1] == "Juanita Shoes"


def test_brand_maestra_respeta_marca_de_tiendanube():
    p = _producto("A", marca="MarcaReal")
    fila = producto_a_fila_maestra(
        p, "Meta_default_4x5", "u", "ARS", True, brand_fallback="SHARK",
    )
    assert fila[HEADERS_META_MAESTRA.index("brand")] == "MarcaReal"


def test_brand_maestra_cae_a_brand_fallback_si_no_hay_marca():
    p = _producto("A", marca="")
    fila = producto_a_fila_maestra(
        p, "Meta_default_4x5", "u", "ARS", True, brand_fallback="SHARK",
    )
    assert fila[HEADERS_META_MAESTRA.index("brand")] == "SHARK"


def test_brand_nunca_es_agency_nusa():
    # Regresión: el viejo hardcode "Agency Nusa" no debe volver a aparecer.
    p = _producto("A", marca="")
    fila_ind = producto_a_fila_individual(p, "u", "ARS", True, brand_fallback="X")
    fila_mae = producto_a_fila_maestra(p, "Meta_default_4x5", "u", "ARS", True, brand_fallback="X")
    assert "Agency Nusa" not in fila_ind
    assert "Agency Nusa" not in fila_mae


# ===================== item_group_id (id numérico TN) + internal_label =====================

def _idx(header, col):
    return header.index(col)


def test_item_group_id_usa_tn_product_id():
    # item_group_id = id numérico de TN (str), no el sku.
    p = _producto("remera-negra")
    p.enriquecimiento = {"tn_product_id": 231328222}
    fila = producto_a_fila_maestra(p, "Meta_default_4x5", "u", "ARS", True)
    assert fila[HEADERS_META_MAESTRA.index("item_group_id")] == "231328222"
    # el id de fila sigue siendo {sku}__{template}, intacto
    assert fila[0] == "remera-negra__Meta_default_4x5"


def test_item_group_id_fallback_a_sku_sin_tn_product_id():
    # Si falta tn_product_id, cae al sku (sin romper el feed).
    p = _producto("remera-negra")  # sin enriquecimiento → sin tn_product_id
    fila = producto_a_fila_maestra(p, "Meta_default_4x5", "u", "ARS", True)
    assert fila[HEADERS_META_MAESTRA.index("item_group_id")] == "remera-negra"


def test_internal_label_se_escribe_en_maestra():
    p = _producto("A")
    p.enriquecimiento = {"tn_product_id": 999}
    fila = producto_a_fila_maestra(
        p, "Meta_default_4x5", "u", "ARS", True, internal_label="nusa_placa",
    )
    assert fila[HEADERS_META_MAESTRA.index("internal_label")] == "nusa_placa"
    assert fila[-1] == "nusa_placa"  # internal_label es la última columna


def test_maestra_largo_coincide_con_headers_meta_y_tiktok():
    p = _producto("A")
    p.enriquecimiento = {"tn_product_id": 1}
    fila = producto_a_fila_maestra(
        p, "Meta_default_4x5", "u", "ARS", True,
        brand_fallback="X", internal_label="nusa_placa",
    )
    # El row builder es compartido por Meta y TikTok: su largo debe coincidir
    # con ambos headers maestros (mismo nº de columnas).
    assert len(fila) == len(HEADERS_META_MAESTRA) == len(HEADERS_TIKTOK_MAESTRA)


def test_headers_maestra_incluyen_internal_label():
    assert HEADERS_META_MAESTRA[-1] == "internal_label"
    assert HEADERS_TIKTOK_MAESTRA[-1] == "internal_label"


@pytest.fixture
def meta():
    return MetaCatalogDestino(ConfigMetaCatalog(sheet_id="sheet-123"))


def test_meta_config_requiere_sheet_id():
    with pytest.raises(ErrorDestino, match="sheet_id"):
        MetaCatalogDestino(ConfigMetaCatalog(sheet_id=""))


def test_meta_nombre(meta):
    assert meta.nombre() == "meta_catalog"


def test_meta_constantes_clave():
    assert META_MAESTRA == "Meta_Feed"


@patch("src.distribucion.destinos.meta_catalog.escribir_pestaña_maestra")
@patch("src.distribucion.destinos.meta_catalog.escribir_pestaña_feed")
@patch("src.distribucion.destinos.meta_catalog.mover_pestaña_a_posicion")
def test_meta_publica_maestra_y_individuales(
    mock_mover, mock_escribir_feed, mock_escribir_maestra, meta,
):
    mock_escribir_maestra.return_value = 3
    mock_escribir_feed.return_value = 2

    productos = [_producto("A"), _producto("B"), _producto("C")]
    placas = [
        _placa("A", "Meta_default_4x5"),
        _placa("B", "Meta_cuotas_4x5"),
        _placa("C", "Meta_default_4x5"),
    ]
    decisiones = [
        _decision("A", "Meta_default_4x5"),
        _decision("B", "Meta_cuotas_4x5"),
        _decision("C", "Meta_default_4x5"),
    ]

    resultados = meta.publicar(productos, placas, decisiones)

    assert "Meta_Feed" in resultados
    assert resultados["Meta_Feed"] == 3
    assert "Meta_default_4x5" in resultados
    assert "Meta_cuotas_4x5" in resultados
    mock_mover.assert_called_with("sheet-123", "Meta_Feed", 0)


@patch("src.distribucion.destinos.meta_catalog.escribir_pestaña_maestra")
@patch("src.distribucion.destinos.meta_catalog.escribir_pestaña_feed")
@patch("src.distribucion.destinos.meta_catalog.mover_pestaña_a_posicion")
def test_meta_filtra_decisiones_no_meta(
    mock_mover, mock_escribir_feed, mock_escribir_maestra, meta,
):
    mock_escribir_maestra.return_value = 1
    mock_escribir_feed.return_value = 1

    productos = [_producto("A")]
    placas = [_placa("A", "Meta_default_4x5")]
    decisiones = [
        _decision("A", "Meta_default_4x5"),
        _decision("A", "TikTok_default_9x16"),
    ]

    resultados = meta.publicar(productos, placas, decisiones)
    assert "TikTok_default_9x16" not in resultados
    assert "Meta_default_4x5" in resultados


def test_meta_sin_decisiones_no_escribe_nada(meta):
    resultados = meta.publicar([], [], [])
    assert resultados == {}


def test_meta_decisiones_solo_tiktok_no_escribe_nada(meta):
    productos = [_producto("A")]
    placas = [_placa("A", "TikTok_default_9x16", "9:16")]
    decisiones = [_decision("A", "TikTok_default_9x16")]
    resultados = meta.publicar(productos, placas, decisiones)
    assert resultados == {}


@pytest.fixture
def tiktok():
    return TikTokCatalogDestino(ConfigTikTokCatalog(sheet_id="sheet-123"))


def test_tiktok_config_requiere_sheet_id():
    with pytest.raises(ErrorDestino, match="sheet_id"):
        TikTokCatalogDestino(ConfigTikTokCatalog(sheet_id=""))


def test_tiktok_nombre(tiktok):
    assert tiktok.nombre() == "tiktok_catalog"


def test_tiktok_constantes_clave():
    assert TIKTOK_MAESTRA == "TikTok_Feed"


@patch("src.distribucion.destinos.tiktok_catalog.escribir_pestaña_maestra")
@patch("src.distribucion.destinos.tiktok_catalog.escribir_pestaña_feed")
@patch("src.distribucion.destinos.tiktok_catalog.mover_pestaña_a_posicion")
def test_tiktok_publica_maestra_y_individuales(
    mock_mover, mock_escribir_feed, mock_escribir_maestra, tiktok,
):
    mock_escribir_maestra.return_value = 1
    mock_escribir_feed.return_value = 1

    productos = [_producto("A")]
    placas = [_placa("A", "TikTok_default_9x16", "9:16")]
    decisiones = [_decision("A", "TikTok_default_9x16")]

    resultados = tiktok.publicar(productos, placas, decisiones)
    assert "TikTok_Feed" in resultados
    assert "TikTok_default_9x16" in resultados


@patch("src.distribucion.destinos.tiktok_catalog.escribir_pestaña_maestra")
@patch("src.distribucion.destinos.tiktok_catalog.escribir_pestaña_feed")
@patch("src.distribucion.destinos.tiktok_catalog.mover_pestaña_a_posicion")
def test_tiktok_filtra_decisiones_meta(
    mock_mover, mock_escribir_feed, mock_escribir_maestra, tiktok,
):
    mock_escribir_maestra.return_value = 1
    mock_escribir_feed.return_value = 1

    productos = [_producto("A")]
    placas = [
        _placa("A", "Meta_default_4x5"),
        _placa("A", "TikTok_default_9x16", "9:16"),
    ]
    decisiones = [
        _decision("A", "Meta_default_4x5"),
        _decision("A", "TikTok_default_9x16"),
    ]

    resultados = tiktok.publicar(productos, placas, decisiones)
    assert "Meta_default_4x5" not in resultados
