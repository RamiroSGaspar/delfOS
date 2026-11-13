"""Pruebas chicas de la coordinación (EXP-013): capas R, T y P, núcleo vacío, alarma por barajado y el cálculo
por lotes de la capa P."""
from types import SimpleNamespace

import numpy as np
import polars as pl

from pipeline import coordinacion as c
from pipeline.configuracion import CONFIG


def tabla(filas):
    """filas: (cuenta, publicación, segundos, familia, padre, vacío)."""
    return pl.DataFrame({
        "comentario_id": [f"c{i}" for i in range(len(filas))], "publicacion_id": [f[1] for f in filas],
        "cuenta_id": [f[0] for f in filas], "t": [f[2] for f in filas], "hashtags": [""] * len(filas),
        "familia": [f[3] for f in filas], "padre": [f[4] for f in filas], "vacio": [f[5] for f in filas]})


def test_r_marca_una_ronda_de_cuatro_cuentas_y_no_un_par_suelto():
    filas = [(f"a{i}", "p1", 10 * i, i, -1, False) for i in range(4)]
    filas += [(f"a{i}", "p1", 100 + i, 9, i - 1 if i else 3, False) for i in range(4)]  # a0->a3, a1->a0, ...
    filas += [("x", "p2", 0, 5, -1, False), ("y", "p2", 5, 6, len(filas), False)]  # y responde a x
    grupos, _ = c.capa_respuestas(tabla(filas), CONFIG)
    assert grupos == [{"a0", "a1", "a2", "a3"}]


def test_t_el_nucleo_vacio_no_es_ficha():
    filas = [(f"g{i}", f"p{j}", 100 * j, 0, -1, True) for i in range(6) for j in range(4)]
    con_vacio, _, _ = c.capa_texto(tabla(filas), {**CONFIG, "c_excluir_vacio": False})
    sin_vacio, _, _ = c.capa_texto(tabla(filas), CONFIG)
    assert len(con_vacio) == 6 and not sin_vacio


def test_t_una_familia_que_pocas_cuentas_repiten_mucho_marca_a_esas_cuentas():
    filas = [(f"op{i}", f"p{j}", 100 * j, 1, -1, False) for i in range(3) for j in range(5)]  # repetición 5
    filas += [(f"gen{i}", "p9", 10 * i, 2, -1, False) for i in range(30)]  # 30 cuentas, una vez cada una
    marcadas, usa, _ = c.capa_texto(tabla(filas), CONFIG)
    assert marcadas == {"op0", "op1", "op2"}
    assert set(usa["ficha"]) == {"f1"}


def test_p_encuentra_las_cuentas_sincronizadas_y_ninguna_genuina():
    filas = [(f"op{i}", f"p{j}", 10_000 * j + 60 * i, 1, -1, False) for i in range(5) for j in range(6)]
    filas += [(f"gen{i}", f"p{(7 * i + 3 * k) % 60}", 3_000 * i + 50_000 * k, 2, -1, False)
              for i in range(40) for k in range(6)]
    grupos, _ = c.capa_publicacion(tabla(filas), CONFIG)
    assert grupos == [{f"op{i}" for i in range(5)}]


def _pares_de_una_vez(b: pl.DataFrame, k_min: int, tau: int) -> pl.DataFrame:
    """La capa P de L2-3 tal como se definió: el cruce completo, con los ids de texto (para comparar)."""
    e = b.filter(pl.col("t").is_not_null()).select("publicacion_id", "cuenta_id", "t")
    act = e.group_by("cuenta_id").agg(pl.col("publicacion_id").n_unique().alias("n"))
    total = e["publicacion_id"].n_unique()
    vent = e.with_columns((pl.col("t") // tau).alias("cub")).group_by("publicacion_id", "cub", "cuenta_id").agg(
        pl.col("t").min().alias("inicio"), pl.col("t").max().alias("fin"))
    claves = ["publicacion_id", "cub"]
    iguales = vent.join(vent, on=claves, suffix="_2").filter(pl.col("cuenta_id") < pl.col("cuenta_id_2"))
    vecinas = vent.join(vent.with_columns(pl.col("cub") - 1), on=claves, suffix="_2").filter(
        (pl.col("cuenta_id") < pl.col("cuenta_id_2")) & ((pl.col("inicio_2") - pl.col("fin")) <= tau))
    pares = pl.concat([iguales, vecinas]).select(
        pl.min_horizontal("cuenta_id", "cuenta_id_2").alias("a"),
        pl.max_horizontal("cuenta_id", "cuenta_id_2").alias("c"), "publicacion_id").unique()
    pares = pares.group_by("a", "c").agg(pl.len().alias("k")).filter(pl.col("k") >= k_min)
    return (pares.join(act.rename({"cuenta_id": "a", "n": "na"}), on="a")
            .join(act.rename({"cuenta_id": "c", "n": "nc"}), on="c")
            .select("a", "c", "k", (pl.col("k") / (pl.col("na") * pl.col("nc") / total)).alias("exceso")))


def test_p_por_lotes_da_lo_mismo_que_cruzar_todo_de_una_vez():
    rng = np.random.default_rng(7)
    n = 3000
    b = pl.DataFrame({"publicacion_id": [f"p{x:02d}" for x in rng.integers(0, 12, n)],
                      "cuenta_id": [f"u{x:03d}" for x in rng.integers(0, 60, n)],
                      "t": rng.integers(0, 6 * 3600, n).tolist()})
    esperado = _pares_de_una_vez(b, 2, 900).sort("a", "c")
    for filas_por_lote in (50, 5_000, 10_000_000):  # muchos lotes, algunos y uno solo
        obtenido = c.pares_por_publicacion(b, 2, 900, filas_por_lote).sort("a", "c")
        assert obtenido.height > 100
        assert obtenido.equals(esperado)


def _conversacion_falsa(filas):
    """Lo mínimo que usa Coordinacion: la tabla de comentarios, los núcleos (el 0 vacío) y los padres."""
    b = tabla(filas)
    return SimpleNamespace(com=b.select("comentario_id", "publicacion_id", "cuenta_id", "t", "hashtags"),
                           nucleos=["", "x"], nuc=np.array([0 if v else 1 for v in b["vacio"]]),
                           padre=b["padre"].to_numpy()), np.array([0, 1]), sorted(set(b["cuenta_id"]))


def test_la_alarma_salta_con_la_familia_vacia_y_el_freno_apaga_la_capa():
    filas = [(f"g{i}", f"p{j}", 100 * j, 0, -1, True) for i in range(6) for j in range(4)]
    conv, familia, cuentas = _conversacion_falsa(filas)
    cfg = {**CONFIG, "c_excluir_vacio": False}
    sin_freno, notas, _ = c.Coordinacion(conv, familia, cuentas, {**cfg, "c_freno": False}).decidir([""] * len(filas))
    assert notas["alarma"]["T"]["salta"] and len(sin_freno) == 6
    con_freno, notas, avisos = c.Coordinacion(conv, familia, cuentas, cfg).decidir([""] * len(filas))
    assert not con_freno and notas["capas_apagadas"] == ["T"]
    assert avisos and avisos[0].startswith("coordinación, capa T") and avisos[0].endswith("y se apagó")


def test_las_operaciones_juntan_cuentas_con_ficha_en_comun():
    filas = [(f"op{i}", f"p{j}", 100 * j, 1, -1, False) for i in range(3) for j in range(5)]
    filas += [(f"gen{i}", "p9", 10 * i, 2, -1, False) for i in range(30)]
    conv, familia, cuentas = _conversacion_falsa(filas)
    conv.nucleos, conv.nuc = ["x", "y", "z"], np.array([f[3] for f in filas])
    grupo, notas, _ = c.Coordinacion(conv, np.array([0, 1, 2]), cuentas, CONFIG).decidir([""] * len(filas))
    assert grupo == {"op0": "op00", "op1": "op00", "op2": "op00"}
    assert notas["operaciones"] == 1
