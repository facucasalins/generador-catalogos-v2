import { notFound } from "next/navigation";
import { AvisoError, EstadoCorrida, intentar } from "@/components/Estados";
import { buscarCliente, repoGithub } from "@/lib/config";
import { obtenerCorridas } from "@/lib/datos";
import { cronLegible, duracion, fechaHora } from "@/lib/formato";

export const dynamic = "force-dynamic";

export default async function Corridas({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const c = buscarCliente(slug);
  if (!c) notFound();

  const r = await intentar(() => obtenerCorridas(c, 15));
  if (!r.ok) return <AvisoError error={r.error} que="las corridas" />;
  const { corridas, aviso } = r.valor;
  const workflowUrl = c.workflow ? `https://github.com/${repoGithub}/actions/workflows/${c.workflow.archivo}` : null;

  return (
    <section className="hoja">
      <div className="hoja-cabeza">
        <div>
          <h2>Corridas del pipeline</h2>
          <p className="suave" style={{ fontSize: "var(--texto-s)" }}>
            {c.workflow ? `${c.workflow.nombre}, ${cronLegible(c.workflow.cron)}.` : "Sin workflow."} Disparar a demanda llega en la Etapa 3.
          </p>
        </div>
        {workflowUrl && (
          <a className="boton boton-secundario" href={workflowUrl} target="_blank" rel="noreferrer">
            Abrir en GitHub Actions
          </a>
        )}
      </div>
      {aviso && <div className="aviso aviso-alerta" style={{ margin: 16 }}>{aviso}</div>}
      {corridas.length === 0 && !aviso ? (
        <div className="vacio"><b>Sin corridas todavía.</b></div>
      ) : corridas.length > 0 ? (
        <div className="tabla-envoltura">
          <table className="tabla">
            <thead>
              <tr>
                <th>Inicio</th>
                <th>Estado</th>
                <th>Origen</th>
                <th className="der">Duración</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {corridas.map((x) => (
                <tr key={x.id}>
                  <td className="num">{fechaHora(x.inicio)}</td>
                  <td><EstadoCorrida estado={x.estado} /></td>
                  <td>{x.disparadaPor}{x.intento > 1 ? `, intento ${x.intento}` : ""}</td>
                  <td className="der num">{duracion(x.inicio, x.fin)}</td>
                  <td className="der">
                    <a href={x.url} target="_blank" rel="noreferrer">Ver log</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
