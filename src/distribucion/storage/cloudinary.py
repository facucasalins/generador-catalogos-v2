"""Storage: subir placas a Cloudinary.

Diseño:
- 1 instancia del storage por run del pipeline.
- public_id determinístico: `{folder}/{sku_sanitizado}`. Mismo SKU = misma URL.
- overwrite=True: si la placa cambió, se reemplaza en Cloudinary.
- invalidate=True: borra el cache de CDN para que Meta/TikTok vean la nueva imagen
  inmediatamente (no esperan TTL).

Lecciones de v1:
- v1 usaba folder "morashop/". v2 usa "morashop-v2/" para no pisar v1 durante
  la migración paralela (decisión #3 en DECISIONES.md).
"""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import cloudinary
import cloudinary.uploader

from src.core.modelo_datos import Placa, PlacaSubida
from src.distribucion.storage.base import StorageBackend, ErrorStorage


log = logging.getLogger(__name__)


@dataclass
class ConfigCloudinary:
    """Config para el storage Cloudinary."""
    cloud_name: str
    api_key: str
    api_secret: str

    # Carpeta dentro de Cloudinary donde se suben las placas del cliente.
    # Ej: "morashop-v2" → URL final: cloudinary.com/.../morashop-v2/SKU.png
    folder: str

    # Timeout para cada subida individual
    timeout_segundos: int = 60


class CloudinaryStorage(StorageBackend):
    """Sube placas a Cloudinary con public_id determinístico."""

    def __init__(self, config: ConfigCloudinary):
        if not config.cloud_name:
            raise ErrorStorage("ConfigCloudinary.cloud_name es obligatorio")
        if not config.api_key:
            raise ErrorStorage("ConfigCloudinary.api_key es obligatorio")
        if not config.api_secret:
            raise ErrorStorage("ConfigCloudinary.api_secret es obligatorio")
        if not config.folder:
            raise ErrorStorage("ConfigCloudinary.folder es obligatorio")

        self.cfg = config

        # Cloudinary tiene un cliente global stateful. Lo configuramos UNA vez.
        cloudinary.config(
            cloud_name=config.cloud_name,
            api_key=config.api_key,
            api_secret=config.api_secret,
            secure=True,  # devolver URLs https://
        )

    def nombre(self) -> str:
        return "cloudinary"

    def _public_id(self, sku: str, aspect_ratio: str = "4:5") -> str:
        """Convierte SKU + aspect_ratio a public_id (sin extensión, con folder).

        '4:5':  'GOLDNU0 CREA 300G' → 'morashop-v2/GOLDNU0_CREA_300G'
        '9:16': 'GOLDNU0 CREA 300G' → 'morashop-v2/GOLDNU0_CREA_300G_9x16'

        Importante: el sanitizado debe ser el MISMO que usa playwright_html
        (para que el nombre del PNG en disco coincida con el public_id).
        4:5 sin sufijo mantiene retrocompat con URLs viejas pre-Fase H.
        """
        sku_sanitizado = _sanitizar_sku(sku)
        if aspect_ratio == "4:5":
            sufijo = ""
        else:
            sufijo = "_" + aspect_ratio.replace(":", "x")
        return f"{self.cfg.folder}/{sku_sanitizado}{sufijo}"

    def subir(self, placa: Placa) -> PlacaSubida:
        """Sube una placa a Cloudinary y devuelve la URL pública."""
        path = Path(placa.path_local)
        if not path.exists():
            raise ErrorStorage(f"No existe el PNG local: {path}")

        public_id = self._public_id(placa.sku, placa.aspect_ratio)
        log.info("Subiendo a Cloudinary: %s [%s] → %s",
                 placa.sku, placa.aspect_ratio, public_id)

        try:
            response = cloudinary.uploader.upload(
                str(path),
                public_id=public_id,
                # No agregar el folder por separado; ya está en public_id
                use_filename=False,
                unique_filename=False,
                overwrite=True,       # mismo SKU = misma URL, reemplaza
                invalidate=True,      # purga CDN cache (Meta/TikTok ven cambio al instante)
                resource_type="image",
                # Tags útiles para gestión en Cloudinary
                tags=[self.cfg.folder, f"sku:{placa.sku}", f"template:{placa.template_usado}"],
                timeout=self.cfg.timeout_segundos,
            )
        except Exception as e:
            # cloudinary lanza varios tipos de excepciones según el problema
            raise ErrorStorage(
                f"Falló subida de {placa.sku} a Cloudinary: {e}"
            ) from e

        url_publica = response.get("secure_url")
        if not url_publica:
            raise ErrorStorage(
                f"Cloudinary no devolvió secure_url para {placa.sku}. "
                f"Respuesta: {response}"
            )

        return PlacaSubida(
            sku=placa.sku,
            url_publica=url_publica,
            storage_backend="cloudinary",
            aspect_ratio=placa.aspect_ratio,
        )

    def borrar(self, sku: str) -> bool:
        """Borra TODAS las imágenes de un SKU en Cloudinary (4:5 y 9:16).

        Usado por la limpieza de SKUs huérfanos al final del pipeline.

        Args:
            sku: SKU del producto. Borra el public_id base + cualquier variante
                con sufijo de aspect_ratio (_9x16).

        Returns:
            True si TODOS los aspect_ratios se borraron (o no existían).
            False si alguno falló.
            Nunca raisea: el borrado es best-effort.
        """
        # Intentamos borrar las dos variantes. Si Mora todavía no tiene 9:16,
        # el 'not found' es válido y cuenta como éxito.
        aspect_ratios_a_borrar = ["4:5", "9:16"]
        todo_ok = True
        for ar in aspect_ratios_a_borrar:
            public_id = self._public_id(sku, ar)
            log.info("Cloudinary: borrando %s [%s] (public_id=%s)", sku, ar, public_id)
            try:
                result = cloudinary.uploader.destroy(
                    public_id, resource_type="image", invalidate=True,
                )
                res = result.get("result", "")
                if res not in ("ok", "not found"):
                    log.warning("Cloudinary: borrado de %s [%s] devolvió result=%s",
                                sku, ar, res)
                    todo_ok = False
            except Exception as e:
                log.warning("Cloudinary: falló borrado de %s [%s]: %s", sku, ar, e)
                todo_ok = False
        return todo_ok


def _sanitizar_sku(sku: str) -> str:
    """Sanea SKU para usar como public_id.

    DEBE coincidir con la función de playwright_html._sanitizar_sku (no la
    importamos directo para mantener los bloques desacoplados, pero la lógica
    es idéntica — si cambia una, hay que cambiar la otra).
    """
    return re.sub(r"[^A-Za-z0-9_\-]", "_", sku.strip())
