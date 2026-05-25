"""Tests del Bloque 3 (Enriquecimiento)."""
import json
from unittest.mock import patch, MagicMock
import urllib.error
import io
import pytest

from src.core.modelo_datos import Producto, Enriquecimiento
from src.enriquecimiento.base import ErrorEnriquecimiento
from src.enriquecimiento.gemini import (
    ConfigGemini,
    GeminiEnriquecimiento,
    _recortar,
    _validar_y_recortar,
    _construir_prompt,
    _extraer_json_de_respuesta,
)
from src.enriquecimiento.sheet_cache import (
    EntradaCacheEnriquecimiento,
    calcular_hash_input,
    enriquecimiento_a_entrada_cache,
    CacheEnriquecimiento,
    HEADERS_ENRIQUECIMIENTO,
)


def _producto(sku="A", nombre="Producto A", descripcion="desc", marca="Marca", categoria="cat"):
    return Producto(
        sku=sku, nombre=nombre, descripcion=descripcion,
        precio_lista=1000.0, precio_promocional=800.0,
        marca=marca, categoria=categoria,
        url_producto="https://x", imagen_url="https://x.jpg",
    )


# ============ _recortar ============

def test_recortar_no_recorta_si_alcanza():
    assert _recortar("hola mundo", 50) == "hola mundo"


def test_recortar_corta_en_espacio_si_posible():
    """Si el texto es más largo, corta en el último espacio razonable."""
    texto = "esta es una frase muy larga que necesita ser recortada"
    r = _recortar(texto, 25)
    assert len(r) <= 25
    assert not r.endswith(" ")
    # No debe cortar palabra a la mitad si hay un espacio razonable
    palabras_originales = texto.split()
    for palabra in r.split():
        assert palabra in palabras_originales


def test_recortar_corta_duro_si_no_hay_espacio_cercano():
    """Si no hay espacio cerca del límite (palabra muy larga), corta duro."""
    texto = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    r = _recortar(texto, 10)
    assert len(r) == 10


def test_recortar_prefiere_fin_de_oracion_sobre_espacio():
    """v3: si hay un punto antes del límite en zona razonable, corta ahí."""
    # 'Pesa 300g.' termina en el char 60. Límite 80. Después sigue cortando palabra.
    texto = "Sacaleche de silicona libre de BPA. Pesa 300g. Es compacto y fácil de usar."
    r = _recortar(texto, 50)
    # Debería cortar después de "BPA." (carácter 35), no a la mitad de la siguiente
    assert r.endswith(".")
    assert "Sacaleche de silicona libre de BPA." in r


def test_recortar_oracion_completa_no_se_recorta():
    """Si la primera oración entera entra y la segunda no, deja la primera."""
    texto = "Primera oración corta. Segunda oración que es mucho más larga y no entra."
    r = _recortar(texto, 30)
    assert r == "Primera oración corta."


def test_recortar_cae_a_espacio_si_no_hay_punto_cercano():
    """Sin punto razonable, sigue funcionando como antes: corta en espacio."""
    texto = "esta es una frase muy larga sin puntos que necesita ser recortada"
    r = _recortar(texto, 25)
    assert len(r) <= 25
    assert not r.endswith(" ")
    # No debe terminar a la mitad de una palabra
    palabras_originales = texto.split()
    for palabra in r.split():
        assert palabra in palabras_originales


# ============ _validar_y_recortar ============

def _cfg(max_titulo=60, max_desc=200, n_tips=3, max_tip=40):
    return ConfigGemini(
        api_key="fake", max_chars_titulo=max_titulo,
        max_chars_descripcion=max_desc,
        cantidad_tips=n_tips, max_chars_tip=max_tip,
    )


def test_validar_acepta_input_correcto():
    data = {
        "titulo_corto": "Horno eléctrico 30L",
        "descripcion_corta": "Horno ideal para casa, bajo consumo, fácil de usar.",
        "tips": ["Bajo consumo", "Ideal para casa", "Llevátelo donde quieras"],
    }
    titulo, desc, tips = _validar_y_recortar(data, _producto(), _cfg())
    assert titulo == "Horno eléctrico 30L"
    assert len(tips) == 3
    assert all(len(t) <= 40 for t in tips)


def test_validar_recorta_titulo_largo():
    data = {
        "titulo_corto": "X" * 200,
        "descripcion_corta": "ok",
        "tips": ["a", "b", "c"],
    }
    titulo, _, _ = _validar_y_recortar(data, _producto(), _cfg(max_titulo=60))
    assert len(titulo) <= 60


def test_validar_falla_si_titulo_vacio():
    data = {"titulo_corto": "", "descripcion_corta": "x", "tips": ["a", "b", "c"]}
    with pytest.raises(ErrorEnriquecimiento, match="titulo_corto"):
        _validar_y_recortar(data, _producto(), _cfg())


def test_validar_falla_si_faltan_tips():
    data = {
        "titulo_corto": "ok",
        "descripcion_corta": "ok",
        "tips": ["solo uno"],
    }
    with pytest.raises(ErrorEnriquecimiento, match="tips"):
        _validar_y_recortar(data, _producto(), _cfg(n_tips=3))


def test_validar_falla_si_tips_no_es_lista():
    data = {
        "titulo_corto": "ok",
        "descripcion_corta": "ok",
        "tips": "esto no es lista",
    }
    with pytest.raises(ErrorEnriquecimiento, match="tips"):
        _validar_y_recortar(data, _producto(), _cfg())


def test_validar_ignora_tips_vacios():
    """Si Gemini manda tips con strings vacíos en el medio, los filtra."""
    data = {
        "titulo_corto": "ok",
        "descripcion_corta": "ok",
        "tips": ["bueno", "", "  ", "otro bueno", "tercero"],
    }
    titulo, _, tips = _validar_y_recortar(data, _producto(), _cfg(n_tips=3))
    assert len(tips) == 3
    assert all(t.strip() for t in tips)


# ============ _construir_prompt ============

def test_prompt_incluye_datos_producto():
    p = _producto(nombre="Horno X", descripcion="Cocina rápido", marca="Acme")
    prompt = _construir_prompt(p, _cfg())
    assert "Horno X" in prompt
    assert "Cocina rápido" in prompt
    assert "Acme" in prompt


def test_prompt_incluye_tono():
    cfg = _cfg()
    cfg.tono = "Tono mexicano, usa 'tú' y 'ustedes'"
    prompt = _construir_prompt(_producto(), cfg)
    assert "mexicano" in prompt


def test_prompt_incluye_limites():
    cfg = _cfg(max_titulo=60, max_desc=200, n_tips=3, max_tip=40)
    prompt = _construir_prompt(_producto(), cfg)
    # v2 prompt usa los números directamente
    assert "60 caracteres" in prompt
    assert "200 caracteres" in prompt
    assert "40 chars" in prompt  # cambió formato
    assert "3 tips" in prompt


def test_prompt_v2_tiene_reglas_anti_cliches():
    """El prompt v2 debe prohibir exclamaciones y clichés explícitamente."""
    prompt = _construir_prompt(_producto(), _cfg())
    # Anti exclamaciones
    assert "CERO signos de exclamación" in prompt or "0 signos" in prompt or "sin exclamación" in prompt.lower()
    # Anti clichés
    assert "ideal para vos" in prompt.lower() or "es para vos" in prompt.lower()
    # Few-shot examples
    assert "Ejemplo" in prompt or "ejemplo" in prompt


# ============ _extraer_json_de_respuesta ============

def test_extraer_json_estructura_normal():
    """Estructura típica de respuesta de Gemini."""
    respuesta = {
        "candidates": [{
            "content": {
                "parts": [{"text": '{"titulo_corto": "ok"}'}],
            },
        }],
    }
    data = _extraer_json_de_respuesta(respuesta)
    assert data == {"titulo_corto": "ok"}


def test_extraer_json_falla_si_no_hay_candidates():
    """Caso edge: bloqueo de safety, contenido filtrado, etc."""
    with pytest.raises(ErrorEnriquecimiento, match="candidatos"):
        _extraer_json_de_respuesta({"candidates": []})


def test_extraer_json_falla_si_text_no_es_json():
    respuesta = {
        "candidates": [{
            "content": {"parts": [{"text": "esto no es JSON"}]},
        }],
    }
    with pytest.raises(ErrorEnriquecimiento, match="no es JSON"):
        _extraer_json_de_respuesta(respuesta)


# ============ GeminiEnriquecimiento (con mock) ============

def test_gemini_requiere_api_key():
    with pytest.raises(ErrorEnriquecimiento, match="api_key"):
        GeminiEnriquecimiento(ConfigGemini(api_key=""))


def test_gemini_nombre_incluye_modelo():
    g = GeminiEnriquecimiento(ConfigGemini(api_key="x", modelo="gemini-2.0-flash"))
    assert "gemini" in g.nombre()
    assert "2.0-flash" in g.nombre()


@patch("src.enriquecimiento.gemini.urllib.request.urlopen")
def test_gemini_enriquece_exitoso(mock_urlopen):
    """Happy path: Gemini responde con JSON válido, devolvemos Enriquecimiento."""
    respuesta_gemini = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": json.dumps({
                        "titulo_corto": "Horno 30L bajo consumo",
                        "descripcion_corta": "Horno eléctrico ideal para casa.",
                        "tips": ["Bajo consumo", "Ideal para casa", "Llevátelo donde quieras"],
                    }),
                }],
            },
        }],
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(respuesta_gemini).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    g = GeminiEnriquecimiento(ConfigGemini(api_key="x"))
    enr = g.enriquecer(_producto(nombre="Horno eléctrico"))

    assert isinstance(enr, Enriquecimiento)
    assert enr.titulo_corto == "Horno 30L bajo consumo"
    assert len(enr.tips) == 3
    assert enr.fallback_aplicado is False


@patch("src.enriquecimiento.gemini.urllib.request.urlopen")
def test_gemini_falla_4xx_no_reintenta(mock_urlopen):
    """Error 4xx (rate limit, key inválida) NO se reintenta, falla directo."""
    error_400 = urllib.error.HTTPError(
        "url", 400, "Bad Request", {}, io.BytesIO(b"invalid key"),
    )
    mock_urlopen.side_effect = error_400

    g = GeminiEnriquecimiento(ConfigGemini(api_key="x"))
    with pytest.raises(ErrorEnriquecimiento, match="400"):
        g.enriquecer(_producto())

    assert mock_urlopen.call_count == 1  # solo 1 intento, no reintenta


# ============ Cache ============

def test_hash_input_determinista():
    p = _producto()
    h1 = calcular_hash_input(p, "gemini:flash")
    h2 = calcular_hash_input(p, "gemini:flash")
    assert h1 == h2


def test_hash_input_cambia_con_nombre():
    p1 = _producto(nombre="A")
    p2 = _producto(nombre="B")
    assert calcular_hash_input(p1, "gemini:flash") != calcular_hash_input(p2, "gemini:flash")


def test_hash_input_cambia_con_descripcion():
    p1 = _producto(descripcion="vieja")
    p2 = _producto(descripcion="nueva")
    assert calcular_hash_input(p1, "gemini:flash") != calcular_hash_input(p2, "gemini:flash")


def test_hash_input_cambia_con_proveedor():
    """Si cambiamos de gemini a otro modelo, regenerar."""
    p = _producto()
    h1 = calcular_hash_input(p, "gemini:2.0-flash")
    h2 = calcular_hash_input(p, "gemini:2.0-pro")
    assert h1 != h2


def test_hash_input_no_cambia_con_precio():
    """El precio NO afecta el enriquecimiento (no impacta título/desc)."""
    p1 = _producto()
    p1.precio_lista = 1000
    p2 = _producto()
    p2.precio_lista = 2000
    assert calcular_hash_input(p1, "gemini:flash") == calcular_hash_input(p2, "gemini:flash")


@patch("src.enriquecimiento.sheet_cache.SheetsClient")
def test_cache_vacio_devuelve_dict_vacio(mock_client_class):
    mock_client = MagicMock()
    mock_client.leer_todas_las_filas.side_effect = Exception("no existe")
    mock_client_class.return_value = mock_client

    cache = CacheEnriquecimiento("sheet-x")
    assert cache.leer_todo() == {}


@patch("src.enriquecimiento.sheet_cache.SheetsClient")
def test_cache_lee_entradas_validas(mock_client_class):
    mock_client = MagicMock()
    mock_client.leer_todas_las_filas.return_value = [
        HEADERS_ENRIQUECIMIENTO,
        ["SKU-1", "abc123", "gemini:flash", "2026-05-24T10:00:00",
         "Mi título", "Mi descripción",
         '["tip1", "tip2", "tip3"]', "FALSE", ""],
    ]
    mock_client_class.return_value = mock_client

    cache = CacheEnriquecimiento("sheet-x")
    entradas = cache.leer_todo()

    assert "SKU-1" in entradas
    assert entradas["SKU-1"].titulo_corto == "Mi título"
    assert entradas["SKU-1"].tips == ["tip1", "tip2", "tip3"]


@patch("src.enriquecimiento.sheet_cache.SheetsClient")
def test_cache_tolera_tips_json_invalido(mock_client_class):
    """Si el JSON de tips se corrompe, devuelve lista vacía sin romper."""
    mock_client = MagicMock()
    mock_client.leer_todas_las_filas.return_value = [
        HEADERS_ENRIQUECIMIENTO,
        ["SKU-1", "abc", "gemini", "2026", "T", "D", "no es json", "FALSE", ""],
    ]
    mock_client_class.return_value = mock_client

    cache = CacheEnriquecimiento("sheet-x")
    entradas = cache.leer_todo()
    assert entradas["SKU-1"].tips == []


@patch("src.enriquecimiento.sheet_cache.SheetsClient")
def test_cache_escribe_replace(mock_client_class):
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    cache = CacheEnriquecimiento("sheet-x")
    entradas = {
        "SKU-1": EntradaCacheEnriquecimiento(
            sku="SKU-1", hash_input="abc", proveedor="gemini",
            generado_en="2026-05-24", titulo_corto="T", descripcion_corta="D",
            tips=["a", "b", "c"], fallback_aplicado=False, error="",
        ),
    }
    cache.escribir_todo(entradas)

    mock_client.escribir_replace.assert_called_once()
    call = mock_client.escribir_replace.call_args
    headers = call[0][0]
    filas = call[0][1]

    assert headers == HEADERS_ENRIQUECIMIENTO
    assert filas[0][0] == "SKU-1"
    assert filas[0][6] == '["a", "b", "c"]'  # tips_json
