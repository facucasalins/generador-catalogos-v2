import Link from "next/link";
import { EstadoCorrida } from "@/components/Estados";
import { clientes } from "@/lib/config";
import { haceCuanto } from "@/lib/formato";
import { resumirCliente } from "@/lib/resumen";
import { ErrorSheets } from "@/lib/sheets";
import { FaltaCredencial } from "@/lib/google";

export const dynamic = "force-dynamic";

export default async function Inicio() {
  const resumenes = await Promise.all(clientes.map(resumirCliente));
  const errorGlobal = resumenes.find((r) => r.error instanceof FaltaCredencial)?.error;
  const conAlertas = resumenes.filter((r) => r.error || r.alertas.length).length;

  return (
    <>
      <header className="cabecera">
        <h1>Resumen</h1>
        <p className="suave">
          {conAlertas === 0
            ? `${clientes.length} clientes, ninguno con alertas.`
            : `${clientes.length} clientes, ${conAlertas} con algo para revisar.`}
        </p>
      </header>

      {errorGlobal instanceof Error && (
        <div className="aviso aviso-error" role="alert">
          <b>El panel todavía no puede leer las sheets.</b> {errorGlobal.message}
        </div>
      )}

      <div className="clientes-lista">
        {resumenes.map((r) => (
          <Link key={r.cliente.slug} href={`/c/${r.cliente.slug}`} className="hoja fila-cliente">
            <div className="dato">
              <h2>{r.cliente.nombre}</h2>
              <span className="rotulo">{r.cliente.templates.length} templates</span>
            </div>
            <div className="dato">
              <span className="valor">{r.skusSeleccionados}</span>
              <span className="rotulo">SKUs seleccionados de {r.productos}</span>
            </div>
            <div className="dato">
              <span className="valor">{r.placasVigentes}</span>
              <span className="rotulo">placas vigentes</span>
            </div>
            <div className="dato">
              {r.ultimaCorrida ? (
                <>
                  <EstadoCorrida estado={r.ultimaCorrida.estado} />
                  <span className="rotulo">{haceCuanto(r.ultimaCorrida.inicio)}</span>
                </>
              ) : (
                <span className="rotulo">Sin corridas leídas</span>
              )}
            </div>
            <div className="alertas">
              {r.error && !(r.error instanceof FaltaCredencial) ? (
                <span className="etiqueta etq-error">
                  {r.error instanceof ErrorSheets ? r.error.message : "No se pudieron leer sus datos"}
                </span>
              ) : r.alertas.length === 0 ? (
                <span className="suave">Sin alertas</span>
              ) : (
                r.alertas.slice(0, 3).map((a, i) => (
                  <span key={i} style={{ color: a.tipo === "error" ? "var(--error)" : "var(--alerta)" }}>
                    {a.texto}
                  </span>
                ))
              )}
            </div>
          </Link>
        ))}
      </div>
    </>
  );
}
