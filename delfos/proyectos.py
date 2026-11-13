"""Los proyectos: un set de comentarios copiado a su carpeta, con su último análisis.

Cada proyecto vive entero en su carpeta:

    proyecto.json    el nombre, la ficha de los datos y el último análisis
    datos/           los 4 archivos del set, copiados
    resultado/       los 4 archivos oficiales que escribe el motor
    informe.json     el registro completo de la corrida
    cache.jsonl      las respuestas del modelo de IA: volver a analizar da lo mismo y no gasta
    tablero.html     el tablero, que también se abre solo, con doble clic

La lista de proyectos de la aplicación es un archivo del usuario (`proyectos.json`, en la carpeta de
configuración) que guarda solo el id y la carpeta de cada uno.
"""
import csv
import gzip
import json
import re
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from delfos.rutas import carpeta_config, documentos

NOMBRE_APP = "delfOS"
ARCHIVOS_SET = ("comentarios.csv.gz", "publicaciones.csv.gz", "fuentes.csv", "cuentas.csv.gz")
_bloqueo = threading.Lock()


class ErrorDeProyecto(ValueError):
    """Un pedido que no se puede cumplir. El mensaje es para mostrárselo a la persona."""


def ahora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def archivos_del_set(carpeta: Path) -> dict:
    """{nombre oficial: ruta, o None si falta}. Cada archivo vale con o sin `.gz`."""
    encontrados = {}
    for nombre in ARCHIVOS_SET:
        alternativa = nombre[:-3] if nombre.endswith(".gz") else nombre + ".gz"
        encontrados[nombre] = next((carpeta / n for n in (nombre, alternativa) if (carpeta / n).is_file()), None)
    return encontrados


def _filas(ruta: Path):
    """Las filas de datos del archivo (sin el encabezado), o None si no se puede leer."""
    abrir = gzip.open if ruta.suffix == ".gz" else open
    try:
        with abrir(ruta, "rt", encoding="utf-8", errors="replace", newline="") as f:
            return max(0, sum(1 for _ in csv.reader(f)) - 1)
    except (OSError, EOFError, csv.Error):
        return None


def nombre_de_carpeta(nombre: str) -> str:
    return re.sub(r"[^\w\- ]+", "_", nombre.strip()).strip(" ._") or "proyecto"


def carpeta_base() -> Path:
    """Donde se propone guardar los proyectos nuevos."""
    return documentos() / NOMBRE_APP


def _ruta_lista() -> Path:
    return carpeta_config() / "proyectos.json"


def _leer_lista() -> list:
    try:
        lista = json.loads(_ruta_lista().read_text(encoding="utf-8")).get("proyectos", [])
    except (OSError, ValueError, AttributeError):
        return []
    return [p for p in lista if isinstance(p, dict) and p.get("id") and p.get("carpeta")]


def _escribir_json(ruta: Path, contenido):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(contenido, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporal.replace(ruta)


def carpeta_de(proyecto_id: str) -> Path:
    for p in _leer_lista():
        if p["id"] == proyecto_id:
            return Path(p["carpeta"])
    raise ErrorDeProyecto("Ese proyecto no está en la lista.")


def estado_de(carpeta: Path, proyecto: dict) -> str:
    if not proyecto:
        return "no_encontrado"
    if (carpeta / "tablero.html").is_file() and (carpeta / "resultado").is_dir():
        return "listo"
    return "error" if (proyecto.get("ultimo_intento") or {}).get("error") else "sin_analizar"


def leer(proyecto_id: str) -> dict:
    carpeta = carpeta_de(proyecto_id)
    try:
        proyecto = json.loads((carpeta / "proyecto.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        proyecto = {}
    return {**proyecto, "id": proyecto_id, "carpeta": str(carpeta), "nombre": proyecto.get("nombre") or carpeta.name,
            "estado": estado_de(carpeta, proyecto)}


def listar() -> list:
    return [leer(p["id"]) for p in _leer_lista()]


def actualizar(proyecto_id: str, **cambios) -> dict:
    carpeta = carpeta_de(proyecto_id)
    with _bloqueo:
        proyecto = json.loads((carpeta / "proyecto.json").read_text(encoding="utf-8"))
        proyecto.update(cambios)
        _escribir_json(carpeta / "proyecto.json", proyecto)
    return leer(proyecto_id)


def crear(nombre: str, datos: str, base: str = "") -> dict:
    """Crea el proyecto: copia los 4 archivos del set a su carpeta y lo suma a la lista."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorDeProyecto("Falta el nombre del proyecto.")
    origen = Path(datos or "").expanduser()
    if not datos or not origen.is_dir():
        raise ErrorDeProyecto("Falta elegir la carpeta de los datos.")
    archivos = archivos_del_set(origen)
    faltan = [n for n, ruta in archivos.items() if ruta is None]
    if faltan:
        raise ErrorDeProyecto(f"En esa carpeta {'falta' if len(faltan) == 1 else 'faltan'} {', '.join(faltan)}. "
                              f"Un set tiene 4 archivos: {', '.join(ARCHIVOS_SET)}.")
    carpeta = ((Path(base).expanduser() if base else carpeta_base()) / nombre_de_carpeta(nombre)).resolve()
    if carpeta.is_file() or (carpeta.is_dir() and any(carpeta.iterdir())):
        raise ErrorDeProyecto(f"La carpeta {carpeta} ya existe y no está vacía. Elegí otro nombre u otra ubicación.")
    try:
        (carpeta / "datos").mkdir(parents=True, exist_ok=True)
        ficha = []
        for ruta in archivos.values():
            destino = carpeta / "datos" / ruta.name
            shutil.copy2(ruta, destino)
            ficha.append({"archivo": ruta.name, "bytes": destino.stat().st_size, "filas": _filas(destino)})
    except OSError as e:
        raise ErrorDeProyecto(f"No se pudo crear el proyecto en {carpeta}: {e.strerror or e}.") from e
    proyecto = {"id": uuid.uuid4().hex[:12], "nombre": nombre, "creado": ahora(), "ficha": ficha,
                "ultimo_analisis": None, "ultimo_intento": None}
    _escribir_json(carpeta / "proyecto.json", proyecto)
    with _bloqueo:
        _escribir_json(_ruta_lista(), {"proyectos": _leer_lista() + [{"id": proyecto["id"], "carpeta": str(carpeta)}]})
    return leer(proyecto["id"])


def quitar(proyecto_id: str):
    """Saca el proyecto de la lista. Sus archivos quedan donde están."""
    with _bloqueo:
        _escribir_json(_ruta_lista(), {"proyectos": [p for p in _leer_lista() if p["id"] != proyecto_id]})
