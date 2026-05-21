"""Tests de src/inventario/tiendanube.py

No llaman a la API real. Mockean las respuestas HTTP con datos
que reflejan la estructura real que devuelve TN (basado en samples
inspeccionados de morashop.ar).
"""
from unittest.mock import patch, MagicMock
import pytest

from src.inventario.tiendanube import (
    ConfigTiendanube,
    TiendanubeInventario,
    limpiar_html,
    _campo_es,
    _a_float,
    _a_int,
)


# ============ Helpers de parseo ============

def test_limpiar_html_basico():
    assert limpiar_html("<p>Hola <b>mundo</b></p>") == "Hola mundo"


def test_limpiar_html_entidades():
    assert limpiar_html("Caf&eacute;&nbsp;&amp; pan") == "Caf&eacute; & pan"
    # Solo decodificamos las 6 entidades más comunes


def test_limpiar_html_vacio():
    assert limpiar_html("") == ""
    assert limpiar_html(None) == ""


def test_limpiar_html_whitespace_multiple():
    assert limpiar_html("<p>uno\n\n   dos</p>") == "uno dos"


def test_campo_es_dict():
    assert _campo_es({"es": "Hola"}) == "Hola"


def test_campo_es_string_directo():
    """Algunos campos como 'brand' vienen como string, no dict."""
    assert _campo_es("Gold Nutrition") == "Gold Nutrition"


def test_campo_es_none():
    assert _campo_es(None) == ""


def test_campo_es_dict_sin_es():
    assert _campo_es({"en": "Hello"}) == ""


def test_a_float_string_con_decimal():
    assert _a_float("23124.00") == 23124.0


def test_a_float_vacio_o_none():
    assert _a_float("") is None
    assert _a_float(None) is None
    assert _a_float("nope") is None


def test_a_int_normal():
    assert _a_int("5") == 5
    assert _a_int(10) == 10


# ============ Config ============

def test_config_requiere_store_id():
    with pytest.raises(ValueError, match="store_id"):
        TiendanubeInventario(ConfigTiendanube(store_id="", access_token="abc"))


def test_config_requiere_token():
    with pytest.raises(ValueError, match="access_token"):
        TiendanubeInventario(ConfigTiendanube(store_id="123", access_token=""))


# ============ Sample data (estructura real de TN) ============

PRODUCTO_TN_BASICO = {
    "id": 190330962,
    "name": {"es": "Creatina Monohidrato 300g Gold Nutrition"},
    "description": {"es": "<p>La <b>mejor</b> creatina del mercado.</p>"},
    "published": True,
    "has_stock": True,
    "is_kit": False,
    "brand": "Gold Nutrition",
    "canonical_url": "https://www.morashop.ar/productos/creatina-mono-300g/",
    "variants": [
        {
            "id": 763959309,
            "sku": "GOLDNU0 CREA 300G",
            "price": "23124.00",
            "compare_at_price": "24324.00",
            "promotional_price": "20000.00",
            "stock": 15,
        }
    ],
    "images": [
        {"src": "https://acdn-us.mitiendanube.com/stores/.../creatina.jpg", "position": 1}
    ],
    "categories": [
        {"id": 1, "name": {"es": "Suplementos"}}
    ],
}


PRODUCTO_TN_MULTIPLES_VARIANTES = {
    "id": 100000,
    "name": {"es": "Whey Protein"},
    "description": {"es": ""},
    "published": True,
    "has_stock": True,
    "is_kit": False,
    "brand": "ENA",
    "canonical_url": "https://www.morashop.ar/productos/whey/",
    "variants": [
        {"id": 1, "sku": "ENA-WHEY-CHOC", "price": "30000.00", "promotional_price": None, "stock": 10},
        {"id": 2, "sku": "ENA-WHEY-VAIN", "price": "30000.00", "promotional_price": None, "stock": 5},
        {"id": 3, "sku": "", "price": "30000.00", "promotional_price": None, "stock": 0},  # sin SKU, ignorar
    ],
    "images": [{"src": "https://example.com/whey.jpg", "position": 1}],
    "categories": [{"id": 2, "name": {"es": "Proteínas"}}],
}


PRODUCTO_TN_SIN_PUBLICAR = {
    "id": 200000,
    "name": {"es": "Producto Borrador"},
    "description": {"es": ""},
    "published": False,        # NO publicado
    "has_stock": False,
    "is_kit": False,
    "brand": "",
    "canonical_url": "",
    "variants": [
        {"id": 100, "sku": "BORRADOR-001", "price": "100.00", "stock": 0}
    ],
    "images": [],
    "categories": [],
}


# ============ Tests de _producto_tn_a_modelo ============

@pytest.fixture
def fuente():
    return TiendanubeInventario(ConfigTiendanube(
        store_id="2268228", access_token="fake_token"
    ))


def test_producto_basico_se_mapea_bien(fuente):
    productos = fuente._producto_tn_a_modelo(PRODUCTO_TN_BASICO)
    assert len(productos) == 1
    p = productos[0]
    assert p.sku == "GOLDNU0 CREA 300G"
    assert p.nombre == "Creatina Monohidrato 300g Gold Nutrition"
    assert p.descripcion == "La mejor creatina del mercado."  # HTML limpiado
    assert p.precio_lista == 23124.0
    assert p.precio_promocional == 20000.0
    assert p.tiene_promo is True
    assert p.cuotas_num == 3  # default acordado
    assert p.stock == 15
    assert p.categoria == "Suplementos"
    assert p.marca == "Gold Nutrition"
    assert p.imagen_url.startswith("https://acdn-us.mitiendanube.com")
    assert p.url_producto.startswith("https://www.morashop.ar")
    assert p.fuente == "tiendanube"


def test_metadata_tn_preservada_en_enriquecimiento(fuente):
    productos = fuente._producto_tn_a_modelo(PRODUCTO_TN_BASICO)
    p = productos[0]
    assert p.enriquecimiento["tn_product_id"] == 190330962
    assert p.enriquecimiento["tn_variant_id"] == 763959309
    assert p.enriquecimiento["tn_published"] is True
    assert p.enriquecimiento["tn_has_stock"] is True
    assert p.enriquecimiento["tn_compare_at_price"] == "24324.00"


def test_multiples_variantes_un_producto_por_variante_con_sku(fuente):
    productos = fuente._producto_tn_a_modelo(PRODUCTO_TN_MULTIPLES_VARIANTES)
    # 3 variantes en TN pero 1 no tiene SKU → 2 Producto en el resultado
    assert len(productos) == 2
    skus = {p.sku for p in productos}
    assert skus == {"ENA-WHEY-CHOC", "ENA-WHEY-VAIN"}
    # Ambos comparten el mismo nombre, imagen, marca (vienen del producto padre)
    assert all(p.nombre == "Whey Protein" for p in productos)
    assert all(p.marca == "ENA" for p in productos)


def test_productos_no_publicados_se_traen_igual(fuente):
    """Decisión: traemos todos, marcamos metadata, filtra Bloque 2 (Selección)."""
    productos = fuente._producto_tn_a_modelo(PRODUCTO_TN_SIN_PUBLICAR)
    assert len(productos) == 1
    assert productos[0].enriquecimiento["tn_published"] is False
    assert productos[0].enriquecimiento["tn_has_stock"] is False


def test_producto_sin_variantes_se_ignora(fuente):
    p_tn = dict(PRODUCTO_TN_BASICO)
    p_tn["variants"] = []
    assert fuente._producto_tn_a_modelo(p_tn) == []


def test_variante_sin_precio_se_ignora(fuente):
    p_tn = dict(PRODUCTO_TN_BASICO)
    p_tn["variants"] = [{"id": 1, "sku": "TEST", "price": None}]
    assert fuente._producto_tn_a_modelo(p_tn) == []


def test_producto_sin_categoria_o_imagen_no_falla(fuente):
    """Edge case: catálogo nuevo sin imágenes ni categorías."""
    p_tn = dict(PRODUCTO_TN_BASICO)
    p_tn["categories"] = []
    p_tn["images"] = []
    productos = fuente._producto_tn_a_modelo(p_tn)
    assert len(productos) == 1
    assert productos[0].categoria == ""
    assert productos[0].imagen_url == ""


# ============ Test de paginación (mockeando requests) ============

@patch("src.inventario.tiendanube.requests.get")
def test_paginacion_para_cuando_recibe_lista_vacia(mock_get, fuente):
    """TN puede devolver lista vacía (no 404) cuando se acaban productos."""
    fuente.cfg.retraso_entre_paginas = 0  # no esperar en tests
    fuente.cfg.max_paginas = 5

    # Página 1: 1 producto. Página 2: vacía.
    r1 = MagicMock(status_code=200, json=lambda: [PRODUCTO_TN_BASICO])
    r1.raise_for_status = MagicMock()
    r2 = MagicMock(status_code=200, json=lambda: [])
    r2.raise_for_status = MagicMock()
    mock_get.side_effect = [r1, r2]

    productos = fuente.traer_productos()
    assert len(productos) == 1
    assert mock_get.call_count == 2


@patch("src.inventario.tiendanube.requests.get")
def test_paginacion_para_cuando_recibe_404(mock_get, fuente):
    """TN responde 404 cuando se acabaron las páginas. No es un error."""
    fuente.cfg.retraso_entre_paginas = 0
    fuente.cfg.max_paginas = 5

    resp_ok = MagicMock(status_code=200, json=lambda: [PRODUCTO_TN_BASICO])
    resp_ok.raise_for_status = MagicMock()
    resp_404 = MagicMock(status_code=404)
    resp_404.raise_for_status = MagicMock()  # no debe llamarse, porque 404 lo manejamos

    mock_get.side_effect = [resp_ok, resp_404]

    productos = fuente.traer_productos()
    assert len(productos) == 1
    assert mock_get.call_count == 2


@patch("src.inventario.tiendanube.requests.get")
def test_headers_son_los_correctos(mock_get, fuente):
    """TN usa header 'Authentication' (no 'Authorization'). Hay que respetarlo."""
    fuente.cfg.retraso_entre_paginas = 0
    fuente.cfg.max_paginas = 2

    resp = MagicMock(status_code=200, json=lambda: [])
    resp.raise_for_status = MagicMock()
    mock_get.return_value = resp

    fuente.traer_productos()

    # Validar el primer call
    call_kwargs = mock_get.call_args_list[0].kwargs
    assert call_kwargs["headers"]["Authentication"] == "bearer fake_token"
    assert "User-Agent" in call_kwargs["headers"]


def test_nombre_modulo(fuente):
    assert fuente.nombre() == "tiendanube"
