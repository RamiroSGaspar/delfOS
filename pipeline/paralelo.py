"""Reparto del trabajo por texto (P4, P5 y el idioma) entre varios procesos.

La normalización y el idioma se calculan texto por texto, en Python puro: son el trabajo más largo del
pipeline y no se pueden repartir entre hilos (Python ejecuta un hilo a la vez). Se reparten entre procesos:
la lista de textos se corta en partes, cada proceso calcula las suyas y los resultados se juntan **en el
orden original**. Cada texto se procesa con la misma función, así que el resultado es el mismo que en un
solo proceso.

Los procesos se arrancan con el método "spawn" (el de Windows y macOS): cada uno importa solo los módulos
livianos del paquete (`pipeline.texto` y `pipeline.idioma`, que no usan Polars). Si no se pueden arrancar,
o si se caen, el trabajo se hace en el proceso principal.
"""
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor

from pipeline.registro import anotar

MINIMO_DE_TEXTOS = 20_000  # con menos textos, arrancar procesos cuesta más de lo que ahorra


def partir(elementos: list, partes: int) -> list:
    """La lista en `partes` pedazos seguidos, de tamaños parecidos."""
    partes = max(1, min(partes, len(elementos)))
    tam, resto = divmod(len(elementos), partes)
    salida, inicio = [], 0
    for i in range(partes):
        fin = inicio + tam + (1 if i < resto else 0)
        salida.append(elementos[inicio:fin])
        inicio = fin
    return salida


class Tarea:
    """Una función por lotes lanzada sobre una lista: `resultados()` devuelve la lista completa, en orden."""

    def __init__(self, funcion_lote, futuros=None, resultado=None, elementos=None):
        self._funcion_lote, self._futuros, self._resultado, self._elementos = funcion_lote, futuros, resultado, elementos

    def resultados(self) -> list:
        if self._resultado is None:
            try:
                self._resultado = [x for f in self._futuros for x in f.result()]
            except Exception as e:  # un proceso que se cayó: se hace en el proceso principal
                anotar(f"  procesos: falló el reparto ({type(e).__name__}); se sigue en un solo proceso")
                self._resultado = self._funcion_lote(self._elementos)
        return self._resultado


class Repartidor:
    """Lanza funciones por lotes en varios procesos (o en el principal, si `procesos` es 1)."""

    def __init__(self, procesos: int):
        self.procesos = max(1, min(int(procesos), os.cpu_count() or 1))
        self._pool = None
        if self.procesos > 1:
            try:
                self._pool = ProcessPoolExecutor(max_workers=self.procesos,
                                                 mp_context=multiprocessing.get_context("spawn"))
            except Exception as e:
                anotar(f"  procesos: no se pudieron arrancar ({type(e).__name__}); se sigue en un solo proceso")
                self.procesos = 1

    def lanzar(self, funcion_lote, elementos: list) -> Tarea:
        """Empieza a calcular `funcion_lote` sobre los elementos y devuelve enseguida."""
        if self._pool is None:
            return Tarea(funcion_lote, resultado=funcion_lote(elementos))
        try:
            futuros = [self._pool.submit(funcion_lote, parte) for parte in partir(elementos, 2 * self.procesos)]
        except Exception as e:
            anotar(f"  procesos: falló el reparto ({type(e).__name__}); se sigue en un solo proceso")
            return Tarea(funcion_lote, resultado=funcion_lote(elementos))
        return Tarea(funcion_lote, futuros=futuros, elementos=elementos)

    def cerrar(self):
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
