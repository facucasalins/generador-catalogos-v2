import "server-only";
import { JWT } from "google-auth-library";

// Misma cuenta de servicio que usa el pipeline (placas-bot@...), cargada en
// Vercel como GOOGLE_SERVICE_ACCOUNT_JSON con el mismo contenido que el secret
// de GitHub Actions.
let cliente: JWT | null = null;

export class FaltaCredencial extends Error {}

function obtenerCliente(): JWT {
  if (cliente) return cliente;
  const crudo = process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
  if (!crudo) {
    throw new FaltaCredencial(
      "Falta GOOGLE_SERVICE_ACCOUNT_JSON en Vercel: el panel no puede leer las sheets.",
    );
  }
  const cred = JSON.parse(crudo) as { client_email: string; private_key: string };
  cliente = new JWT({
    email: cred.client_email,
    key: cred.private_key,
    // Etapa 0 solo lee. La escritura de Selección se habilita en la Etapa 1.
    scopes: ["https://www.googleapis.com/auth/spreadsheets.readonly"],
  });
  return cliente;
}

export async function tokenGoogle(): Promise<string> {
  const { token } = await obtenerCliente().getAccessToken();
  if (!token) throw new Error("Google no devolvió un token de acceso.");
  return token;
}

export function emailCuentaServicio(): string | null {
  try {
    const crudo = process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
    return crudo ? (JSON.parse(crudo).client_email as string) : null;
  } catch {
    return null;
  }
}
