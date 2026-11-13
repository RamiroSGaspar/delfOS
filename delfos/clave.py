"""La clave del modelo de IA: se guarda una vez, fuera de los proyectos, y nunca se vuelve a mostrar.

Se guarda en el mismo archivo que ya lee el motor (`pipeline/modelo.py`), legible solo por el usuario. Este módulo
nunca devuelve la clave, no la imprime y no la escribe en ningún otro lado.
"""
import os

import pipeline.modelo as modelo

from delfos.proyectos import ErrorDeProyecto


def estado() -> dict:
    """Si hay clave y de dónde sale: de la variable del sistema (que gana) o del archivo."""
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return {"configurada": True, "origen": "variable"}
    try:
        hay = bool(modelo.RUTA_CLAVE.read_text(encoding="utf-8").strip())
    except OSError:
        hay = False
    return {"configurada": hay, "origen": "archivo" if hay else None}


def guardar(clave: str):
    clave = (clave or "").strip()
    if not clave.startswith("sk-ant-") or len(clave) < 20 or any(c.isspace() for c in clave):
        raise ErrorDeProyecto("Eso no parece una clave de Anthropic: empiezan con sk-ant- y no llevan espacios.")
    ruta = modelo.RUTA_CLAVE
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with os.fdopen(os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            f.write(clave)
        os.chmod(ruta, 0o600)
    except OSError as e:
        raise ErrorDeProyecto(f"No se pudo guardar la clave: {e.strerror or 'error de disco'}.") from e


def borrar():
    try:
        modelo.RUTA_CLAVE.unlink(missing_ok=True)
    except OSError as e:
        raise ErrorDeProyecto(f"No se pudo borrar la clave: {e.strerror or 'error de disco'}.") from e
