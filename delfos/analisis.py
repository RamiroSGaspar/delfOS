"""El análisis de un proyecto: corre el motor, arma el tablero y cuenta por dónde va.

Corre `python -m pipeline` y después `python -m tablero`, cada uno en su proceso, sobre la carpeta del proyecto.
El resultado nuevo se escribe aparte y reemplaza al anterior recién cuando todo terminó bien: si el análisis falla
o se cancela, el resultado anterior queda como estaba.

Los pasos que se muestran son los que el motor avisa de verdad en su registro; no hay porcentajes inventados.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from delfos import proyectos
from delfos.proyectos import ErrorDeProyecto
from delfos.rutas import RAIZ

PASOS = ("Leer los datos", "Armar las narrativas", "Posturas, origen, títulos y coordinación", "Armar el tablero")
MARCAS = (("pipeline ", 0), ("  lectura:", 1), ("  puente:", 2))  # la línea del registro que abre cada paso
MAX_LINEAS = 200
_bloqueo = threading.Lock()
_analisis = {}  # {id del proyecto: su último Analisis}


class Analisis:
    def __init__(self, proyecto_id: str, carpeta: Path):
        self.proyecto_id, self.carpeta = proyecto_id, Path(carpeta)
        self.estado, self.paso, self.lineas, self.error = "analizando", 0, [], None
        self.inicio, self.fin = time.time(), None
        self.proceso, self.cancelado = None, False

    def como_dict(self) -> dict:
        return {"estado": self.estado, "paso": self.paso, "pasos": list(PASOS), "error": self.error,
                "segundos": round((self.fin or time.time()) - self.inicio, 1),
                # Las líneas con sangría son las etapas que anota el motor; las demás llevan rutas de esta computadora.
                "registro": [linea.strip() for linea in self.lineas if linea.startswith("  ")][-12:]}

    def _correr(self, argumentos: list) -> int:
        """Corre un módulo de Python desde la raíz del repositorio y sigue su registro línea por línea."""
        opciones = {"start_new_session": True} if os.name == "posix" else {}
        entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # el registro llega en UTF-8 también en Windows
        self.proceso = subprocess.Popen([sys.executable, "-m", *argumentos], cwd=RAIZ, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                        env=entorno, **opciones)
        if self.cancelado:
            self.cancelar()
        for linea in self.proceso.stderr:
            linea = linea.rstrip("\n")
            self.lineas = (self.lineas + [linea])[-MAX_LINEAS:]
            for marca, paso in MARCAS:
                if linea.startswith(marca):
                    self.paso = max(self.paso, paso)
        return self.proceso.wait()

    def cancelar(self):
        self.cancelado = True
        proceso = self.proceso
        if proceso and proceso.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(proceso.pid, signal.SIGTERM)  # el motor reparte trabajo en varios procesos
                else:
                    proceso.terminate()
            except OSError:
                pass

    def ejecutar(self):
        c = self.carpeta
        nuevo, informe, tablero = c / "resultado.nuevo", c / "informe.nuevo.json", c / "tablero.nuevo.html"
        try:
            self._limpiar(nuevo, informe, tablero)
            codigo = self._correr(["pipeline", "--datos", str(c / "datos"), "--salida", str(nuevo),
                                   "--cache", str(c / "cache.jsonl"), "--informe", str(informe)])
            if codigo == 0 and not self.cancelado:
                self.paso = 3
                codigo = self._correr(["tablero", "--datos", str(c / "datos"), "--entrega", str(nuevo), "--informe", str(informe),
                                       "--nombre", proyectos.leer(self.proyecto_id)["nombre"], "--salida", str(tablero)])
            if self.cancelado:
                self.estado = "cancelado"
            elif codigo != 0:
                self.error = self._motivo()
            else:
                if (c / "resultado").exists():
                    shutil.rmtree(c / "resultado")
                nuevo.rename(c / "resultado")
                informe.replace(c / "informe.json")
                tablero.replace(c / "tablero.html")
                self.paso, self.estado = len(PASOS), "listo"
        except OSError as e:
            self.error = f"No se pudo correr el análisis: {e.strerror or e}."
        finally:
            self._limpiar(nuevo, informe, tablero)
            self.fin = time.time()
            if self.error:
                self.estado = "error"
            self._anotar()

    @staticmethod
    def _limpiar(nuevo: Path, informe: Path, tablero: Path):
        shutil.rmtree(nuevo, ignore_errors=True)
        for ruta in (informe, tablero):
            ruta.unlink(missing_ok=True)

    def _motivo(self) -> str:
        errores = [linea[6:].strip() for linea in self.lineas if linea.startswith("error:")]
        motivo = errores[-1] if errores else "el análisis se cortó antes de terminar"
        return motivo[:1].upper() + motivo[1:] + ("" if motivo.endswith(".") else ".")

    def _anotar(self):
        """Deja en `proyecto.json` cómo terminó: el último análisis bueno o el último intento fallido."""
        try:
            if self.estado == "listo":
                proyectos.actualizar(self.proyecto_id, ultimo_intento=None, ultimo_analisis={
                    "fecha": proyectos.ahora(), "segundos": round(self.fin - self.inicio, 1), **self._del_informe()})
            elif self.estado == "error":
                proyectos.actualizar(self.proyecto_id, ultimo_intento={
                    "fecha": proyectos.ahora(), "error": self.error, "registro": self.lineas[-40:]})
        except (OSError, ValueError):
            pass

    def _del_informe(self) -> dict:
        try:
            informe = json.loads((self.carpeta / "informe.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        modelo = informe.get("uso_modelo") or {}
        return {"segundos_del_motor": informe.get("segundos"), "conteos": informe.get("conteos") or {},
                "usd_ia": (informe.get("costo") or {}).get("usd_ia"),
                "con_ia": (modelo.get("llamadas_api") or 0) + (modelo.get("respuestas_de_cache") or 0) > 0,
                "llamadas_a_la_api": modelo.get("llamadas_api") or 0, "usd_gastado": modelo.get("usd_gastado") or 0}


def iniciar(proyecto_id: str) -> Analisis:
    carpeta = proyectos.carpeta_de(proyecto_id)
    if not (carpeta / "datos").is_dir():
        raise ErrorDeProyecto("No se encuentran los datos del proyecto.")
    with _bloqueo:
        if hay_en_curso():
            raise ErrorDeProyecto("Ya hay un análisis en curso. Esperá a que termine o cancelalo.")
        analisis = _analisis[proyecto_id] = Analisis(proyecto_id, carpeta)
    threading.Thread(target=analisis.ejecutar, daemon=True).start()
    return analisis


def en_curso(proyecto_id: str):
    """El análisis de ese proyecto si está corriendo, o None."""
    analisis = _analisis.get(proyecto_id)
    return analisis if analisis and analisis.estado == "analizando" else None


def hay_en_curso() -> bool:
    return any(a.estado == "analizando" for a in list(_analisis.values()))


def cancelar(proyecto_id: str):
    analisis = en_curso(proyecto_id)
    if analisis:
        analisis.cancelar()


def cancelar_todos():
    for analisis in list(_analisis.values()):
        if analisis.estado == "analizando":
            analisis.cancelar()
