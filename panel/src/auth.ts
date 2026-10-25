import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import { buscarUsuario, type Rol } from "@/lib/usuarios";

declare module "next-auth" {
  interface Session {
    rol?: Rol;
  }
}

// Login con Google. Solo entran los emails de PANEL_ADMIN_EMAILS o los activos
// en la pestaña Usuarios de la sheet "Panel de Catálogos".
export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [Google],
  trustHost: true,
  session: { strategy: "jwt", maxAge: 60 * 60 * 12 },
  pages: { signIn: "/login", error: "/login" },
  callbacks: {
    async signIn({ profile }) {
      if (!profile?.email || profile.email_verified === false) return false;
      return (await buscarUsuario(profile.email)) !== null;
    },
    async jwt({ token, profile }) {
      if (profile?.email) {
        const usuario = await buscarUsuario(profile.email);
        token.rol = usuario?.rol ?? "operador";
      }
      return token;
    },
    async session({ session, token }) {
      session.rol = (token.rol as Rol | undefined) ?? "operador";
      return session;
    },
  },
});
