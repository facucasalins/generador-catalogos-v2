import "server-only";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { modoDemo } from "./config";
import type { Rol } from "./usuarios";

export type Sesion = { email: string; nombre: string; rol: Rol };

/** Sesión del usuario; si no hay, manda al login. El proxy ya filtra, esto es la segunda llave. */
export async function exigirSesion(): Promise<Sesion> {
  if (modoDemo) return { email: "demo@agencynusa.com", nombre: "Demo", rol: "admin" };
  const s = await auth();
  if (!s?.user?.email) redirect("/login");
  return { email: s.user.email, nombre: s.user.name ?? s.user.email, rol: s.rol ?? "operador" };
}
