"""Helpers de Google Sheets para casos avanzados.

Estos no van en el SheetsClient base porque son específicos de Bloque 2:
- Leer pestañas como lista de dicts
- Aplicar data validation (dropdowns)
- Escribir fórmulas (IMAGE, etc.)
- Format de header row
"""
from __future__ import annotations
import logging
from typing import Optional

import gspread

from src.core.sheets_client import SheetsClient, ConfigSheets, ErrorSheets


log = logging.getLogger(__name__)


def leer_pestaña_como_dicts(
    sheet_id: str,
    pestaña: str,
    credenciales_json: Optional[str] = None,
) -> list[dict]:
    """Lee toda una pestaña y la devuelve como lista de dicts.

    La primera fila se usa como headers. Si una celda está vacía, el valor es "".

    Returns:
        Lista de dicts. Vacía si la pestaña está vacía o no existe.
    """
    client = SheetsClient(ConfigSheets(
        sheet_id=sheet_id,
        pestaña=pestaña,
        credenciales_json=credenciales_json,
    ))
    sheet = client._abrir_sheet()
    try:
        ws = sheet.worksheet(pestaña)
    except gspread.exceptions.WorksheetNotFound:
        log.warning("Pestaña '%s' no existe en sheet %s", pestaña, sheet_id)
        return []

    # get_all_records devuelve lista de dicts usando la primera fila como keys
    # default_blank="" para que celdas vacías sean string vacío
    return ws.get_all_records(default_blank="")


def escribir_pestaña_con_formulas(
    client: SheetsClient,
    headers: list[str],
    filas: list[list],
) -> int:
    """Igual que escribir_replace pero permite fórmulas en las celdas.

    Las celdas que empiezan con `=` son interpretadas como fórmulas por Sheets.
    Importante: `value_input_option="USER_ENTERED"` es la diferencia clave.
    """
    if not headers:
        raise ErrorSheets("headers no puede estar vacío")

    sheet = client._abrir_sheet()
    ws = client._abrir_pestaña(sheet)
    ws.clear()

    data = [headers] + filas
    # USER_ENTERED hace que "=IMAGE(...)" se interprete como fórmula
    ws.update(values=data, range_name="A1", value_input_option="USER_ENTERED")

    log.info(
        "Sheet '%s' / '%s': %d filas escritas (modo fórmulas)",
        client.cfg.sheet_id, client.cfg.pestaña, len(filas),
    )
    return len(filas)


def aplicar_data_validation_dropdown(
    client: SheetsClient,
    columna_letra: str,
    fila_inicio: int,
    fila_fin: int,
    source_pestaña: str,
    source_columna_letra: str,
    source_fila_inicio: int = 2,
    source_fila_fin: int = 1000,
) -> None:
    """Aplica un dropdown a un rango de celdas, con opciones de otra pestaña.

    Ejemplo: dropdown en Seleccion!C2:C1000 con opciones de Templates!A2:A1000

    Args:
        client: SheetsClient ya configurado con la pestaña DESTINO (Seleccion)
        columna_letra: columna destino donde va el dropdown (ej: "C")
        fila_inicio: primera fila con dropdown (típicamente 2, para saltar header)
        fila_fin: última fila con dropdown (ej: 1000)
        source_pestaña: pestaña ORIGEN de las opciones (ej: "Templates")
        source_columna_letra: columna origen (ej: "A")
    """
    sheet = client._abrir_sheet()
    destino_ws = sheet.worksheet(client.cfg.pestaña)
    source_ws = sheet.worksheet(source_pestaña)

    # Range destino
    rango_destino = f"{columna_letra}{fila_inicio}:{columna_letra}{fila_fin}"

    # Construir el request de data validation usando la API batch
    # https://developers.google.com/sheets/api/samples/data#apply_a_data_validation_rule_to_a_range
    request = {
        "setDataValidation": {
            "range": {
                "sheetId": destino_ws.id,
                "startRowIndex": fila_inicio - 1,  # 0-indexed
                "endRowIndex": fila_fin,
                "startColumnIndex": _letra_a_indice(columna_letra),
                "endColumnIndex": _letra_a_indice(columna_letra) + 1,
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_RANGE",
                    "values": [{
                        "userEnteredValue": (
                            f"={source_pestaña}!"
                            f"{source_columna_letra}{source_fila_inicio}:"
                            f"{source_columna_letra}{source_fila_fin}"
                        )
                    }],
                },
                "strict": False,  # permite valores fuera del rango (warning, no error)
                "showCustomUi": True,  # muestra el dropdown
            },
        }
    }

    sheet.batch_update({"requests": [request]})
    log.info(
        "Data validation aplicada en %s!%s (source: %s!%s)",
        client.cfg.pestaña, rango_destino, source_pestaña, source_columna_letra,
    )


def aplicar_checkboxes(
    client: SheetsClient,
    columna_letra: str,
    fila_inicio: int,
    fila_fin: int,
) -> None:
    """Convierte un rango de celdas en checkboxes booleanos."""
    sheet = client._abrir_sheet()
    ws = sheet.worksheet(client.cfg.pestaña)

    request = {
        "setDataValidation": {
            "range": {
                "sheetId": ws.id,
                "startRowIndex": fila_inicio - 1,
                "endRowIndex": fila_fin,
                "startColumnIndex": _letra_a_indice(columna_letra),
                "endColumnIndex": _letra_a_indice(columna_letra) + 1,
            },
            "rule": {
                "condition": {"type": "BOOLEAN"},
                "strict": True,
            },
        }
    }
    sheet.batch_update({"requests": [request]})
    log.info("Checkboxes aplicados en %s!%s%d:%s%d",
             client.cfg.pestaña, columna_letra, fila_inicio, columna_letra, fila_fin)


def congelar_header(client: SheetsClient, filas: int = 1) -> None:
    """Congela las primeras N filas del worksheet."""
    sheet = client._abrir_sheet()
    ws = sheet.worksheet(client.cfg.pestaña)
    request = {
        "updateSheetProperties": {
            "properties": {
                "sheetId": ws.id,
                "gridProperties": {"frozenRowCount": filas},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    }
    sheet.batch_update({"requests": [request]})


def _letra_a_indice(letra: str) -> int:
    """Convierte letra de columna ('A', 'B', ..., 'AA') a índice 0-based."""
    letra = letra.upper()
    indice = 0
    for c in letra:
        indice = indice * 26 + (ord(c) - ord("A") + 1)
    return indice - 1
