@echo off
rem Instala delfOS en Windows. Se corre una sola vez: doble clic en este archivo.
rem Arma el entorno de Python dentro de esta carpeta (.venv) e instala las bibliotecas.
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY goto sinpython
%PY% -c "import sys; sys.exit(sys.version_info < (3, 9))" || goto sinpython
echo 1 de 3 - Python encontrado.

if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv || goto fallo
)
echo 2 de 3 - Instalando las bibliotecas. Necesita internet, solo esta vez...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt || goto fallo
".venv\Scripts\python.exe" -c "import polars, numpy, scipy, sklearn, networkx, anthropic" || goto fallo
echo 3 de 3 - Listo.
echo.
echo Para abrir delfOS: doble clic en abrir.bat, en esta misma carpeta.
pause
exit /b 0

:sinpython
echo.
echo delfOS necesita Python 3.9 o superior, y no lo encontré en esta computadora.
echo Instalalo desde https://www.python.org/downloads/ marcando "Add python.exe to PATH"
echo y después volvé a abrir instalar.bat
pause
exit /b 1

:fallo
echo.
echo La instalación no terminó. Revisá el mensaje de arriba y volvé a intentar.
pause
exit /b 1
