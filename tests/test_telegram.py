"""Tests del notifier Telegram."""
from unittest.mock import patch, MagicMock
import urllib.error

from src.distribucion.telegram_notifier import (
    notificar,
    formatear_resumen_exito,
    formatear_resumen_falla,
    _enviar_telegram,
)


# ============ Formatters ============

def test_resumen_exito_basico():
    msg = formatear_resumen_exito(
        cliente="morashop",
        fecha_iso="2026-05-24 06:00",
        duracion_segundos=134,
        inventario=247,
        seleccionados=38,
        placas_regeneradas=3,
        placas_reusadas=35,
        feeds_resumen={"Meta_default": 30, "TikTok_default": 30},
        skus_regenerados=["A", "B", "C"],
        motivos_regeneracion={
            "A": "precio: $8.500 → $7.999",
            "B": "nuevo",
            "C": "template cambió",
        },
    )

    assert "✅" in msg
    assert "morashop" in msg
    assert "247" in msg
    assert "Meta_default" in msg
    assert "$8.500 → $7.999" in msg
    assert "2m 14s" in msg


def test_resumen_exito_trunca_lista_larga_de_skus():
    """Si hay más de 10 SKUs regenerados, los recorta."""
    skus = [f"SKU-{i}" for i in range(15)]
    msg = formatear_resumen_exito(
        cliente="test", fecha_iso="now", duracion_segundos=10,
        inventario=15, seleccionados=15,
        placas_regeneradas=15, placas_reusadas=0,
        feeds_resumen={}, skus_regenerados=skus,
    )
    # "...y 5 más"
    assert "5 más" in msg


def test_resumen_exito_sin_regenerados():
    """Caso ideal: todo reusado, mensaje corto."""
    msg = formatear_resumen_exito(
        cliente="morashop", fecha_iso="now", duracion_segundos=60,
        inventario=10, seleccionados=10,
        placas_regeneradas=0, placas_reusadas=10,
        feeds_resumen={"Meta_default": 10},
        skus_regenerados=[],
    )
    assert "0" in msg
    # No debería incluir la sección "SKUs regenerados" si está vacía
    assert "🔄 SKUs regenerados:" not in msg


def test_resumen_falla_basico():
    msg = formatear_resumen_falla(
        cliente="morashop",
        fecha_iso="2026-05-24 06:00",
        error_msg="ConnectionError: timeout",
        bloque="5.1 Storage",
        url_run="https://github.com/x/runs/123",
    )
    assert "❌" in msg
    assert "ConnectionError" in msg
    assert "5.1 Storage" in msg
    assert "https://github.com" in msg


def test_resumen_falla_trunca_error_largo():
    error_largo = "X" * 1000
    msg = formatear_resumen_falla(
        cliente="t", fecha_iso="now", error_msg=error_largo,
    )
    # 300 chars max
    assert msg.count("X") <= 300


# ============ notificar() ============

@patch("src.distribucion.telegram_notifier._enviar_telegram")
def test_notificar_sin_credenciales_no_falla(mock_enviar, monkeypatch):
    """Si faltan credenciales, no envía nada pero NO tira excepción."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    notificar("hola")  # no debe raisear

    mock_enviar.assert_not_called()


@patch("src.distribucion.telegram_notifier._enviar_telegram")
def test_notificar_con_credenciales_llama_a_enviar(mock_enviar, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOKEN-X")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    mock_enviar.return_value = True

    notificar("hola")

    mock_enviar.assert_called_once_with("TOKEN-X", "12345", "hola")


@patch("src.distribucion.telegram_notifier._enviar_telegram")
def test_notificar_si_envio_falla_no_tira_excepcion(mock_enviar, monkeypatch):
    """Telegram caído ≠ pipeline rojo."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "TOKEN-X")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    mock_enviar.return_value = False

    # No debe raisear
    notificar("hola")


# ============ _enviar_telegram() ============

@patch("src.distribucion.telegram_notifier.urllib.request.urlopen")
def test_enviar_telegram_exitoso(mock_urlopen):
    """Caso happy path: API responde ok=true."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"ok": true, "result": {}}'
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    ok = _enviar_telegram("token", "chat", "msg")
    assert ok is True


@patch("src.distribucion.telegram_notifier.urllib.request.urlopen")
def test_enviar_telegram_reintenta_sin_markdown_si_400(mock_urlopen):
    """Si Markdown falla con 400, reintenta sin parse_mode."""
    # Primer call: 400. Segundo: OK.
    error_400 = urllib.error.HTTPError(
        "url", 400, "Bad Request", {}, MagicMock(read=lambda: b"bad markdown"),
    )

    mock_resp_ok = MagicMock()
    mock_resp_ok.read.return_value = b'{"ok": true}'

    mock_urlopen.side_effect = [
        error_400,
        MagicMock(__enter__=lambda s: mock_resp_ok, __exit__=lambda *a: None),
    ]

    ok = _enviar_telegram("token", "chat", "msg *malo")
    assert ok is True
    assert mock_urlopen.call_count == 2


# ============ Sección huérfanos (Fase H) ============

def test_resumen_exito_sin_huerfanos_no_muestra_seccion():
    """Si no hay huérfanos, no aparece la sección 🗑️"""
    msg = formatear_resumen_exito(
        cliente="m", fecha_iso="x", duracion_segundos=60,
        inventario=10, seleccionados=10,
        placas_regeneradas=0, placas_reusadas=10,
        feeds_resumen={"Meta_default": 10},
        skus_regenerados=[],
        skus_huerfanos_borrados=[],
        skus_huerfanos_fallidos=[],
    )
    assert "🗑️" not in msg
    assert "huérfanos" not in msg


def test_resumen_exito_con_huerfanos_muestra_seccion():
    msg = formatear_resumen_exito(
        cliente="m", fecha_iso="x", duracion_segundos=60,
        inventario=10, seleccionados=10,
        placas_regeneradas=0, placas_reusadas=10,
        feeds_resumen={},
        skus_regenerados=[],
        skus_huerfanos_borrados=["SKU-1", "SKU-2", "SKU-3"],
        skus_huerfanos_fallidos=[],
    )
    assert "🗑️" in msg
    assert "3" in msg
    assert "SKU-1" in msg


def test_resumen_exito_huerfanos_trunca_lista_larga():
    """Si hay más de 5 huérfanos OK, los recorta."""
    skus = [f"X-{i}" for i in range(10)]
    msg = formatear_resumen_exito(
        cliente="m", fecha_iso="x", duracion_segundos=60,
        inventario=10, seleccionados=10,
        placas_regeneradas=0, placas_reusadas=10,
        feeds_resumen={},
        skus_regenerados=[],
        skus_huerfanos_borrados=skus,
        skus_huerfanos_fallidos=[],
    )
    assert "5 más" in msg


def test_resumen_exito_huerfanos_fallidos_warning():
    """Si algunos huérfanos no se pudieron borrar, lo marca con ⚠️"""
    msg = formatear_resumen_exito(
        cliente="m", fecha_iso="x", duracion_segundos=60,
        inventario=10, seleccionados=10,
        placas_regeneradas=0, placas_reusadas=10,
        feeds_resumen={},
        skus_regenerados=[],
        skus_huerfanos_borrados=["SKU-OK"],
        skus_huerfanos_fallidos=["SKU-FALLO"],
    )
    assert "⚠️" in msg
    assert "SKU-FALLO" in msg
