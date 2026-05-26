"""Motor de estilo: render de placas con Playwright (HTML → PNG).

Flujo:
1. Cargar template HTML del cliente (clients/{cliente}/templates/{template}.html)
2. Descargar imagen del producto + logo del cliente → convertir a base64
3. Calcular variables derivadas (precio formateado, cuota, etc.)
4. Reemplazar todos los placeholders {variable} en el HTML
5. Renderizar con Playwright headless Chromium → PNG en disco
6. Devolver Placa apuntando al PNG

Diseño:
- 1 instancia del motor por run del pipeline (reutiliza el browser de Playwright)
- Usar context manager: el browser se cierra al final del with
- Imágenes se cachean en memoria por URL (si 50 productos comparten logo,
  no lo descargamos 50 veces)
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

from src.core.modelo_datos import Producto, DecisionSeleccion, Placa
from src.estilo.base import MotorEstilo, ErrorEstilo


log = logging.getLogger(__name__)


# ============ Config ============

@dataclass
class ConfigPlaywrightHtml:
    """Config del motor de estilo HTML."""
    # Path al directorio con los HTML templates del cliente
    templates_dir: Path

    # Path al directorio donde se guardan las placas renderizadas
    output_dir: Path

    # Dimensiones de la placa (Meta/TikTok feed: 1080x1350)
    placa_width: int = 1080
    placa_height: int = 1350

    # Variables globales accesibles en todos los templates del cliente
    # (vienen del pipeline.yaml: brand_name, logo_url, evento_legal, etc.)
    variables_globales: dict = field(default_factory=dict)

    # Factor para calcular el precio promocional desde precio_lista cuando
    # la fuente no lo provee (legado de Mora v1). 1.0 = sin descuento adicional.
    hotsale_discount_factor: float = 1.0

    # Factor de descuento adicional para "precio efectivo" (ej. pago en
    # efectivo / transferencia). Opt-in por cliente: si es None, no se
    # calcula la variable y los templates siguen igual.
    # MoraShop usa 0.85 (15% off sobre el precio promocional).
    descuento_efectivo_factor: Optional[float] = None

    # Si True, calcula cuotas sobre precio_hotsale (promocional) en vez de
    # precio_lista. Refleja que las cuotas sin interés se aplican sobre el
    # precio web actual, no sobre el tachado.
    # Default False = comportamiento legado (cuotas sobre precio_lista).
    cuotas_sobre_promocional: bool = False

    # Timeout en ms para descargar imágenes
    download_timeout_seg: int = 15


# ============ Helpers de formateo ============

def formatear_precio_ars(valor: float) -> str:
    """Formatea un float a string con separadores de miles estilo argentino.

    1234567.89 → '$1.234.567'
    97656.0 → '$97.656'

    Se redondea a entero porque las placas no muestran decimales (mirar v1).
    """
    entero = int(round(valor))
    # Separador de miles con punto (formato AR)
    formateado = f"{entero:,}".replace(",", ".")
    return f"${formateado}"


def calcular_cuota(precio_base: float, cuotas_num: int = 3) -> float:
    """Calcula el monto de cada cuota.

    El precio base sobre el que se calcula viene del caller. Históricamente
    era precio_lista; con el flag `cuotas_sobre_promocional` ahora puede ser
    precio_hotsale.
    """
    if cuotas_num <= 0:
        return precio_base
    return precio_base / cuotas_num


# ============ Motor ============

class PlaywrightHtmlEstilo(MotorEstilo):
    """Renderiza placas usando templates HTML + Playwright headless."""

    def __init__(self, config: ConfigPlaywrightHtml):
        if not config.templates_dir.exists():
            raise ErrorEstilo(
                f"Directorio de templates no existe: {config.templates_dir}"
            )
        if not config.output_dir.exists():
            config.output_dir.mkdir(parents=True, exist_ok=True)

        self.cfg = config

        # Cache de imágenes descargadas (URL → base64 data URI)
        # Se vacía cuando el motor se destruye
        self._cache_imagenes: dict[str, str] = {}

        # Cache de templates ya cargados desde disco (path → contenido HTML)
        self._cache_templates: dict[str, str] = {}

        # Playwright se inicializa lazy (al primer renderizar)
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    def nombre(self) -> str:
        return "playwright_html"

    # ---------- Context manager ----------

    def __enter__(self):
        self._iniciar_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cerrar()

    def _iniciar_browser(self):
        """Lanza Playwright + Chromium headless. Una sola vez por instancia."""
        if self._browser is not None:
            return
        log.info("Iniciando Playwright + Chromium headless")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(
            viewport={
                "width": self.cfg.placa_width,
                "height": self.cfg.placa_height,
            },
            device_scale_factor=1,  # 1080x1350 reales, sin retina
        )

    def cerrar(self):
        """Cierra Playwright. Idempotente."""
        if self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None

    # ---------- Helpers ----------

    def _cargar_template(self, nombre_template: str) -> str:
        """Carga el HTML del template desde disco. Cachea en memoria."""
        if nombre_template in self._cache_templates:
            return self._cache_templates[nombre_template]

        path = self.cfg.templates_dir / f"{nombre_template}.html"
        if not path.exists():
            raise ErrorEstilo(
                f"Template '{nombre_template}' no encontrado en {path}"
            )

        with open(path, encoding="utf-8") as f:
            contenido = f.read()

        self._cache_templates[nombre_template] = contenido
        return contenido

    def _descargar_imagen_a_base64(self, url: str) -> str:
        """Descarga una imagen y la devuelve como data URI base64.

        Usa cache: si la URL ya fue descargada en este run, no se vuelve a pedir.

        Returns:
            String con formato 'data:image/jpeg;base64,...' (listo para meter
            en src="..." de un <img>).

        Raises:
            ErrorEstilo si la descarga falla.
        """
        if not url:
            raise ErrorEstilo("URL de imagen vacía")

        if url in self._cache_imagenes:
            return self._cache_imagenes[url]

        try:
            resp = requests.get(url, timeout=self.cfg.download_timeout_seg)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise ErrorEstilo(f"Falló descarga de imagen {url}: {e}") from e

        # Detectar content-type. Si no viene, asumimos JPEG (caso típico TN).
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        # Limpiar parámetros tipo "image/jpeg; charset=binary"
        content_type = content_type.split(";")[0].strip()

        b64 = base64.b64encode(resp.content).decode("ascii")
        data_uri = f"data:{content_type};base64,{b64}"

        self._cache_imagenes[url] = data_uri
        log.debug("Imagen descargada y cacheada: %s (%d bytes)", url, len(resp.content))
        return data_uri

    def _construir_variables(
        self, producto: Producto, decision: DecisionSeleccion
    ) -> dict[str, str]:
        """Arma el diccionario de {variable: valor} para reemplazar en el HTML.

        Las variables son las que usa v1, para que el porteo del template
        sea sin tocar nada.

        Variables de precio expuestas:
          - precio_original_formateado: precio_lista tachado (web compare_at)
          - precio_hotsale_formateado:  precio_promocional o lista*factor
          - precio_efectivo_formateado: precio_hotsale * descuento_efectivo_factor
                                        (solo si el cliente lo configuró)
          - cuota_formateada:           cuota sobre lista o sobre hotsale,
                                        según cuotas_sobre_promocional
        """
        # Precio original = precio_lista (lo tachado en placas estándar)
        precio_original = producto.precio_lista

        # Precio "hotsale" = el promocional si existe, sino el lista * factor
        # En v1, hotsale_discount_factor=1.0 implica que el precio promocional
        # ES el precio efectivo de la promo.
        if producto.precio_promocional is not None and producto.precio_promocional > 0:
            precio_hotsale = producto.precio_promocional
        else:
            # No hay promo: el "precio hotsale" es el lista (la placa se va
            # a ver "rara" pero no rompemos el run, decisión de Faco)
            precio_hotsale = precio_original * self.cfg.hotsale_discount_factor

        # Precio "efectivo" (opt-in por cliente vía descuento_efectivo_factor).
        # Aplica un factor adicional SOBRE precio_hotsale.
        # Caso MoraShop: precio_hotsale es el precio web (TN ya tiene 5% off),
        # y descuento_efectivo_factor=0.85 lo lleva al precio final en efectivo.
        # Si el factor no está seteado, la variable no se expone.
        precio_efectivo: Optional[float] = None
        if self.cfg.descuento_efectivo_factor is not None:
            precio_efectivo = precio_hotsale * self.cfg.descuento_efectivo_factor

        # Cuota: base depende del cliente.
        # - cuotas_sobre_promocional=False (default legado): sobre precio_lista
        # - cuotas_sobre_promocional=True (caso Mora): sobre precio_hotsale
        # En ambos casos las cuotas se calculan sobre el precio que se paga
        # cuando NO es efectivo (las cuotas no son en efectivo).
        base_cuota = precio_hotsale if self.cfg.cuotas_sobre_promocional else precio_original
        cuota = calcular_cuota(base_cuota, producto.cuotas_num)

        # Descargar imágenes a base64
        imagen_b64 = self._descargar_imagen_a_base64(producto.imagen_url)

        logo_url = self.cfg.variables_globales.get("logo_url", "")
        if not logo_url:
            raise ErrorEstilo(
                "Falta 'logo_url' en variables_globales del pipeline.yaml"
            )
        logo_b64 = self._descargar_imagen_a_base64(logo_url)

        variables = {
            # Identificación
            "sku": producto.sku,
            "nombre": producto.nombre,
            "marca": producto.marca,
            "categoria": producto.categoria,

            # Imágenes (base64 inline)
            "imagen_b64": imagen_b64,
            "logo_b64": logo_b64,

            # Precios crudos (por si algún template los necesita sin formato)
            "precio_lista": str(precio_original),
            "precio_promocional": str(precio_hotsale),

            # Precios formateados (los que usa el template v1)
            "precio_original_formateado": formatear_precio_ars(precio_original),
            "precio_hotsale_formateado": formatear_precio_ars(precio_hotsale),
            "cuota_formateada": formatear_precio_ars(cuota),

            # Metadata
            "cuotas_num": str(producto.cuotas_num),

            # Precio efectivo (solo si el cliente lo configuró)
            **({
                "precio_efectivo": str(precio_efectivo),
                "precio_efectivo_formateado": formatear_precio_ars(precio_efectivo),
            } if precio_efectivo is not None else {}),
        }

        # Mergear variables globales del pipeline.yaml
        # (brand_name, evento_legal, etc.). Si una global pisa una calculada,
        # gana la calculada (no querés que un yaml mal escrito rompa la placa).
        for k, v in self.cfg.variables_globales.items():
            if k not in variables:
                variables[k] = str(v)

        return variables

    def _reemplazar_variables(self, html: str, variables: dict[str, str]) -> str:
        """Reemplaza todos los {nombre_var} en el HTML por su valor.

        Usa replace simple (no Jinja). Es lo mismo que hace v1.
        Si una variable referenciada en el HTML no existe en `variables`,
        queda como `{nombre_var}` literal (no se rompe, pero se loggea warning).
        """
        resultado = html
        for nombre, valor in variables.items():
            resultado = resultado.replace("{" + nombre + "}", valor)

        # Detectar placeholders no reemplazados (warning, no error)
        no_reemplazados = re.findall(r"\{([a-z_]+)\}", resultado)
        # Filtramos falsos positivos: CSS puede tener {} en otros contextos,
        # pero el patrón [a-z_]+ es lo bastante específico para variables nuestras.
        # OJO: si esto da falsos positivos, hay que afinar el regex.
        if no_reemplazados:
            log.warning(
                "Placeholders sin reemplazar en template: %s",
                set(no_reemplazados),
            )

        return resultado

    def _renderizar_html_a_png(self, html: str, path_destino: Path) -> None:
        """Toma HTML inline y genera el PNG en disco usando Playwright."""
        if self._browser is None:
            self._iniciar_browser()

        page = self._context.new_page()
        try:
            # set_content carga el HTML directamente, sin pasar por filesystem
            # ni servidor. Las imágenes ya están en base64 inline, así que
            # no necesita acceso a red.
            page.set_content(html, wait_until="networkidle", timeout=30_000)

            # Screenshot del viewport completo (1080x1350)
            page.screenshot(
                path=str(path_destino),
                full_page=False,  # solo viewport
                type="png",
                omit_background=False,
            )
        finally:
            page.close()

    # ---------- API pública ----------

    def renderizar(
        self, producto: Producto, decision: DecisionSeleccion
    ) -> Placa:
        """Renderiza la placa de UN producto.

        Las dimensiones vienen del config del motor (placa_width/height),
        así que para generar 4:5 y 9:16 hay que instanciar 2 motores con
        configs distintas. El aspect_ratio del config se propaga a la placa
        resultante, y se incluye en el nombre del archivo para no pisar.
        """
        log.info("Renderizando %s (template=%s, %dx%d)",
                 producto.sku, decision.template,
                 self.cfg.placa_width, self.cfg.placa_height)

        # 1. Cargar template
        html_template = self._cargar_template(decision.template)

        # 2. Construir variables (incluye descargar imágenes a base64)
        variables = self._construir_variables(producto, decision)

        # 3. Reemplazar placeholders en el HTML
        html_final = self._reemplazar_variables(html_template, variables)

        # 4. Renderizar a PNG. El nombre del archivo incluye el aspect_ratio
        # para no pisar la placa 4:5 con la 9:16 cuando se renderizan ambas.
        sku_sanitizado = _sanitizar_sku(producto.sku)
        aspect = _aspect_ratio_label(self.cfg)
        if aspect == "4:5":
            # retrocompat: no agregamos sufijo a la 4:5 (mantiene URLs viejas)
            sufijo = ""
        else:
            # "9:16" → "_9x16" (los : no son válidos en URLs / filenames)
            sufijo = "_" + aspect.replace(":", "x")
        path_png = self.cfg.output_dir / f"{sku_sanitizado}{sufijo}.png"

        self._renderizar_html_a_png(html_final, path_png)

        return Placa(
            sku=producto.sku,
            template_usado=decision.template,
            path_local=str(path_png),
            width=self.cfg.placa_width,
            height=self.cfg.placa_height,
            aspect_ratio=aspect,
        )


def _aspect_ratio_label(cfg: "ConfigPlaywrightHtml") -> str:
    """Calcula el label de aspect ratio desde las dimensiones del config.

    1080x1350 → "4:5"
    1080x1920 → "9:16"
    Si no coincide con ninguno conocido, usa la fracción literal.
    """
    w, h = cfg.placa_width, cfg.placa_height
    if (w, h) == (1080, 1350):
        return "4:5"
    if (w, h) == (1080, 1920):
        return "9:16"
    # Fallback: simplificar fracción (no crítico, solo etiqueta)
    from math import gcd
    g = gcd(w, h) or 1
    return f"{w // g}:{h // g}"


def _sanitizar_sku(sku: str) -> str:
    """Convierte un SKU a un nombre de archivo seguro.

    'GOLDNU0 CREA 300G' → 'GOLDNU0_CREA_300G'
    """
    # Solo permitir alfanumérico, guión y guión bajo
    return re.sub(r"[^A-Za-z0-9_\-]", "_", sku.strip())
