"use client";
import { useDeferredValue, useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { guardarTemplate } from "@/app/acciones";
import { EditorPreview, type OpcionProducto } from "./EditorPreview";
import { parsearMeta } from "@/lib/render/meta";
import { puedePublicar, validarTemplate } from "@/lib/render/validar";
import type { EstiloCliente } from "@/lib/render/variables";

export function EditorTemplate({
  slug,
  nombreInicial,
  htmlInicial,
  sha,
  esNuevo,
  existentes,
  productos,
  estilo,
}: {
  slug: string;
  nombreInicial: string;
  htmlInicial: string;
  sha: string | null;
  esNuevo: boolean;
  existentes: string[];
  productos: OpcionProducto[];
  estilo: EstiloCliente;
}) {
  const [nombre, setNombre] = useState(nombreInicial);
  const [html, setHtml] = useState(htmlInicial);
  const [mensaje, setMensaje] = useState("");
  const [publicarIgual, setPublicarIgual] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendiente, iniciar] = useTransition();
  const router = useRouter();
  // La preview usa una versión "diferida" para no recalcular en cada tecla.
  const htmlPreview = useDeferredValue(html);
  const meta = useMemo(() => parsearMeta(htmlPreview), [htmlPreview]);
  const muestra = productos.find((p) => p.seleccionado && p.tieneStock) ?? productos[0] ?? null;
  const v = useMemo(
    () => validarTemplate({ nombre, html: htmlPreview, existentes, esNuevo, estilo, muestra }),
    [nombre, htmlPreview, existentes, esNuevo, estilo, muestra],
  );
  const cambios = html !== htmlInicial || nombre !== nombreInicial;
  const habilitado = puedePublicar(v, publicarIgual) && cambios && !pendiente;

  const guardar = () =>
    iniciar(async () => {
      setError(null);
      const r = await guardarTemplate(slug, { nombre, html, esNuevo, shaPrevio: sha, mensaje, publicarIgual });
      if (!r.ok) return setError(r.error);
      router.push(`/c/${slug}/templates/${encodeURIComponent(nombre)}?guardado=1`);
      router.refresh();
    });

  // Cmd/Ctrl+S guarda; aviso al salir con cambios sin guardar.
  useEffect(() => {
    const teclas = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        if (habilitado) guardar();
      }
    };
    const salir = (e: BeforeUnloadEvent) => {
      if (cambios && !pendiente) e.preventDefault();
    };
    window.addEventListener("keydown", teclas);
    window.addEventListener("beforeunload", salir);
    return () => {
      window.removeEventListener("keydown", teclas);
      window.removeEventListener("beforeunload", salir);
    };
  });

  return (
    <div className="editor-template">
      <div className="barra-guardar hoja">
        <label className="campo campo-linea">
          <span>Nombre</span>
          <input value={nombre} onChange={(e) => setNombre(e.target.value.trim())} disabled={!esNuevo} spellCheck={false} />
        </label>
        <label className="campo campo-linea" style={{ flex: 1 }}>
          <span>Qué cambiaste (opcional)</span>
          <input value={mensaje} onChange={(e) => setMensaje(e.target.value)} placeholder="Ej: precio más grande, nuevo color de banda" />
        </label>
        <Link className="boton boton-secundario" href={esNuevo ? `/c/${slug}/templates` : `/c/${slug}/templates/${encodeURIComponent(nombreInicial)}`}>
          Cancelar
        </Link>
        <button className="boton" disabled={!habilitado} onClick={guardar} title="Cmd/Ctrl + S">
          {pendiente ? "Publicando…" : esNuevo ? "Crear y publicar" : "Publicar cambios"}
        </button>
      </div>

      {(v.errores.length > 0 || v.variablesDesconocidas.length > 0 || v.avisos.length > 0 || error) && (
        <div className="validacion">
          {error && (
            <div className="aviso aviso-error" role="alert">
              {error}
            </div>
          )}
          {v.errores.length > 0 && (
            <div className="aviso aviso-error">
              <b>No se puede publicar:</b>
              <ul>{v.errores.map((e) => <li key={e}>{e}</li>)}</ul>
            </div>
          )}
          {v.variablesDesconocidas.length > 0 && (
            <div className="aviso aviso-error">
              <b>Usa variables que este cliente no tiene:</b> {v.variablesDesconocidas.map((x) => `{${x}}`).join(", ")}. En la placa se verían tal cual, con llaves.
              <label style={{ display: "flex", gap: 6, marginTop: 6 }}>
                <input type="checkbox" checked={publicarIgual} onChange={(e) => setPublicarIgual(e.target.checked)} />
                Publicar igual (solo si este template lo usa otro flujo que sí completa esas variables)
              </label>
            </div>
          )}
          {v.avisos.length > 0 && (
            <div className="aviso aviso-alerta">
              <ul>{v.avisos.map((a) => <li key={a}>{a}</li>)}</ul>
            </div>
          )}
        </div>
      )}

      <div className="editor-columnas">
        <section className="hoja codigo">
          <div className="codigo-cabeza">
            <span>HTML</span>
            <span className="suave num">
              {meta.aspect_ratio}, {meta.width}×{meta.height} px
            </span>
          </div>
          <textarea
            value={html}
            onChange={(e) => setHtml(e.target.value)}
            spellCheck={false}
            aria-label="Código HTML del template"
            onKeyDown={(e) => {
              // Tab inserta dos espacios en vez de salir del campo.
              if (e.key === "Tab" && !e.shiftKey) {
                e.preventDefault();
                const el = e.currentTarget;
                const { selectionStart: a, selectionEnd: b } = el;
                const nuevo = html.slice(0, a) + "  " + html.slice(b);
                setHtml(nuevo);
                requestAnimationFrame(() => el.setSelectionRange(a + 2, a + 2));
              }
            }}
          />
        </section>
        <div className="vista">
          <EditorPreview html={htmlPreview} ancho={meta.width} alto={meta.height} nombre={nombre || "nuevo"} productos={productos} estilo={estilo} compacto />
        </div>
      </div>
    </div>
  );
}
