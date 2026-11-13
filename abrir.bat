@echo off
rem Abre delfOS en Windows. Antes hay que haber corrido instalar.bat una vez.
rem Esta ventana queda abierta mientras delfOS está en uso: al cerrarla, delfOS se cierra.
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Falta instalar delfOS: abrí instalar.bat primero.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m delfos %*
