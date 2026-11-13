"""El comando que abre delfOS.

    python -m delfos [--puerto <número>] [--sin-abrir]

Arranca el servidor en esta computadora y abre la ventana de la aplicación. Si delfOS ya está corriendo, solo
abre otra ventana; si el que está corriendo quedó con una versión anterior del código, lo reemplaza. Se cierra
con Ctrl+C, o solo, unos minutos después de cerrar la última ventana.

- `--puerto`: el puerto donde escucha. Si está ocupado, usa cualquiera libre.
- `--sin-abrir`: no abre la ventana; imprime la dirección para abrirla a mano.
"""
import argparse
import signal
import sys


def _terminar(*_):
    """Un pedido de cierre de afuera se trata como un Ctrl+C: el servidor cancela lo que corre y se cierra en orden."""
    raise KeyboardInterrupt


def main(argv=None) -> int:
    from delfos import servidor

    ap = argparse.ArgumentParser(prog="python -m delfos", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--puerto", type=int, default=servidor.PUERTO, help="el puerto donde escucha")
    ap.add_argument("--sin-abrir", action="store_true", help="no abre la ventana")
    args = ap.parse_args(argv)

    abierta = servidor.instancia_abierta()
    if abierta and (abierta["al_dia"] or abierta["ocupada"]):
        print(f"delfOS ya está abierto en {abierta['url']}" + ("" if abierta["al_dia"] else ", con una versión anterior que está analizando"),
              file=sys.stderr)
        if not args.sin_abrir:
            servidor.abrir_ventana(abierta["url"])
        return 0
    if abierta:
        servidor.cerrar_instancia(abierta)  # quedó corriendo con una versión anterior del código: se reemplaza

    signal.signal(signal.SIGTERM, _terminar)
    s = servidor.Servidor(args.puerto)
    servidor.anotar_instancia(s)
    print(f"delfOS está en {s.url} (Ctrl+C para cerrarlo)", file=sys.stderr)
    if not args.sin_abrir:
        servidor.abrir_ventana(s.url)
    try:
        s.servir()
    except KeyboardInterrupt:
        pass
    finally:
        s.cerrar()
        servidor.borrar_instancia()
    return 0


if __name__ == "__main__":
    sys.exit(main())
