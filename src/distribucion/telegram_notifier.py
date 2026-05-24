"""Notificaciones por Telegram.

Manda mensajes al chat configurado vía API HTTP de Telegram.
No requiere librerías externas: usa urllib estándar.

Si TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no están seteados, NO falla:
solo logea un warning y sigue. La notificación es un nice-to-have.
"""
from __future__ import annotations
import json
import logging
import os
import urllib.parse
import urllib.request
import urllib.error

log = logging.getLogger(__name__)


def _enviar_telegram(bot_token: str, chat_id: str, mensaje: str) -> bool:
    """Manda un mensaje al chat. Devuelve True si OK, False si falló.

    Usa parse_mode=Markdown para formato. Si Markdown falla (caracteres
    raros en el mensaje), reintenta sin parse_mode.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    for parse_mode in ("Markdown", None):
        data = {
            "chat_id": chat_id,
            "text": mensaje,
            "disable_web_page_preview": "true",
        }
        if parse_mode:
            data["parse_mode"] = parse_mode

        encoded = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(url, data=encoded)

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if payload.get("ok"):
                    return True
                log.warning(
                    "Telegram respondió ok=false (parse_mode=%s): %s",
                    parse_mode, payload,
                )
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            log.warning(
                "Telegram HTTPError %s (parse_mode=%s): %s",
                e.code, parse_mode, body,
            )
            # Si fue 400 por parsing de Markdown, reintenta sin parse_mode
            if e.code == 400 and parse_mode == "Markdown":
                continue
            return False
        except Exception as e:
            log.warning("Telegram falló (parse_mode=%s): %s", parse_mode, e)
            return False

    return False


def notificar(mensaje: str) -> None:
    """Punto de entrada principal. Lee credenciales del env y manda mensaje.

    Si falta alguna credencial, solo logea warning. NUNCA tira excepción
    (no queremos que un fallo de Telegram rompa el pipeline).
    """
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        log.warning(
            "Telegram no configurado (faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID). "
            "Mensaje no enviado."
        )
        return

    if _enviar_telegram(bot_token, chat_id, mensaje):
        log.info("Telegram: mensaje enviado")
    else:
        log.warning("Telegram: el mensaje NO se envió, sigue el pipeline")


# ============ Helpers para armar mensajes ============

def formatear_resumen_exito(
    cliente: str,
    fecha_iso: str,
    duracion_segundos: float,
    inventario: int,
    seleccionados: int,
    placas_regeneradas: int,
    placas_reusadas: int,
    feeds_resumen: dict[str, int],
    skus_regenerados: list[str],
    motivos_regeneracion: dict[str, str] | None = None,
) -> str:
    """Arma el mensaje de éxito para Telegram (formato Markdown).

    Args:
        feeds_resumen: {nombre_pestaña: cantidad_filas}
        skus_regenerados: lista de SKUs que se re-renderizaron
        motivos_regeneracion: {sku: "precio: $8500 → $7999"} (opcional)
    """
    duracion = f"{int(duracion_segundos // 60)}m {int(duracion_segundos % 60)}s"

    lineas = [
        f"✅ *{cliente}* - Run diario OK",
        f"_{fecha_iso}_",
        "",
        f"📦 Inventario: *{inventario}* productos",
        f"✓ Seleccionados: *{seleccionados}* SKUs",
        "",
        "🎨 Placas:",
        f"  • *{placas_regeneradas}* regeneradas",
        f"  • *{placas_reusadas}* reusadas",
    ]

    if feeds_resumen:
        lineas.append("")
        lineas.append("📤 Feeds:")
        for pestaña, n in sorted(feeds_resumen.items()):
            lineas.append(f"  • `{pestaña}`: {n}")

    if skus_regenerados:
        lineas.append("")
        lineas.append("🔄 SKUs regenerados:")
        # Mostramos máximo 10, después truncamos
        max_mostrar = 10
        for sku in skus_regenerados[:max_mostrar]:
            motivo = motivos_regeneracion.get(sku, "") if motivos_regeneracion else ""
            if motivo:
                lineas.append(f"  - `{sku}`: {motivo}")
            else:
                lineas.append(f"  - `{sku}`")
        if len(skus_regenerados) > max_mostrar:
            lineas.append(f"  _...y {len(skus_regenerados) - max_mostrar} más_")

    lineas.append("")
    lineas.append(f"⏱️ {duracion}")

    return "\n".join(lineas)


def formatear_resumen_falla(
    cliente: str,
    fecha_iso: str,
    error_msg: str,
    bloque: str = "?",
    url_run: str = "",
) -> str:
    """Arma el mensaje de falla para Telegram (formato Markdown)."""
    lineas = [
        f"❌ *{cliente}* - Run FALLÓ",
        f"_{fecha_iso}_",
        "",
        f"*Bloque:* {bloque}",
        f"*Error:* `{error_msg[:300]}`",  # truncamos por las dudas
    ]
    if url_run:
        lineas.append("")
        lineas.append(f"🔗 [Ver detalles]({url_run})")
    return "\n".join(lineas)
