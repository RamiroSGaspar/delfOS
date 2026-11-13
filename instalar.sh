#!/usr/bin/env bash
# Instala delfOS. Se corre una sola vez, desde la carpeta del repositorio: ./instalar.sh
# Arma el entorno de Python dentro de esta carpeta (.venv), instala las bibliotecas y, en Linux, deja delfOS en el
# menú de aplicaciones. Fuera de esta carpeta solo escribe ese acceso.
set -e
cd "$(dirname "$0")"
RAIZ="$(pwd)"

guia_python() {
    cat <<'FIN'

delfOS necesita Python 3.9 o superior, y no lo encontré en esta computadora.

  Ubuntu, Debian o Mint:   sudo apt install python3 python3-venv python3-pip
  Fedora:                  sudo dnf install python3
  Arch o Manjaro:          sudo pacman -S python
  macOS:                   brew install python   (o el instalador de https://www.python.org/downloads/)
  Windows:                 el instalador de https://www.python.org/downloads/, marcando "Add python.exe to PATH"

Después de instalarlo, volvé a correr ./instalar.sh
FIN
}

PY=""
for candidato in python3 python; do
    if command -v "$candidato" >/dev/null 2>&1 && "$candidato" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
        PY="$candidato"
        break
    fi
done
if [ -z "$PY" ]; then
    guia_python
    exit 1
fi
echo "1 de 3 · $("$PY" --version) encontrado."

if [ ! -x .venv/bin/python ]; then
    if ! "$PY" -m venv .venv; then
        echo
        echo "No se pudo armar el entorno de Python. En Ubuntu o Debian suele faltar un paquete:"
        echo "  sudo apt install python3-venv"
        echo "Instalalo, borrá la carpeta .venv si quedó a medias y volvé a correr ./instalar.sh"
        exit 1
    fi
fi

echo "2 de 3 · Instalando las bibliotecas. Necesita internet, solo esta vez..."
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt
.venv/bin/python -c "import polars, numpy, scipy, sklearn, networkx, anthropic"

chmod +x abrir.sh
if [ "$(uname -s)" = "Linux" ]; then
    APLICACIONES="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
    mkdir -p "$APLICACIONES"
    cat > "$APLICACIONES/delfos.desktop" <<FIN
[Desktop Entry]
Type=Application
Name=delfOS
Comment=Narrativas y cuentas coordinadas en sets de comentarios
Exec="$RAIZ/abrir.sh"
Icon=$RAIZ/tablero/marca/icono.svg
Path=$RAIZ
Terminal=false
Categories=Office;
FIN
    echo "3 de 3 · delfOS quedó en el menú de aplicaciones."
else
    echo "3 de 3 · Listo."
fi

echo
echo "Para abrir delfOS: buscalo en el menú de aplicaciones, o corré ./abrir.sh desde esta carpeta."
