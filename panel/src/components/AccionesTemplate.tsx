"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { eliminarTemplate, restaurarVersion, usoDeTemplate } from "@/app/acciones";

export function EliminarTemplate({ slug, nombre }: { slug: string; nombre: string }) {
  const [abierto, setAbierto] = useState(false);
  const [uso, setUso] = useState<string[] | null>(null);
  const [confirmacion, setConfirmacion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pendiente, iniciar] = useTransition();
  const router = useRouter();

  const abrir = () => {
    setAbierto(true);
    setConfirmacion("");
    setError(null);
    usoDeTemplate(slug, nombre).then((r) => (r.ok ? setUso(r.skus) : setError(r.error)));
  };

  const eliminar = () =>
    iniciar(async () => {
      const r = await eliminarTemplate(slug, nombre, confirmacion);
      if (!r.ok) return setError(r.error);
      router.push(`/c/${slug}/templates?eliminado=${encodeURIComponent(nombre)}&corrida=${r.corrida ? 1 : 0}`);
      router.refresh();
    });

  return (
    <>
      <button className="boton boton-peligro" onClick={abrir}>
        Eliminar
      </button>
      {abierto && (
        <div className="modal-fondo" role="dialog" aria-modal="true" aria-label={`Eliminar ${nombre}`} onClick={(e) => e.target === e.currentTarget && setAbierto(false)}>
          <div className="modal">
            <h2>Eliminar {nombre}</h2>
            <p>Se borra de todos lados:</p>
            <ul className="lista-efectos">
              <li>El archivo del template en el repo. Queda en el historial de git por si hay que recuperarlo.</li>
              <li>Sus columnas Meta y TikTok en la Selección, con todas sus marcas.</li>
              <li>
                Sus placas del feed y de Cloudinary: se dispara una corrida ahora mismo y, al terminar, esas placas dejan de estar en los
                catálogos de Meta y TikTok.
              </li>
            </ul>
            <p>
              {uso === null ? (
                <span className="suave">Contando cuántos productos lo usan…</span>
              ) : uso.length === 0 ? (
                <b>Ningún producto lo usa hoy.</b>
              ) : (
                <b>
                  Lo usan {uso.length} {uso.length === 1 ? "producto" : "productos"}: sus placas con este diseño salen de los anuncios.
                </b>
              )}
            </p>
            <label className="campo">
              <span>
                Para confirmar, escribí <code>{nombre}</code>
              </span>
              <input value={confirmacion} onChange={(e) => setConfirmacion(e.target.value)} autoFocus spellCheck={false} />
            </label>
            {error && <div className="aviso aviso-error" role="alert" style={{ margin: "12px 0 0" }}>{error}</div>}
            <div className="modal-pie">
              <span style={{ flex: 1 }} />
              <button className="boton boton-secundario" onClick={() => setAbierto(false)}>
                Cancelar
              </button>
              <button className="boton boton-peligro" disabled={pendiente || confirmacion.trim() !== nombre} onClick={eliminar}>
                {pendiente ? "Eliminando…" : "Eliminar de todos lados"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function BotonRestaurar({ slug, nombre, sha, fecha }: { slug: string; nombre: string; sha: string; fecha: string }) {
  const [confirmar, setConfirmar] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendiente, iniciar] = useTransition();
  const router = useRouter();
  if (error) return <span style={{ color: "var(--error)" }}>{error}</span>;
  if (!confirmar)
    return (
      <button className="enlace" onClick={() => setConfirmar(true)}>
        Volver a esta versión
      </button>
    );
  return (
    <span className="filtros">
      <span className="suave">¿Volver a la del {fecha}?</span>
      <button
        className="boton"
        disabled={pendiente}
        onClick={() =>
          iniciar(async () => {
            const r = await restaurarVersion(slug, nombre, sha);
            if (!r.ok) return setError(r.error);
            setConfirmar(false);
            router.refresh();
          })
        }
      >
        {pendiente ? "Restaurando…" : "Sí, restaurar"}
      </button>
      <button className="boton boton-secundario" onClick={() => setConfirmar(false)}>
        No
      </button>
    </span>
  );
}
