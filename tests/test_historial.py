"""Tests del módulo historial (multi-template).

Clave del historial: (sku, template). El refactor cambió esta clave
desde (sku, aspect_ratio).
"""
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile

from src.core.modelo_datos import Producto, DecisionSeleccion
from src.distribucion.historial import (
    EntradaHistorial, HistorialPlacas, calcular_hash, HEADERS_HISTORIAL,
)


def _producto(sku="A", precio=1000.0, promo=800.0, nombre="P", imagen="img.jpg"):
    return Producto(
        sku=sku, nombre=nombre, descripcion="d",
        precio_lista=precio, precio_promocional=promo,
        stock=10, marca="M",
        url_producto=f"https://x/{sku}", imagen_url=imagen,
    )


def _decision(sku="A", template="default_4x5"):
    return DecisionSeleccion(sku=sku, generar=True, template=template)


def _templates_dir_con(nombre="default_4x5", contenido="<html>X</html>") -> Path:
    d = Path(tempfile.mkdtemp())
    (d / f"{nombre}.html").write_text(contenido, encoding="utf-8")
    return d


def test_hash_determinista():
    td = _templates_dir_con()
    p, d = _producto(), _decision()
    h1 = calcular_hash(p, d, td)
    h2 = calcular_hash(p, d, td)
    assert h1 == h2


def test_hash_cambia_si_cambia_precio_lista():
    td = _templates_dir_con()
    d = _decision()
    h1 = calcular_hash(_producto(precio=1000.0), d, td)
    h2 = calcular_hash(_producto(precio=1100.0), d, td)
    assert h1 != h2


def test_hash_cambia_si_cambia_precio_promo():
    td = _templates_dir_con()
    d = _decision()
    h1 = calcular_hash(_producto(promo=800.0), d, td)
    h2 = calcular_hash(_producto(promo=750.0), d, td)
    assert h1 != h2


def test_hash_cambia_si_cambia_imagen():
    td = _templates_dir_con()
    d = _decision()
    h1 = calcular_hash(_producto(imagen="a.jpg"), d, td)
    h2 = calcular_hash(_producto(imagen="b.jpg"), d, td)
    assert h1 != h2


def test_hash_cambia_si_cambia_nombre():
    td = _templates_dir_con()
    d = _decision()
    h1 = calcular_hash(_producto(nombre="Producto A"), d, td)
    h2 = calcular_hash(_producto(nombre="Producto A Mejorado"), d, td)
    assert h1 != h2


def test_hash_cambia_si_cambia_template_asignado():
    d_a = Path(tempfile.mkdtemp())
    (d_a / "default_4x5.html").write_text("<html>X</html>", encoding="utf-8")
    (d_a / "cuotas_4x5.html").write_text("<html>Y</html>", encoding="utf-8")
    p = _producto()
    h1 = calcular_hash(p, _decision(template="default_4x5"), d_a)
    h2 = calcular_hash(p, _decision(template="cuotas_4x5"), d_a)
    assert h1 != h2


def test_hash_cambia_si_cambia_contenido_html():
    p, d = _producto(), _decision()
    td1 = _templates_dir_con(contenido="<html>VIEJO</html>")
    td2 = _templates_dir_con(contenido="<html>NUEVO</html>")
    h1 = calcular_hash(p, d, td1)
    h2 = calcular_hash(p, d, td2)
    assert h1 != h2


def test_hash_incluye_contenido_html_con_template_prefijado():
    # Bug fix: el nombre de template viene con prefijo de plataforma
    # (Meta_/TikTok_) pero el archivo en disco no lo tiene. Antes el hash
    # no encontraba el archivo y usaba "" → cambiar el HTML no regeneraba.
    # Ahora el prefijo se resuelve y el contenido entra al hash.
    p = _producto()
    d = _decision(template="Meta_juanita_4x5")

    td_viejo = _templates_dir_con(nombre="juanita_4x5", contenido="<html>HEADER VIEJO</html>")
    td_nuevo = _templates_dir_con(nombre="juanita_4x5", contenido="<html>HEADER NUEVO</html>")

    h_viejo = calcular_hash(p, d, td_viejo)
    h_nuevo = calcular_hash(p, d, td_nuevo)

    # Si el contenido entra al hash, cambiar el HTML cambia el hash aun
    # con el nombre de template prefijado.
    assert h_viejo != h_nuevo


def test_hash_resuelve_mismo_archivo_que_motor_de_estilo():
    # El HTML base se llama 'juanita_4x5.html'. Tanto 'Meta_juanita_4x5'
    # como 'TikTok_juanita_4x5' deben leer ESE archivo (no string vacío),
    # así que su contenido afecta el hash.
    td = _templates_dir_con(nombre="juanita_4x5", contenido="<html>CONTENIDO REAL</html>")
    p = _producto()

    # Mismo archivo, contenido real → hash distinto a un dir vacío (donde
    # el archivo no existe y el contenido cae a "").
    h_con_contenido = calcular_hash(p, _decision(template="Meta_juanita_4x5"), td)
    h_sin_archivo = calcular_hash(p, _decision(template="Meta_juanita_4x5"), Path(tempfile.mkdtemp()))
    assert h_con_contenido != h_sin_archivo


def test_hash_no_cambia_si_cambia_stock():
    td = _templates_dir_con()
    d = _decision()
    p1 = _producto()
    p1.stock = 10
    p2 = _producto()
    p2.stock = 5
    h1 = calcular_hash(p1, d, td)
    h2 = calcular_hash(p2, d, td)
    assert h1 == h2


def test_hash_tolera_template_inexistente():
    td = Path(tempfile.mkdtemp())
    p = _producto()
    d = _decision(template="no_existe")
    h = calcular_hash(p, d, td)
    assert isinstance(h, str) and len(h) == 16


@patch("src.distribucion.historial.SheetsClient")
def test_leer_todo_pestaña_vacia(mock_client_class):
    mock_client = MagicMock()
    mock_client.leer_todas_las_filas.side_effect = Exception("no existe")
    mock_client_class.return_value = mock_client

    h = HistorialPlacas("sheet-123")
    assert h.leer_todo() == {}


@patch("src.distribucion.historial.SheetsClient")
def test_leer_todo_solo_headers(mock_client_class):
    mock_client = MagicMock()
    mock_client.leer_todas_las_filas.return_value = [HEADERS_HISTORIAL]
    mock_client_class.return_value = mock_client

    h = HistorialPlacas("sheet-123")
    assert h.leer_todo() == {}


@patch("src.distribucion.historial.SheetsClient")
def test_leer_todo_devuelve_entradas(mock_client_class):
    mock_client = MagicMock()
    mock_client.leer_todas_las_filas.return_value = [
        HEADERS_HISTORIAL,
        ["SKU-1", "default_4x5", "4:5", "1000.00", "800.00",
         "https://cdn/1.png", "2026-05-24 06:00:00", "abc123"],
        ["SKU-2", "cuotas_4x5", "4:5", "2000.00", "1500.00",
         "https://cdn/2.png", "2026-05-24 06:00:00", "def456"],
    ]
    mock_client_class.return_value = mock_client

    h = HistorialPlacas("sheet-123")
    entradas = h.leer_todo()

    assert len(entradas) == 2
    assert entradas[("SKU-1", "default_4x5")].hash_render == "abc123"
    assert entradas[("SKU-1", "default_4x5")].precio_lista == 1000.0
    assert entradas[("SKU-2", "cuotas_4x5")].template == "cuotas_4x5"


@patch("src.distribucion.historial.SheetsClient")
def test_leer_todo_mismo_sku_dos_templates(mock_client_class):
    mock_client = MagicMock()
    mock_client.leer_todas_las_filas.return_value = [
        HEADERS_HISTORIAL,
        ["SKU-X", "default_4x5", "4:5", "1000", "800",
         "https://cdn/x.png", "2026", "hash4x5"],
        ["SKU-X", "default_9x16", "9:16", "1000", "800",
         "https://cdn/x_9x16.png", "2026", "hash9x16"],
    ]
    mock_client_class.return_value = mock_client

    h = HistorialPlacas("sheet-123")
    entradas = h.leer_todo()
    assert ("SKU-X", "default_4x5") in entradas
    assert ("SKU-X", "default_9x16") in entradas


@patch("src.distribucion.historial.SheetsClient")
def test_leer_todo_filas_sin_aspect_ratio_default_a_4_5(mock_client_class):
    headers_viejos = ["sku", "template", "precio_lista", "precio_promo",
                      "url_cloudinary", "fecha_render", "hash_render"]
    mock_client = MagicMock()
    mock_client.leer_todas_las_filas.return_value = [
        headers_viejos,
        ["SKU-OLD", "default_4x5", "1000", "800", "https://x", "2026", "abc"],
    ]
    mock_client_class.return_value = mock_client

    h = HistorialPlacas("sheet-123")
    entradas = h.leer_todo()
    assert ("SKU-OLD", "default_4x5") in entradas
    assert entradas[("SKU-OLD", "default_4x5")].aspect_ratio == "4:5"


@patch("src.distribucion.historial.SheetsClient")
def test_leer_todo_tolera_filas_corruptas(mock_client_class):
    mock_client = MagicMock()
    mock_client.leer_todas_las_filas.return_value = [
        HEADERS_HISTORIAL,
        ["SKU-1", "default_4x5", "4:5", "1000", "800", "https://x", "2026", "abc"],
        ["SKU-INCOMPLETO"],
        [],
        ["SKU-2", "default_4x5", "4:5", "1000", "800", "https://x", "2026", "xyz"],
    ]
    mock_client_class.return_value = mock_client

    h = HistorialPlacas("sheet-123")
    entradas = h.leer_todo()
    assert ("SKU-1", "default_4x5") in entradas
    assert ("SKU-2", "default_4x5") in entradas


@patch("src.distribucion.historial.SheetsClient")
def test_escribir_todo_replace_completo(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    h = HistorialPlacas("sheet-123")
    entradas = {
        ("SKU-1", "default_4x5"): EntradaHistorial(
            sku="SKU-1", template="default_4x5",
            precio_lista=1000.0, precio_promo=800.0,
            url_cloudinary="https://cdn/1.png",
            fecha_render="2026-05-24 06:00:00",
            hash_render="abc",
            aspect_ratio="4:5",
        ),
    }
    h.escribir_todo(entradas)

    mock_client.escribir_replace.assert_called_once()
    call = mock_client.escribir_replace.call_args
    headers = call[0][0]
    filas = call[0][1]

    assert headers == HEADERS_HISTORIAL
    assert len(filas) == 1
    assert filas[0][0] == "SKU-1"
    assert filas[0][1] == "default_4x5"
    assert filas[0][2] == "4:5"
    assert filas[0][3] == "1000.00"
