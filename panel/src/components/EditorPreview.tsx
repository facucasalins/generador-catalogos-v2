"use client";
import { Fragment, useMemo, useState } from "react";
import { HtmlEscalado, Prueba } from "./Prueba";
import {
  construirVariables,
  reemplazarVariables,
  type EstiloCliente,
  type ProductoRender,
} from "@/lib/render/variables";

export type OpcionProducto = ProductoRender & { seleccionado: boolean; tieneStock: boolean };

type Atajo = { id: string; texto: string; elegir: (ps: OpcionProducto[]) => OpcionProducto | undefined };

const titulo = (p: ProductoRender) => p.tituloPlaca || p.tituloCorto || p.nombre;
const atajos: Atajo[] = [
  { id: "sel", texto: "Un seleccionado", elegir: (ps) => ps.find((p) => p.seleccionado && p.tieneStock) },
  { id: "largo", texto: "Título más largo", elegir: (ps) => [...ps].sort((a, b) => titulo(b).length - titulo(a).length)[0] },
  { id: "caro", texto: "Precio más alto", elegir: (ps) => [...ps].sort((a, b) => b.precioLista - a.precioLista)[0] },
  { id: "sinpromo", texto: "Sin promo", elegir: (ps) => ps.find((p) => !p.precioPromocional || p.precioPromocional >= p.precioLista) },
];

export function EditorPreview({
  html,
  ancho,
  alto,
  nombre,
  productos,
  estilo,
}: {
  html: string;
  ancho: number;
  alto: number;
  nombre: string;
  productos: OpcionProducto[];
  estilo: EstiloCliente;
}) {
  const inicial = atajos[0].elegir(productos) ?? productos[0];
  const [sku, setSku] = useState(inicial?.sku ?? "");
  const [atajoActivo, setAtajoActivo] = useState<string | null>(inicial ? "sel" : null);
  const producto = productos.find((p) => p.sku === sku) ?? productos[0];

  const { render, variables } = useMemo(() => {
    if (!producto) return { render: null, variables: {} as Record<string, string> };
    const v = construirVariables(producto, estilo);
    return { render: reemplazarVariables(html, v), variables: v };
  }, [producto, estilo, html]);

  if (!producto || !render) {
    return <div className="vacio"><b>No hay productos en el inventario para probar este template.</b></div>;
  }

  const visibles = Object.entries(variables).filter(([k]) => !k.endsWith("_b64"));

  return (
    <div className="editor">
      <div className="mesa" style={{ display: "grid", placeItems: "center" }}>
        <div style={{ width: "100%", maxWidth: ancho >= alto ? 760 : 520 }}>
          <Prueba ancho={ancho} alto={alto}>
            <HtmlEscalado html={render.html} ancho={ancho} alto={alto} titulo={`Vista previa de ${nombre} con ${producto.sku}`} />
          </Prueba>
        </div>
      </div>

      <aside className="editor-lateral">
        <section className="hoja">
          <h2>Probar con</h2>
          <select
            className="selector"
            value={producto.sku}
            onChange={(e) => {
              setSku(e.target.value);
              setAtajoActivo(null);
            }}
            aria-label="Producto para la vista previa"
          >
            {productos.map((p) => (
              <option key={p.sku} value={p.sku}>
                {titulo(p)} {p.seleccionado ? "(seleccionado)" : ""}
              </option>
            ))}
          </select>
          <div className="atajos" role="group" aria-label="Casos para probar">
            {atajos.map((a) => {
              const elegido = a.elegir(productos);
              return (
                <button
                  key={a.id}
                  type="button"
                  disabled={!elegido}
                  aria-pressed={atajoActivo === a.id}
                  onClick={() => {
                    if (elegido) {
                      setSku(elegido.sku);
                      setAtajoActivo(a.id);
                    }
                  }}
                >
                  {a.texto}
                </button>
              );
            })}
          </div>
        </section>

        {render.sinReemplazar.length > 0 && (
          <div className="aviso aviso-error" role="alert" style={{ margin: 0 }}>
            <b>El template usa variables que no existen para este cliente:</b> {render.sinReemplazar.map((v) => `{${v}}`).join(", ")}.
            En la placa real se van a ver tal cual, con llaves.
          </div>
        )}

        <section className="hoja">
          <h2>Valores que recibe</h2>
          <div className="variables">
            {visibles.map(([k, v]) => (
              <Fragment key={k}>
                <code>{k}</code>
                <span>{v || <em className="suave">vacío</em>}</span>
              </Fragment>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}
