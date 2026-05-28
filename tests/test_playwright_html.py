"""Tests del Bloque 4: estilo/playwright_html.py (multi-template)."""
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.core.modelo_datos import Producto, DecisionSeleccion
from src.estilo.base import ErrorEstilo
from src.estilo.playwright_html import (
    ConfigPlaywrightHtml,
    PlaywrightHtmlEstilo,
    formatear_precio_ars,
    calcular_cuota,
    _sanitizar_id,
)


@pytest.mark.parametrize("valor,esperado", [
    (97656.0, "$97.656"),
    (114890.0, "$114.890"),
    (1234567.89, "$1.234.568"),
    (999.0, "$999"),
    (0.0, "$0"),
    (1000.0, "$1.000"),
])
def test_formatear_precio_ars(valor, esperado):
    assert formatear_precio_ars(valor) == esperado


def test_calcular_cuota_basico():
    assert calcular_cuota(114890.0, 3) == pytest.approx(38296.67, rel=1e-3)


def test_calcular_cuota_cero_devuelve_base():
    assert calcular_cuota(1000.0, 0) == 1000.0


def test_sanitizar_id_con_espacios():
    assert _sanitizar_id("GOLDNU0 CREA 300G") == "GOLDNU0_CREA_300G"


def test_sanitizar_id_con_caracteres_especiales():
    assert _sanitizar_id("SKU/ABC-123") == "SKU_ABC-123"


def test_sanitizar_id_alfanumerico_no_se_modifica():
    assert _sanitizar_id("ABC123-XYZ") == "ABC123-XYZ"


METADATA_HEADER = (
    "<!-- META\n"
    "aspect_ratio: 4:5\n"
    "width: 1080\n"
    "height: 1350\n"
    "-->\n"
)


@pytest.fixture
def templates_dir(tmp_path):
    d = tmp_path / "templates"
    d.mkdir()
    (d / "default_4x5.html").write_text(
        METADATA_HEADER +
        "<html><body>"
        "<img src='{logo_b64}'>"
        "<img src='{imagen_b64}'>"
        "<p>{nombre} - {precio_original_formateado} → {precio_hotsale_formateado}</p>"
        "<p>{cuotas_num} cuotas de {cuota_formateada}</p>"
        "<p>{brand_name} - {evento_legal}</p>"
        "</body></html>",
        encoding="utf-8",
    )
    return d


@pytest.fixture
def config(templates_dir, tmp_path):
    return ConfigPlaywrightHtml(
        templates_dir=templates_dir,
        output_dir=tmp_path / "out",
        variables_globales={
            "brand_name": "TEST",
            "logo_url": "https://example.com/logo.png",
            "evento_legal": "Promo válida hasta el 30/06.",
        },
    )


@pytest.fixture
def motor(config):
    return PlaywrightHtmlEstilo(config)


@pytest.fixture
def producto_basico():
    return Producto(
        sku="TEST-001",
        nombre="Producto de Prueba",
        precio_lista=10000.0,
        precio_promocional=8000.0,
        cuotas_num=3,
        imagen_url="https://example.com/producto.jpg",
        marca="MarcaX",
    )


@pytest.fixture
def decision_basica():
    return DecisionSeleccion(sku="TEST-001", generar=True, template="Meta_default_4x5")


def test_config_falla_sin_templates_dir(tmp_path):
    cfg = ConfigPlaywrightHtml(
        templates_dir=tmp_path / "no-existe",
        output_dir=tmp_path / "out",
    )
    with pytest.raises(ErrorEstilo, match="no existe"):
        PlaywrightHtmlEstilo(cfg)


def test_config_crea_output_dir_si_no_existe(templates_dir, tmp_path):
    out = tmp_path / "out-nuevo"
    assert not out.exists()
    cfg = ConfigPlaywrightHtml(templates_dir=templates_dir, output_dir=out)
    PlaywrightHtmlEstilo(cfg)
    assert out.exists()


@patch("src.estilo.playwright_html.requests.get")
def test_imagen_se_descarga_una_sola_vez(mock_get, motor):
    mock_resp = MagicMock()
    mock_resp.content = b"fake-image-bytes"
    mock_resp.headers = {"Content-Type": "image/png"}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    url = "https://example.com/img.png"
    r1 = motor._descargar_imagen_a_base64(url)
    r2 = motor._descargar_imagen_a_base64(url)
    r3 = motor._descargar_imagen_a_base64(url)

    assert r1 == r2 == r3
    assert r1.startswith("data:image/png;base64,")
    assert mock_get.call_count == 1


@patch("src.estilo.playwright_html.requests.get")
def test_imagen_falla_si_descarga_da_error(mock_get, motor):
    import requests
    mock_get.side_effect = requests.ConnectionError("network down")

    with pytest.raises(ErrorEstilo, match="Falló descarga"):
        motor._descargar_imagen_a_base64("https://example.com/x.jpg")


def test_imagen_falla_si_url_vacia(motor):
    with pytest.raises(ErrorEstilo, match="vacía"):
        motor._descargar_imagen_a_base64("")


@patch("src.estilo.playwright_html.requests.get")
def test_content_type_default_a_jpeg_si_no_viene(mock_get, motor):
    mock_resp = MagicMock()
    mock_resp.content = b"fake"
    mock_resp.headers = {}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    result = motor._descargar_imagen_a_base64("https://example.com/x")
    assert result.startswith("data:image/jpeg;base64,")


@patch("src.estilo.playwright_html.requests.get")
def test_construir_variables_basico(
    mock_get, motor, producto_basico, decision_basica
):
    mock_resp = MagicMock()
    mock_resp.content = b"fake"
    mock_resp.headers = {"Content-Type": "image/jpeg"}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    vars_ = motor._construir_variables(producto_basico, decision_basica)

    assert vars_["sku"] == "TEST-001"
    assert vars_["nombre"] == "Producto de Prueba"
    assert vars_["precio_original_formateado"] == "$10.000"
    assert vars_["precio_hotsale_formateado"] == "$8.000"
    assert vars_["cuota_formateada"] == "$3.333"
    assert vars_["cuotas_num"] == "3"
    assert vars_["brand_name"] == "TEST"
    assert vars_["evento_legal"] == "Promo válida hasta el 30/06."
    assert vars_["imagen_b64"].startswith("data:image/jpeg;base64,")
    assert vars_["logo_b64"].startswith("data:image/jpeg;base64,")


@patch("src.estilo.playwright_html.requests.get")
def test_variables_sin_promo_usa_precio_lista(
    mock_get, motor, decision_basica
):
    mock_resp = MagicMock(content=b"x", headers={"Content-Type": "image/jpeg"})
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    p = Producto(
        sku="X", nombre="X", precio_lista=5000.0,
        precio_promocional=None,
        imagen_url="https://example.com/x.jpg",
    )
    vars_ = motor._construir_variables(p, decision_basica)
    assert vars_["precio_original_formateado"] == "$5.000"
    assert vars_["precio_hotsale_formateado"] == "$5.000"


@patch("src.estilo.playwright_html.requests.get")
def test_variables_aplica_hotsale_discount_factor(
    mock_get, templates_dir, tmp_path, decision_basica
):
    mock_resp = MagicMock(content=b"x", headers={"Content-Type": "image/jpeg"})
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    cfg = ConfigPlaywrightHtml(
        templates_dir=templates_dir,
        output_dir=tmp_path / "out",
        variables_globales={"logo_url": "https://example.com/l.png"},
        hotsale_discount_factor=0.8,
    )
    motor = PlaywrightHtmlEstilo(cfg)

    p = Producto(
        sku="X", nombre="X", precio_lista=10000.0,
        precio_promocional=None,
        imagen_url="https://example.com/x.jpg",
    )
    vars_ = motor._construir_variables(p, decision_basica)
    assert vars_["precio_hotsale_formateado"] == "$8.000"


def test_falla_si_no_hay_logo_url(
    templates_dir, tmp_path, producto_basico, decision_basica
):
    cfg = ConfigPlaywrightHtml(
        templates_dir=templates_dir,
        output_dir=tmp_path / "out",
        variables_globales={},
    )
    motor = PlaywrightHtmlEstilo(cfg)

    with patch("src.estilo.playwright_html.requests.get") as mock_get:
        mock_resp = MagicMock(content=b"x", headers={"Content-Type": "image/jpeg"})
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp
        with pytest.raises(ErrorEstilo, match="logo_url"):
            motor._construir_variables(producto_basico, decision_basica)


@patch("src.estilo.playwright_html.requests.get")
def test_variables_globales_no_sobreescriben_calculadas(
    mock_get, templates_dir, tmp_path, producto_basico, decision_basica
):
    mock_resp = MagicMock(content=b"x", headers={"Content-Type": "image/jpeg"})
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    cfg = ConfigPlaywrightHtml(
        templates_dir=templates_dir,
        output_dir=tmp_path / "out",
        variables_globales={
            "logo_url": "https://example.com/l.png",
            "sku": "VARIABLE-GLOBAL-MALA",
        },
    )
    motor = PlaywrightHtmlEstilo(cfg)
    vars_ = motor._construir_variables(producto_basico, decision_basica)
    assert vars_["sku"] == "TEST-001"


def test_reemplazar_variables_simple(motor):
    html = "<p>{nombre}</p>"
    out = motor._reemplazar_variables(html, {"nombre": "Test"})
    assert out == "<p>Test</p>"


def test_reemplazar_variables_no_existente_queda_literal(motor, caplog):
    import logging
    caplog.set_level(logging.WARNING)
    html = "<p>{existe} - {no_existe}</p>"
    out = motor._reemplazar_variables(html, {"existe": "OK"})
    assert "OK" in out
    assert "{no_existe}" in out
    assert "no_existe" in caplog.text


def test_cargar_template_inexistente_falla(motor):
    with pytest.raises(ErrorEstilo, match="no encontrado"):
        motor._cargar_template("Meta_template-que-no-existe")


def test_cargar_template_quita_prefijo_meta(motor, templates_dir):
    """'Meta_default_4x5' carga el archivo 'default_4x5.html'."""
    contenido, metadata = motor._cargar_template("Meta_default_4x5")
    assert "{nombre}" in contenido
    assert metadata.aspect_ratio == "4:5"
    assert metadata.width == 1080
    assert metadata.height == 1350


def test_cargar_template_quita_prefijo_tiktok(motor, templates_dir):
    """'TikTok_default_4x5' también carga 'default_4x5.html'."""
    contenido, metadata = motor._cargar_template("TikTok_default_4x5")
    assert "{nombre}" in contenido


def test_cargar_template_cachea(motor, templates_dir):
    motor._cargar_template("Meta_default_4x5")
    (templates_dir / "default_4x5.html").write_text("MODIFICADO", encoding="utf-8")
    contenido, _ = motor._cargar_template("Meta_default_4x5")
    assert "MODIFICADO" not in contenido
    assert "{nombre}" in contenido


def test_nombre_motor(motor):
    assert motor.nombre() == "playwright_html"


@patch("src.estilo.playwright_html.requests.get")
def test_precio_efectivo_no_se_expone_si_factor_es_none(
    mock_get, motor, producto_basico, decision_basica
):
    mock_resp = MagicMock(content=b"x", headers={"Content-Type": "image/jpeg"})
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp
    vars_ = motor._construir_variables(producto_basico, decision_basica)
    assert "precio_efectivo_formateado" not in vars_


@patch("src.estilo.playwright_html.requests.get")
def test_precio_efectivo_caso_mora(
    mock_get, templates_dir, tmp_path, decision_basica
):
    mock_resp = MagicMock(content=b"x", headers={"Content-Type": "image/jpeg"})
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    cfg = ConfigPlaywrightHtml(
        templates_dir=templates_dir,
        output_dir=tmp_path / "out",
        variables_globales={"logo_url": "https://example.com/l.png"},
        descuento_efectivo_factor=0.85,
    )
    motor = PlaywrightHtmlEstilo(cfg)

    p = Producto(
        sku="OMEGA-001", nombre="Omega 3 Max",
        precio_lista=86626.0, precio_promocional=82294.0,
        imagen_url="https://example.com/x.jpg",
    )
    vars_ = motor._construir_variables(p, decision_basica)
    assert vars_["precio_hotsale_formateado"] == "$82.294"
    assert vars_["precio_efectivo_formateado"] == "$69.950"


@patch("src.estilo.playwright_html.requests.get")
def test_cuotas_default_sobre_precio_lista(
    mock_get, motor, producto_basico, decision_basica
):
    mock_resp = MagicMock(content=b"x", headers={"Content-Type": "image/jpeg"})
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp
    vars_ = motor._construir_variables(producto_basico, decision_basica)
    assert vars_["cuota_formateada"] == "$3.333"


@patch("src.estilo.playwright_html.requests.get")
def test_cuotas_sobre_promocional_caso_mora(
    mock_get, templates_dir, tmp_path, decision_basica
):
    mock_resp = MagicMock(content=b"x", headers={"Content-Type": "image/jpeg"})
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    cfg = ConfigPlaywrightHtml(
        templates_dir=templates_dir,
        output_dir=tmp_path / "out",
        variables_globales={"logo_url": "https://example.com/l.png"},
        cuotas_sobre_promocional=True,
    )
    motor = PlaywrightHtmlEstilo(cfg)

    p = Producto(
        sku="OMEGA-001", nombre="Omega 3 Max",
        precio_lista=86626.0, precio_promocional=82294.0,
        cuotas_num=3,
        imagen_url="https://example.com/x.jpg",
    )
    vars_ = motor._construir_variables(p, decision_basica)
    assert vars_["cuota_formateada"] == "$27.431"


@patch("src.estilo.playwright_html.requests.get")
def test_combo_efectivo_y_cuotas_caso_mora_completo(
    mock_get, templates_dir, tmp_path, decision_basica
):
    mock_resp = MagicMock(content=b"x", headers={"Content-Type": "image/jpeg"})
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    cfg = ConfigPlaywrightHtml(
        templates_dir=templates_dir,
        output_dir=tmp_path / "out",
        variables_globales={"logo_url": "https://example.com/l.png"},
        descuento_efectivo_factor=0.85,
        cuotas_sobre_promocional=True,
    )
    motor = PlaywrightHtmlEstilo(cfg)

    p = Producto(
        sku="OMEGA-001", nombre="Omega 3 Max",
        precio_lista=86626.0, precio_promocional=82294.0,
        cuotas_num=3,
        imagen_url="https://example.com/x.jpg",
    )
    vars_ = motor._construir_variables(p, decision_basica)
    assert vars_["precio_hotsale_formateado"] == "$82.294"
    assert vars_["precio_efectivo_formateado"] == "$69.950"
    assert vars_["cuota_formateada"] == "$27.431"
