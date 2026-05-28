"""Historial de placas renderizadas.

Cambio multi-template:
- La clave del historial ahora es (sku, template) en vez de (sku, aspect_ratio).
- Esto permite que un SKU tenga N placas distintas (una por template) y se
  trackeen por separado.
"""
from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.core.modelo_datos import Producto, DecisionSeleccion
from src.core.sheets_client import ConfigSheets, SheetsClient
from src.core.templates import nombre_base_template


log = logging.getLogger(__name__)


PESTAÑA_HISTORIAL = "Historial_Placas"
HEADERS_HISTORIAL = [
    "sku",
    "template",
    "aspect_ratio",   # info derivada del template, útil para reportes
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
    fecha_render: str
    hash_render: str
    aspect_ratio: str = "4:5"


def _leer_template_html(templates_dir: Path, template_name: str) -> str:
    # El nombre puede venir con prefijo de plataforma (Meta_/TikTok_); el
    # archivo en disco no lo tiene. Resolvemos con el MISMO helper que usa
    # el motor de estilo para que el hash refleje el contenido real del HTML.
    nombre_base = nombre_base_template(template_name)
    path = templates_dir / f"{nombre_base}.html"
    if not path.exists():
        log.warning("Template '%s' no existe, hash usará string vacío", path)
        return ""
    return path.read_text(encoding="utf-8")


def calcular_hash(
    producto: Producto,
    decision: DecisionSeleccion,
    templates_dir: Path,
) -> str:
    """Calcula hash que cambia si cualquier input visual cambia.

    Incluye: precios, nombre, descripción, marca, URL imagen, template
    asignado, y el CONTENIDO del HTML del template.
    """
    template_html = _leer_template_html(templates_dir, decision.template)
    partes = [
        producto.sku,
        decision.template,
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
    """Lee y escribe el historial. Key: (sku, template)."""

    def __init__(self, sheet_id: str):
        self.client = SheetsClient(ConfigSheets(
            sheet_id=sheet_id, pestaña=PESTAÑA_HISTORIAL,
        ))

    def leer_todo(self) -> dict[tuple[str, str], EntradaHistorial]:
        """Devuelve {(sku, template): EntradaHistorial}."""
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
            template = fila[idx["template"]].strip() if idx["template"] < len(fila) else ""
            if not sku or not template:
                continue
            try:
                aspect_ratio = "4:5"
                ar_idx = idx.get("aspect_ratio", -1)
                if 0 <= ar_idx < len(fila):
                    valor = fila[ar_idx].strip()
                    if valor:
                        aspect_ratio = valor

                entrada = EntradaHistorial(
                    sku=sku,
                    template=template,
                    precio_lista=_a_float(fila[idx.get("precio_lista", -1)]) if idx.get("precio_lista", -1) < len(fila) else 0.0,
                    precio_promo=_a_float(fila[idx.get("precio_promo", -1)]) if idx.get("precio_promo", -1) < len(fila) else 0.0,
                    url_cloudinary=fila[idx["url_cloudinary"]] if idx["url_cloudinary"] < len(fila) else "",
                    fecha_render=fila[idx.get("fecha_render", -1)] if idx.get("fecha_render", -1) < len(fila) else "",
                    hash_render=fila[idx["hash_render"]] if idx["hash_render"] < len(fila) else "",
                    aspect_ratio=aspect_ratio,
                )
                resultado[(sku, template)] = entrada
            except (IndexError, ValueError) as e:
                log.warning("Fila inválida en Historial_Placas para sku=%s: %s", sku, e)
                continue

        log.info("Historial cargado: %d entradas (SKU × template)", len(resultado))
        return resultado

    def escribir_todo(
        self, entradas: dict[tuple[str, str], EntradaHistorial],
    ) -> None:
        """Reemplaza toda la pestaña con las entradas."""
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
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).replace(",", "."))
    except ValueError:
        return 0.0


def ahora_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
