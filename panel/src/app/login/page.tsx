import { redirect } from "next/navigation";
import { auth, signIn } from "@/auth";

const errores: Record<string, string> = {
  AccessDenied: "Tu cuenta de Google no tiene acceso al panel. Pedile a un admin que te agregue en la pestaña Usuarios.",
  Configuration: "El login no está configurado en el servidor. Falta cargar las credenciales de Google en Vercel.",
};

export default async function Login({ searchParams }: { searchParams: Promise<{ error?: string; volver?: string }> }) {
  const { error, volver } = await searchParams;
  if (process.env.PANEL_DEMO === "1" || (await auth())) redirect(volver ?? "/");
  const destino = volver?.startsWith("/") ? volver : "/";

  return (
    <main className="login">
      <div className="hoja login-caja">
        <div>
          <h1>Catálogos Nusa</h1>
          <p className="suave">Entrá con la cuenta de Google que te dio la agencia.</p>
        </div>
        {error && (
          <div className="aviso aviso-error" role="alert" style={{ margin: 0 }}>
            {errores[error] ?? "No se pudo iniciar sesión. Probá de nuevo."}
          </div>
        )}
        <form
          action={async () => {
            "use server";
            await signIn("google", { redirectTo: destino });
          }}
        >
          <button className="boton" type="submit" style={{ width: "100%", justifyContent: "center", padding: "10px 14px" }}>
            Entrar con Google
          </button>
        </form>
      </div>
    </main>
  );
}
