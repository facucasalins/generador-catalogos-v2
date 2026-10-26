"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { agregarProductos, guardarSeleccionSku, revisarEntradas, type FichaEntrada } from "@/app/acciones";
import { EstadoEnVivo, useCorrida } from "./Corridas";

const PLATAFORMAS = ["Meta", "TikTok"] as const;

/** Grilla template × plataforma. `valor` son nombres con prefijo: Meta_default_4x5. */
export function SelectorTemplates({
  templates,
  valor,
  onChange,
}: {
  templates: string[];
  valor: Set<string>;
  onChange: (v: Set<string>) => void;
}) {
  const alternar = (n: string) => {
    const s = new Set(valor);
    if (s.has(n)) s.delete(n);
    else s.add(n);
    onChange(s);
  };
  const todaLaColumna = (p: string) => templates.every((t) => valor.has(`${p}_${t}`));
  return (
    <table className="grilla-templates-sel">
      <thead>
        <tr>
          <th>Template</th>
          {PLATAFORMAS.map((p) => (
            <th key={p}>
              <label>
                <input
                  type="checkbox"
                  checked={todaLaColumna(p)}
                  onChange={() => {
                    const s = new Set(valor);
                    const marcar = !todaLaColumna(p);
                    for (const t of templates) {
                      if (marcar) s.add(`${p}_${t}`);
                      else s.delete(`${p}_${t}`);
                    }
                    onChange(s);
                  }}
                />{" "}
                {p}
              </label>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {templates.map((t) => (
          <tr key={t}>
            <td>{t}</td>
            {PLATAFORMAS.map((p) => (
              <td key={p}>
                <input
                  type="checkbox"
                  aria-label={`${t} en ${p}`}
                  checked={valor.has(`${p}_${t}`)}
                  onChange={() => alternar(`${p}_${t}`)}
                />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const textoEstado: Record<FichaEntrada["estado"], [string, string]> = {
  ok: ["Se puede agregar", "etq-ok"],
  sin_stock: ["Sin stock: no va a salir", "etq-alerta"],
  no_publicado: ["No publicado en la tienda", "etq-alerta"],
  no_encontrado: ["No está en el inventario", "etq-error"],
};

const pesos = (n: number | null) => (n === null ? "" : "$" + Math.round(n).toLocaleString("es-AR"));

export function AgregarProductos({ slug, templates }: { slug: string; templates: string[] }) {
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState("");
  const [fichas, setFichas] = useState<FichaEntrada[] | null>(null);
  const [elegidos, setElegidos] = useState<Set<string>>(new Set());
  const [plantillas, setPlantillas] = useState<Set<string>>(new Set());
  const [mensaje, setMensaje] = useState<{ tipo: "ok" | "error"; texto: string } | null>(null);
  const [pendiente, iniciar] = useTransition();
  const router = useRouter();
  const inventario = useCorrida(slug, null);

  const revisar = () =>
    iniciar(async () => {
      setMensaje(null);
      const r = await revisarEntradas(slug, texto);
      if (!r.ok) return setMensaje({ tipo: "error", texto: r.error });
      setFichas(r.fichas);
      setElegidos(new Set(r.fichas.filter((f) => f.estado === "ok").flatMap((f) => f.productos.filter((p) => p.tieneStock && p.publicado).map((p) => p.sku))));
    });

  const agregar = () =>
    iniciar(async () => {
      const r = await agregarProductos(slug, [...elegidos], [...plantillas]);
      if (!r.ok) return setMensaje({ tipo: "error", texto: r.error });
      setMensaje({
        tipo: "ok",
        texto: `Listo: ${elegidos.size} ${elegidos.size === 1 ? "producto agregado" : "productos agregados"} a la Selección. Las placas se generan en la próxima corrida (o con "Generar ahora" en Corridas).`,
      });
      setFichas(null);
      setTexto("");
      router.refresh();
    });

  if (!abierto) {
    return (
      <button className="boton" onClick={() => setAbierto(true)}>
        Agregar productos
      </button>
    );
  }

  const faltan = fichas?.some((f) => f.estado === "no_encontrado");

  return (
    <section className="agregar">
      <div className="agregar-cabeza">
        <h2>Agregar productos</h2>
        <button className="boton boton-secundario" onClick={() => setAbierto(false)}>
          Cerrar
        </button>
      </div>
      <label className="campo">
        <span>Pegá URLs de la tienda o SKUs, uno por línea</span>
        <textarea
          rows={4}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder={"https://tienda.com.ar/productos/creatina-300g/\notro-sku"}
        />
      </label>
      <div className="filtros">
        <button className="boton" onClick={revisar} disabled={pendiente || !texto.trim()}>
          {pendiente && !fichas ? "Revisando…" : "Revisar"}
        </button>
      </div>

      {fichas && (
        <>
          <ul className="fichas">
            {fichas.map((f) => (
              <li key={f.entrada}>
                <div className="ficha-entrada">
                  <span className="sku">{f.entrada}</span>
                  <span className={`etiqueta ${textoEstado[f.estado][1]}`}>
                    {f.productos.length > 1 ? `${f.productos.length} variantes` : textoEstado[f.estado][0]}
                  </span>
                </div>
                {f.productos.map((p) => {
                  const sale = p.tieneStock && p.publicado;
                  return (
                    <label key={p.sku} className="ficha" data-apagada={!sale}>
                      <input
                        type="checkbox"
                        disabled={!sale}
                        checked={elegidos.has(p.sku)}
                        onChange={() => {
                          const s = new Set(elegidos);
                          if (s.has(p.sku)) s.delete(p.sku);
                          else s.add(p.sku);
                          setElegidos(s);
                        }}
                      />
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      {p.imagenUrl ? <img className="miniatura" src={p.imagenUrl} alt="" /> : <span className="miniatura" />}
                      <span className="ficha-datos">
                        <b>{p.nombre}</b>
                        <span className="sku">{p.sku}</span>
                        <span className="num">
                          {p.precioPromocional && p.precioPromocional < p.precioLista ? (
                            <>
                              <span className="tachado">{pesos(p.precioLista)}</span> {pesos(p.precioPromocional)}
                            </>
                          ) : (
                            pesos(p.precioLista)
                          )}
                          {" · "}stock {p.stock ?? "?"}
                        </span>
                        {!p.publicado && <span className="etiqueta etq-alerta">No publicado</span>}
                        {p.publicado && !p.tieneStock && <span className="etiqueta etq-alerta">Sin stock</span>}
                        {p.templatesActuales.length > 0 && (
                          <span className="suave">Ya tiene: {p.templatesActuales.join(", ")}</span>
                        )}
                      </span>
                    </label>
                  );
                })}
              </li>
            ))}
          </ul>

          {faltan && (
            <div className="aviso aviso-alerta">
              <b>Hay productos que no están en el inventario.</b> Si son nuevos en la tienda, actualizá el inventario (tarda un par de minutos) y revisá de nuevo.
              <div className="filtros" style={{ marginTop: 8 }}>
                <button className="boton boton-secundario" disabled={inventario.ocupado} onClick={() => inventario.correr("solo_inventario")}>
                  Actualizar inventario
                </button>
                {!inventario.ocupado && inventario.corrida?.estado === "ok" && (
                  <button className="boton" onClick={revisar}>
                    Revisar de nuevo
                  </button>
                )}
              </div>
              <EstadoEnVivo corrida={inventario.corrida} esperando={inventario.esperando} />
              {inventario.error && <p style={{ color: "var(--error)" }}>{inventario.error}</p>}
            </div>
          )}

          {elegidos.size > 0 && (
            <>
              <h3 className="sub">Con qué templates</h3>
              <SelectorTemplates templates={templates} valor={plantillas} onChange={setPlantillas} />
              <div className="filtros" style={{ marginTop: 12 }}>
                <button className="boton" onClick={agregar} disabled={pendiente || plantillas.size === 0}>
                  {pendiente ? "Guardando…" : `Agregar ${elegidos.size} ${elegidos.size === 1 ? "producto" : "productos"}`}
                </button>
                {plantillas.size === 0 && <span className="suave">Elegí al menos un template.</span>}
              </div>
            </>
          )}
        </>
      )}

      {mensaje && (
        <div className={`aviso ${mensaje.tipo === "ok" ? "aviso-info" : "aviso-error"}`} role="status" style={{ marginTop: 12, marginBottom: 0 }}>
          {mensaje.texto}
        </div>
      )}
    </section>
  );
}

/** Botón "Editar" de una fila: abre la grilla de templates de ese SKU. */
export function EditarSeleccion({ slug, sku, nombre, templates, actuales }: { slug: string; sku: string; nombre: string; templates: string[]; actuales: string[] }) {
  const [abierto, setAbierto] = useState(false);
  const [valor, setValor] = useState(new Set(actuales));
  const [error, setError] = useState<string | null>(null);
  const [pendiente, iniciar] = useTransition();
  const router = useRouter();

  const guardar = (final: Set<string>) =>
    iniciar(async () => {
      setError(null);
      const r = await guardarSeleccionSku(slug, sku, [...final]);
      if (!r.ok) return setError(r.error);
      setAbierto(false);
      router.refresh();
    });

  return (
    <>
      <button className="enlace" onClick={() => { setValor(new Set(actuales)); setAbierto(true); }}>
        {actuales.length ? "Editar" : "Agregar"}
      </button>
      {abierto && (
        <div className="modal-fondo" role="dialog" aria-modal="true" aria-label={`Templates de ${nombre}`} onClick={(e) => e.target === e.currentTarget && setAbierto(false)}>
          <div className="modal">
            <h2>{nombre}</h2>
            <p className="sku">{sku}</p>
            <SelectorTemplates templates={templates} valor={valor} onChange={setValor} />
            {error && <div className="aviso aviso-error" role="alert" style={{ margin: "12px 0 0" }}>{error}</div>}
            <div className="modal-pie">
              {actuales.length > 0 && (
                <button className="boton boton-peligro" disabled={pendiente} onClick={() => guardar(new Set())}>
                  Quitar de la selección
                </button>
              )}
              <span style={{ flex: 1 }} />
              <button className="boton boton-secundario" onClick={() => setAbierto(false)}>
                Cancelar
              </button>
              <button className="boton" disabled={pendiente} onClick={() => guardar(valor)}>
                {pendiente ? "Guardando…" : "Guardar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
