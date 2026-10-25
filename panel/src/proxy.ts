import { NextResponse } from "next/server";
import { auth } from "@/auth";

// Todo el panel requiere sesión, salvo el login y las rutas de Auth.js.
// En modo demo (solo desarrollo local) no hay login.
export default auth((req) => {
  if (process.env.PANEL_DEMO === "1") return NextResponse.next();
  const { pathname } = req.nextUrl;
  if (pathname.startsWith("/login") || pathname.startsWith("/api/auth")) return NextResponse.next();
  if (!req.auth) {
    const url = new URL("/login", req.nextUrl);
    if (pathname !== "/") url.searchParams.set("volver", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg).*)"],
};
