const zona = "America/Argentina/Buenos_Aires";

export function fechaHora(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso.includes("T") || iso.endsWith("Z") ? iso : iso.replace(" ", "T") + "-03:00");
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-AR", { timeZone: zona, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function haceCuanto(iso: string | null | undefined, ahora = Date.now()): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const min = Math.round((ahora - d.getTime()) / 60000);
  if (min < 1) return "recién";
  if (min < 60) return `hace ${min} min`;
  const h = Math.round(min / 60);
  if (h < 24) return `hace ${h} h`;
  const dias = Math.round(h / 24);
  return dias === 1 ? "ayer" : `hace ${dias} días`;
}

export function duracion(inicio: string, fin: string | null): string {
  if (!fin) return "";
  const s = Math.round((new Date(fin).getTime() - new Date(inicio).getTime()) / 1000);
  if (!Number.isFinite(s) || s < 0) return "";
  const m = Math.floor(s / 60);
  return m > 0 ? `${m} min ${s % 60} s` : `${s} s`;
}

export function pesos(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  return "$" + Math.round(n).toLocaleString("es-AR");
}

// "37 9 * * *" (UTC) → "todos los días 06:37"
export function cronLegible(cron: string | null): string {
  if (!cron) return "sin horario";
  const [min, hora, dia, mes, semana] = cron.split(/\s+/);
  if (dia !== "*" || mes !== "*" || semana !== "*" || !/^\d+$/.test(min) || !/^\d+$/.test(hora)) return cron;
  const horaArt = (Number(hora) - 3 + 24) % 24;
  return `todos los días ${String(horaArt).padStart(2, "0")}:${min.padStart(2, "0")}`;
}
