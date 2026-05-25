"""Historial de placas renderizadas.

Persiste en Google Sheets (pestaña Historial_Placas) los metadatos de
cada placa generada: precios, URL en Cloudinary, hash de inputs.

El hash permite saber si un SKU necesita regenerarse:
- Hash diferente al guardado → algún input cambió → regenerar
- Hash igual → reusar URL existente

Diseño:
- 1 fila por SKU. Se sobrescribe al regenerar.
- El hash incluye el contenido del HTML del template, así si el archivo
  HTML cambia (vos lo editás y commiteás), todos los SKUs que usaban
  ese template se regeneran al próximo run.
"""
from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.modelo_datos import Producto, DecisionSeleccion
from src.core.sheets_client import ConfigSheets, SheetsClient


log = logging.getLogger(__name__)


PESTAÑA_HISTORIAL = "Historial_Placas"
HEADERS_HISTORIAL = [
    "sku",
    "template",
    "aspect_ratio",  # NUEVO Fase H: "4:5" Meta, "9:16" TikTok
    "precio_lista",
    "precio_promo",
    "url_cloudinary",
    "fecha_render",
    "hash_render",
]


@dataclass
class EntradaHistorial:
    """Una fila del historial."""
    sku: str
    template: str
    precio_lista: float
    precio_promo: float
    url_cloudinary: str
    fecha_render: str  # ISO format
    hash_render: str
    aspect_ratio: str = "4:5"  # default para retrocompat con filas viejas


def _leer_template_html(templates_dir: Path, template_name: str) -> str:
    """Lee el contenido crudo del template para incluirlo en el hash.

    Si el archivo no existe, devuelve string vacío (mejor regenerar que
    fallar; Bloque 4 va a validar la existencia del template).
    """
    path = templates_dir / f"{template_name}.html"
    if not path.exists():
        log.warning("Template '%s' no existe, hash usará string vacío", path)
        return ""
    return path.read_text(encoding="utf-8")


def calcular_hash(
    producto: Producto,
    decision: DecisionSeleccion,
    templates_dir: Path,
    template_name: str | None = None,
    aspect_ratio: str = "4:5",
) -> str:
    """Calcula hash que cambia si cualquier input visual cambia.

    Incluye: precios, nombre, descripción, marca, URL imagen, template
    asignado, el CONTENIDO del HTML del template, y el aspect_ratio.

    Args:
        template_name: si se pasa, se usa para leer el HTML (para soportar
            templates _tiktok que difieren del decision.template). Si es None,
            usa decision.template como antes.
        aspect_ratio: "4:5" o "9:16". Cambiarlo invalida el hash, así que la
            placa 4:5 y la 9:16 se trackean por separado.
    """
    nombre_template = template_name or decision.template
    template_html = _leer_template_html(templates_dir, nombre_template)
    partes = [
        producto.sku,
        nombre_template,
        aspect_ratio,
        f"{producto.precio_lista:.2f}",
        f"{producto.precio_promocional:.2f}" if producto.precio_promocional else "",
        producto.nombre or "",
        producto.descripcion or "",
        producto.marca or "",
        producto.imagen_url or "",
        template_html,
    ]
    blob = "||".join(partes).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


class HistorialPlacas:
    """Lee y escribe el historial en una pestaña dedicada del sheet."""

    def __init__(self, sheet_id: str):
        self.client = SheetsClient(ConfigSheets(
            sheet_id=sheet_id, pestaña=PESTAÑA_HISTORIAL,
        ))

    def leer_todo(self) -> dict[tuple[str, str], EntradaHistorial]:
        """Devuelve {(sku, aspect_ratio): EntradaHistorial}.

        Clave compuesta porque un SKU puede tener varias placas (4:5 para
        Meta, 9:16 para TikTok). Si la pestaña no existe, dict vacío.

        Filas viejas sin columna `aspect_ratio` se interpretan como 4:5
        (retrocompat con historial pre-Fase H).
        """
        try:
            filas = self.client.leer_todas_las_filas()
        except Exception as e:
            log.info("Pestaña Historial_Placas vacía o inexistente (%s)", e)
            return {}

        if not filas or len(filas) < 2:
            return {}

        header = filas[0]
        rows = filas[1:]

        idx = {col: i for i, col in enumerate(header)}
        requeridos = {"sku", "template", "url_cloudinary", "hash_render"}
        faltantes = requeridos - set(idx.keys())
        if faltantes:
            log.warning("Historial: faltan columnas %s, se ignora", faltantes)
            return {}

        resultado: dict[tuple[str, str], EntradaHistorial] = {}
        for fila in rows:
            if not fila or len(fila) <= idx["sku"]:
                continue
            sku = fila[idx["sku"]].strip()
            if not sku:
                continue
            try:
                # aspect_ratio: si la columna no existe (historial viejo)
                # o está vacía, default a "4:5"
                aspect_ratio = "4:5"
                ar_idx = idx.get("aspect_ratio", -1)
                if 0 <= ar_idx < len(fila):
                    valor = fila[ar_idx].strip()
                    if valor:
                        aspect_ratio = valor

                entrada = EntradaHistorial(
                    sku=sku,
                    template=fila[idx["template"]] if idx["template"] < len(fila) else "",
                    precio_lista=_a_float(fila[idx.get("precio_lista", -1)]) if idx.get("precio_lista", -1) < len(fila) else 0.0,
                    precio_promo=_a_float(fila[idx.get("precio_promo", -1)]) if idx.get("precio_promo", -1) < len(fila) else 0.0,
                    url_cloudinary=fila[idx["url_cloudinary"]] if idx["url_cloudinary"] < len(fila) else "",
                    fecha_render=fila[idx.get("fecha_render", -1)] if idx.get("fecha_render", -1) < len(fila) else "",
                    hash_render=fila[idx["hash_render"]] if idx["hash_render"] < len(fila) else "",
                    aspect_ratio=aspect_ratio,
                )
                resultado[(sku, aspect_ratio)] = entrada
            except (IndexError, ValueError) as e:
                log.warning("Fila inválida en Historial_Placas para sku=%s: %s", sku, e)
                continue

        log.info("Historial cargado: %d entradas (SKU × aspect_ratio)", len(resultado))
        return resultado

    def escribir_todo(
        self, entradas: dict[tuple[str, str], EntradaHistorial],
    ) -> None:
        """Reemplaza toda la pestaña con las entradas. Crea pestaña si no existe."""
        filas = [
            [
                e.sku,
                e.template,
                e.aspect_ratio,
                f"{e.precio_lista:.2f}",
                f"{e.precio_promo:.2f}",
                e.url_cloudinary,
                e.fecha_render,
                e.hash_render,
            ]
            for e in entradas.values()
        ]
        self.client.escribir_replace(HEADERS_HISTORIAL, filas)
        log.info("Historial guardado: %d entradas", len(filas))


def _a_float(valor) -> float:
    """Convierte un valor de celda a float, tolerando strings vacíos."""
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).replace(",", "."))
    except ValueError:
        return 0.0


def ahora_iso() -> str:
    """Timestamp ISO para fecha_render."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
