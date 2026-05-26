# Generador de Catálogos v2

Sistema multi-cliente para generar **placas de producto automáticamente** y publicarlas como catálogos de Meta y TikTok.

Cada día, para cada cliente, el pipeline:
1. Lee inventario desde Tiendanube
2. Selecciona los SKUs marcados por el cliente
3. Enriquece textos con IA (Gemini)
4. Renderiza placas con HTML+Playwright (4:5 para Meta, 9:16 para TikTok)
5. Sube las imágenes a Cloudinary
6. Escribe los feeds a Google Sheets listos para Meta/TikTok Catalog Manager

Notifica el resultado por Telegram. Funciona en GitHub Actions.

---

## 🚀 Quickstart

**¿Querés agregar un cliente nuevo?**
→ Leé **[`docs/01-quickstart-nuevo-cliente.md`](docs/01-quickstart-nuevo-cliente.md)**.

**¿Querés diseñar templates para un cliente?**
→ Leé **[`docs/02-diseno-templates.md`](docs/02-diseno-templates.md)**.

**¿Querés entender cómo funciona el sistema por dentro?**
→ Leé **[`docs/03-arquitectura.md`](docs/03-arquitectura.md)**.

**¿Algo no anda?**
→ Leé **[`docs/04-troubleshooting.md`](docs/04-troubleshooting.md)**.

---

## Clientes activos

| Cliente | Estado | Industria | Cron |
|---|---|---|---|
| MoraShop | ✅ Activo | Suplementos + electrohogar | 06:00 ART diario |
| Shark | 🟡 Pendiente | Ropa deportiva | - |
| Juanita Shoes | 🟡 Pendiente | Calzado femenino | - |
| Antonia | 🟡 Pendiente | Calzado femenino | - |

---

## Stack técnico

- **Lenguaje**: Python 3.11
- **Orquestación**: GitHub Actions (1 workflow por cliente)
- **Inventario**: Tiendanube API
- **IA**: Google Gemini 2.5 Flash
- **Renderizado**: Playwright + HTML/CSS
- **Storage**: Cloudinary (folder por cliente)
- **Destinos**: Google Sheets (publica feed CSV)
- **Notificaciones**: Telegram Bot
- **Tests**: pytest (147 tests, corren en CI)

---

## Estructura del repo

```
generador-catalogos-v2/
├── .github/workflows/        ← 1 workflow YAML por cliente
├── clients/                  ← CONFIGURACIÓN por cliente (pipeline.yaml + templates)
│   ├── morashop/
│   ├── shark/
│   └── ...
├── src/                      ← CÓDIGO compartido entre clientes
├── tests/                    ← 147 tests automatizados
├── scripts/
│   └── preview_template.py   ← preview local de templates (sin correr el pipeline)
├── docs/                     ← esta documentación
└── requirements.txt
```

**Principio fundamental**: agregar un cliente nuevo NO requiere tocar `src/`. Solo agregás una carpeta en `clients/` y un workflow YAML en `.github/workflows/`.

---

## Workflows en cada uno

| Workflow | Qué hace | Cuándo corre |
|---|---|---|
| `morashop-v2.yml` | Pipeline completo de Mora | Cron diario 06:00 ART + manual |
| `shark.yml` | Pipeline completo de Shark | - |
| `ci.yml` | Corre `pytest tests/` | En cada push |

---

## Desarrollo local

```bash
# Setup
pip install -r requirements.txt
playwright install chromium

# Correr tests
pytest tests/ -v

# Previsualizar un template
python scripts/preview_template.py --cliente=morashop --template=default
```

---

## Contacto

- Mantenedor: Facu (Agency Nusa)
- Decisiones de diseño: ver `docs/03-arquitectura.md`
- Algo no anda: `docs/04-troubleshooting.md` o mandame log del run
