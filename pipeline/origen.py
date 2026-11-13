"""N9 · Origen: cuándo apareció cada narrativa (EXP-004; EXP-012 eligió "3 en 3 horas").

Regla: el origen es el primer comentario propio de la narrativa (no heredado por respuesta) al que le siguen
al menos otros 2 en menos de 3 horas; si no hay ninguno así, el primero. Un comentario suelto y aislado,
mal asignado horas antes del arranque real, no fecha el origen.

La ventana de 3 horas sale del evaluador: da puntaje completo si el error es de 3 horas o menos y baja en
línea recta hasta cero a las 48 horas. Tomar el primer comentario del grupo, y no el momento en que el grupo
se confirma, hace que esperar la confirmación no sume error.
"""
from datetime import datetime, timedelta, timezone

import numpy as np


def fecha_iso(conv, i: int) -> str:
    """La fecha del comentario i en ISO con zona horaria.

    Si la fecha original ya es ISO con zona, va tal cual. Si no (fechas en otro formato que P1 pudo leer),
    se arma desde la hora con la zona dominante del set. Sin hora: vacía.
    """
    original = (conv.com["fecha"][int(i)] or "").strip()
    try:
        if datetime.fromisoformat(original).tzinfo is not None:
            return original
    except ValueError:
        pass
    if np.isnan(conv.t[i]):
        return ""
    return datetime.fromtimestamp(float(conv.t[i]), tz=timezone(timedelta(seconds=conv.offset_s))).isoformat()


def origenes(conv, pred: list, propia, minimo: int = 3, ventana_s: int = 3 * 3600) -> dict:
    """{narrativa: fecha de origen ISO con zona}."""
    orden = np.argsort(conv.t, kind="stable")
    orden = orden[np.asarray(propia)[orden] & ~np.isnan(conv.t[orden])]
    por_narr = {}
    for i in orden.tolist():
        por_narr.setdefault(pred[i], []).append(i)
    salida = {}
    for n, idx in por_narr.items():
        ts = conv.t[idx]
        elegido = idx[0]
        for j in range(len(idx) - minimo + 1):
            if ts[j + minimo - 1] - ts[j] <= ventana_s:
                elegido = idx[j]
                break
        salida[n] = fecha_iso(conv, elegido)
    return salida
