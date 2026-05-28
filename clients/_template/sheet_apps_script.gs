/**
 * Apps Script: sincroniza columnas de templates en pestaña Seleccion.
 *
 * Lee la pestaña Templates (mantenida por el pipeline Python) y agrega
 * 1 columna con checkbox en Seleccion por cada template activo (activo=SI).
 *
 * Se ejecuta automáticamente al abrir el sheet.
 *
 * Reglas:
 * - Columnas FIJAS (sku, generar, prioridad, notas) NUNCA se tocan.
 * - Si un template nuevo aparece en Templates → se agrega columna en Seleccion.
 * - Si un template ya no está en Templates (activo=NO o eliminado) → su
 *   columna se BORRA de Seleccion (con sus checks).
 * - Las marcas existentes se preservan cuando se reordena.
 *
 * Para instalar:
 * 1. Abrir el Google Sheet del cliente
 * 2. Extensiones → Apps Script
 * 3. Pegar este código completo en Code.gs
 * 4. Guardar (Ctrl+S)
 * 5. Cerrar y reabrir el sheet — al abrir se ejecuta solo
 */

const PESTANA_SELECCION = "Seleccion";
const PESTANA_TEMPLATES = "Templates";
const FILAS_CHECKBOX = 1000;

// Columnas fijas en orden. Las de templates van DESPUÉS de "generar" y ANTES
// de "prioridad" para que sigan visibles cerca del checkbox master.
const COL_SKU = "sku";
const COL_GENERAR = "generar";
const COL_PRIORIDAD = "prioridad";
const COL_NOTAS = "notas";

const COLS_FIJAS_ORDEN = [COL_SKU, COL_GENERAR, COL_PRIORIDAD, COL_NOTAS];


function onOpen() {
  try {
    sincronizarColumnasTemplates();
  } catch (e) {
    SpreadsheetApp.getUi().alert(
      "Error sincronizando columnas: " + e.message
    );
  }
}


function sincronizarColumnasTemplates() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheetSel = ss.getSheetByName(PESTANA_SELECCION);
  const sheetTemplates = ss.getSheetByName(PESTANA_TEMPLATES);

  if (!sheetSel) {
    Logger.log("Pestaña Seleccion no existe, salgo.");
    return;
  }
  if (!sheetTemplates) {
    Logger.log("Pestaña Templates no existe, salgo.");
    return;
  }

  // 1. Leer templates activos
  const templatesActivos = leerTemplatesActivos(sheetTemplates);
  Logger.log("Templates activos: " + JSON.stringify(templatesActivos));

  // 2. Leer estado actual de Seleccion
  const lastCol = sheetSel.getLastColumn();
  const headerActual = lastCol > 0
    ? sheetSel.getRange(1, 1, 1, lastCol).getValues()[0]
    : [];

  // Si la pestaña no tiene siquiera columnas fijas, inicializarla
  if (headerActual.length === 0 || headerActual[0] !== COL_SKU) {
    inicializarPestanaSeleccion(sheetSel);
    return sincronizarColumnasTemplates(); // re-ejecutar con la pestaña limpia
  }

  // 3. Snapshot de datos actuales (para preservar marcas al reordenar)
  const lastRow = Math.max(sheetSel.getLastRow(), 1);
  const datosActuales = lastRow > 1
    ? sheetSel.getRange(2, 1, lastRow - 1, headerActual.length).getValues()
    : [];

  // Mapear: para cada fila, {nombre_columna: valor}
  const filasComoObjetos = datosActuales.map(fila => {
    const obj = {};
    headerActual.forEach((col, idx) => {
      obj[col] = fila[idx];
    });
    return obj;
  });

  // 4. Construir el nuevo header en orden:
  //    sku | generar | <templates ordenados> | prioridad | notas
  const nuevoHeader = [COL_SKU, COL_GENERAR];
  templatesActivos.sort().forEach(t => nuevoHeader.push(t));
  nuevoHeader.push(COL_PRIORIDAD, COL_NOTAS);

  // 5. Reescribir el sheet
  sheetSel.clear();

  // Header
  sheetSel.getRange(1, 1, 1, nuevoHeader.length).setValues([nuevoHeader]);
  sheetSel.getRange(1, 1, 1, nuevoHeader.length).setFontWeight("bold");
  sheetSel.setFrozenRows(1);

  // Datos: reconstruir filas respetando el nuevo orden de columnas
  const nuevasFilas = filasComoObjetos.map(obj => {
    return nuevoHeader.map(col => {
      if (col in obj) return obj[col];
      // Columna nueva (template recién agregado): valor por defecto
      if (col === COL_GENERAR) return false;
      if (templatesActivos.includes(col)) return false;
      return "";
    });
  });

  if (nuevasFilas.length > 0) {
    sheetSel.getRange(2, 1, nuevasFilas.length, nuevoHeader.length)
      .setValues(nuevasFilas);
  }

  // Aplicar checkboxes a la columna `generar` (col 2)
  sheetSel.getRange(2, 2, FILAS_CHECKBOX, 1).insertCheckboxes();

  // Aplicar checkboxes a cada columna de template
  templatesActivos.forEach((t, idx) => {
    const colNum = 3 + idx; // columnas 3 en adelante
    sheetSel.getRange(2, colNum, FILAS_CHECKBOX, 1).insertCheckboxes();
  });

  Logger.log("Sincronización completada. Columnas: " + nuevoHeader.join(", "));
}


function leerTemplatesActivos(sheetTemplates) {
  const lastRow = sheetTemplates.getLastRow();
  if (lastRow < 2) return [];

  const lastCol = sheetTemplates.getLastColumn();
  const datos = sheetTemplates.getRange(1, 1, lastRow, lastCol).getValues();
  const header = datos[0];

  const idxNombre = header.indexOf("nombre_template");
  const idxActivo = header.indexOf("activo");
  if (idxNombre === -1 || idxActivo === -1) {
    throw new Error(
      "Pestaña Templates falta columnas 'nombre_template' y/o 'activo'"
    );
  }

  const activos = [];
  for (let i = 1; i < datos.length; i++) {
    const nombre = String(datos[i][idxNombre] || "").trim();
    const activo = String(datos[i][idxActivo] || "").trim().toUpperCase();
    if (nombre && (activo === "SI" || activo === "SÍ" || activo === "TRUE" || activo === "YES")) {
      activos.push(nombre);
    }
  }
  return activos;
}


function inicializarPestanaSeleccion(sheetSel) {
  sheetSel.clear();
  const header = [COL_SKU, COL_GENERAR, COL_PRIORIDAD, COL_NOTAS];
  sheetSel.getRange(1, 1, 1, header.length).setValues([header]);
  sheetSel.getRange(1, 1, 1, header.length).setFontWeight("bold");
  sheetSel.setFrozenRows(1);
  sheetSel.getRange(2, 2, FILAS_CHECKBOX, 1).insertCheckboxes();
}


/**
 * Función manual: ejecutar desde el menú de Apps Script si querés forzar
 * sincronización sin esperar a abrir el sheet.
 */
function sincronizarAhora() {
  sincronizarColumnasTemplates();
  SpreadsheetApp.getUi().alert("Sincronización completada");
}
