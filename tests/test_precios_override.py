"""Tests de src/inventario/precios_override.py (sin llamar a Sheets)."""
import pytest

from src.core.modelo_datos import Producto
from src.inventario.precios_override import (
    ConfigPreciosOverride,
    parsear_precio,
    construir_mapa,
    leer_precios_override,
    aplicar_precios_override,
)

CFG = ConfigPreciosOverride(sheet_id="x", pestaña="MAESTRA CYBER")
HEADERS = ["Temporada", "Modelo (Pablo)", "URL (handle TN)", "Nombre en TN",
           "Precio full", "Descuento", "Precio Cyber", "Generar"]


@pytest.mark.parametrize("entrada,esperado", [
    (153600, 153600.0),
    ("153600", 153600.0),
    ("$153.600", 153600.0),
    ("$ 153,600.00", 153600.0),
    ("153.600,50", 153600.5),
    ("1.234.567", 1234567.0),
    ("99,5", 99.5),
    ("", None),
    ("—", None),
    (None, None),
])
def test_parsear_precio(entrada, esperado):
    assert parsear_precio(entrada) == esperado


def test_construir_mapa_basico():
    filas = [
        HEADERS,
        ["VERANO 27", "ALONDRA", "alondra-cuero-negro-lt6m4", "SANDALIA", "176900", "20%", "141520", "TRUE"],
        ["VERANO 26", "Afrodita", "afrodita-cuero-negro", "AFRODITA", "$155.000", "50%", "$77.500", "TRUE"],
    ]
    mapa = construir_mapa(filas, CFG)
    assert mapa == {
        "alondra-cuero-negro-lt6m4": (176900.0, 141520.0),
        "afrodita-cuero-negro": (155000.0, 77500.0),
    }


def test_construir_mapa_ignora_filas_invalidas():
    filas = [
        HEADERS,
        ["", "", "", "", "100", "", "50", ""],               # sin sku
        ["", "", "sin-precio", "", "", "", "50", ""],        # sin lista
        ["", "", "promo-mayor", "", "100", "", "150", ""],   # promo > lista
        ["", "", "corta"],                                    # fila corta
        ["", "", "ok", "", "100", "", "80", ""],
    ]
    assert construir_mapa(filas, CFG) == {"ok": (100.0, 80.0)}


def test_construir_mapa_vacio():
    assert construir_mapa([], CFG) == {}


def test_construir_mapa_falla_si_faltan_columnas():
    with pytest.raises(ValueError, match="Precio Cyber"):
        construir_mapa([["URL (handle TN)", "Precio full"]], CFG)


def test_columnas_configurables():
    cfg = ConfigPreciosOverride(sheet_id="x", pestaña="p", col_sku="sku",
                                col_precio_lista="lista", col_precio_promo="promo")
    assert construir_mapa([["sku", "lista", "promo"], ["a", "10", "8"]], cfg) == {"a": (10.0, 8.0)}


def test_leer_precios_override_con_lector_inyectado():
    filas = [HEADERS, ["", "", "a", "", "200", "", "100", ""]]
    assert leer_precios_override(CFG, leer_filas=lambda: filas) == {"a": (200.0, 100.0)}


def test_aplicar_precios_override():
    productos = [
        Producto(sku="a", nombre="A", precio_lista=176900, precio_promocional=None),
        Producto(sku="b", nombre="B", precio_lista=99000, precio_promocional=70000),
    ]
    n = aplicar_precios_override(productos, {"a": (176900.0, 141520.0), "zzz": (1.0, 1.0)})
    assert n == 1
    assert productos[0].precio_lista == 176900.0
    assert productos[0].precio_promocional == 141520.0
    assert productos[0].tiene_promo and productos[0].precio_efectivo == 141520.0
    # El que no está en la planilla conserva los precios de TN
    assert (productos[1].precio_lista, productos[1].precio_promocional) == (99000, 70000)
