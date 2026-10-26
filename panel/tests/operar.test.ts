import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { handleDeUrl, resolverEntradas } from "../src/lib/entradas";
import { planificar } from "../src/lib/seleccion-plan";
import { validarTemplate } from "../src/lib/render/validar";
import type { EstiloCliente } from "../src/lib/render/variables";

// ---------- URLs y SKUs ----------

test("handle de URLs de Tiendanube", () => {
  assert.equal(handleDeUrl("https://www.flint.com.ar/productos/creatina-300g/"), "creatina-300g");
  assert.equal(handleDeUrl("flint.com.ar/productos/creatina-300g?variant=123"), "creatina-300g");
  assert.equal(handleDeUrl("https://tienda.com/productos/Bota-Texana/"), "bota-texana");
  assert.equal(handleDeUrl("creatina-300g"), null);
});

const inv = [
  { sku: "creatina-300g", urlProducto: "https://flint.com.ar/productos/creatina-300g/", tieneStock: true, publicado: true },
  { sku: "whey-choco", urlProducto: "https://flint.com.ar/productos/whey-choco/", tieneStock: false, publicado: true },
  // MoraShop: variantes con SKU propio que comparten la URL del producto
  { sku: "MS-100-A", urlProducto: "https://morashop.com.ar/productos/proteina/", tieneStock: true, publicado: true },
  { sku: "MS-100-B", urlProducto: "https://morashop.com.ar/productos/proteina/", tieneStock: false, publicado: true },
];

test("resuelve URL, SKU, variantes y problemas", () => {
  const r = resolverEntradas(
    "https://flint.com.ar/productos/creatina-300g/\nwhey-choco, https://morashop.com.ar/productos/proteina/ MS-100-B nada-que-ver",
    inv,
  );
  assert.deepEqual(
    r.map((x) => [x.entrada, x.estado, x.productos.map((p) => p.sku)]),
    [
      ["https://flint.com.ar/productos/creatina-300g/", "ok", ["creatina-300g"]],
      ["whey-choco", "sin_stock", ["whey-choco"]],
      ["https://morashop.com.ar/productos/proteina/", "ok", ["MS-100-A", "MS-100-B"]],
      ["MS-100-B", "sin_stock", ["MS-100-B"]],
      ["nada-que-ver", "no_encontrado", []],
    ],
  );
});

// ---------- Plan de escritura en Selección ----------

const header = ["sku", "generar", "Meta_cuotas_4x5", "TikTok_cuotas_4x5", "prioridad", "notas"];
const filas = [
  ["creatina", true, true, false, "", "nota"],
  ["", false, false, false, "", ""],
];

test("tilda un SKU existente sin tocar prioridad ni notas", () => {
  const p = planificar(header, filas, [{ sku: "creatina", templates: ["TikTok_cuotas_4x5"] }]);
  assert.deepEqual(p.columnasNuevas, []);
  assert.deepEqual(p.filas, [{ fila: 2, desde: 1, valores: [true, false, true] }]);
});

test("agrega un SKU nuevo en la primera fila libre y crea la columna que falta", () => {
  const p = planificar(header, filas, [{ sku: "whey", templates: ["Meta_default_4x5", "Meta_cuotas_4x5"] }]);
  assert.deepEqual(p.columnasNuevas, ["Meta_default_4x5"]);
  assert.equal(p.indiceInsercion, 4);
  // header final: sku generar Meta_cuotas TikTok_cuotas Meta_default prioridad notas
  assert.deepEqual(p.filas, [{ fila: 3, desde: 0, valores: ["whey", true, true, false, true] }]);
});

test("quitar deja la fila con generar=FALSE", () => {
  const p = planificar(header, filas, [{ sku: "creatina", templates: [] }]);
  assert.deepEqual(p.filas, [{ fila: 2, desde: 1, valores: [false, false, false] }]);
});

test("se niega a escribir una pestaña con otro formato", () => {
  assert.throws(() => planificar(["nombre", "x"], [], [{ sku: "a", templates: ["Meta_x"] }]));
});

// ---------- Validación de templates ----------

const generado = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "generated", "clientes.json"), "utf8"));
const muestra = {
  sku: "x",
  nombre: "PRODUCTO DE PRUEBA",
  precioLista: 39999,
  precioPromocional: 24999,
  cuotasNum: 3,
  marca: "M",
  categoria: "",
  imagenUrl: "https://x/y.jpg",
  tituloPlaca: "Producto de prueba",
};

test("los templates actuales del repo pasan la validación (salvo los casos conocidos)", () => {
  const fallas: string[] = [];
  for (const c of generado.clientes as { slug: string; estilo: EstiloCliente; templates: { nombre: string; html: string }[] }[]) {
    for (const t of c.templates) {
      const v = validarTemplate({ nombre: t.nombre, html: t.html, existentes: [], esNuevo: false, estilo: c.estilo, muestra });
      if (v.errores.length || v.variablesDesconocidas.length) {
        fallas.push(`${c.slug}/${t.nombre}: ${[...v.errores, ...v.variablesDesconocidas].join(" | ")}`);
      }
    }
  }
  // Conocidos: genki y seleccion sin bloque META; seguimiento usa variables de otro flujo.
  const esperadas = fallas.filter((f) => !/^morashop\/(genki|seleccion|seguimiento):/.test(f));
  assert.deepEqual(esperadas, []);
});

test("el validador frena lo que rompería la placa", () => {
  const estilo = { hotsaleDiscountFactor: 1, descuentoEfectivoFactor: null, cuotasSobrePromocional: false, variablesGlobales: {} };
  const v = validarTemplate({
    nombre: "Meta_Nuevo",
    html: "<html>{precio_efectivo_formateado}<script src='https://x.com/a.js'></script></html>",
    existentes: [],
    esNuevo: true,
    estilo,
    muestra,
  });
  assert.equal(v.errores.length, 4); // nombre inválido x2, sin META, script externo
  assert.deepEqual(v.variablesDesconocidas, ["precio_efectivo_formateado"]);
});
