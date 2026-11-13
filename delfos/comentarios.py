"""El explorador de comentarios: los comentarios de un proyecto, uno por uno, con lo que les asignó el análisis.

Es el único módulo de la aplicación que carga Polars, y lo hace recién cuando alguien abre el explorador. La tabla
del último proyecto consultado queda en memoria mientras su resultado no cambie.
"""
import threading
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from tablero.resumen import cuentas_del_set, fuentes, tabla_completa

POR_PAGINA = 50
_bloqueo = threading.Lock()
_en_memoria = {}


def _tabla(carpeta: Path) -> dict:
    marca = (str(carpeta), (carpeta / "resultado" / "comentarios.csv").stat().st_mtime_ns)
    with _bloqueo:
        if _en_memoria.get("marca") != marca:
            lectura, df, _, narrativas = tabla_completa(carpeta / "datos", carpeta / "resultado")
            df = df.join(cuentas_del_set(carpeta / "datos").select("cuenta_id", "usuario"), on="cuenta_id", how="left")
            _en_memoria.clear()
            _en_memoria.update(marca=marca, df=df, zona_s=lectura.offset_s,
                               fuentes={f: nombre for f, (nombre, _) in fuentes(carpeta / "datos").items()},
                               titulos=dict(narrativas.select("narrativa", "titulo").iter_rows()))
        return dict(_en_memoria)


def buscar(carpeta: Path, consulta: dict) -> dict:
    """Una página de comentarios con los filtros pedidos: narrativa, postura, cuentas coordinadas y texto."""
    m = _tabla(Path(carpeta))
    df = m["df"]
    narrativa, postura = consulta.get("narrativa", ""), consulta.get("postura", "")
    if narrativa == "ruido":
        df = df.filter(pl.col("narrativa").is_null())
    elif narrativa:
        df = df.filter(pl.col("narrativa") == narrativa)
    if postura in ("apoya", "rechaza"):
        df = df.filter(pl.col("postura") == postura)
    if consulta.get("coordinadas") == "1":
        df = df.filter(pl.col("grupo").is_not_null())
    texto = consulta.get("texto", "").strip().lower()
    if texto:
        df = df.filter(pl.col("texto").str.to_lowercase().str.contains(texto, literal=True))
    if consulta.get("orden") == "me_gusta":
        df = df.sort(["me_gusta", "t", "comentario_id"], descending=[True, False, False], nulls_last=True)
    else:
        df = df.sort(["t", "comentario_id"], nulls_last=True)
    try:
        pagina = max(0, int(consulta.get("pagina", 0)))
    except ValueError:
        pagina = 0
    filas = df.slice(pagina * POR_PAGINA, POR_PAGINA).select(
        "comentario_id", "t", "cuenta_id", "usuario", "grupo", "texto", "narrativa", "postura", "me_gusta", "fuente_id")
    return {"total": df.height, "pagina": pagina, "por_pagina": POR_PAGINA, "filas": [
        {"id": c, "fecha": None if t is None else datetime.fromtimestamp(t + m["zona_s"], timezone.utc).strftime(
            "%d/%m/%Y %H:%M"), "cuenta": cuenta, "usuario": usuario or "", "operacion": grupo, "texto": x,
         "narrativa": n, "titulo": m["titulos"].get(n) or n, "postura": p, "me_gusta": g,
         "fuente": m["fuentes"].get(f) or f}
        for c, t, cuenta, usuario, grupo, x, n, p, g, f in filas.iter_rows()]}
