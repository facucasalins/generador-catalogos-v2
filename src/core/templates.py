"""Utilidades compartidas para resolver nombres de templates.

Los templates se EXPONEN con prefijo de plataforma en la pestaña Seleccion
(ver src/seleccion/sync.py: sync_templates), por ejemplo 'Meta_default_4x5'
o 'TikTok_juanita_9x16'. Pero el archivo HTML en disco NO lleva prefijo
('default_4x5.html', 'juanita_9x16.html').

Tanto el motor de estilo (al cargar el HTML para renderizar) como el cálculo
de hash de regeneración (al leer el HTML para incluirlo en el hash) tienen
que resolver el MISMO archivo a partir del nombre prefijado. Si esa lógica
se desincroniza, el hash deja de reflejar el contenido real del template y
las placas no se regeneran al cambiar el diseño. Por eso vive acá, en una
sola función compartida.
"""
from __future__ import annotations

import re

# Prefijos de plataforma con los que se exponen los templates en la pestaña
# Seleccion. Mantener en sync con src/seleccion/sync.py (sync_templates).
PREFIJOS_PLATAFORMA = ("Meta_", "TikTok_")


def sanitizar_id(valor: str) -> str:
    """Sanea un sku/template para usarlo como ID estable.

    Se usa para DOS cosas que DEBEN coincidir exactamente:
      - el nombre del PNG en disco (motor de estilo), y
      - el public_id de Cloudinary (storage).
    Mismo (sku, template) → mismo ID → misma URL. Si las dos puntas no
    sanitizan igual, se rompen las subidas y la limpieza de huérfanos. Por
    eso vive en una sola función compartida (mismo motivo que
    nombre_base_template).

    Reemplaza cualquier carácter fuera de [A-Za-z0-9_-] por '_'.
    """
    return re.sub(r"[^A-Za-z0-9_\-]", "_", valor.strip())


def nombre_base_template(nombre_template: str) -> str:
    """Devuelve el nombre del HTML base, sin prefijo de plataforma.

        'Meta_default_4x5'   -> 'default_4x5'
        'TikTok_cuotas_9x16' -> 'cuotas_9x16'
        'default_4x5'        -> 'default_4x5'   (sin prefijo: igual)

    Solo quita el prefijo de plataforma del INICIO del nombre; no toca el
    resto (electro, innova, cuotas, juanita_4x5, etc. quedan intactos).
    """
    for prefijo in PREFIJOS_PLATAFORMA:
        if nombre_template.startswith(prefijo):
            return nombre_template[len(prefijo):]
    return nombre_template
