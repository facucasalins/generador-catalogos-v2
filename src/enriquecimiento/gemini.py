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
    """Prompt v2 (más estricto, sin exclamaciones, sin clichés).

    Reglas duras para evitar los patrones malos detectados en v1:
    - 0 signos de exclamación
    - Sin clichés publicitarios genéricos
    - Priorizar hechos (litros, watts, materiales) sobre adjetivos
    - Tips distintos del título y descripción
    - Sin info comercial (cuotas, envío, descuentos)
    - Few-shot examples (bueno + malo) para anclar el estilo
    """
    return f"""Sos copywriter senior especializado en e-commerce argentino. Generás metadata
optimizada para Meta Ads y TikTok Ads.

Tono: {cfg.tono}

REGLAS DURAS (no negociables):

1. CERO signos de exclamación (¡ o !). Lenguaje sobrio, profesional.

2. CERO clichés publicitarios. Frases prohibidas (no usar nunca):
   - "ideal para vos" / "es para vos" / "pensado para vos"
   - "al siguiente nivel" / "máxima calidad" / "calidad superior"
   - "tu mejor aliado" / "el mejor del mercado"
   - "no te lo pierdas" / "aprovechalo"
   - "diseñado para vos" / "hecho para vos"
   - Adjetivos vagos solos: "increíble", "fantástico", "espectacular"

3. PRIORIZAR HECHOS sobre adjetivos. Si el producto tiene:
   - capacidad (litros, kg, ml), potencia (W), medidas → INCLUILA
   - materiales (acero, silicona, plástico) → INCLUILOS si son relevantes
   - cantidad de partes/accesorios incluidos → MENCIONALA
   - certificaciones (sin BPA, libre de gluten) → DESTACALA
   Preferí "Horno 45L con convección" sobre "Horno potente y versátil".

4. NO incluyas info comercial: envío, cuotas, descuentos, transferencia,
   precios, marca. Eso lo agrega Meta automáticamente del feed.

5. LOS TIPS NO REPITEN el título ni la descripción. Cada tip debe agregar
   info que NO está en los otros dos campos.

6. Cada tip resalta UN beneficio CONCRETO y DISTINTO. Nada de "más fuerza
   y resistencia" (vago). Sí "Recuperación en 24hs" (concreto).

Producto:
- Nombre: {producto.nombre}
- Descripción: {producto.descripcion or "(sin descripción)"}
- Marca: {producto.marca or "(sin marca)"}
- Categoría: {producto.categoria or "(sin categoría)"}

EJEMPLOS DE BUEN OUTPUT:

Ejemplo 1 (parlante bluetooth portátil):
{{
  "titulo_corto": "Parlante bluetooth 20W con 12hs de batería",
  "descripcion_corta": "Sonido envolvente con 20W de potencia y resistencia al agua IPX7. Conexión bluetooth 5.0 estable hasta 10 metros. Batería de 4000 mAh para 12 horas continuas.",
  "tips": ["Resistente al agua IPX7", "12 horas de batería", "Conecta dos parlantes"]
}}

Ejemplo 2 (zapatillas running):
{{
  "titulo_corto": "Zapatillas running con amortiguación EVA",
  "descripcion_corta": "Suela de EVA inyectada para reducir el impacto en cada pisada. Upper de mesh transpirable y refuerzo lateral. Drop de 8mm pensado para correr 5K a 21K.",
  "tips": ["Drop 8mm para correr largo", "Mesh que ventila el pie", "Suela antideslizante"]
}}

EJEMPLOS DE MAL OUTPUT (NUNCA hagas esto):

Mal 1: "¡Las mejores zapatillas para vos! ¡Calidad premium al siguiente nivel!"
  → Demasiadas exclamaciones, clichés, sin info concreta.

Mal 2: tips=["Excelente calidad", "Lo vas a amar", "Aprovechá la oferta"]
  → Vacíos, genéricos, mencionan oferta (info comercial).

FORMATO DE RESPUESTA:

Devolvé SOLO un JSON con esta estructura. Sin markdown, sin ``` , sin texto extra:
{{
  "titulo_corto": "máximo {cfg.max_chars_titulo} caracteres",
  "descripcion_corta": "máximo {cfg.max_chars_descripcion} caracteres",
  "tips": [
    "tip 1 (máx {cfg.max_chars_tip} chars)",
    "tip 2 (máx {cfg.max_chars_tip} chars)",
    "tip 3 (máx {cfg.max_chars_tip} chars)"
  ]
}}

Exactamente {cfg.cantidad_tips} tips. Si el producto tiene poca info, hacé
lo mejor posible con lo que tengas — pero respetá todas las reglas."""


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
