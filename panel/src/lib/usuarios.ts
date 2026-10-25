import "server-only";
import { aObjetos, esSi, leerPestanas, nombresPestanas, texto } from "./sheets";

export type Rol = "admin" | "operador";
export type Usuario = { email: string; nombre: string; rol: Rol };

// Admins fijos por variable de entorno: entran aunque la sheet de usuarios
// no exista o no se pueda leer. Así nunca quedás afuera de tu propio panel.
function adminsFijos(): string[] {
  return (process.env.PANEL_ADMIN_EMAILS ?? "")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter(Boolean);
}

/** Busca al usuario en PANEL_ADMIN_EMAILS y en la pestaña Usuarios de "Panel de Catálogos". */
export async function buscarUsuario(emailCrudo: string | null | undefined): Promise<Usuario | null> {
  const email = (emailCrudo ?? "").trim().toLowerCase();
  if (!email) return null;
  if (adminsFijos().includes(email)) return { email, nombre: email, rol: "admin" };

  const sheetId = process.env.PANEL_SHEET_ID;
  if (!sheetId) return null;
  try {
    // Pestaña "Usuarios"; si no existe (sheet recién creada), la primera.
    const nombres = await nombresPestanas(sheetId);
    const pestana = nombres.includes("Usuarios") ? "Usuarios" : nombres[0];
    if (!pestana) return null;
    const filas = (await leerPestanas(sheetId, [pestana]))[pestana];
    const fila = aObjetos(filas).find((f) => texto(f.email).toLowerCase() === email);
    if (!fila || !esSi(fila.activo)) return null;
    return {
      email,
      nombre: texto(fila.nombre) || email,
      rol: texto(fila.rol).toLowerCase() === "admin" ? "admin" : "operador",
    };
  } catch (e) {
    console.error("[usuarios] No pude leer la pestaña Usuarios:", e);
    return null;
  }
}
