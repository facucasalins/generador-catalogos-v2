"""Cache de Enriquecimiento en pestaña de Google Sheets.

Similar al Historial_Placas de Fase F, pero para guardar lo que Gemini
generó por SKU. Permite reusar el enriquecimiento si el input no cambió
y así no gastar llamadas a Gemini al pedo.

Cache hit: el SKU está en la pestaña Y su hash_input coincide con el
hash actual (calculado de nombre + descripción TN).

Cache miss: SKU nuevo, o cambió nombre/descripción TN, o cambió el
proveedor (cambiamos de modelo). En cualquiera de los 3 casos: regenerar.
"""
from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime

from src.core.modelo_datos import Producto, Enriquecimiento
from src.core.sheets_client import ConfigSheets, SheetsClient


log = logging.getLogger(__name__)


PESTAÑA_ENRIQUECIMIENTO = "Enriquecimiento"
HEADERS_ENRIQUECIMIENTO = [
    "sku",
    "hash_input",
    "proveedor",
    "generado_en",
    "titulo_corto",
    "descripcion_corta",
    "tips_json",  # tips como JSON string (lista de strings)
    "fallback_aplicado",
    "error",
]


@dataclass
class EntradaCacheEnriquecimiento:
    """Una fila del cache."""
    sku: str
    hash_input: str
    proveedor: str
    generado_en: str  # ISO
    titulo_corto: str
    descripcion_corta: str
    tips: list[str]
    fallback_aplicado: bool
    error: str

    def a_enriquecimiento(self) -> Enriquecimiento:
        """Convierte la entrada cacheada de vuelta a un objeto Enriquecimiento."""
        try:
            generado = datetime.fromisoformat(self.generado_en) if self.generado_en else datetime.now()
        except ValueError:
            generado = datetime.now()

        return Enriquecimiento(
            sku=self.sku,
            hash_input=self.hash_input,
            proveedor=self.proveedor,
            generado_en=generado,
            tips=self.tips,
            titulo_corto=self.titulo_corto,
            descripcion_corta=self.descripcion_corta,
            slogan="",
            categoria_inferida="",
            fallback_aplicado=self.fallback_aplicado,
            error=self.error,
        )


def calcular_hash_input(producto: Producto, proveedor: str) -> str:
    """Hash que cambia si:
    - cambia el nombre del producto en TN
    - cambia la descripción del producto en TN
    - cambia la marca o categoría
    - cambia el proveedor (modelo)

    Si cambia el prompt en el código, NO regenera automáticamente. Si querés
    que regenere, cambia el sufijo de versión acá. El proveedor incluye el
    modelo, así que cambiar de gemini-2.0-flash a gemini-2.0-pro fuerza
    regenerar.
    """
    partes = [
        producto.sku,
        producto.nombre or "",
        producto.descripcion or "",
        producto.marca or "",
        producto.categoria or "",
        proveedor,
        "v2",  # versión del prompt; bumpealo manualmente si cambias prompt
    ]
    blob = "||".join(partes).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


class CacheEnriquecimiento:
    """Lee y escribe la pestaña Enriquecimiento."""

    def __init__(self, sheet_id: str):
        self.client = SheetsClient(ConfigSheets(
            sheet_id=sheet_id, pestaña=PESTAÑA_ENRIQUECIMIENTO,
        ))

    def leer_todo(self) -> dict[str, EntradaCacheEnriquecimiento]:
        """Devuelve {sku: EntradaCache}. Si la pestaña no existe → {}."""
        try:
            filas = self.client.leer_todas_las_filas()
        except Exception as e:
            log.info("Pestaña %s vacía o inexistente (%s)", PESTAÑA_ENRIQUECIMIENTO, e)
            return {}

        if not filas or len(filas) < 2:
            return {}

        header = filas[0]
        idx = {col: i for i, col in enumerate(header)}
        requeridos = {"sku", "hash_input", "titulo_corto"}
        if not requeridos.issubset(idx.keys()):
            log.warning("Cache enriquecimiento: faltan columnas requeridas")
            return {}

        resultado: dict[str, EntradaCacheEnriquecimiento] = {}
        for fila in filas[1:]:
            if not fila or len(fila) <= idx["sku"]:
                continue
            sku = fila[idx["sku"]].strip()
            if not sku:
                continue

            tips_json_str = fila[idx.get("tips_json", -1)] if idx.get("tips_json", -1) < len(fila) else "[]"
            try:
                tips = json.loads(tips_json_str) if tips_json_str else []
                if not isinstance(tips, list):
                    tips = []
            except json.JSONDecodeError:
                tips = []

            resultado[sku] = EntradaCacheEnriquecimiento(
                sku=sku,
                hash_input=fila[idx["hash_input"]] if idx["hash_input"] < len(fila) else "",
                proveedor=fila[idx.get("proveedor", -1)] if 0 <= idx.get("proveedor", -1) < len(fila) else "",
                generado_en=fila[idx.get("generado_en", -1)] if 0 <= idx.get("generado_en", -1) < len(fila) else "",
                titulo_corto=fila[idx["titulo_corto"]] if idx["titulo_corto"] < len(fila) else "",
                descripcion_corta=fila[idx.get("descripcion_corta", -1)] if 0 <= idx.get("descripcion_corta", -1) < len(fila) else "",
                tips=tips,
                fallback_aplicado=_a_bool(fila[idx.get("fallback_aplicado", -1)]) if 0 <= idx.get("fallback_aplicado", -1) < len(fila) else False,
                error=fila[idx.get("error", -1)] if 0 <= idx.get("error", -1) < len(fila) else "",
            )

        log.info("Cache enriquecimiento: %d entradas cargadas", len(resultado))
        return resultado

    def escribir_todo(self, entradas: dict[str, EntradaCacheEnriquecimiento]) -> None:
        """Reemplaza toda la pestaña con las entradas. Crea pestaña si no existe."""
        filas = [
            [
                e.sku,
                e.hash_input,
                e.proveedor,
                e.generado_en,
                e.titulo_corto,
                e.descripcion_corta,
                json.dumps(e.tips, ensure_ascii=False),
                "TRUE" if e.fallback_aplicado else "FALSE",
                e.error,
            ]
            for e in entradas.values()
        ]
        self.client.escribir_replace(HEADERS_ENRIQUECIMIENTO, filas)
        log.info("Cache enriquecimiento: %d entradas guardadas", len(filas))


def _a_bool(valor) -> bool:
    if valor is None:
        return False
    return str(valor).strip().upper() in ("TRUE", "1", "YES", "SI", "SÍ")


def enriquecimiento_a_entrada_cache(
    enr: Enriquecimiento, hash_input: str,
) -> EntradaCacheEnriquecimiento:
    """Convierte un Enriquecimiento (recién generado) a EntradaCache."""
    return EntradaCacheEnriquecimiento(
        sku=enr.sku,
        hash_input=hash_input,
        proveedor=enr.proveedor,
        generado_en=enr.generado_en.isoformat(timespec="seconds"),
        titulo_corto=enr.titulo_corto,
        descripcion_corta=enr.descripcion_corta,
        tips=enr.tips,
        fallback_aplicado=enr.fallback_aplicado,
        error=enr.error,
    )
