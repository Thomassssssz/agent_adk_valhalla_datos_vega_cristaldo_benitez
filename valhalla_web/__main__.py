"""Levanta la interfaz web:  python -m valhalla_web"""
import argparse

import uvicorn

from .server import crear_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Interfaz web de Valhalla")
    parser.add_argument("--host", default="127.0.0.1", help="Dirección donde escucha (por defecto, solo tu equipo)")
    parser.add_argument("--port", type=int, default=8080, help="Puerto (por defecto 8080)")
    args = parser.parse_args()
    print(f"\n  Valhalla listo en  http://{args.host}:{args.port}\n  (Ctrl+C para cerrar)\n")
    uvicorn.run(crear_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
