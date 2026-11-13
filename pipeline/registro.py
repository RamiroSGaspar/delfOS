"""El registro de la corrida: lo que el pipeline cuenta mientras corre, por la salida de errores.

Va a la salida de errores para no mezclarse con nada que se quiera capturar de la salida estándar.
"""
import sys
import threading

_bloqueo = threading.Lock()


def anotar(mensaje: str) -> None:
    """Escribe una línea del registro (los hilos del modelo también lo usan)."""
    with _bloqueo:
        print(mensaje, file=sys.stderr, flush=True)
