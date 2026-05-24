"""Tests del módulo historial."""
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


def _decision(sku="A", template="default"):
    return DecisionSeleccion(sku=sku, generar=True, template=template)


def _templates_dir_con(default_html="<html>X</html>") -> Path:
    """Crea un dir temporal con default.html dentro."""
    d = Path(tempfile.mkdtemp())
    (d / "default.html").write_text(default_html, encoding="utf-8")
    return d


# ============ calcular_hash ============

def test_hash_determinista():
    """Mismo input → mismo hash."""
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
    """SKU cambia de template=default a template=electrohogar → hash diff."""
    td = _templates_dir_con()
    (td / "electrohogar.html").write_text("<html>Y</html>", encoding="utf-8")
    p = _producto()
    h1 = calcular_hash(p, _decision(template="default"), td)
    h2 = calcular_hash(p, _decision(template="electrohogar"), td)
    assert h1 != h2


def test_hash_cambia_si_cambia_contenido_html():
    """Esto es CLAVE: si editás default.html, el hash debe cambiar."""
    p, d = _producto(), _decision()
    td1 = _templates_dir_con(default_html="<html>VIEJO</html>")
    td2 = _templates_dir_con(default_html="<html>NUEVO</html>")
    h1 = calcular_hash(p, d, td1)
    h2 = calcular_hash(p, d, td2)
    assert h1 != h2


def test_hash_no_cambia_si_cambia_stock():
    """Stock NO afecta visualmente la placa → no debe regenerar."""
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
    """Si el template no existe, no rompe (hash con string vacío)."""
    td = Path(tempfile.mkdtemp())  # vacío
    p = _producto()
    d = _decision(template="no_existe")
    h = calcular_hash(p, d, td)
    assert isinstance(h, str) and len(h) == 16


# ============ HistorialPlacas: leer ============

@patch("src.distribucion.historial.SheetsClient")
def test_leer_todo_pestaña_vacia(mock_client_class):
    """Si la pestaña no existe, devuelve {}."""
    mock_client = MagicMock()
    mock_client.leer_todas_las_filas.side_effect = Exception("no existe")
    mock_client_class.return_value = mock_client

    h = HistorialPlacas("sheet-123")
    assert h.leer_todo() == {}


@patch("src.distribucion.historial.SheetsClient")
def test_leer_todo_solo_headers(mock_client_class):
    """Pestaña con solo headers → {}."""
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
        ["SKU-1", "default", "1000.00", "800.00", "https://cdn/1.png",
         "2026-05-24 06:00:00", "abc123"],
        ["SKU-2", "electrohogar", "2000.00", "1500.00", "https://cdn/2.png",
         "2026-05-24 06:00:00", "def456"],
    ]
    mock_client_class.return_value = mock_client

    h = HistorialPlacas("sheet-123")
    entradas = h.leer_todo()

    assert len(entradas) == 2
    assert entradas["SKU-1"].hash_render == "abc123"
    assert entradas["SKU-1"].precio_lista == 1000.0
    assert entradas["SKU-2"].template == "electrohogar"


@patch("src.distribucion.historial.SheetsClient")
def test_leer_todo_tolera_filas_corruptas(mock_client_class):
    """Si una fila tiene menos columnas, no rompe."""
    mock_client = MagicMock()
    mock_client.leer_todas_las_filas.return_value = [
        HEADERS_HISTORIAL,
        ["SKU-1", "default", "1000", "800", "https://x", "2026", "abc"],
        ["SKU-INCOMPLETO"],  # corrupta
        [],  # vacía
        ["SKU-2", "default", "1000", "800", "https://x", "2026", "xyz"],
    ]
    mock_client_class.return_value = mock_client

    h = HistorialPlacas("sheet-123")
    entradas = h.leer_todo()

    # Las 2 válidas se devuelven; las otras se ignoran sin error
    assert "SKU-1" in entradas
    assert "SKU-2" in entradas


# ============ HistorialPlacas: escribir ============

@patch("src.distribucion.historial.SheetsClient")
def test_escribir_todo_replace_completo(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    h = HistorialPlacas("sheet-123")
    entradas = {
        "SKU-1": EntradaHistorial(
            sku="SKU-1", template="default",
            precio_lista=1000.0, precio_promo=800.0,
            url_cloudinary="https://cdn/1.png",
            fecha_render="2026-05-24 06:00:00",
            hash_render="abc",
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
    assert filas[0][2] == "1000.00"  # precio formateado
