# Cómo sumar un cliente nuevo

> ⏳ **Documento en construcción**. Se completa cuando esté terminado Mora v2 y validemos con un cliente real.

## Vista previa del proceso (objetivo: ≤30 minutos)

1. **Configurar fuente de inventario** (depende del módulo)
   - Si Tiendanube: completar OAuth flow → obtener tokens
   - Si Shopify: API key + store URL
   - Si CSV manual: nada

2. **Crear estructura en Drive** (Agency Nusa)
   - Carpeta del cliente dentro de "Generador de Catálogos"
   - 4 Sheets: Inventario, Selección, Enriquecimiento, Feed-Output

3. **Compartir Sheets con la Service Account** (Editor)

4. **Crear carpeta del cliente en el repo**
   - Copiar `clients/_template/` a `clients/{cliente}/`
   - Editar `pipeline.yaml` con valores reales
   - Personalizar templates HTML

5. **Configurar secrets específicos del cliente** en GitHub Actions
   - Tokens de la fuente de inventario
   - (Cloudinary y otros secrets compartidos NO se duplican)

6. **Crear workflow** `.github/workflows/{cliente}.yml`

7. **Run manual** y validar resultado

## Cuándo se completa este documento

Después de hacer el onboarding real del primer cliente nuevo (post-Mora v2). El proceso real se va a documentar tal como fue.
