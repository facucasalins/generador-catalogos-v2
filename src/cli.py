"""CLI principal del generador de catálogos v2.

Uso:
    python -m src.cli --cliente=morashop
    CLIENTE=morashop python -m src.cli

En Fase A este CLI solo valida que el repo está bien configurado.
Los bloques se implementan en fases siguientes.
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generador de catálogos v2 (Agency Nusa)"
    )
    parser.add_argument(
        "--cliente",
        type=str,
        default=os.environ.get("CLIENTE"),
        help="Nombre del cliente (carpeta dentro de clients/). "
             "También se acepta vía env var CLIENTE.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ejecuta sin escribir nada (modo prueba).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.cliente:
        print("❌ Falta --cliente o env var CLIENTE")
        print("   Uso: python -m src.cli --cliente=morashop")
        sys.exit(2)

    cliente_dir = Path(__file__).parent.parent / "clients" / args.cliente
    if not cliente_dir.exists():
        clientes_disponibles = [
            p.name for p in cliente_dir.parent.iterdir()
            if p.is_dir() and not p.name.startswith("_")
        ]
        print(f"❌ Cliente '{args.cliente}' no existe.")
        print(f"   Clientes disponibles: {clientes_disponibles}")
        print(f"   Esperaba carpeta: {cliente_dir}")
        sys.exit(3)

    pipeline_path = cliente_dir / "pipeline.yaml"
    if not pipeline_path.exists():
        print(f"❌ Falta {pipeline_path}")
        sys.exit(4)

    # Fase A: solo confirmamos que el setup está OK
    print(f"✅ Setup OK para cliente: {args.cliente}")
    print(f"   Carpeta: {cliente_dir}")
    print(f"   Config: {pipeline_path}")
    print(f"   Dry run: {args.dry_run}")
    print()
    print("⚠️  Bloques de negocio aún no implementados (Fase A).")
    print("   Ver docs/ARCHITECTURE.md para el roadmap.")
    sys.exit(0)


if __name__ == "__main__":
    main()
