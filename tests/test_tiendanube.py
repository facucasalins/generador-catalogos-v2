"""Tests de src/inventario/tiendanube.py

No llaman a la API real. Mockean las respuestas HTTP con datos
que reflejan la estructura real que devuelve TN (basado en samples
inspeccionados de morashop.ar y shark.com.ar).
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
    _sku_desde_handle,
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


def test_config_agrupar_por_producto_default_false():
    """Retrocompat: el default es False (comportamiento histórico de Mora)."""
    cfg = ConfigTiendanube(store_id="123", access_token="abc")
    assert cfg.agrupar_por_producto is False


# ============ Sample data (estructura real de TN) ============

PRODUCTO_TN_BASICO = {
    "id": 190330962,
    "name": {"es": "Creatina Monohidrato 300g Gold Nutrition"},
    "description": {"es": "<p>La <b>mejor</b> creatina del mercado.</p>"},
    "handle": {"es": "creatina-mono-300g"},
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
    "handle": {"es": "whey"},
    "published": True,
    "has_stock": True,
    "is_kit": False,
    "brand": "ENA",
    "canonical_url": "https://www.morashop.ar/productos/whey/",
    "variants": [
        {"id": 1, "sku": "ENA-WHEY-CHOC", "price": "30000.00", "promotional_price": None, "stock": 10},
        {"id": 2, "sku": "ENA-WHEY-VAIN", "price": "30000.00", "promotional_price": None, "stock": 5},
        {"id": 3, "sku": "", "price": "30000.00", "promotional_price": None, "stock": 0},  # sin SKU
    ],
    "images": [{"src": "https://example.com/whey.jpg", "position": 1}],
    "categories": [{"id": 2, "name": {"es": "Proteínas"}}],
}


PRODUCTO_TN_SIN_PUBLICAR = {
    "id": 200000,
    "name": {"es": "Producto Borrador"},
    "description": {"es": ""},
    "handle": {"es": "borrador"},
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


# Sample típico de tienda de ropa Tiendanube: NINGUNA variante carga SKU.
# Talles distintos, mismo handle, mismo precio. Stock variable.
PRODUCTO_TN_ROPA = {
    "id": 999001,
    "name": {"es": "Remera Oversize Negra"},
    "description": {"es": "Algodón premium"},
    "handle": {"es": "remera-oversize-negra"},
    "published": True,
    "has_stock": True,
    "is_kit": False,
    "brand": "SHARK",
    "canonical_url": "https://shark.com.ar/productos/remera-oversize-negra/",
    "variants": [
        {"id": 555001, "sku": "", "price": "15000.00", "stock": 10},  # Talle S
        {"id": 555002, "sku": "", "price": "15000.00", "stock": 5},   # Talle M
        {"id": 555003, "sku": "", "price": "15000.00", "stock": 0},   # Talle L (agotado)
    ],
    "images": [{"src": "https://example.com/remera.jpg", "position": 1}],
    "categories": [{"id": 10, "name": {"es": "Remeras"}}],
}


# ============ Tests de _producto_tn_a_modelo (MODO POR VARIANTE - Mora) ============

@pytest.fixture
def fuente():
    """Fixture default: modo por variante (Mora)."""
    return TiendanubeInventario(ConfigTiendanube(
        store_id="2268228", access_token="fake_token"
    ))


@pytest.fixture
def fuente_agrupada():
    """Fixture con agrupar_por_producto=True (Shark)."""
    return TiendanubeInventario(ConfigTiendanube(
        store_id="2268228",
        access_token="fake_token",
        agrupar_por_producto=True,
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
    """Modo por variante: 1 fila por variante CON SKU."""
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


def test_modo_por_variante_descarta_ropa_sin_sku(fuente):
    """Comportamiento histórico (Mora): variantes sin SKU se descartan.

    Este test PROTEGE a Mora de cambios accidentales. Si alguien activa
    el flag por error o cambia el default, este test falla antes del deploy.
    """
    productos = fuente._producto_tn_a_modelo(PRODUCTO_TN_ROPA)
    assert productos == []  # las 3 variantes sin SKU se descartan


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


# ============ Tests del helper _sku_desde_handle ============

def test_sku_desde_handle_normal():
    """Caso normal: handle válido → SKU = handle tal cual."""
    assert _sku_desde_handle("remera-oversize-negra", 999) == "remera-oversize-negra"


def test_sku_desde_handle_sin_handle():
    """Fallback defensivo: sin handle → 'tn-{product_id}'."""
    assert _sku_desde_handle("", 999001) == "tn-999001"
    assert _sku_desde_handle(None, 999001) == "tn-999001"
    assert _sku_desde_handle("   ", 999001) == "tn-999001"


def test_sku_desde_handle_sin_nada():
    """Sin handle ni product_id no podemos generar nada."""
    assert _sku_desde_handle("", None) is None
    assert _sku_desde_handle(None, None) is None


# ============ Tests del MODO AGRUPADO (Shark) ============

def test_modo_agrupado_genera_un_solo_producto_por_producto_tn(fuente_agrupada):
    """Shark: 1 producto TN con 3 variantes → 1 Producto en el resultado."""
    productos = fuente_agrupada._producto_tn_a_modelo(PRODUCTO_TN_ROPA)
    assert len(productos) == 1
    p = productos[0]
    # SKU = handle, sin variant_id ni nada al final
    assert p.sku == "remera-oversize-negra"
    assert p.nombre == "Remera Oversize Negra"
    assert p.marca == "SHARK"
    assert p.url_producto == "https://shark.com.ar/productos/remera-oversize-negra/"


def test_modo_agrupado_precio_es_de_la_primera_variante(fuente_agrupada):
    """Precio = primera variante (en Shark todas valen lo mismo)."""
    productos = fuente_agrupada._producto_tn_a_modelo(PRODUCTO_TN_ROPA)
    assert productos[0].precio_lista == 15000.0


def test_modo_agrupado_stock_es_suma_de_variantes(fuente_agrupada):
    """Stock total = suma de todas las variantes (10 + 5 + 0 = 15)."""
    productos = fuente_agrupada._producto_tn_a_modelo(PRODUCTO_TN_ROPA)
    assert productos[0].stock == 15


def test_modo_agrupado_metadata_incluye_info_de_variantes(fuente_agrupada):
    """Metadata útil para diagnóstico: cuántas variantes y cuántas con stock."""
    productos = fuente_agrupada._producto_tn_a_modelo(PRODUCTO_TN_ROPA)
    enriq = productos[0].enriquecimiento
    assert enriq["tn_handle"] == "remera-oversize-negra"
    assert enriq["tn_variantes_total"] == 3
    assert enriq["tn_variantes_con_stock"] == 2  # solo S y M tienen stock
    assert enriq["tn_sku_es_handle"] is True
    assert enriq["tn_product_id"] == 999001


def test_modo_agrupado_sin_handle_usa_tn_product_id(fuente_agrupada):
    """Fallback defensivo: si TN no devuelve handle, usar 'tn-{product_id}'."""
    p_tn = dict(PRODUCTO_TN_ROPA)
    p_tn["handle"] = {"es": ""}
    productos = fuente_agrupada._producto_tn_a_modelo(p_tn)
    assert len(productos) == 1
    assert productos[0].sku == "tn-999001"


def test_modo_agrupado_sin_variantes_se_ignora(fuente_agrupada):
    p_tn = dict(PRODUCTO_TN_ROPA)
    p_tn["variants"] = []
    assert fuente_agrupada._producto_tn_a_modelo(p_tn) == []


def test_modo_agrupado_sin_precio_en_primera_variante_se_ignora(fuente_agrupada):
    p_tn = dict(PRODUCTO_TN_ROPA)
    p_tn["variants"] = [
        {"id": 1, "sku": "", "price": None, "stock": 5},
        {"id": 2, "sku": "", "price": "15000.00", "stock": 5},
    ]
    # Aunque la 2da tenga precio, la 1ra define el precio → descartamos
    assert fuente_agrupada._producto_tn_a_modelo(p_tn) == []


def test_modo_agrupado_warnea_si_precios_distintos(fuente_agrupada, caplog):
    """Si las variantes tienen precios distintos, log.warning lo registra."""
    import logging
    p_tn = dict(PRODUCTO_TN_ROPA)
    p_tn["variants"] = [
        {"id": 1, "sku": "", "price": "15000.00", "stock": 5},
        {"id": 2, "sku": "", "price": "18000.00", "stock": 3},
    ]
    with caplog.at_level(logging.WARNING):
        productos = fuente_agrupada._producto_tn_a_modelo(p_tn)
    assert len(productos) == 1
    # Usa el precio de la primera variante
    assert productos[0].precio_lista == 15000.0
    # Y warnea sobre los precios distintos
    assert any("precios distintos" in r.message for r in caplog.records)


def test_modo_agrupado_stock_none_cuando_todas_las_variantes_no_lo_tienen(fuente_agrupada):
    """Si TN no devuelve stock en ninguna variante, dejamos stock=None."""
    p_tn = dict(PRODUCTO_TN_ROPA)
    p_tn["variants"] = [
        {"id": 1, "sku": "", "price": "15000.00", "stock": None},
        {"id": 2, "sku": "", "price": "15000.00", "stock": None},
    ]
    productos = fuente_agrupada._producto_tn_a_modelo(p_tn)
    assert len(productos) == 1
    assert productos[0].stock is None


def test_modo_agrupado_no_duplica_si_producto_tiene_un_solo_sku_explicito(fuente_agrupada):
    """Aunque la variante tenga SKU, en modo agrupado se ignora y usamos handle.

    En modo agrupado, el SKU = handle SIEMPRE. No mezclamos modos.
    """
    productos = fuente_agrupada._producto_tn_a_modelo(PRODUCTO_TN_BASICO)
    # PRODUCTO_TN_BASICO tiene 1 variante con SKU "GOLDNU0 CREA 300G", pero
    # en modo agrupado el SKU resultante es el handle, no el sku de la variante.
    assert len(productos) == 1
    assert productos[0].sku == "creatina-mono-300g"  # el handle
