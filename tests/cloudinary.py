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

    def _public_id(self, sku: str) -> str:
        """Convierte SKU a public_id (sin extensión, con folder).

        'GOLDNU0 CREA 300G' → 'morashop-v2/GOLDNU0_CREA_300G'

        Importante: el sanitizado debe ser el MISMO que usa playwright_html
        (para que el nombre del PNG en disco coincida con el public_id).
        """
        sku_sanitizado = _sanitizar_sku(sku)
        return f"{self.cfg.folder}/{sku_sanitizado}"

    def subir(self, placa: Placa) -> PlacaSubida:
        """Sube una placa a Cloudinary y devuelve la URL pública."""
        path = Path(placa.path_local)
        if not path.exists():
            raise ErrorStorage(f"No existe el PNG local: {path}")

        public_id = self._public_id(placa.sku)
        log.info("Subiendo a Cloudinary: %s → %s", placa.sku, public_id)

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
        )


def _sanitizar_sku(sku: str) -> str:
    """Sanea SKU para usar como public_id.

    DEBE coincidir con la función de playwright_html._sanitizar_sku (no la
    importamos directo para mantener los bloques desacoplados, pero la lógica
    es idéntica — si cambia una, hay que cambiar la otra).
    """
    return re.sub(r"[^A-Za-z0-9_\-]", "_", sku.strip())
