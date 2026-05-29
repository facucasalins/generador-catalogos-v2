"""Storage: subir placas a Cloudinary (multi-template).

Diseño:
- 1 instancia del storage por run del pipeline.
- public_id determinístico: `{folder}/{sku_sanitizado}__{template_sanitizado}`.
  Mismo (SKU, template) = misma URL. Un SKU con N templates genera N URLs.
- overwrite=True: si la placa cambió, se reemplaza en Cloudinary.
- invalidate=True: borra el cache de CDN para que Meta/TikTok vean la nueva
  imagen inmediatamente (no esperan TTL).
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path

import cloudinary
import cloudinary.uploader

from src.core.modelo_datos import Placa, PlacaSubida
from src.core.templates import sanitizar_id
from src.distribucion.storage.base import StorageBackend, ErrorStorage


log = logging.getLogger(__name__)


@dataclass
class ConfigCloudinary:
    """Config para el storage Cloudinary."""
    cloud_name: str
    api_key: str
    api_secret: str

    # Carpeta dentro de Cloudinary donde se suben las placas del cliente.
    # Ej: "antonia" → URL final: cloudinary.com/.../antonia/SKU__TEMPLATE.png
    folder: str

    # Timeout para cada subida individual
    timeout_segundos: int = 60


class CloudinaryStorage(StorageBackend):
    """Sube placas a Cloudinary con public_id determinístico por (SKU, template)."""

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

    def _public_id(self, sku: str, template: str) -> str:
        """Convierte (sku, template) a public_id (sin extensión, con folder).

        Ej: ('bota-soraya-negro', 'default_4x5')
            → 'antonia/bota-soraya-negro__default_4x5'

        Importante: usa el MISMO sanitizador (sanitizar_id, en src/core/
        templates.py) que playwright_html para el nombre del PNG, para que
        el archivo en disco y el public_id coincidan.
        """
        sku_sanitizado = sanitizar_id(sku)
        template_sanitizado = sanitizar_id(template)
        return f"{self.cfg.folder}/{sku_sanitizado}__{template_sanitizado}"

    def subir(self, placa: Placa) -> PlacaSubida:
        """Sube una placa a Cloudinary y devuelve la URL pública."""
        path = Path(placa.path_local)
        if not path.exists():
            raise ErrorStorage(f"No existe el PNG local: {path}")

        public_id = self._public_id(placa.sku, placa.template_usado)
        log.info("Subiendo a Cloudinary: %s [%s] → %s",
                 placa.sku, placa.template_usado, public_id)

        try:
            response = cloudinary.uploader.upload(
                str(path),
                public_id=public_id,
                use_filename=False,
                unique_filename=False,
                overwrite=True,
                invalidate=True,
                resource_type="image",
                tags=[
                    self.cfg.folder,
                    f"sku:{placa.sku}",
                    f"template:{placa.template_usado}",
                ],
                timeout=self.cfg.timeout_segundos,
            )
        except Exception as e:
            raise ErrorStorage(
                f"Falló subida de {placa.sku}/{placa.template_usado} a Cloudinary: {e}"
            ) from e

        url_publica = response.get("secure_url")
        if not url_publica:
            raise ErrorStorage(
                f"Cloudinary no devolvió secure_url para {placa.sku}/{placa.template_usado}. "
                f"Respuesta: {response}"
            )

        return PlacaSubida(
            sku=placa.sku,
            template_usado=placa.template_usado,
            url_publica=url_publica,
            storage_backend="cloudinary",
            aspect_ratio=placa.aspect_ratio,
        )

    def borrar(self, public_id_relativo: str) -> bool:
        """Borra una placa de Cloudinary por su public_id.

        Args:
            public_id_relativo: identificador relativo de la placa, formato
                'sku__template' (sin el prefijo del folder).

        Returns:
            True si se borró o no existía. False si falló por otro motivo.
            Nunca raisea: el borrado es best-effort.
        """
        # Si el caller pasa solo 'sku__template' (sin folder), agregamos folder.
        # Si pasa 'folder/sku__template', lo usamos tal cual.
        if "/" not in public_id_relativo:
            public_id = f"{self.cfg.folder}/{public_id_relativo}"
        else:
            public_id = public_id_relativo

        log.info("Cloudinary: borrando %s", public_id)
        try:
            result = cloudinary.uploader.destroy(
                public_id, resource_type="image", invalidate=True,
            )
            res = result.get("result", "")
            if res in ("ok", "not found"):
                return True
            log.warning("Cloudinary: borrado de %s devolvió result=%s", public_id, res)
            return False
        except Exception as e:
            log.warning("Cloudinary: falló borrado de %s: %s", public_id, e)
            return False
