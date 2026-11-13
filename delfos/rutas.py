"""Las carpetas que usa la aplicación. Se calculan al pedirlas y no al importar: las pruebas cambian el HOME."""
import os
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]  # la carpeta del repositorio: desde ahí se corren `pipeline` y `tablero`


def carpeta_config() -> Path:
    """Donde la aplicación guarda la lista de proyectos. Se puede cambiar con la variable `DELFOS_CONFIG`."""
    return Path(os.environ.get("DELFOS_CONFIG") or Path.home() / ".config" / "delfos")


def _del_usuario(tipo: str, alternativas: tuple) -> Path:
    """Una carpeta del usuario: la que diga el sistema y, si no, la primera alternativa que exista."""
    try:
        r = subprocess.run(["xdg-user-dir", tipo], capture_output=True, text=True, timeout=3)
        ruta = Path(r.stdout.strip())
        if r.returncode == 0 and r.stdout.strip() and ruta.is_dir() and ruta != Path.home():
            return ruta
    except (OSError, subprocess.SubprocessError):
        pass
    return next((Path.home() / n for n in alternativas if (Path.home() / n).is_dir()), Path.home())


def descargas() -> Path:
    return _del_usuario("DOWNLOAD", ("Descargas", "Downloads"))


def documentos() -> Path:
    return _del_usuario("DOCUMENTS", ("Documentos", "Documents"))
