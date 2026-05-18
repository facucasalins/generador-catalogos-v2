# `_template/` — Plantilla para nuevos clientes

> 🚫 Esta carpeta es una **plantilla**. NO se procesa. El guion bajo del nombre la excluye.

## Cómo usarla

Cuando sumes un cliente nuevo:

1. Copiá esta carpeta entera a `clients/{nombre-cliente}/`
2. Renombrá `pipeline.yaml.example` a `pipeline.yaml`
3. Editá `pipeline.yaml` con los valores reales del cliente
4. Personalizá los templates HTML en `templates/`
5. Creá el workflow `.github/workflows/{nombre-cliente}.yml`

Ver `docs/ONBOARDING.md` para el paso a paso completo.

## Contenido

- `pipeline.yaml.example` — config de ejemplo con todos los bloques
- `templates/default.html` — placa visual de placeholder, REEMPLAZAR
- Esta carpeta vive en git para que cualquiera pueda clonar y empezar.
