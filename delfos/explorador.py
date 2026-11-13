"""El explorador de carpetas de la aplicación: lista las carpetas de una ruta y dice si ahí hay un set.

Es propio, y no la ventana del sistema, para que se vea y funcione igual en todos lados. Solo lista carpetas: no
abre ni muestra archivos, salvo decir cuáles de los 4 archivos del set están en la carpeta.
"""
from pathlib import Path

from delfos.proyectos import archivos_del_set
from delfos.rutas import descargas, documentos


def listar(ruta: str = "") -> dict:
    carpeta = (Path(ruta).expanduser() if ruta else descargas()).resolve()
    while not carpeta.is_dir() and carpeta.parent != carpeta:  # si todavía no existe, la más cercana que sí
        carpeta = carpeta.parent
    try:
        carpetas = sorted((d for d in carpeta.iterdir() if d.is_dir() and not d.name.startswith(".")),
                          key=lambda d: d.name.lower())
        sin_permiso = False
    except OSError:
        carpetas, sin_permiso = [], True
    archivos = archivos_del_set(carpeta)
    return {"ruta": str(carpeta), "padre": str(carpeta.parent) if carpeta.parent != carpeta else None,
            "carpetas": [{"nombre": d.name, "ruta": str(d)} for d in carpetas], "sin_permiso": sin_permiso,
            "set": {nombre: encontrado is not None for nombre, encontrado in archivos.items()},
            "set_completo": all(encontrado is not None for encontrado in archivos.values()),
            "atajos": [{"nombre": "Inicio", "ruta": str(Path.home())}, {"nombre": "Descargas", "ruta": str(descargas())},
                       {"nombre": "Documentos", "ruta": str(documentos())}]}
