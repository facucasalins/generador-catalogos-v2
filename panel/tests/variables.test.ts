// Paridad preview (TypeScript) vs pipeline (Python).
// Corre los mismos casos por las dos implementaciones y exige igualdad exacta.
// Si no hay Python con las dependencias del pipeline, el test de paridad se
// saltea (los tests unitarios de abajo corren igual).
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import {
  construirVariables,
  formatearPrecioArs,
  reemplazarVariables,
  redondearComoPython,
  type EstiloCliente,
  type ProductoRender,
} from "../src/lib/render/variables";

const raizRepo = path.resolve(__dirname, "..", "..");
const clientes = JSON.parse(
  fs.readFileSync(path.join(__dirname, "..", "generated", "clientes.json"), "utf8"),
).clientes as { slug: string; estilo: EstiloCliente; cuotasNum: number }[];

const base: ProductoRender = {
  sku: "creatina-monohidratada-300g",
  nombre: "CREATINA MONOHIDRATADA ULTRAMICRONIZADA 300G SABOR NEUTRO",
  precioLista: 39999,
  precioPromocional: 24999,
  cuotasNum: 3,
  marca: "Flint",
  categoria: "",
  imagenUrl: "https://acdn-us.mitiendanube.com/stores/x/products/creatina.jpg",
  tituloPlaca: "Creatina Monohidratada 300g",
};

// Casos límite: sin promo, promo con decimales, .5 exacto, cuotas 0,
// sin enriquecimiento, precio de 7 dígitos.
const productos: Record<string, ProductoRender> = {
  base,
  sinPromo: { ...base, precioPromocional: null },
  promoCero: { ...base, precioPromocional: 0 },
  decimales: { ...base, precioLista: 59999.99, precioPromocional: 53999.5 },
  medioExacto: { ...base, precioLista: 2001, precioPromocional: 1001 },
  // .5 sobre número par: Python redondea a 24998, un Math.round daría 24999.
  medioPar: { ...base, precioLista: 30000, precioPromocional: 24998.5 },
  cuotasCero: { ...base, cuotasNum: 0 },
  sinEnriquecimiento: { ...base, tituloPlaca: undefined, tituloCorto: undefined },
  soloTituloCorto: { ...base, tituloPlaca: undefined, tituloCorto: "Creatina 300g" },
  millonario: { ...base, precioLista: 1234567, precioPromocional: 987654.33, cuotasNum: 9 },
};

const casos = clientes.flatMap((c) =>
  Object.entries(productos).map(([nombre, p]) => ({
    id: `${c.slug}/${nombre}`,
    producto: { ...p, cuotasNum: nombre === "cuotasCero" ? 0 : c.cuotasNum },
    estilo: c.estilo,
  })),
);

test("las variables de la preview coinciden con las del pipeline Python", (t) => {
  const py = spawnSync("python3", [path.join(__dirname, "paridad_python.py")], {
    cwd: raizRepo,
    input: JSON.stringify(casos),
    encoding: "utf8",
  });
  if (py.status !== 0) {
    // En CI la paridad es obligatoria: si Python no corre, el test falla.
    if (process.env.CI) assert.fail(`No pude correr el pipeline Python:\n${py.stderr}`);
    t.skip(`Python del pipeline no disponible: ${py.stderr.split("\n").slice(-3).join(" ")}`);
    return;
  }
  const esperado = JSON.parse(py.stdout) as Record<string, Record<string, string>>;
  for (const caso of casos) {
    const ts = construirVariables(caso.producto, caso.estilo);
    assert.deepEqual(ts, esperado[caso.id], `diferencia en ${caso.id}`);
  }
});

test("redondeo igual a round() de Python", () => {
  assert.equal(redondearComoPython(2.5), 2);
  assert.equal(redondearComoPython(3.5), 4);
  assert.equal(redondearComoPython(22499.1), 22499);
  assert.equal(redondearComoPython(22499.9), 22500);
});

test("formato de precio argentino", () => {
  assert.equal(formatearPrecioArs(39999), "$39.999");
  assert.equal(formatearPrecioArs(1234567.4), "$1.234.567");
  assert.equal(formatearPrecioArs(999), "$999");
});

test("reemplazo marca los placeholders que no existen", () => {
  const r = reemplazarVariables("<b>{titulo_placa}</b>{precio_efectivo_formateado} .a { margin: 0 }", {
    titulo_placa: "Hola",
  });
  assert.equal(r.html, "<b>Hola</b>{precio_efectivo_formateado} .a { margin: 0 }");
  assert.deepEqual(r.sinReemplazar, ["precio_efectivo_formateado"]);
});
