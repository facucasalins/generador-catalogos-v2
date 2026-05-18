# generador-catalogos-v2

> 🚧 **Sistema en construcción** — Este es un repositorio nuevo. v1 (`generador-catalogos`) sigue corriendo en producción.

Pipeline modular para generar placas publicitarias y feeds de catálogo para Meta Ads, TikTok Ads y otros destinos. Diseñado para escalar a múltiples clientes de Agency Nusa.

## Estado actual

**Fase A — Setup de infraestructura** (en curso).

Ver [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) para el diseño completo.

## ¿Por qué v2?

v1 funciona pero está acoplado al caso de MoraShop, con varios pasos manuales no documentados y un Apps Script roto. v2 implementa la arquitectura de 5 bloques modulares descrita en `ARCHITECTURE.md`:

```
Inventario → Selección → Enriquecimiento → Estilo → Distribución
```

Sumar un cliente nuevo en v2 debe tomar ≤30 minutos sin escribir código.

## Reglas críticas durante el desarrollo

1. **NO TOCAR v1.** Mora v1 sigue corriendo en `generador-catalogos`. Cualquier cambio acá NO debe afectar producción.
2. **Migración con red de seguridad.** Mora v2 corre en paralelo a v1 durante mínimo 7 días antes de cualquier switch.
3. **Cloudinary, catálogos y sheets son SEPARADOS de v1**:
   - Cloudinary folder: `morashop-v2/` (NO `morashop/`)
   - Catálogos Meta/TikTok: `MoraShop V2 - *` (catálogos nuevos)
   - Sheets: carpeta nueva en Drive de Agency Nusa
4. **Cero modificación de campañas activas** durante la migración.

## Roadmap

Ver `docs/ARCHITECTURE.md` sección 11. Resumen:

| Mes | Hito |
|---|---|
| 1 | Mora-v2 corriendo en paralelo a v1 |
| 1 | Switch productivo: Mora 100% v2 |
| 2 | Onboarding de 1 cliente nuevo |
| 2 | Bloque Enriquecimiento con Gemini |
| 3 | Soporte Shopify |

## Estructura

Ver `docs/ARCHITECTURE.md` sección 5.

## Para empezar a contribuir

Antes de tocar cualquier código, leer en orden:

1. `docs/ARCHITECTURE.md` (entero)
2. `docs/DECISIONES.md` (decisiones tomadas y por qué)
3. `docs/ONBOARDING.md` (cuando lleguemos a sumar clientes)
