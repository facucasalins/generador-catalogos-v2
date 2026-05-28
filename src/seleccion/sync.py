"""Sync de las pestañas Catalogo, Templates y Seleccion del sheet de Selección.

Catalogo y Templates se REGENERAN cada vez que corre el bloque.
Seleccion: las columnas FIJAS (sku, generar, prioridad, notas) se inicializan
solo si la pestaña no existe; las columnas de templates las maneja el Apps
Script del sheet (al abrir sincroniza con Templates activos).

Catalogo: espejo del Inventario con thumbnails IMAGE(). Sirve para que el
  usuario busque SKUs visualmente.

Templates: lista de archivos HTML disponibles en clients/{cliente}/templates/.
  Cada fila representa un template (nombre, descripcion, activo). El Apps
  Script del sheet usa esta tabla para sincronizar las columnas de Seleccion.
"""
from __future__ import annotations
import logging
import re
from pathlib import Path

from src.core.modelo_datos import Producto, TemplateMetadata
from src.core.sheets_client import ConfigSheets, SheetsClient
from src.core.sheets_helpers import (
    escribir_pestaña_con_formulas,
    aplicar_checkboxes,
    congelar_header,
)


log = logging.getLogger(__name__)


# Headers de la pestaña Catalogo. Orden importa (afecta la UX del que busca).
HEADERS_CATALOGO = [
    "sku",
    "imagen",         # =IMAGE(url) — thumbnail
    "nombre",
    "precio_lista",
    "precio_promo",
    "tiene_promo",
    "stock",
    "categoria",
    "marca",
    "tn_published",
]

# Las columnas fijas de Seleccion. Las de templates las agrega el Apps Script.
HEADERS_SELECCION_FIJOS = [
    "sku",
    "generar",
    "prioridad",
    "notas",
]

HEADERS_TEMPLATES = [
    "nombre_template",
    "descripcion",
    "aspect_ratio",
    "width",
    "height",
    "activo",
]


def parsear_metadata_template(contenido_html: str, nombre_template: str) -> TemplateMetadata:
    """Extrae metadata del comentario <!-- META ... --> al inicio del HTML.

    Formato esperado:
        <!-- META
        aspect_ratio: 4:5
        width: 1080
        height: 1350
        descripcion: Texto descriptivo
        -->

    Si falta algún campo obligatorio (aspect_ratio, width, height) loguea
    warning y usa defaults razonables (1080x1350 / 4:5). Esto evita que un
    template mal escrito rompa el pipeline; sale con warning visible.
    """
    aspect_ratio = "4:5"
    width = 1080
    height = 1350
    descripcion = ""

    m = re.search(r"<!--\s*META\s*(.+?)\s*-->", contenido_html, re.DOTALL)
    if not m:
        # Fallback: buscar el formato viejo <!-- DESC: ... --> para retrocompat
        m_desc = re.search(r"<!--\s*DESC:\s*(.+?)\s*-->", contenido_html)
        if m_desc:
            descripcion = m_desc.group(1).strip()
        log.warning(
            "Template '%s' sin bloque META. Usando defaults: 4:5 (1080x1350). "
            "Agrega un comentario <!-- META ... --> al inicio del HTML.",
            nombre_template,
        )
        return TemplateMetadata(
            nombre=nombre_template,
            aspect_ratio=aspect_ratio,
            width=width,
            height=height,
            descripcion=descripcion,
        )

    bloque = m.group(1)
    for linea in bloque.split("\n"):
        linea = linea.strip()
        if not linea or ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        clave = clave.strip().lower()
        valor = valor.strip()
        if clave == "aspect_ratio":
            aspect_ratio = valor
        elif clave == "width":
            try:
                width = int(valor)
            except ValueError:
                log.warning("Template '%s': width inválido '%s'", nombre_template, valor)
        elif clave == "height":
            try:
                height = int(valor)
            except ValueError:
                log.warning("Template '%s': height inválido '%s'", nombre_template, valor)
        elif clave in ("descripcion", "descripción", "desc"):
            descripcion = valor

    return TemplateMetadata(
        nombre=nombre_template,
        aspect_ratio=aspect_ratio,
        width=width,
        height=height,
        descripcion=descripcion,
    )


def descubrir_templates(templates_dir: Path) -> list[TemplateMetadata]:
    """Escanea los .html del cliente y devuelve su metadata."""
    if not templates_dir.exists():
        log.warning("Directorio de templates no existe: %s", templates_dir)
        templates_dir.mkdir(parents=True, exist_ok=True)
        return []

    templates: list[TemplateMetadata] = []
    for html in sorted(templates_dir.glob("*.html")):
        nombre = html.stem
        try:
            contenido = html.read_text(encoding="utf-8")
        except Exception as e:
            log.warning("No pude leer template %s: %s", html, e)
            continue
        templates.append(parsear_metadata_template(contenido, nombre))

    return templates


def sync_catalogo(
    sheet_id: str,
    productos: list[Producto],
    credenciales_json: str | None = None,
    pestaña: str = "Catalogo",
) -> int:
    """Regenera la pestaña Catalogo con espejo del inventario actual."""
    client = SheetsClient(ConfigSheets(
        sheet_id=sheet_id,
        pestaña=pestaña,
        credenciales_json=credenciales_json,
    ))

    filas = []
    for p in productos:
        imagen_formula = f'=IMAGE("{p.imagen_url}")' if p.imagen_url else ""
        filas.append([
            p.sku,
            imagen_formula,
            p.nombre,
            p.precio_lista,
            p.precio_promocional if p.precio_promocional is not None else "",
            "SI" if p.tiene_promo else "NO",
            p.stock if p.stock is not None else "",
            p.categoria,
            p.marca,
            "SI" if (p.enriquecimiento or {}).get("tn_published") else "NO",
        ])

    n = escribir_pestaña_con_formulas(client, HEADERS_CATALOGO, filas)
    congelar_header(client, filas=1)

    log.info("Catalogo: %d productos sincronizados", n)
    return n


def sync_templates(
    sheet_id: str,
    templates_dir: Path,
    credenciales_json: str | None = None,
    pestaña: str = "Templates",
) -> list[TemplateMetadata]:
    """Escanea HTMLs del cliente y escribe sus metadatos en la pestaña Templates.

    Returns:
        Lista de TemplateMetadata con todos los templates encontrados.
    """
    templates = descubrir_templates(templates_dir)

    if not templates:
        log.warning("No se encontraron templates en %s", templates_dir)
        # Escribir solo headers para que el sheet quede inicializado
        templates = []

    client = SheetsClient(ConfigSheets(
        sheet_id=sheet_id,
        pestaña=pestaña,
        credenciales_json=credenciales_json,
    ))

    filas = [
        [t.nombre, t.descripcion, t.aspect_ratio, t.width, t.height, "SI"]
        for t in templates
    ]
    client.escribir_replace(HEADERS_TEMPLATES, filas)
    congelar_header(client, filas=1)

    log.info("Templates: %d encontrados (%s)",
             len(templates), [t.nombre for t in templates])
    return templates


def inicializar_pestaña_seleccion(
    sheet_id: str,
    credenciales_json: str | None = None,
    pestaña: str = "Seleccion",
    filas_max: int = 1000,
) -> None:
    """Si la pestaña Seleccion no existe, la crea con headers FIJOS y checkboxes.

    Las columnas de templates las agrega el Apps Script del sheet al abrir
    (lee la pestaña Templates y agrega 1 columna por cada template activo).

    NO toca contenido existente. Solo inicializa si la pestaña está vacía.
    """
    client = SheetsClient(ConfigSheets(
        sheet_id=sheet_id,
        pestaña=pestaña,
        credenciales_json=credenciales_json,
    ))

    sheet = client._abrir_sheet()
    try:
        ws = sheet.worksheet(pestaña)
        valores_existentes = ws.row_values(1)
        if valores_existentes and valores_existentes[0] == HEADERS_SELECCION_FIJOS[0]:
            log.info("Pestaña '%s' ya estaba inicializada. No la toco.", pestaña)
            return
    except Exception:
        pass

    ws = client._abrir_pestaña(sheet)
    ws.clear()
    ws.update(values=[HEADERS_SELECCION_FIJOS], range_name="A1")

    # Checkboxes en la columna 'generar' (col B)
    aplicar_checkboxes(client, columna_letra="B", fila_inicio=2, fila_fin=filas_max)

    congelar_header(client, filas=1)

    log.info(
        "Pestaña '%s' inicializada con columnas fijas. "
        "Las columnas de templates las agrega el Apps Script al abrir el sheet.",
        pestaña,
    )
