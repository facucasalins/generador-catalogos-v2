// Validación de un template antes de publicarlo. Pura: corre igual en el
// navegador (mientras se edita) y en el servidor (al guardar).
import { parsearMeta } from "./meta";
import { construirVariables, reemplazarVariables, type EstiloCliente, type ProductoRender } from "./variables";

export type Validacion = {
  errores: string[]; // bloquean publicar
  variablesDesconocidas: string[]; // bloquean, salvo "publicar igual"
  avisos: string[]; // no bloquean
};

// Ratios que aceptan los feeds de Meta y TikTok de todos los clientes
// (aspect_ratios_aceptados en pipeline.yaml). Otro ratio no llega al feed.
const RATIOS_FEED = ["4:5", "9:16", "1:1"];
const HOSTS_PERMITIDOS = ["fonts.googleapis.com", "fonts.gstatic.com"];

export function validarNombre(nombre: string, existentes: string[], esNuevo: boolean): string[] {
  const errores: string[] = [];
  if (!/^[a-z0-9][a-z0-9_]*$/.test(nombre)) {
    errores.push("El nombre solo puede tener minúsculas, números y guion bajo, sin espacios (ej: cyber_4x5).");
  }
  if (/^(meta|tiktok)_/i.test(nombre)) {
    errores.push("El nombre no puede empezar con meta_ ni tiktok_: la plataforma se elige al seleccionar productos.");
  }
  if (nombre.length > 60) errores.push("El nombre es demasiado largo (máximo 60 caracteres).");
  if (["nuevo", "editar"].includes(nombre)) errores.push(`«${nombre}» está reservado; elegí otro nombre.`);
  if (esNuevo && existentes.includes(nombre)) errores.push(`Ya existe un template llamado ${nombre}.`);
  return errores;
}

export function validarTemplate(params: {
  nombre: string;
  html: string;
  existentes: string[];
  esNuevo: boolean;
  estilo: EstiloCliente;
  muestra: ProductoRender | null;
}): Validacion {
  const { nombre, html, existentes, esNuevo, estilo, muestra } = params;
  const errores = validarNombre(nombre, existentes, esNuevo);
  const avisos: string[] = [];

  if (!html.trim()) errores.push("El template está vacío.");
  const meta = parsearMeta(html);
  if (!meta.tieneMeta) {
    errores.push("Falta el bloque <!-- META ... --> al inicio, con aspect_ratio, width y height.");
  } else {
    if (meta.width < 200 || meta.width > 4000 || meta.height < 200 || meta.height > 4000) {
      errores.push(`Tamaño fuera de rango: ${meta.width}×${meta.height} px.`);
    }
    if (!RATIOS_FEED.includes(meta.aspect_ratio)) {
      errores.push(`aspect_ratio ${meta.aspect_ratio} no lo aceptan los feeds: usá 4:5, 9:16 o 1:1.`);
    } else {
      const [a, b] = meta.aspect_ratio.split(":").map(Number);
      if (Math.abs(meta.width / meta.height - a / b) > 0.02) {
        avisos.push(`El tamaño ${meta.width}×${meta.height} no coincide con ${meta.aspect_ratio}.`);
      }
    }
  }

  if (/<script[^>]+src\s*=/i.test(html)) {
    errores.push("No se permiten scripts externos (<script src=...>). Los scripts escritos dentro del template sí.");
  }
  const hosts = [...html.matchAll(/https?:\/\/([^/"'\s)]+)/g)].map((m) => m[1].toLowerCase());
  const raros = [...new Set(hosts.filter((h) => !HOSTS_PERMITIDOS.includes(h)))];
  if (raros.length) {
    avisos.push(`Carga recursos de ${raros.join(", ")}: si ese sitio falla, la placa sale incompleta.`);
  }
  if (html.length > 300_000) avisos.push("El template pesa más de 300 KB; el render va a ser lento.");

  let variablesDesconocidas: string[] = [];
  if (muestra) {
    const r = reemplazarVariables(html, construirVariables(muestra, estilo));
    variablesDesconocidas = r.sinReemplazar;
  }
  if (!/\{imagen_b64\}/.test(html)) avisos.push("No usa {imagen_b64}: la placa no va a mostrar la foto del producto.");
  if (/\{nombre\}/.test(html)) avisos.push("Usa {nombre}; para la placa conviene {titulo_placa}, que es más corto y no se corta.");

  return { errores, variablesDesconocidas, avisos };
}

export function puedePublicar(v: Validacion, publicarIgual: boolean): boolean {
  return v.errores.length === 0 && (v.variablesDesconocidas.length === 0 || publicarIgual);
}
