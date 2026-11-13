"""P3 · Cada texto distinto, una sola vez: P4, P5 y P6 se aplican a los textos distintos y el resultado se
reparte a todos los comentarios que los repiten.

En la práctica, 200.000 comentarios son 112.340 textos distintos (EXP-000 y EXP-004); en el set final,
150.000 son 79.495. Es lo que abarata todo lo demás.
"""
import polars as pl

from pipeline.texto import extraer_nucleos, normalizar_lote


def textos_distintos(comentarios: pl.DataFrame) -> list:
    """Los textos distintos, en el orden de aparición (el de la tabla de comentarios de P1)."""
    return comentarios["texto"].unique(maintain_order=True).to_list()


def preparar(comentarios: pl.DataFrame, cfg: dict, crudos: list = None, normalizados: list = None):
    """Devuelve (comentarios con su texto preparado, tabla de textos distintos, muletillas, coletillas).

    La tabla de textos distintos sale en el orden de aparición, con un `texto_id` ("t000000", ...): es el mapa
    de texto a comentarios que pide P3. Los comentarios vuelven ordenados por hora y por id (los que no
    tienen hora, al final). `crudos` y `normalizados` (P4 y P5 de cada texto distinto) se pueden pasar ya
    calculados, por ejemplo en varios procesos (`pipeline.paralelo`).
    """
    crudos = textos_distintos(comentarios) if crudos is None else crudos
    normalizados = normalizar_lote(crudos) if normalizados is None else normalizados
    norm, emojis, hashtags, grita = zip(*normalizados) if crudos else ((), (), (), ())
    nucleos, muletillas, coletillas = extraer_nucleos(
        norm, rondas=cfg["p6_rondas"], min_restos=cfg["p6_min_restos"], max_pre=cfg["p6_max_muletilla"],
        max_suf=cfg["p6_max_coletilla"], min_resto=cfg["p6_min_nucleo"])
    por_texto = [nucleos[n] for n in norm]
    tabla = pl.DataFrame({
        "texto_id": [f"t{k:06d}" for k in range(len(crudos))],
        "texto": crudos,
        "norm": list(norm),
        "nucleo": [x[0] for x in por_texto],
        "muletillas": [x[1] for x in por_texto],
        "coletillas": [x[2] for x in por_texto],
        "emojis": list(emojis),
        "hashtags": list(hashtags),
        "grita": list(grita),
    }, schema={"texto_id": pl.String, "texto": pl.String, "norm": pl.String, "nucleo": pl.String,
               "muletillas": pl.String, "coletillas": pl.String, "emojis": pl.String, "hashtags": pl.String,
               "grita": pl.Boolean})
    preparados = comentarios.join(tabla, on="texto", how="left").sort("t", "comentario_id", nulls_last=True)
    return preparados, tabla, muletillas, coletillas
