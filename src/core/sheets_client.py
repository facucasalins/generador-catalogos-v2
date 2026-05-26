"""Cliente de Google Sheets para Agency Nusa.

Cliente fino sobre gspread, usado por todos los bloques que escriben
o leen de Sheets (Inventario, Selección, Enriquecimiento, Feed-Output).

Diseño:
- Autenticación: Service Account vía JSON (env var o archivo)
- Modo de escritura: replace (limpia la pestaña y reescribe todo)
- Crea la pestaña si no existe (en escritura)
- Maneja cuotas de Google (1 batch update grande, no fila por fila)
"""
from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials


log = logging.getLogger(__name__)


# Google Sheets API requiere estos scopes para leer/escribir
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@dataclass
class ConfigSheets:
    """Config para conectarse a un sheet."""
    sheet_id: str
    pestaña: str
    # Las credenciales se pasan como string JSON (desde env var en GitHub Actions)
    # o se leen de archivo local en desarrollo.
    credenciales_json: Optional[str] = None
    credenciales_path: Optional[str] = None


class ErrorSheets(Exception):
    """Cualquier error relacionado con Sheets."""


def _cargar_credenciales(cfg: ConfigSheets) -> Credentials:
    """Carga las credenciales desde JSON string o archivo.

    Prioridad: credenciales_json > credenciales_path > variable de entorno.
    """
    json_str = cfg.credenciales_json or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

    if json_str:
        try:
            info = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ErrorSheets(f"GOOGLE_SERVICE_ACCOUNT_JSON no es JSON válido: {e}")
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    if cfg.credenciales_path:
        if not os.path.exists(cfg.credenciales_path):
            raise ErrorSheets(f"Archivo de credenciales no encontrado: {cfg.credenciales_path}")
        return Credentials.from_service_account_file(cfg.credenciales_path, scopes=SCOPES)

    raise ErrorSheets(
        "Sin credenciales. Pasá credenciales_json, credenciales_path, "
        "o seteá la env var GOOGLE_SERVICE_ACCOUNT_JSON."
    )


class SheetsClient:
    """Wrapper sobre gspread con utilidades comunes."""

    def __init__(self, cfg: ConfigSheets):
        if not cfg.sheet_id:
            raise ErrorSheets("ConfigSheets.sheet_id es obligatorio")
        if not cfg.pestaña:
            raise ErrorSheets("ConfigSheets.pestaña es obligatorio")
        self.cfg = cfg
        self._creds = _cargar_credenciales(cfg)
        self._gc = gspread.authorize(self._creds)

    def _abrir_sheet(self):
        try:
            return self._gc.open_by_key(self.cfg.sheet_id)
        except gspread.exceptions.APIError as e:
            # El error típico cuando no compartiste el sheet con la service account
            if "PERMISSION_DENIED" in str(e):
                raise ErrorSheets(
                    f"No tengo permisos sobre el sheet {self.cfg.sheet_id}. "
                    f"¿Lo compartiste con la service account como Editor?"
                ) from e
            raise

    def _abrir_pestaña(self, sheet) -> gspread.Worksheet:
        """Abre la pestaña; la crea si no existe."""
        try:
            return sheet.worksheet(self.cfg.pestaña)
        except gspread.exceptions.WorksheetNotFound:
            log.info("Creando pestaña '%s' en sheet %s", self.cfg.pestaña, self.cfg.sheet_id)
            return sheet.add_worksheet(title=self.cfg.pestaña, rows=1000, cols=26)

    def escribir_replace(
        self,
        headers: list[str],
        filas: list[list],
    ) -> int:
        """Reescribe la pestaña entera: limpia, escribe headers, escribe filas.

        Args:
            headers: nombres de columnas (primera fila)
            filas: lista de filas, cada fila es lista de valores (mismo largo que headers)

        Returns:
            Cantidad de filas escritas (sin contar el header)
        """
        if not headers:
            raise ErrorSheets("headers no puede estar vacío")

        # Validación: todas las filas con la misma cantidad de columnas que headers
        for i, fila in enumerate(filas):
            if len(fila) != len(headers):
                raise ErrorSheets(
                    f"Fila {i} tiene {len(fila)} columnas pero headers tiene {len(headers)}. "
                    f"Fila: {fila}"
                )

        sheet = self._abrir_sheet()
        ws = self._abrir_pestaña(sheet)

        # Limpiar todo (más rápido que borrar fila por fila)
        ws.clear()

        # Escribir todo en un batch (1 sola request a la API)
        # Si filas es vacía, escribir solo headers
        data = [headers] + filas
        ws.update(values=data, range_name="A1")

        log.info(
            "Sheet '%s' / '%s': %d filas escritas (más headers)",
            self.cfg.sheet_id, self.cfg.pestaña, len(filas),
        )
        return len(filas)

    def leer_todas_las_filas(self) -> list[list[str]]:
        """Lee todas las filas de la pestaña como lista de listas de strings.

        A diferencia de escribir_replace, NO crea la pestaña si no existe:
        levanta WorksheetNotFound. Esto es intencional: si el historial no
        existe, queremos saberlo (no inventarlo silenciosamente).

        Returns:
            Lista de filas. La primera fila normalmente son los headers.
            Si la pestaña está completamente vacía, devuelve [].

        Raises:
            gspread.exceptions.WorksheetNotFound: la pestaña no existe.
            ErrorSheets: problema de permisos u otra API error.
        """
        sheet = self._abrir_sheet()
        # NO usar _abrir_pestaña porque ese crea la pestaña si falta.
        # Acá queremos que falle (capturable por el caller).
        ws = sheet.worksheet(self.cfg.pestaña)
        filas = ws.get_all_values()
        log.info(
            "Sheet '%s' / '%s': %d filas leídas",
            self.cfg.sheet_id, self.cfg.pestaña, len(filas),
        )
        return filas

    def listar_pestañas(self) -> list[str]:
        """Devuelve los nombres de todas las pestañas del sheet.

        NO usa self.cfg.pestaña (es una operación a nivel sheet, no pestaña).
        NO crea ninguna pestaña.

        Returns:
            Lista de nombres en el orden que aparecen en el sheet.

        Raises:
            ErrorSheets: problema de permisos u otra API error.
        """
        sheet = self._abrir_sheet()
        nombres = [ws.title for ws in sheet.worksheets()]
        log.debug("Sheet '%s': %d pestañas (%s)",
                  self.cfg.sheet_id, len(nombres), nombres)
        return nombres
