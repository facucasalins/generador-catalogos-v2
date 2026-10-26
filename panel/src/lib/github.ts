import "server-only";
import { repoGithub } from "./config";

// Cliente mínimo de la API REST de GitHub con el token del panel
// (fine-grained, solo este repo: Contents y Actions en lectura y escritura).

export class FaltaTokenGithub extends Error {
  constructor() {
    super("Falta GITHUB_TOKEN en Vercel: el panel no puede hablar con GitHub.");
  }
}

export class ErrorGithub extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

function token(): string {
  const t = process.env.GITHUB_TOKEN;
  if (!t) throw new FaltaTokenGithub();
  return t;
}

export async function gh<T>(ruta: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...resto } = init;
  const resp = await fetch(`https://api.github.com/repos/${repoGithub}${ruta}`, {
    ...resto,
    headers: {
      Authorization: `Bearer ${token()}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(resto.headers ?? {}),
    },
    body: json !== undefined ? JSON.stringify(json) : resto.body,
    cache: "no-store",
  });
  if (!resp.ok) {
    const texto = await resp.text().catch(() => "");
    const pista =
      resp.status === 403 || resp.status === 404
        ? " Revisá que el token tenga permisos de escritura en Contents y Actions sobre este repo."
        : "";
    throw new ErrorGithub(`GitHub respondió ${resp.status}.${pista} ${texto.slice(0, 200)}`, resp.status);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

// ---------- Actions ----------

export type ModoCorrida = "completo" | "solo_inventario";

export async function dispararWorkflow(archivo: string, modo: ModoCorrida): Promise<void> {
  await gh(`/actions/workflows/${archivo}/dispatches`, {
    method: "POST",
    json: { ref: "main", inputs: { modo } },
  });
}

export type RunGithub = {
  id: number;
  status: string;
  conclusion: string | null;
  event: string;
  run_started_at: string;
  created_at: string;
  updated_at: string;
  html_url: string;
  run_attempt: number;
  display_title: string;
};

export async function listarRuns(archivo: string, cantidad: number): Promise<RunGithub[]> {
  const r = await gh<{ workflow_runs: RunGithub[] }>(
    `/actions/workflows/${archivo}/runs?per_page=${cantidad}&branch=main`,
  );
  return r.workflow_runs;
}

export type PasoGithub = { name: string; status: string; conclusion: string | null; number: number };

export async function pasosDeRun(runId: number): Promise<PasoGithub[]> {
  const r = await gh<{ jobs: { steps?: PasoGithub[] }[] }>(`/actions/runs/${runId}/jobs`);
  return r.jobs.flatMap((j) => j.steps ?? []);
}

// ---------- Contenidos del repo (templates) ----------

export type ArchivoRepo = { path: string; sha: string };

/** Archivos de una carpeta del repo en main. Carpeta inexistente → []. */
export async function listarCarpeta(carpeta: string): Promise<(ArchivoRepo & { name: string; type: string })[]> {
  try {
    return await gh(`/contents/${carpeta}?ref=main`);
  } catch (e) {
    if (e instanceof ErrorGithub && e.status === 404) return [];
    throw e;
  }
}

export async function leerArchivo(path: string): Promise<{ texto: string; sha: string } | null> {
  try {
    const r = await gh<{ content: string; encoding: string; sha: string }>(`/contents/${path}?ref=main`);
    return { texto: Buffer.from(r.content, "base64").toString("utf8"), sha: r.sha };
  } catch (e) {
    if (e instanceof ErrorGithub && e.status === 404) return null;
    throw e;
  }
}

type Autor = { nombre: string; email: string };

/** Crea o actualiza un archivo en main con un commit. `sha` es obligatorio para actualizar. */
export async function escribirArchivo(path: string, texto: string, mensaje: string, autor: Autor, sha?: string): Promise<string> {
  const r = await gh<{ content: { sha: string } }>(`/contents/${path}`, {
    method: "PUT",
    json: {
      message: mensaje,
      content: Buffer.from(texto, "utf8").toString("base64"),
      branch: "main",
      ...(sha ? { sha } : {}),
      author: { name: autor.nombre, email: autor.email },
    },
  });
  return r.content.sha;
}

export async function borrarArchivo(path: string, sha: string, mensaje: string, autor: Autor): Promise<void> {
  await gh(`/contents/${path}`, {
    method: "DELETE",
    json: { message: mensaje, sha, branch: "main", author: { name: autor.nombre, email: autor.email } },
  });
}

export type CommitGithub = { sha: string; commit: { message: string; author: { name: string; date: string } }; html_url: string };

export async function historialArchivo(path: string, cantidad = 10): Promise<CommitGithub[]> {
  return gh(`/commits?path=${encodeURIComponent(path)}&sha=main&per_page=${cantidad}`);
}

export async function archivoEnCommit(path: string, sha: string): Promise<string | null> {
  try {
    const r = await gh<{ content: string }>(`/contents/${path}?ref=${sha}`);
    return Buffer.from(r.content, "base64").toString("utf8");
  } catch (e) {
    if (e instanceof ErrorGithub && e.status === 404) return null;
    throw e;
  }
}
