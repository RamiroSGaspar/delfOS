#!/usr/bin/env bash
# Abre delfOS. Antes hay que haber corrido ./instalar.sh una vez.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Falta instalar delfOS: corré ./instalar.sh desde esta carpeta."
    exit 1
fi
exec .venv/bin/python -m delfos "$@"
