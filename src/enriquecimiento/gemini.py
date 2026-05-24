"""Enriquecimiento con Gemini (Google AI Studio).

Modelo por default: gemini-2.0-flash. Devuelve JSON con titulo_corto,
descripcion_corta y tips. Tono argentino (vos/tuyo).

Diseño:
- Usa la API REST de Gemini directamente con urllib (sin SDK extra).
- response_mime_type=application/json para forzar JSON parseable.
- Si Gemini devuelve algo que no se puede parsear → ErrorEnriquecimiento.
- 1 reintento con backoff si hay error de red (no si es 4xx).
"""
from __future__ import annotations
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from src.core.modelo_datos import Producto, Enriquecimiento
from src.enriquecimiento.base import FuenteEnriquecimiento, ErrorEnriquecimiento


log = logging.getLogger(__name__)


# Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


@dataclass
class ConfigGemini:
    """Config del proveedor Gemini."""
    api_key: str
    modelo: str = "gemini-2.0-flash"
    max_chars_titulo: int = 60
    max_chars_descripcion: int = 200
    cantidad_tips: int = 3
    max_chars_tip: int = 40
    timeout_segundos: int = 30
    # Tono se inyecta al prompt. Lo dejamos configurable por cliente.
    tono: str = (
        "Argentino. Usa voseo cuando corresponda (ej: 'llevátelo', 'es para vos'). "
        "Lenguaje natural, sin extranjerismos innecesarios."
    )


def _construir_prompt(producto: Producto, cfg: ConfigGemini) -> str:
    """Prompt que le pedimos a Gemini.

    Le damos contexto del producto y le pedimos JSON con campos fijos.
    Importante: usamos respuesta forzada JSON (response_mime_type) además
    del prompt, así que aunque divague va a devolver JSON parseable.
    """
    return f"""Sos un experto en marketing digital y copy para e-commerce.
Generá metadata optimizada para Meta Ads y TikTok Ads para este producto.

Tono: {cfg.tono}

Producto:
- Nombre: {producto.nombre}
- Descripción: {producto.descripcion or "(sin descripción)"}
- Marca: {producto.marca or "(sin marca)"}
- Categoría: {producto.categoria or "(sin categoría)"}

Devolvé un JSON con esta estructura exacta:
{{
  "titulo_corto": "string máximo {cfg.max_chars_titulo} caracteres, claro y conciso, destacar lo principal",
  "descripcion_corta": "string máximo {cfg.max_chars_descripcion} caracteres, descriptiva y persuasiva",
  "tips": ["tip 1", "tip 2", "tip 3"]
}}

Reglas para los tips:
- Exactamente {cfg.cantidad_tips} tips
- Cada tip máximo {cfg.max_chars_tip} caracteres
- Cortos, punchy, destacan un beneficio concreto
- Ejemplos de buen tip: "Bajo consumo", "Ideal para casa", "Llevátelo a todos lados"
- NO uses jerga publicitaria genérica ("la mejor calidad", "increíble")
- Cada tip debe resaltar UN beneficio específico distinto del producto

Reglas generales:
- Respondé SOLO el JSON, sin texto adicional, sin markdown, sin ```
- Respetá ESTRICTAMENTE los límites de caracteres
- Si el producto tiene poca info, usá lo que tengas con criterio"""


def _llamar_gemini(cfg: ConfigGemini, prompt: str) -> dict:
    """Llama a la API de Gemini y devuelve el JSON parseado.

    Raises:
        ErrorEnriquecimiento si falla el request, el parseo, o el formato.
    """
    url = f"{GEMINI_API_BASE}/{cfg.modelo}:generateContent?key={cfg.api_key}"

    payload = {
        "contents": [{
            "parts": [{"text": prompt}],
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.7,  # balance entre creatividad y consistencia
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
    )

    # 1 reintento con backoff exponencial si hay error de red
    for intento in range(2):
        try:
            with urllib.request.urlopen(req, timeout=cfg.timeout_segundos) as resp:
                respuesta = json.loads(resp.read().decode("utf-8"))
                return _extraer_json_de_respuesta(respuesta)
        except urllib.error.HTTPError as e:
            # 4xx no se reintenta; 5xx sí
            body = e.read().decode("utf-8", errors="replace")
            if e.code < 500:
                raise ErrorEnriquecimiento(
                    f"Gemini HTTP {e.code}: {body[:300]}"
                )
            if intento == 0:
                log.warning("Gemini 5xx, reintentando en 2s...")
                time.sleep(2)
                continue
            raise ErrorEnriquecimiento(f"Gemini HTTP {e.code} persistente: {body[:300]}")
        except urllib.error.URLError as e:
            if intento == 0:
                log.warning("Gemini network error, reintentando en 2s... (%s)", e)
                time.sleep(2)
                continue
            raise ErrorEnriquecimiento(f"Gemini network error: {e}")
        except json.JSONDecodeError as e:
            raise ErrorEnriquecimiento(f"Gemini devolvió JSON inválido: {e}")

    # Nunca debería llegar acá
    raise ErrorEnriquecimiento("Gemini: lógica de reintento agotada sin resolución")


def _extraer_json_de_respuesta(respuesta: dict) -> dict:
    """De la respuesta cruda de Gemini, extraer el JSON que generó.

    Estructura típica:
    {
      "candidates": [{
        "content": {
          "parts": [{"text": "{\"titulo_corto\": \"...\", ...}"}]
        }
      }]
    }
    """
    try:
        text = respuesta["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise ErrorEnriquecimiento(
            f"Gemini: respuesta sin candidatos válidos: {respuesta}"
        ) from e

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ErrorEnriquecimiento(
            f"Gemini: el texto generado no es JSON: {text[:300]}"
        ) from e


def _validar_y_recortar(
    data: dict, producto: Producto, cfg: ConfigGemini,
) -> tuple[str, str, list[str]]:
    """Valida la estructura y aplica los recortes de chars duros.

    Si Gemini se pasa del límite (suele pasar), recortamos en el último
    espacio antes del límite para no cortar palabras a la mitad.
    """
    titulo = data.get("titulo_corto", "")
    descripcion = data.get("descripcion_corta", "")
    tips = data.get("tips", [])

    if not isinstance(titulo, str) or not titulo.strip():
        raise ErrorEnriquecimiento(f"titulo_corto vacío o inválido para {producto.sku}")
    if not isinstance(descripcion, str):
        raise ErrorEnriquecimiento(f"descripcion_corta inválida para {producto.sku}")
    if not isinstance(tips, list):
        raise ErrorEnriquecimiento(f"tips no es lista para {producto.sku}")

    titulo = _recortar(titulo.strip(), cfg.max_chars_titulo)
    descripcion = _recortar(descripcion.strip(), cfg.max_chars_descripcion)

    # Tips: validar cantidad y recortar
    tips_limpios = []
    for t in tips:
        if not isinstance(t, str) or not t.strip():
            continue
        tips_limpios.append(_recortar(t.strip(), cfg.max_chars_tip))

    if len(tips_limpios) < cfg.cantidad_tips:
        # Si Gemini no generó suficientes tips, fallamos. El SKU queda fuera.
        raise ErrorEnriquecimiento(
            f"Gemini devolvió {len(tips_limpios)} tips, esperaba {cfg.cantidad_tips} para {producto.sku}"
        )

    return titulo, descripcion, tips_limpios[:cfg.cantidad_tips]


def _recortar(texto: str, max_chars: int) -> str:
    """Recorta texto al último espacio antes del límite. Si no hay, corta duro."""
    if len(texto) <= max_chars:
        return texto
    # Buscar el último espacio para no cortar palabras
    recortado = texto[:max_chars]
    ultimo_espacio = recortado.rfind(" ")
    if ultimo_espacio > max_chars * 0.7:  # si el espacio está en un lugar razonable
        return recortado[:ultimo_espacio].rstrip()
    return recortado.rstrip()


class GeminiEnriquecimiento(FuenteEnriquecimiento):
    """Proveedor de enriquecimiento usando Gemini."""

    def __init__(self, config: ConfigGemini):
        if not config.api_key:
            raise ErrorEnriquecimiento("ConfigGemini.api_key es obligatorio")
        self.cfg = config

    def nombre(self) -> str:
        return f"gemini:{self.cfg.modelo}"

    def enriquecer(self, producto: Producto) -> Enriquecimiento:
        prompt = _construir_prompt(producto, self.cfg)
        data = _llamar_gemini(self.cfg, prompt)
        titulo, descripcion, tips = _validar_y_recortar(data, producto, self.cfg)

        return Enriquecimiento(
            sku=producto.sku,
            hash_input="",  # lo setea sheet_cache después
            proveedor=self.nombre(),
            generado_en=datetime.now(),
            titulo_corto=titulo,
            descripcion_corta=descripcion,
            tips=tips,
            slogan="",  # no lo generamos por ahora
            categoria_inferida="",  # no lo generamos por ahora
            fallback_aplicado=False,
            error="",
        )
