# 04 - Troubleshooting

> Errores comunes y cómo resolverlos. Si lo que te pasa no está acá, pasame el log del run y lo agregamos.

---

## Cómo leer un workflow fallido

1. Andá a GitHub → **Actions**
2. Click en el run rojo (❌)
3. Click en el step que falló (tiene un ❌ rojo)
4. Scrolleá los logs hasta encontrar el **traceback** o mensaje de error

> **[SCREENSHOT: workflow rojo con step fallido]**

Buscá específicamente líneas con:
- `Traceback (most recent call last):` ← stack trace de Python
- `ERROR` o `CRITICAL` en los logs
- `Pipeline falló:` ← mensaje custom del cli

---

## Errores frecuentes

### 🔴 "Failed to fetch TN products" (Bloque 1)

**Síntoma**: el run falla en "Bloque 1: Inventario". Telegram dice "Bloque 1 (Inventario - TN no responde)".

**Causas posibles**:

1. **Tiendanube tuvo un blip de red**. El sistema ya reintenta 1 vez con 30s de espera. Si igual falla, esperá unos minutos y disparalo de nuevo manualmente.

2. **El access token venció o fue revocado**. Re-pedile acceso al cliente (ver `01-quickstart-nuevo-cliente.md` Paso 1) y actualizá el secret en GitHub.

3. **Store ID equivocado**. Verificá en el yaml que `store_id_secret` apunte a un secret con el valor correcto.

**Cómo verificar el secret**: Settings del repo → Secrets and variables → Actions. Los secrets no se pueden leer (solo sobrescribir). Si dudás, sobrescribilo con el valor correcto.

---

### 🟡 "Workflow verde pero pestañas vacías"

**Síntoma**: el workflow termina OK pero abrís el sheet Feed-Output y `Meta_default`, `TikTok_default`, etc están en 0 filas.

**Causa más común**: **el template no existe**. El workflow no falla porque el sistema saltea SKUs cuyo template no exista, pero ningún SKU encuentra su template → 0 filas.

**Cómo verificar**:

1. Andá al log del run → buscá líneas con `Template '...' no existe`
2. Te va a decir qué archivo estaba buscando, ej: `electrohogar_tiktok.html`
3. Verificá en `clients/<cliente>/templates/` que el archivo exista con ese nombre exacto

**Caso clásico**: en el sheet de Selección marcaste `template = electro` pero el archivo se llama `electrohogar.html`. Tienen que coincidir.

**Otro caso clásico**: querés generar 9:16 pero falta el archivo `<template>_tiktok.html`. Solo se genera la 4:5 → Meta tiene filas pero TikTok queda en 0.

---

### 🟡 "Pestañas Meta llenas pero TikTok vacías" (o al revés)

**Síntoma**: una de las dos pestañas (Meta o TikTok) tiene datos, la otra está vacía.

**Causa**: falta el template del aspect_ratio que no se llena.

- Si **Meta tiene datos y TikTok no** → falta `<template>_tiktok.html` para el aspect 9:16
- Si **TikTok tiene datos y Meta no** → falta `<template>.html` (el 4:5)

**Solución**: crear el archivo HTML faltante en `clients/<cliente>/templates/`.

---

### 🔴 "URLs muertas en las pestañas (404)"

**Síntoma**: el sheet tiene URLs de Cloudinary, pero al abrirlas en el browser tiran 404.

**Causa más común**: moviste/renombraste el folder en Cloudinary manualmente, pero las URLs viejas siguen en el historial.

**Solución**:

1. Andá al sheet de Inventario del cliente → pestaña `Historial_Placas`
2. Seleccioná todas las filas excepto el header → borrar
3. Disparás el workflow manual
4. Va a regenerar TODAS las placas y subirlas con URLs correctas

> **NOTA importante**: si querés mover/renombrar folders en Cloudinary, **avisame antes**. Es una operación delicada que puede dejar URLs huérfanas en producción.

---

### 🔴 "Cloudinary upload failed" o errores de API key

**Síntoma**: el run falla en Bloque 5.1. Mensaje tipo "Cloudinary authentication failed" o "Invalid signature".

**Causa**: las credenciales de Cloudinary están mal.

**Solución**:

1. Andá a https://cloudinary.com/console
2. Copy `Cloud name`, `API Key`, `API Secret`
3. Actualizá los secrets de GitHub (`CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`)

---

### 🟡 "Telegram no notifica nada"

**Síntoma**: el workflow corre OK (verde) pero no llega notificación a Telegram.

**Causas posibles**:

1. **El bot no está agregado al chat**. Verificá que `@Generadorplacas17_bot` esté en el chat (Mora actual).
2. **`TELEGRAM_CHAT_ID` está mal**. Verificá el secret. Para Mora es `7186034803`.
3. **`TELEGRAM_BOT_TOKEN` se revocó**. Si fue así, en BotFather generás un nuevo token y actualizás el secret.

> **NOTA**: el chat actual notifica solo para Mora. Para sumar otros clientes a Telegram, hay que decidir si quieren su propio chat o si todos van al mismo grupo. Hablamos cuando llegue ese momento.

---

### 🟡 "Gemini falló para X SKUs"

**Síntoma**: en Telegram dice "Enriquecimiento: N nuevos, M reusados, K fallidos". Algunos SKUs fallaron.

**Causas posibles**:

1. **Rate limit de Gemini free tier**. Si marcaste muchos SKUs nuevos de una (50+) y Gemini te tira 429. **Solución**: marcar menos de a poco, o esperar 1 minuto y dispará manualmente — el cache va a recoger los que ya quedaron.

2. **Producto sin info útil**. Si el nombre del producto es "Producto 1" sin descripción, Gemini puede no tener nada para escribir y devolver vacío. El SKU se saltea del feed.

3. **API key venció**. Renová la `GEMINI_API_KEY` desde Google AI Studio.

**Verificación**: en el log del run, buscar líneas con `[Bloque 3]` o `gemini`. Te dice qué SKU falló y por qué.

---

### 🔴 "Playwright timeout" o "Browser launch failed"

**Síntoma**: el run falla en Bloque 4. Mensaje tipo "Timeout 30000ms exceeded" o "browserType.launch: Executable doesn't exist".

**Causas posibles**:

1. **Cache de Playwright corrupto**. Borrá el cache en GitHub:
   - Settings → Actions → Caches → borrá los que dicen `playwright-Linux-...`
   - Próximo run reinstala todo limpio.

2. **HTML del template lentísimo**. Si tu template tiene `@import` a un CSS externo gigante (ej: Tailwind CDN), puede tardar. Inline el CSS.

3. **Imagen externa que tarda mucho**. Si la URL de imagen del producto tarda 20s en responder, Playwright timeout-ea. Esto es difícil de evitar, pero si pasa seguido habría que aumentar el timeout en el código (no es config).

---

### 🟡 "Cloudinary me dice que llegué al límite de cuota"

**Síntoma**: emails de Cloudinary o errores en logs sobre "quota exceeded".

**Causas y soluciones**:

| Métrica | Free tier | Si te pasás |
|---|---|---|
| **Storage** | 1 GB | Borrá folders de clientes inactivos |
| **Bandwidth** (CDN) | 1 GB/mes | Reducir tamaño de PNG → JPG/WebP |
| **Transformations** | 25.000/mes | Configurar Meta/TikTok para no pedir transformaciones |
| **Credits** | 25/mes | Plan pago: USD 89/mes (Plus, 225 créditos) |

**Más en detalle**: ver `03-arquitectura.md` sección "decisiones de diseño".

---

### 🔴 "Pude correr el preview local en Mora pero en mi cliente nuevo no funciona"

**Síntoma**: `python scripts/preview_template.py --cliente=shark --template=default` falla.

**Verificación rápida**:

1. ¿Existe `clients/shark/templates/default.html`? Si no, creálo.
2. ¿La carpeta `clients/shark/templates/` existe (incluso vacía)? Si no, creála.
3. Pasame el error exacto que tira.

---

### 🟡 "El cron no se dispara"

**Síntoma**: el workflow funciona si lo disparás manual, pero no corre solo a las 06:00 ART.

**Causas posibles**:

1. **El cron está bien pero GitHub atrasa hasta 15 min los crons de free tier**. Es normal. Confirmá esperando.

2. **El repo está sin actividad por más de 60 días**. GitHub Actions deshabilita los crons automáticamente en repos inactivos. Solución: hacé cualquier commit (aunque sea un cambio mínimo) o re-enableá el workflow desde Actions.

3. **El YAML del cron está mal**. Verificá que la línea `- cron: '0 9 * * *'` esté indentada correctamente. Cualquier desfasaje rompe.

---

### 🔴 "El sheet de Selección tiene SKUs marcados pero el sistema dice que están vacíos"

**Síntoma**: en el log dice `0 productos seleccionados` aunque marcaste 10 SKUs.

**Causas posibles**:

1. **La columna `generar` no tiene un valor válido**. Verificá:
   - Valores aceptados: `TRUE`, `SI`, `YES`, `X`, `1` (case insensitive)
   - Que no haya espacios al final
   - Si usás un checkbox de Google Sheets, también funciona

2. **La pestaña se llama distinto a `Seleccion`**. Verificá en el `pipeline.yaml`:
   ```yaml
   seleccion:
     config:
       sheet:
         pestaña: Seleccion  ← este nombre tiene que matchear EXACTAMENTE el de la pestaña
   ```

3. **El SKU marcado no existe en el inventario**. Si el SKU del sheet de Selección no existe en el sheet de Inventario, se saltea con warning en el log.

---

### 🟡 "Se sube todo a Cloudinary pero veo dos folders con el mismo nombre"

**Síntoma**: en Cloudinary Media Library aparecen 2 folders llamados igual (ej: 2 carpetas "morashop").

**Causa**: Cloudinary tiene **dos tipos de folders**:

- **Lógicos** (auto-creados desde el `public_id` del upload)
- **Manuales** (creados desde la UI clickeando "New folder")

Si vos creaste manualmente uno con un nombre que ya estaba siendo usado lógicamente por el sistema, los ves duplicados.

**Solución**:

1. Verificá que el folder con assets tiene `Location: Home` (folder lógico) — ese es el real.
2. Borrá el folder manual vacío.

**Prevención**: para clientes nuevos, **NO crees folders manuales en Cloudinary**. El código los crea solos al primer upload.

---

## Cómo pedir ayuda eficientemente

Si algo no anda y no está en este doc, mandame:

1. **Qué intentaste hacer** (ej: "agregué cliente Shark y disparé el workflow manual")
2. **Qué pasó** (ej: "el workflow tiró rojo en el paso de Bloque 5.1")
3. **Log del run** (descargar el log completo desde la UI de GitHub Actions: click en el ⚙️ del run → "Download log archive")
4. **Screenshot** del error si es visual

Con eso lo destrabamos rápido. Sin eso, paso 20 minutos adivinando.

---

## Próximos pasos

- **Volver a empezar a iterar**: ver `01-quickstart-nuevo-cliente.md`
- **Entender por dentro**: `03-arquitectura.md`
- **Mejorar tus templates**: `02-diseno-templates.md`
