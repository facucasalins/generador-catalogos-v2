"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { consultarCorrida, correrPipeline } from "@/app/acciones";
import type { CorridaEnVivo } from "@/lib/datos";
import type { ModoCorrida } from "@/lib/github";

const enCurso = (c: CorridaEnVivo | null) => c !== null && (c.estado === "corriendo" || c.estado === "en_cola");

/**
 * Sigue la última corrida del cliente. Consulta cada 4 s mientras hay una en
 * curso (o mientras se espera que arranque la que se acaba de pedir).
 */
export function useCorrida(slug: string, inicial: CorridaEnVivo | null) {
  const [corrida, setCorrida] = useState<CorridaEnVivo | null>(inicial);
  const [esperandoDesde, setEsperandoDesde] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const estabaEnCurso = useRef(enCurso(inicial));

  const consultar = useCallback(async () => {
    const r = await consultarCorrida(slug);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    setCorrida(r.corrida);
    // La corrida pedida ya apareció en GitHub.
    if (esperandoDesde && r.corrida && new Date(r.corrida.inicio).getTime() >= esperandoDesde - 15_000) {
      setEsperandoDesde(null);
    }
    const ahora = enCurso(r.corrida);
    if (estabaEnCurso.current && !ahora) router.refresh(); // terminó: refresca tablas y placas
    estabaEnCurso.current = ahora;
  }, [slug, esperandoDesde, router]);

  useEffect(() => {
    if (!enCurso(corrida) && esperandoDesde === null) return;
    const id = setInterval(consultar, 4000);
    return () => clearInterval(id);
  }, [corrida, esperandoDesde, consultar]);

  const correr = useCallback(
    async (modo: ModoCorrida) => {
      setError(null);
      const r = await correrPipeline(slug, modo);
      if (!r.ok) {
        setError(r.error);
        return false;
      }
      setEsperandoDesde(Date.now());
      estabaEnCurso.current = true;
      return true;
    },
    [slug],
  );

  return { corrida, correr, error, ocupado: enCurso(corrida) || esperandoDesde !== null, esperando: esperandoDesde !== null };
}

const textoPaso = (estado: string, conclusion: string | null) =>
  estado === "completed" ? (conclusion === "success" ? "listo" : conclusion === "skipped" ? "salteado" : "falló") : estado === "in_progress" ? "en curso" : "pendiente";

export function EstadoEnVivo({ corrida, esperando }: { corrida: CorridaEnVivo | null; esperando: boolean }) {
  if (esperando) return <p className="suave">Pedido enviado. GitHub tarda unos segundos en arrancar la corrida…</p>;
  if (!corrida || !enCurso(corrida)) return null;
  return (
    <div className="en-vivo" aria-live="polite">
      <p>
        <b>{corrida.estado === "en_cola" ? "En cola" : "Corriendo"}</b>{" "}
        <a href={corrida.url} target="_blank" rel="noreferrer">
          ver log
        </a>
      </p>
      {corrida.pasos.length > 0 && (
        <ol className="pasos">
          {corrida.pasos.map((p) => (
            <li key={p.nombre} data-estado={p.estado === "completed" ? (p.conclusion === "success" ? "ok" : "error") : p.estado}>
              <span>{p.nombre}</span>
              <span className="suave">{textoPaso(p.estado, p.conclusion)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function ControlCorridas({ slug, inicial }: { slug: string; inicial: CorridaEnVivo | null }) {
  const { corrida, correr, error, ocupado, esperando } = useCorrida(slug, inicial);
  const [confirmar, setConfirmar] = useState(false);

  return (
    <div className="control-corridas">
      <div className="filtros">
        {confirmar ? (
          <>
            <span>Regenera las placas que cambiaron y reescribe los feeds de Meta y TikTok.</span>
            <button
              className="boton"
              disabled={ocupado}
              onClick={async () => {
                setConfirmar(false);
                await correr("completo");
              }}
            >
              Sí, generar ahora
            </button>
            <button className="boton boton-secundario" onClick={() => setConfirmar(false)}>
              Cancelar
            </button>
          </>
        ) : (
          <>
            <button className="boton" disabled={ocupado} onClick={() => setConfirmar(true)}>
              Generar ahora
            </button>
            <button className="boton boton-secundario" disabled={ocupado} onClick={() => correr("solo_inventario")}>
              Solo actualizar inventario
            </button>
          </>
        )}
      </div>
      {error && (
        <div className="aviso aviso-error" role="alert" style={{ marginTop: 12, marginBottom: 0 }}>
          {error}
        </div>
      )}
      <EstadoEnVivo corrida={corrida} esperando={esperando} />
    </div>
  );
}
