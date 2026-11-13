"""Escritura: los 4 archivos del formato oficial del desafío.

| Archivo | Columnas |
|---|---|
| `comentarios.csv` | `comentario_id, narrativa, postura`: una fila por comentario; el ruido va con narrativa y postura vacías |
| `narrativas.csv` | `narrativa, titulo, frases_clave, fecha_origen`: una fila por narrativa; frases separadas por `|`; fecha ISO con zona |
| `cuentas.csv` | `cuenta_id, grupo`: una fila por cuenta; el grupo vacío es una cuenta genuina |
| `costo.json` | `comentarios_procesados, segundos, tokens_ia, usd_ia, usd_por_mil_comentarios, hardware, almacenamiento, notas` |
"""
import json
import os
import platform
from pathlib import Path

import polars as pl


def escribir_csv(carpeta: Path, ids: list, pred: list, postura: list, titulos: dict, origen: dict,
                 cuentas: list, grupo: dict):
    carpeta.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"comentario_id": ids, "narrativa": pred, "postura": postura},
                 schema={"comentario_id": pl.String, "narrativa": pl.String, "postura": pl.String}
                 ).write_csv(carpeta / "comentarios.csv")
    filas = [(n, titulo, "|".join(frases), origen.get(n, "")) for n, (titulo, frases) in sorted(titulos.items())]
    pl.DataFrame(filas, schema=["narrativa", "titulo", "frases_clave", "fecha_origen"], orient="row"
                 ).write_csv(carpeta / "narrativas.csv")
    pl.DataFrame({"cuenta_id": cuentas, "grupo": [grupo.get(c, "") for c in cuentas]},
                 schema={"cuenta_id": pl.String, "grupo": pl.String}).write_csv(carpeta / "cuentas.csv")


def escribir_costo(carpeta: Path, costo: dict):
    (carpeta / "costo.json").write_text(json.dumps(costo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def hardware() -> str:
    """El procesador, los hilos, la memoria y el sistema de la máquina que corrió el pipeline."""
    cpu = platform.processor() or platform.machine()
    try:
        for linea in Path("/proc/cpuinfo").read_text().splitlines():
            if linea.startswith("model name"):
                cpu = linea.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    memoria = ""
    try:
        for linea in Path("/proc/meminfo").read_text().splitlines():
            if linea.startswith("MemTotal:"):
                memoria = f", {int(linea.split()[1]) / 1024 / 1024:.1f} GiB de RAM".replace(".", ",")
                break
    except OSError:
        pass
    return f"{cpu}, {os.cpu_count()} hilos{memoria}, {platform.system()} {platform.release()}"


def memoria_pico_mib() -> float:
    """El pico de memoria residente de este proceso, en MiB. Donde no se puede medir (Windows), devuelve 0."""
    try:
        for linea in Path("/proc/self/status").read_text().splitlines():
            if linea.startswith("VmHWM:"):
                return int(linea.split()[1]) / 1024
    except (OSError, ValueError, IndexError):
        pass
    try:
        import resource
    except ImportError:
        return 0.0
    pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return pico / (1024 * 1024) if platform.system() == "Darwin" else pico / 1024
