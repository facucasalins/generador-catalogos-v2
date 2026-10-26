import "server-only";
// Templates en vivo desde GitHub (main). Así un template guardado desde el
// panel se ve al instante, sin esperar el redeploy. Si no hay token o GitHub
// falla, se usan los empaquetados en el build.
import { modoDemo, type Cliente, type TemplateRepo } from "../config";
import { ErrorGithub, FaltaTokenGithub, leerArchivo, listarCarpeta } from "../github";
import { parsearMeta } from "../render/meta";

export type TemplateVivo = TemplateRepo & { sha: string | null; path: string };

const carpeta = (c: Cliente) => `clients/${c.slug}/templates`;
export const rutaTemplate = (c: Cliente, nombre: string) => `${carpeta(c)}/${nombre}.html`;

// Contenido por sha: un archivo que no cambió no se vuelve a bajar.
const porSha = new Map<string, string>();
const listados = new Map<string, { vence: number; valor: Promise<TemplateVivo[]> }>();

export function invalidarTemplates(c: Cliente): void {
  listados.delete(c.slug);
}

export async function listarTemplates(c: Cliente): Promise<TemplateVivo[]> {
  if (modoDemo || !process.env.GITHUB_TOKEN) return empaquetados(c);
  const ahora = Date.now();
  const cache = listados.get(c.slug);
  if (cache && cache.vence > ahora) return cache.valor;
  const valor = deGithub(c).catch((e) => {
    if (e instanceof FaltaTokenGithub || e instanceof ErrorGithub) {
      console.error(`[templates] ${c.slug}: uso los del build. ${e.message}`);
      return empaquetados(c);
    }
    throw e;
  });
  listados.set(c.slug, { vence: ahora + 15_000, valor });
  return valor;
}

function empaquetados(c: Cliente): TemplateVivo[] {
  return c.templates.map((t) => ({ ...t, sha: null, path: rutaTemplate(c, t.nombre) }));
}

async function deGithub(c: Cliente): Promise<TemplateVivo[]> {
  const archivos = (await listarCarpeta(carpeta(c))).filter((a) => a.type === "file" && a.name.endsWith(".html"));
  const salida = await Promise.all(
    archivos.map(async (a) => {
      let html = porSha.get(a.sha);
      if (html === undefined) {
        const leido = await leerArchivo(a.path);
        html = leido?.texto ?? "";
        porSha.set(a.sha, html);
      }
      return { nombre: a.name.replace(/\.html$/, ""), html, ...parsearMeta(html), sha: a.sha, path: a.path };
    }),
  );
  return salida.sort((x, y) => x.nombre.localeCompare(y.nombre));
}

export async function buscarTemplate(c: Cliente, nombre: string): Promise<TemplateVivo | undefined> {
  return (await listarTemplates(c)).find((t) => t.nombre === nombre);
}
