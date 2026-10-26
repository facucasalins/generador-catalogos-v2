"use server";
// Acciones del panel que cambian algo: corridas, Selección y templates.
// Todas exigen sesión y devuelven { ok, ... } para mostrar el resultado sin romper la página.
import { revalidatePath } from "next/cache";
import { buscarCliente, modoDemo, PLATAFORMAS, separarTemplate, type Cliente } from "@/lib/config";
import { corridaActual, obtenerInventario, obtenerSeleccion, type CorridaEnVivo } from "@/lib/datos";
import { aplicarCambiosSeleccion, quitarTemplateDeSheets, registrarTemplateEnSheet, templatesActuales } from "@/lib/datos/escritura";
import { buscarTemplate, invalidarTemplates, listarTemplates, rutaTemplate } from "@/lib/datos/templates";
import { resolverEntradas, type EstadoEntrada } from "@/lib/entradas";
import { archivoEnCommit, borrarArchivo, dispararWorkflow, escribirArchivo, type ModoCorrida } from "@/lib/github";
import { parsearMeta } from "@/lib/render/meta";
import { aProductoRender } from "@/lib/render/preparar";
import { puedePublicar, validarTemplate, type Validacion } from "@/lib/render/validar";
import { exigirSesion } from "@/lib/sesion";

type Resultado<T = object> = ({ ok: true } & T) | { ok: false; error: string };

function mensajeDe(e: unknown): string {
  return e instanceof Error ? e.message : "Error inesperado.";
}

const DEMO = { ok: false as const, error: "Modo demo: el panel no escribe nada en las sheets, GitHub ni Actions." };

function cliente(slug: string): Cliente {
  const c = buscarCliente(slug);
  if (!c) throw new Error(`No existe el cliente ${slug}.`);
  return c;
}

// ---------- Corridas ----------

export async function correrPipeline(slug: string, modo: ModoCorrida): Promise<Resultado> {
  await exigirSesion();
  if (modoDemo) return DEMO;
  try {
    const c = cliente(slug);
    if (!c.workflow) return { ok: false, error: "Este cliente no tiene workflow de pipeline." };
    const actual = await corridaActual(c);
    if (actual && (actual.estado === "corriendo" || actual.estado === "en_cola")) {
      return { ok: false, error: "Ya hay una corrida en curso para este cliente. Esperá a que termine." };
    }
    await dispararWorkflow(c.workflow.archivo, modo);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: mensajeDe(e) };
  }
}

export async function consultarCorrida(slug: string): Promise<Resultado<{ corrida: CorridaEnVivo | null }>> {
  await exigirSesion();
  try {
    if (modoDemo) return { ok: true, corrida: null };
    return { ok: true, corrida: await corridaActual(cliente(slug)) };
  } catch (e) {
    return { ok: false, error: mensajeDe(e) };
  }
}

// ---------- Selección ----------

export type FichaProducto = {
  sku: string;
  nombre: string;
  imagenUrl: string;
  precioLista: number;
  precioPromocional: number | null;
  stock: number | null;
  publicado: boolean;
  tieneStock: boolean;
  templatesActuales: string[];
};

export type FichaEntrada = { entrada: string; estado: EstadoEntrada; productos: FichaProducto[] };

/** Busca en el inventario (leído en el momento) lo que se pegó en "Agregar productos". */
export async function revisarEntradas(slug: string, texto: string): Promise<Resultado<{ fichas: FichaEntrada[] }>> {
  await exigirSesion();
  try {
    const c = cliente(slug);
    const { productos } = await obtenerInventario(c, { fresco: true });
    const resueltas = resolverEntradas(texto, productos);
    const actuales = modoDemo
      ? new Map<string, string[]>()
      : await templatesActuales(
          c,
          resueltas.flatMap((r) => r.productos.map((p) => p.sku)),
        );
    return {
      ok: true,
      fichas: resueltas.map((r) => ({
        entrada: r.entrada,
        estado: r.estado,
        productos: r.productos.map((p) => ({
          sku: p.sku,
          nombre: p.tituloPlaca || p.nombre,
          imagenUrl: p.imagenUrl,
          precioLista: p.precioLista,
          precioPromocional: p.precioPromocional,
          stock: p.stock,
          publicado: p.publicado,
          tieneStock: p.tieneStock,
          templatesActuales: actuales.get(p.sku) ?? [],
        })),
      })),
    };
  } catch (e) {
    return { ok: false, error: mensajeDe(e) };
  }
}

function exigirTemplatesValidos(templates: string[], existentes: string[]): void {
  const validos = new Set(existentes.flatMap((t) => PLATAFORMAS.map((p) => `${p}_${t}`)));
  const malos = templates.filter((t) => !validos.has(t));
  if (malos.length) throw new Error(`Templates que no existen: ${malos.join(", ")}.`);
}

/** Suma templates a varios SKUs (sin quitar los que ya tenían). */
export async function agregarProductos(slug: string, skus: string[], templates: string[]): Promise<Resultado<{ filas: number }>> {
  await exigirSesion();
  if (modoDemo) return DEMO;
  try {
    const c = cliente(slug);
    if (skus.length === 0 || templates.length === 0) return { ok: false, error: "Elegí al menos un producto y un template." };
    exigirTemplatesValidos(templates, (await listarTemplates(c)).map((t) => t.nombre));
    const actuales = await templatesActuales(c, skus);
    const r = await aplicarCambiosSeleccion(
      c,
      skus.map((sku) => ({ sku, templates: [...new Set([...(actuales.get(sku) ?? []), ...templates])] })),
    );
    revalidatePath(`/c/${slug}`);
    return { ok: true, filas: r.filas };
  } catch (e) {
    return { ok: false, error: mensajeDe(e) };
  }
}

/** Deja un SKU exactamente con estos templates. [] lo saca de la selección. */
export async function guardarSeleccionSku(slug: string, sku: string, templates: string[]): Promise<Resultado> {
  await exigirSesion();
  if (modoDemo) return DEMO;
  try {
    const c = cliente(slug);
    exigirTemplatesValidos(templates, (await listarTemplates(c)).map((t) => t.nombre));
    await aplicarCambiosSeleccion(c, [{ sku, templates }]);
    revalidatePath(`/c/${slug}`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: mensajeDe(e) };
  }
}

// ---------- Templates ----------

async function muestraPara(c: Cliente) {
  try {
    const { productos } = await obtenerInventario(c);
    const p = productos.find((x) => x.imagenUrl && x.tieneStock) ?? productos[0];
    return p ? aProductoRender(p) : null;
  } catch {
    return null;
  }
}

export type DatosGuardado = {
  nombre: string;
  html: string;
  esNuevo: boolean;
  shaPrevio: string | null;
  mensaje: string;
  publicarIgual: boolean;
};

export async function guardarTemplate(slug: string, d: DatosGuardado): Promise<Resultado<{ validacion?: Validacion }>> {
  const sesion = await exigirSesion();
  if (modoDemo) return DEMO;
  try {
    const c = cliente(slug);
    const existentes = await listarTemplates(c);
    const v = validarTemplate({
      nombre: d.nombre,
      html: d.html,
      existentes: existentes.map((t) => t.nombre),
      esNuevo: d.esNuevo,
      estilo: c.estilo,
      muestra: await muestraPara(c),
    });
    if (!puedePublicar(v, d.publicarIgual)) {
      return { ok: false, error: "El template tiene errores; corregilos antes de guardar.", };
    }
    const actual = existentes.find((t) => t.nombre === d.nombre);
    if (!d.esNuevo && actual?.sha && d.shaPrevio && actual.sha !== d.shaPrevio) {
      return { ok: false, error: "Alguien guardó este template mientras lo editabas. Recargá la página para ver su versión." };
    }
    const accion = d.esNuevo ? "Nuevo template" : "Edita template";
    const mensaje = `${accion} ${c.slug}/${d.nombre}${d.mensaje.trim() ? `: ${d.mensaje.trim()}` : ""}\n\nDesde el panel, por ${sesion.nombre} <${sesion.email}>.`;
    await escribirArchivo(rutaTemplate(c, d.nombre), d.html, mensaje, { nombre: sesion.nombre, email: sesion.email }, d.esNuevo ? undefined : (actual?.sha ?? undefined));
    invalidarTemplates(c);
    const meta = parsearMeta(d.html);
    // La pestaña Templates la regenera el pipeline; se actualiza ya para que el
    // Apps Script de la sheet no borre las columnas del template nuevo.
    await registrarTemplateEnSheet(c, { nombre: d.nombre, ...meta }).catch((e) =>
      console.error("[templates] No pude actualizar la pestaña Templates:", e),
    );
    revalidatePath(`/c/${slug}/templates`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: mensajeDe(e) };
  }
}

/**
 * Elimina un template de todos lados: el archivo del repo, sus columnas en la
 * Selección y (con la corrida que se dispara al final) sus placas del feed y de Cloudinary.
 */
export async function eliminarTemplate(slug: string, nombre: string, confirmacion: string): Promise<Resultado<{ skusAfectados: number; corrida: boolean }>> {
  const sesion = await exigirSesion();
  if (modoDemo) return DEMO;
  try {
    const c = cliente(slug);
    if (confirmacion.trim() !== nombre) return { ok: false, error: `Para confirmar, escribí el nombre exacto: ${nombre}` };
    const t = await buscarTemplate(c, nombre);
    if (!t?.sha) return { ok: false, error: "No encontré ese template en el repo." };
    await borrarArchivo(t.path, t.sha, `Elimina template ${c.slug}/${nombre}\n\nDesde el panel, por ${sesion.nombre} <${sesion.email}>.`, {
      nombre: sesion.nombre,
      email: sesion.email,
    });
    invalidarTemplates(c);
    const { skusAfectados } = await quitarTemplateDeSheets(c, nombre);
    let corrida = false;
    if (c.workflow) {
      await dispararWorkflow(c.workflow.archivo, "completo");
      corrida = true;
    }
    revalidatePath(`/c/${slug}`, "layout");
    return { ok: true, skusAfectados, corrida };
  } catch (e) {
    return { ok: false, error: mensajeDe(e) };
  }
}

/** Vuelve un template a una versión anterior (queda como un commit nuevo). */
export async function restaurarVersion(slug: string, nombre: string, commitSha: string): Promise<Resultado> {
  const sesion = await exigirSesion();
  if (modoDemo) return DEMO;
  try {
    const c = cliente(slug);
    const t = await buscarTemplate(c, nombre);
    const html = await archivoEnCommit(rutaTemplate(c, nombre), commitSha);
    if (html === null) return { ok: false, error: "Esa versión no tiene el archivo." };
    await escribirArchivo(
      rutaTemplate(c, nombre),
      html,
      `Restaura template ${c.slug}/${nombre} a ${commitSha.slice(0, 7)}\n\nDesde el panel, por ${sesion.nombre} <${sesion.email}>.`,
      { nombre: sesion.nombre, email: sesion.email },
      t?.sha ?? undefined,
    );
    invalidarTemplates(c);
    revalidatePath(`/c/${slug}/templates`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: mensajeDe(e) };
  }
}

/** SKUs que hoy usan un template (para avisar antes de eliminarlo). */
export async function usoDeTemplate(slug: string, nombre: string): Promise<Resultado<{ skus: string[] }>> {
  await exigirSesion();
  try {
    const sel = await obtenerSeleccion(cliente(slug));
    const skus = sel.filas
      .filter((f) => f.generar && f.templates.some((t) => separarTemplate(t).base === nombre))
      .map((f) => f.sku);
    return { ok: true, skus };
  } catch (e) {
    return { ok: false, error: mensajeDe(e) };
  }
}
