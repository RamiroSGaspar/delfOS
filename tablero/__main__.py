"""El comando del tablero: arma la página a partir del set y de la entrega.

    python -m tablero --datos <carpeta del set> --entrega <carpeta con los 4 archivos> [--informe <archivo.json>]
                      [--nombre <texto>] [--salida <archivo.html>]

- `--datos`: la carpeta del set (la misma que se le pasó al pipeline).
- `--entrega`: la carpeta con `comentarios.csv`, `narrativas.csv`, `cuentas.csv` y `costo.json`.
- `--informe`: el archivo que escribe el pipeline con `--informe`. Suma al tablero los avisos, las medidas del set
  de entrada, las señales de coordinación, el uso de la IA y los tiempos por etapa. Sin él, el tablero sale igual,
  con lo que hay en la entrega.
- `--nombre`: cómo llamar al set en el tablero. Por defecto, el nombre de su carpeta.
- `--salida`: el archivo que se escribe. Por defecto, `tablero.html` al lado de la carpeta de la entrega, para
  que en la entrega queden solo los 4 archivos oficiales.
"""
import argparse
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tablero", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", required=True, help="carpeta con los 4 archivos del set")
    ap.add_argument("--entrega", required=True, help="carpeta con los 4 archivos de la entrega")
    ap.add_argument("--informe", help="archivo .json del registro de la corrida (el de --informe del pipeline)")
    ap.add_argument("--nombre", help="cómo llamar al set en el tablero (por defecto, el nombre de su carpeta)")
    ap.add_argument("--salida", help="archivo .html que se escribe (por defecto, tablero.html al lado de la entrega)")
    args = ap.parse_args(argv)
    datos, entrega = Path(args.datos), Path(args.entrega)
    for nombre, carpeta in (("datos", datos), ("la entrega", entrega)):
        if not carpeta.is_dir():
            print(f"error: no existe la carpeta de {nombre} {carpeta}", file=sys.stderr)
            return 2

    from tablero.pagina import escribir
    from tablero.resumen import calcular

    try:
        resumen = calcular(datos, entrega, args.informe, args.nombre)
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    ruta = escribir(resumen, args.salida or entrega.resolve().parent / "tablero.html")
    t = resumen["totales"]
    print(f"tablero: {ruta} · {t['comentarios']} comentarios, {t['narrativas']} narrativas, "
          f"{t['cuentas_coordinadas']} cuentas coordinadas en {t['operaciones']} operaciones", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
