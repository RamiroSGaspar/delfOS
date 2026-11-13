"""El comando del pipeline: corre de punta a punta sobre un set y deja los 4 archivos oficiales.

    python -m pipeline --datos <carpeta> --salida <carpeta> [--sin-modelo] [--cache <archivo>]
                       [--informe <archivo>] [--enganche <archivo>]

- `--datos`: la carpeta con `comentarios.csv.gz`, `publicaciones.csv.gz`, `fuentes.csv` y `cuentas.csv.gz`.
- `--salida`: donde se escriben `comentarios.csv`, `narrativas.csv`, `cuentas.csv` y `costo.json`.
- `--sin-modelo`: sin IA; usa los respaldos (N8 por "tope", N10 por núcleos, N12 apagado). Funciona siempre.
- `--cache`: archivo de caché de las respuestas del modelo (se lee y se completa). Con la caché de una
  corrida anterior, la salida es idéntica y no hace falta clave.
- `--informe`: archivo JSON con el registro completo de la corrida (perfil de entrada, tiempos, modelo).
- `--enganche`: archivo CSV con la tabla de N11 para la capa interpretativa (apagado por defecto).

La clave del modelo se lee de `ANTHROPIC_API_KEY` o de `~/.config/qualydata/anthropic_api_key`.
"""
import time

INICIO = time.perf_counter()  # el tiempo del comando se mide desde acá, antes de importar las bibliotecas

import argparse  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", required=True, help="carpeta con los 4 archivos del set")
    ap.add_argument("--salida", required=True, help="carpeta donde se escriben los 4 archivos oficiales")
    ap.add_argument("--sin-modelo", action="store_true", help="corre sin IA, con los respaldos")
    ap.add_argument("--cache", help="archivo .jsonl de caché de las respuestas del modelo")
    ap.add_argument("--informe", help="archivo .json donde se escribe el registro completo de la corrida")
    ap.add_argument("--enganche", help="archivo .csv donde se escribe la tabla de N11 para la capa interpretativa")
    args = ap.parse_args(argv)

    datos = Path(args.datos)
    if not datos.is_dir():
        print(f"error: no existe la carpeta de datos {datos}", file=sys.stderr)
        return 2

    from pipeline.corrida import ejecutar  # las bibliotecas pesadas se cargan recién acá

    try:
        informe = ejecutar(datos, Path(args.salida), sin_modelo=args.sin_modelo, cache=args.cache, inicio=INICIO,
                           enganche=args.enganche)
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.informe:
        ruta = Path(args.informe)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(informe, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
