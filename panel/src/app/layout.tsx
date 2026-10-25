import type { Metadata } from "next";
// Tipografía autoalojada (no depende de Google Fonts en el build ni en el navegador).
import "@fontsource-variable/schibsted-grotesk/index.css";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Catálogos Nusa", template: "%s · Catálogos Nusa" },
  description: "Panel para operar los catálogos de placas de Nusa Agency",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-AR">
      <body>{children}</body>
    </html>
  );
}
