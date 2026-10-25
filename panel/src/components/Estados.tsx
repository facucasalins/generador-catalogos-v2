import type { Corrida } from "@/lib/datos";
import { ErrorSheets } from "@/lib/sheets";
import { FaltaCredencial } from "@/lib/google";

const textos: Record<Corrida["estado"], [string, string]> = {
  ok: ["Terminó bien", "etq-ok"],
  fallida: ["Falló", "etq-error"],
  corriendo: ["Corriendo", "etq-curso"],
  en_cola: ["En cola", "etq-curso"],
  cancelada: ["Cancelada", "etq-neutra"],
  otra: ["Otro estado", "etq-neutra"],
};

export function EstadoCorrida({ estado }: { estado: Corrida["estado"] }) {
  const [texto, clase] = textos[estado];
  return <span className={`etiqueta ${clase}`}>{texto}</span>;
}

/** Explica un error de datos en el idioma del panel, con qué hacer. */
export function AvisoError({ error, que }: { error: unknown; que: string }) {
  let detalle = "Error inesperado. Revisá los logs del proyecto en Vercel.";
  if (error instanceof FaltaCredencial || error instanceof ErrorSheets) detalle = error.message;
  else if (error instanceof Error) detalle = error.message;
  return (
    <div className="aviso aviso-error" role="alert">
      <b>No se pudo leer {que}.</b> {detalle}
    </div>
  );
}

/** Ejecuta una lectura y devuelve el resultado o el error, para mostrarlo sin romper la página. */
export async function intentar<T>(f: () => Promise<T>): Promise<{ ok: true; valor: T } | { ok: false; error: unknown }> {
  try {
    return { ok: true, valor: await f() };
  } catch (error) {
    console.error(error);
    return { ok: false, error };
  }
}
