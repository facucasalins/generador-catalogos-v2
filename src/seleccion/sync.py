"""Sync de las pestañas Catalogo y Templates del sheet de Selección.

Estas dos pestañas se REGENERAN cada vez que corre el bloque. La pestaña
Seleccion (editable) NO se toca acá.

Catalogo: espejo del Inventario con thumbnails IMAGE(). Sirve para que el
  usuario busque SKUs visualmente.

Templates: lista de archivos HTML disponibles en clients/{cliente}/templates/.
  Es el source del dropdown de la columna template en Seleccion.
"""
from __future__ import annotations
import logging
from pathlib import Path

from src.core.modelo_datos import Producto
from src.core.sheets_client import ConfigSheets, SheetsClient
from src.core.sheets_helpers import (
    escribir_pestaña_con_formulas,
    aplicar_data_validation_dropdown,
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

HEADERS_SELECCION = [
    "sku",
    "generar",
    "template",
    "prioridad",
    "notas",
]

HEADERS_TEMPLATES = [
    "nombre_template",
    "descripcion",
    "activo",
]


def sync_catalogo(
    sheet_id: str,
    productos: list[Producto],
    credenciales_json: str | None = None,
    pestaña: str = "Catalogo",
) -> int:
    """Regenera la pestaña Catalogo con espejo del inventario actual.

    Returns:
        Cantidad de productos escritos.
    """
    client = SheetsClient(ConfigSheets(
        sheet_id=sheet_id,
        pestaña=pestaña,
        credenciales_json=credenciales_json,
    ))

    filas = []
    for p in productos:
        # =IMAGE() necesita comillas dobles ESCAPADAS porque va dentro de string
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
) -> list[str]:
    """Escanea archivos HTML del cliente y los lista en la pestaña Templates.

    Returns:
        Lista de nombres de template encontrados.
    """
    if not templates_dir.exists():
        log.warning("Directorio de templates no existe: %s", templates_dir)
        templates_dir.mkdir(parents=True, exist_ok=True)

    templates: list[tuple[str, str]] = []  # (nombre, descripcion)
    for html in sorted(templates_dir.glob("*.html")):
        nombre = html.stem  # sin extensión
        # Buscar comentario al inicio del HTML con descripción: <!-- DESC: ... -->
        try:
            with open(html, encoding="utf-8") as f:
                contenido_inicio = f.read(500)
            desc = _extraer_descripcion(contenido_inicio)
        except Exception as e:
            log.warning("No pude leer descripción de %s: %s", html, e)
            desc = ""
        templates.append((nombre, desc))

    if not templates:
        log.warning("No se encontraron templates en %s", templates_dir)
        templates = [("default", "Template por defecto (falta crear archivo)")]

    client = SheetsClient(ConfigSheets(
        sheet_id=sheet_id,
        pestaña=pestaña,
        credenciales_json=credenciales_json,
    ))

    filas = [[nombre, desc, "SI"] for nombre, desc in templates]
    client.escribir_replace(HEADERS_TEMPLATES, filas)
    congelar_header(client, filas=1)

    log.info("Templates: %d encontrados (%s)",
             len(templates), [t[0] for t in templates])
    return [t[0] for t in templates]


def _extraer_descripcion(contenido: str) -> str:
    """Busca <!-- DESC: ... --> en el inicio del HTML."""
    import re
    m = re.search(r"<!--\s*DESC:\s*(.+?)\s*-->", contenido)
    return m.group(1).strip() if m else ""


def inicializar_pestaña_seleccion(
    sheet_id: str,
    credenciales_json: str | None = None,
    pestaña: str = "Seleccion",
    filas_max: int = 1000,
) -> None:
    """Si la pestaña Seleccion no existe, la crea con headers, checkboxes
    y dropdown. NO toca contenido existente (no es destructivo).

    Esto se llama solo la primera vez o cuando la pestaña fue borrada.
    """
    client = SheetsClient(ConfigSheets(
        sheet_id=sheet_id,
        pestaña=pestaña,
        credenciales_json=credenciales_json,
    ))

    # Si ya hay headers, asumimos que la pestaña está inicializada
    sheet = client._abrir_sheet()
    try:
        ws = sheet.worksheet(pestaña)
        valores_existentes = ws.row_values(1)
        if valores_existentes and valores_existentes[0] == HEADERS_SELECCION[0]:
            log.info("Pestaña '%s' ya estaba inicializada. No la toco.", pestaña)
            return
    except Exception:
        pass  # No existe, la crea _abrir_pestaña

    # Escribir solo headers (filas vacías para que el usuario complete)
    ws = client._abrir_pestaña(sheet)
    ws.clear()
    ws.update(values=[HEADERS_SELECCION], range_name="A1")

    # Aplicar checkboxes en la columna 'generar' (col B, filas 2 a filas_max)
    aplicar_checkboxes(client, columna_letra="B", fila_inicio=2, fila_fin=filas_max)

    # Aplicar dropdown en la columna 'template' (col C) apuntando a Templates!A
    aplicar_data_validation_dropdown(
        client,
        columna_letra="C",
        fila_inicio=2,
        fila_fin=filas_max,
        source_pestaña="Templates",
        source_columna_letra="A",
    )

    congelar_header(client, filas=1)

    log.info("Pestaña '%s' inicializada con checkboxes y dropdown", pestaña)
