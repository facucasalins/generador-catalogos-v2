"""Motor de estilo: render de placas con Playwright (HTML → PNG).

Cambio multi-template:
- Las dimensiones de cada placa vienen del COMENTARIO <!-- META --> del HTML,
  no del config global del cliente.
- Esto permite que un mismo cliente tenga templates de distintas dimensiones
  (ej. default_4x5 + default_9x16 + default_1x1) sin tener que iterar
  aspect_ratios en el cli.py.
"""
from __future__ import annotations
import base64
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from playwright.sync_api import sync_playwright, Browser, BrowserContext

from src.core.modelo_datos import Producto, DecisionSeleccion, Placa, TemplateMetadata
from src.estilo.base import MotorEstilo, ErrorEstilo
from src.seleccion.sync import parsear_metadata_template


log = logging.getLogger(__name__)


# ============ Config ============

@dataclass
class ConfigPlaywrightHtml:
    """Config del motor. Las dimensiones por placa las decide cada template."""
    templates_dir: Path
    output_dir: Path

    # Variables globales accesibles en todos los templates del cliente
    variables_globales: dict = field(default_factory=dict)

    # Factor para calcular el precio promocional desde precio_lista cuando
    # la fuente no lo provee (legado de Mora v1). 1.0 = sin descuento adicional.
    hotsale_discount_factor: float = 1.0

    # Factor de descuento adicional para "precio efectivo" (ej. transferencia).
    descuento_efectivo_factor: Optional[float] = None

    # Si True, calcula cuotas sobre precio_hotsale en vez de precio_lista.
    cuotas_sobre_promocional: bool = False

    # Timeout en ms para descargar imágenes
    download_timeout_seg: int = 15


# ============ Helpers de formateo ============

def formatear_precio_ars(valor: float) -> str:
    entero = int(round(valor))
    formateado = f"{entero:,}".replace(",", ".")
    return f"${formateado}"


def calcular_cuota(precio_base: float, cuotas_num: int = 3) -> float:
    if cuotas_num <= 0:
        return precio_base
    return precio_base / cuotas_num


# ============ Motor ============

class PlaywrightHtmlEstilo(MotorEstilo):
    """Renderiza placas usando templates HTML + Playwright headless.

    Las dimensiones vienen del template mismo (metadata <!-- META -->).
    Una sola instancia puede renderizar placas de distintos tamaños porque
    el viewport se ajusta por página, no por contexto global.
    """

    def __init__(self, config: ConfigPlaywrightHtml):
        if not config.templates_dir.exists():
            raise ErrorEstilo(
                f"Directorio de templates no existe: {config.templates_dir}"
            )
        if not config.output_dir.exists():
            config.output_dir.mkdir(parents=True, exist_ok=True)

        self.cfg = config
        self._cache_imagenes: dict[str, str] = {}
        self._cache_templates: dict[str, str] = {}
        self._cache_metadata: dict[str, TemplateMetadata] = {}

        self._playwright = None
        self._browser: Optional[Browser] = None

    def nombre(self) -> str:
        return "playwright_html"

    def __enter__(self):
        self._iniciar_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cerrar()

    def _iniciar_browser(self):
        """Lanza Playwright + Chromium headless. Una sola vez."""
        if self._browser is not None:
            return
        log.info("Iniciando Playwright + Chromium headless")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)

    def cerrar(self):
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    def _cargar_template(self, nombre_template: str) -> tuple[str, TemplateMetadata]:
    """Carga el HTML y su metadata. Cachea ambos.

    nombre_template viene con prefijo de plataforma (ej: 'Meta_default_4x5').
    El archivo HTML base no tiene prefijo ('default_4x5.html'), así que
    lo sacamos para encontrar el archivo.
    """
    if nombre_template in self._cache_templates:
        return self._cache_templates[nombre_template], self._cache_metadata[nombre_template]

    # Quitar prefijo de plataforma (Meta_ o TikTok_) para encontrar el HTML base
    nombre_base = nombre_template
    for prefijo in ("Meta_", "TikTok_"):
        if nombre_base.startswith(prefijo):
            nombre_base = nombre_base[len(prefijo):]
            break

    path = self.cfg.templates_dir / f"{nombre_base}.html"
    if not path.exists():
        raise ErrorEstilo(
            f"Template '{nombre_template}' (base: '{nombre_base}') no encontrado en {path}"
        )

    with open(path, encoding="utf-8") as f:
        contenido = f.read()

    metadata = parsear_metadata_template(contenido, nombre_template)

    self._cache_templates[nombre_template] = contenido
    self._cache_metadata[nombre_template] = metadata
    return contenido, metadata

    def _descargar_imagen_a_base64(self, url: str) -> str:
        if not url:
            raise ErrorEstilo("URL de imagen vacía")

        if url in self._cache_imagenes:
            return self._cache_imagenes[url]

        try:
            resp = requests.get(url, timeout=self.cfg.download_timeout_seg)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise ErrorEstilo(f"Falló descarga de imagen {url}: {e}") from e

        content_type = resp.headers.get("Content-Type", "image/jpeg")
        content_type = content_type.split(";")[0].strip()

        b64 = base64.b64encode(resp.content).decode("ascii")
        data_uri = f"data:{content_type};base64,{b64}"

        self._cache_imagenes[url] = data_uri
        log.debug("Imagen descargada y cacheada: %s (%d bytes)", url, len(resp.content))
        return data_uri

    def _construir_variables(
        self, producto: Producto, decision: DecisionSeleccion
    ) -> dict[str, str]:
        precio_original = producto.precio_lista

        if producto.precio_promocional is not None and producto.precio_promocional > 0:
            precio_hotsale = producto.precio_promocional
        else:
            precio_hotsale = precio_original * self.cfg.hotsale_discount_factor

        precio_efectivo: Optional[float] = None
        if self.cfg.descuento_efectivo_factor is not None:
            precio_efectivo = precio_hotsale * self.cfg.descuento_efectivo_factor

        base_cuota = precio_hotsale if self.cfg.cuotas_sobre_promocional else precio_original
        cuota = calcular_cuota(base_cuota, producto.cuotas_num)

        imagen_b64 = self._descargar_imagen_a_base64(producto.imagen_url)

        logo_url = self.cfg.variables_globales.get("logo_url", "")
        if not logo_url:
            raise ErrorEstilo(
                "Falta 'logo_url' en variables_globales del pipeline.yaml"
            )
        logo_b64 = self._descargar_imagen_a_base64(logo_url)

        variables = {
            "sku": producto.sku,
            "nombre": producto.nombre,
            "marca": producto.marca,
            "categoria": producto.categoria,
            "imagen_b64": imagen_b64,
            "logo_b64": logo_b64,
            "precio_lista": str(precio_original),
            "precio_promocional": str(precio_hotsale),
            "precio_original_formateado": formatear_precio_ars(precio_original),
            "precio_hotsale_formateado": formatear_precio_ars(precio_hotsale),
            "cuota_formateada": formatear_precio_ars(cuota),
            "cuotas_num": str(producto.cuotas_num),
            **({
                "precio_efectivo": str(precio_efectivo),
                "precio_efectivo_formateado": formatear_precio_ars(precio_efectivo),
            } if precio_efectivo is not None else {}),
        }

        for k, v in self.cfg.variables_globales.items():
            if k not in variables:
                variables[k] = str(v)

        return variables

    def _reemplazar_variables(self, html: str, variables: dict[str, str]) -> str:
        resultado = html
        for nombre, valor in variables.items():
            resultado = resultado.replace("{" + nombre + "}", valor)

        no_reemplazados = re.findall(r"\{([a-z_]+)\}", resultado)
        if no_reemplazados:
            log.warning(
                "Placeholders sin reemplazar en template: %s",
                set(no_reemplazados),
            )

        return resultado

    def _renderizar_html_a_png(
        self, html: str, path_destino: Path, width: int, height: int
    ) -> None:
        """Genera el PNG usando un context con las dimensiones específicas."""
        if self._browser is None:
            self._iniciar_browser()

        context = self._browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
        )
        page = context.new_page()
        try:
            page.set_content(html, wait_until="networkidle", timeout=30_000)
            page.screenshot(
                path=str(path_destino),
                full_page=False,
                type="png",
                omit_background=False,
            )
        finally:
            page.close()
            context.close()

    def renderizar(
        self, producto: Producto, decision: DecisionSeleccion
    ) -> Placa:
        """Renderiza la placa de UN producto con UN template.

        Las dimensiones se leen del comentario <!-- META --> del template.
        """
        html_template, metadata = self._cargar_template(decision.template)
        log.info(
            "Renderizando %s (template=%s, %dx%d, aspect=%s)",
            producto.sku, decision.template,
            metadata.width, metadata.height, metadata.aspect_ratio,
        )

        variables = self._construir_variables(producto, decision)
        html_final = self._reemplazar_variables(html_template, variables)

        # Nombre del archivo: sku + template para no pisar entre placas distintas
        sku_sanitizado = _sanitizar_id(producto.sku)
        template_sanitizado = _sanitizar_id(decision.template)
        path_png = self.cfg.output_dir / f"{sku_sanitizado}__{template_sanitizado}.png"

        self._renderizar_html_a_png(
            html_final, path_png, metadata.width, metadata.height,
        )

        return Placa(
            sku=producto.sku,
            template_usado=decision.template,
            path_local=str(path_png),
            width=metadata.width,
            height=metadata.height,
            aspect_ratio=metadata.aspect_ratio,
        )


def _sanitizar_id(valor: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", valor.strip())
