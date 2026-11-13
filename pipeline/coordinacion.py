"""C · Coordinación: qué cuentas actúan coordinadas y en qué operación (EXP-013, "respuestas-publicacion-freno").

Una ráfaga sola no alcanza: lo que delata a una operación es la repetición (las mismas cuentas, juntas, una y
otra vez). Cuatro capas, cada una con umbrales fijos:

- **T, texto propio (EXP-003):** una "ficha" es una familia de núcleos (N1) o un hashtag que pocas cuentas
  repiten mucho: repetición media por cuenta de 2 o más y 3 cuentas o más. El núcleo vacío no cuenta como
  ficha. Una cuenta está marcada si el 20 % o más de sus comentarios (y al menos 2) llevan una ficha.
- **S, sincronía por narrativa (EXP-007, "compacta"):** pares de cuentas que comentan la misma publicación y
  la misma narrativa dentro de 15 minutos, en 4 publicaciones o más, y 10 veces más de lo esperable por azar
  dada la actividad de cada una. Grupos: núcleo de grado 2 del grafo de pares, de 3 cuentas o más.
- **R, respuestas (EXP-013):** núcleo de grado 2 del grafo de respuestas entre cuentas distintas,
  componentes de 3 cuentas o más.
- **P, sincronía por publicación (L2-3):** como S pero sin narrativas, con lo esperable medido en el set
  entero y exceso mínimo de 5.

**Alarma por barajado:** cada capa se corre también sobre el set con la columna de cuenta permutada al azar
(semilla 13), que conserva cuántos comentarios tiene cada cuenta y destruye qué escribe, dónde, cuándo y a
quién responde. Si el set barajado marca la mitad o más de las cuentas que marca el real, la capa no
discrimina: **se apaga** en ese set y se avisa.

**Decisión:** una cuenta está marcada si la marca alguna capa encendida. Una operación es un componente del
grafo que une las cuentas que comparten una ficha o un grupo.

Solo la capa S usa las narrativas: T, R y P se pueden calcular antes, mientras el modelo responde.
"""
import networkx as nx
import numpy as np
import polars as pl

CAPAS = ("T", "S", "R", "P")


# ----------------------------------------------------------------------------- la tabla
def tabla_de_comentarios(conv, familia: np.ndarray) -> pl.DataFrame:
    """Una fila por comentario, en el orden de la conversación (el de `padre`). Sin narrativa todavía."""
    vacio = np.array([t == "" for t in conv.nucleos], dtype=bool)[conv.nuc] if len(conv.nuc) else np.zeros(0, bool)
    return conv.com.select("comentario_id", "publicacion_id", "cuenta_id", "t", "hashtags").with_columns(
        pl.Series("familia", familia[conv.nuc]), pl.Series("padre", conv.padre), pl.Series("vacio", vacio))


def barajar(b: pl.DataFrame, semilla: int) -> pl.DataFrame:
    """La misma tabla con la columna de cuenta permutada al azar (semilla fija)."""
    rng = np.random.default_rng(semilla)
    return b.with_columns(pl.Series("cuenta_id", b["cuenta_id"].to_numpy()[rng.permutation(b.height)]))


def grupos_de_pares(pares: pl.DataFrame, k_min: int, exceso_min: float, tam_min: int) -> list:
    """Grupos de cuentas unidos por coincidencias recurrentes muy por encima de lo esperable: núcleo de
    grado 2 del grafo de pares y componentes de `tam_min` cuentas o más."""
    g = nx.Graph()
    for a, c, k in pares.filter((pl.col("k") >= k_min) & (pl.col("exceso") >= exceso_min)).select(
            "a", "c", "k").iter_rows():
        g.add_edge(a, c, weight=k)
    g = nx.k_core(g, 2) if g.number_of_edges() else g
    return [comp for comp in nx.connected_components(g) if len(comp) >= tam_min]


# ----------------------------------------------------------------------------- capa T
def capa_texto(b: pl.DataFrame, cfg: dict):
    """Cuentas marcadas por texto propio y los pares (cuenta, ficha) que las unen en operaciones."""
    elegibles = b.filter(~pl.col("vacio")) if cfg["c_excluir_vacio"] else b
    con_hashtag = b.filter(pl.col("hashtags") != "")
    fam = elegibles.group_by("familia").agg(pl.len().alias("n"), pl.col("cuenta_id").n_unique().alias("cuentas"))
    ht = con_hashtag.group_by("hashtags").agg(pl.len().alias("n"), pl.col("cuenta_id").n_unique().alias("cuentas"))
    cond = ((pl.col("n") / pl.col("cuentas")) >= cfg["c_repeticion_min"]) & (pl.col("cuentas") >= cfg["c_cuentas_min"])
    fichas_f = fam.filter(cond)["familia"].to_list()
    fichas_h = ht.filter(cond)["hashtags"].to_list()
    vale = ~pl.col("vacio") if cfg["c_excluir_vacio"] else pl.lit(True)
    m = b.with_columns((pl.col("familia").is_in(fichas_f) & vale).alias("pf"),
                       pl.col("hashtags").is_in(fichas_h).alias("ph"))
    m = m.with_columns((pl.col("pf") | pl.col("ph")).alias("propio"))
    por_cuenta = m.group_by("cuenta_id").agg(pl.col("propio").mean().alias("t"), pl.len().alias("n_com"))
    marcadas = set(por_cuenta.filter((pl.col("t") >= cfg["c_t_min"]) & (pl.col("n_com") >= 2))["cuenta_id"].to_list())
    usa = pl.concat([
        m.filter(pl.col("pf")).select("cuenta_id", pl.format("f{}", "familia").alias("ficha")),
        m.filter(pl.col("ph")).select("cuenta_id", pl.format("h{}", "hashtags").alias("ficha"))]).unique()
    usa = usa.filter(pl.col("cuenta_id").is_in(list(marcadas)))
    info = {"familias_de_baja_difusion": len(fichas_f), "hashtags_de_baja_difusion": len(fichas_h)}
    return marcadas, usa, info


# ----------------------------------------------------------------------------- capa S
def pares_sincronizados(e: pl.DataFrame, k_min: int, tau: int) -> pl.DataFrame:
    """Pares de cuentas (a < c) que comentan la misma publicación y la misma narrativa dentro de `tau`
    segundos, en `k_min` publicaciones o más, con su exceso sobre lo esperable por azar.

    Solo entran las cuentas que tienen `k_min` publicaciones o más en la narrativa (las demás no pueden llegar
    a `k_min` coincidencias), con el primer y el último comentario de cada cuenta en cada ventana de `tau`.
    Lo esperable es n_a * n_c / N, con N las publicaciones de la narrativa.
    """
    tot = e.group_by("narrativa").agg(pl.col("publicacion_id").n_unique().alias("N"))
    act = e.group_by("cuenta_id", "narrativa").agg(pl.col("publicacion_id").n_unique().alias("n"))
    act = act.filter(pl.col("n") >= k_min)
    claves = ["publicacion_id", "narrativa", "cub"]
    ventanas = (e.join(act.select("cuenta_id", "narrativa"), on=["cuenta_id", "narrativa"])
                .with_columns((pl.col("t") // tau).alias("cub"))
                .group_by(*claves, "cuenta_id")
                .agg(pl.col("t").min().alias("inicio"), pl.col("t").max().alias("fin")))
    iguales = ventanas.join(ventanas, on=claves, suffix="_2").filter(pl.col("cuenta_id") < pl.col("cuenta_id_2"))
    vecinas = ventanas.join(ventanas.with_columns(pl.col("cub") - 1), on=claves, suffix="_2").filter(
        (pl.col("cuenta_id") != pl.col("cuenta_id_2")) & (pl.col("inicio_2") - pl.col("fin") <= tau))
    pares = pl.concat([iguales, vecinas]).select(
        pl.min_horizontal("cuenta_id", "cuenta_id_2").alias("a"),
        pl.max_horizontal("cuenta_id", "cuenta_id_2").alias("c"), "publicacion_id", "narrativa")
    pares = pares.unique().group_by("a", "c", "narrativa").agg(pl.len().alias("k")).filter(pl.col("k") >= k_min)
    return (pares.join(act.rename({"cuenta_id": "a", "n": "na"}), on=["a", "narrativa"])
            .join(act.rename({"cuenta_id": "c", "n": "nc"}), on=["c", "narrativa"])
            .join(tot, on="narrativa")
            .with_columns((pl.col("k") / (pl.col("na") * pl.col("nc") / pl.col("N"))).alias("exceso")))


def capa_sincronia(b: pl.DataFrame, narrativa: pl.Series, cfg: dict):
    """Grupos sincronizados por narrativa (lista de conjuntos de cuentas)."""
    e = b.select("publicacion_id", "cuenta_id", "t").with_columns(narrativa.alias("narrativa")).filter(
        (pl.col("narrativa") != "") & pl.col("t").is_not_null())
    if e.height == 0:
        return [], {"pares": 0}
    pares = pares_sincronizados(e, cfg["c_k_min"], cfg["c_ventana_s"])
    grupos = grupos_de_pares(pares, cfg["c_k_min"], cfg["c_exceso_min"], cfg["c_tam_min"])
    return grupos, {"pares": pares.height, "exceso_min": cfg["c_exceso_min"]}


# ----------------------------------------------------------------------------- capa R
def capa_respuestas(b: pl.DataFrame, cfg: dict):
    """Componentes del núcleo de grado 2 del grafo de respuestas entre cuentas distintas."""
    if not cfg["c_capa_r"]:
        return [], {}
    cuenta = b["cuenta_id"].to_numpy()
    padre = b["padre"].to_numpy()
    i = np.where(padre >= 0)[0]
    a, c = cuenta[i], cuenta[padre[i]]
    distinto = a != c
    g = nx.Graph()
    g.add_edges_from(zip(a[distinto], c[distinto]))
    g = nx.k_core(g, 2) if g.number_of_edges() else g
    grupos = [comp for comp in nx.connected_components(g) if len(comp) >= cfg["c_tam_min"]]
    return grupos, {"respuestas_entre_cuentas": int(distinto.sum())}


# ----------------------------------------------------------------------------- capa P
FILAS_POR_LOTE = 2_000_000  # filas máximas de cada cruce de la capa P (cuida la memoria)


def pares_por_publicacion(b: pl.DataFrame, k_min: int, tau: int, filas_por_lote: int = FILAS_POR_LOTE) -> pl.DataFrame:
    """Pares de cuentas (a < c) que coinciden en la misma publicación dentro de `tau` segundos, en `k_min`
    publicaciones o más, con lo esperable n_a * n_c / N medido en el set entero (L2-3).

    Dos cuentas coinciden en una publicación si comentan en la misma ventana de `tau` segundos, o en ventanas
    seguidas con menos de `tau` entre el último comentario de la primera ventana y el primero de la
    siguiente; en ese segundo caso, solo cuenta el par en que la cuenta de la ventana anterior es la menor
    (así lo definió L2-3 y así se midió).

    Cómo se calcula sin llenar la memoria (el resultado es el mismo que cruzar todo de una vez):
    - Solo entran las cuentas con `k_min` publicaciones o más: las demás no pueden coincidir en `k_min`.
    - Cuentas y publicaciones van como códigos enteros; el código de cuenta respeta el orden de los ids, así
      que "a < c" es el mismo par.
    - El cruce de cada ventana con sí misma y con la siguiente se hace por lotes de publicaciones de hasta
      `filas_por_lote` filas: un par se cuenta una vez por publicación, y cada publicación cae en un solo lote.
    """
    vacio = pl.DataFrame(schema={"a": pl.String, "c": pl.String, "k": pl.UInt32, "exceso": pl.Float64})
    e = b.filter(pl.col("t").is_not_null()).select("publicacion_id", "cuenta_id", "t")
    if e.height == 0:
        return vacio
    act = e.group_by("cuenta_id").agg(pl.col("publicacion_id").n_unique().alias("n"))
    total = e["publicacion_id"].n_unique()
    activas = act.filter(pl.col("n") >= k_min).sort("cuenta_id").with_row_index("cc")
    if activas.height < 2:
        return vacio
    pubs = e.select("publicacion_id").unique().sort("publicacion_id").with_row_index("pc")
    vent = (e.join(activas.select("cuenta_id", "cc"), on="cuenta_id").join(pubs, on="publicacion_id")
            .with_columns((pl.col("t") // tau).alias("cub"))
            .group_by("pc", "cub", "cc").agg(pl.col("t").min().alias("inicio"), pl.col("t").max().alias("fin")))
    # Lotes de publicaciones: las filas de cada cruce son m² en la misma ventana y m · m' con la siguiente.
    tam = vent.group_by("pc", "cub").len()
    tam = tam.join(tam.select("pc", (pl.col("cub") - 1).alias("cub"), pl.col("len").alias("sig")),
                   on=["pc", "cub"], how="left")
    costo = (tam.group_by("pc").agg((pl.col("len").cast(pl.Int64) ** 2
                                     + pl.col("len").cast(pl.Int64) * pl.col("sig").fill_null(0)).sum().alias("filas"))
             .sort("pc").with_columns((pl.col("filas").cum_sum() // filas_por_lote).alias("lote")))
    # Cada par (a, c) va como un solo entero, a · n + c. Por lote quedan los pares distintos de cada
    # publicación; k es cuántas veces aparece cada par en total (ordenar y contar repeticiones seguidas usa
    # mucha menos memoria que agrupar).
    n = activas.height
    partes = []
    claves = ["pc", "cub"]
    for lote in vent.join(costo.select("pc", "lote"), on="pc").partition_by("lote", include_key=False):
        iguales = (lote.select("pc", "cub", "cc").join(lote.select("pc", "cub", "cc"), on=claves, suffix="_2")
                   .filter(pl.col("cc") < pl.col("cc_2")))
        vecinas = (lote.join(lote.with_columns(pl.col("cub") - 1), on=claves, suffix="_2")
                   .filter((pl.col("cc") < pl.col("cc_2")) & ((pl.col("inicio_2") - pl.col("fin")) <= tau)))
        distintos = pl.concat([iguales.select("cc", "cc_2", "pc"), vecinas.select("cc", "cc_2", "pc")]).unique()
        partes.append(distintos.select((pl.col("cc").cast(pl.UInt64) * n + pl.col("cc_2")).alias("x"))["x"])
    repeticiones = pl.concat(partes).sort().rle().struct.unnest().filter(pl.col("len") >= k_min)
    pares = repeticiones.select((pl.col("value") // n).cast(pl.UInt32).alias("cc"),
                                (pl.col("value") % n).cast(pl.UInt32).alias("cc_2"),
                                pl.col("len").cast(pl.UInt32).alias("k"))
    codigos = activas.select("cc", "cuenta_id", "n")
    return (pares.join(codigos.rename({"cuenta_id": "a", "n": "na"}), on="cc")
            .join(codigos.rename({"cc": "cc_2", "cuenta_id": "c", "n": "nc"}), on="cc_2")
            .select("a", "c", "k", (pl.col("k") / (pl.col("na") * pl.col("nc") / total)).alias("exceso")))


def capa_publicacion(b: pl.DataFrame, cfg: dict):
    if not cfg["c_capa_p"]:
        return [], {}
    pares = pares_por_publicacion(b, cfg["c_k_min"], cfg["c_ventana_s"])
    grupos = grupos_de_pares(pares, cfg["c_k_min"], cfg["c_p_exceso_min"], cfg["c_tam_min"])
    return grupos, {"pares": pares.height}


# ----------------------------------------------------------------------------- todas las capas
def cuentas_de(capa: str, valor) -> set:
    if capa == "T":
        return valor[0]
    return set().union(*valor[0]) if valor[0] else set()


class Coordinacion:
    """La coordinación en dos pasos: `sin_narrativas()` corre T, R y P (no dependen de las narrativas, se
    pueden adelantar) y `decidir(pred)` corre S y arma las operaciones."""

    def __init__(self, conv, familia: np.ndarray, cuentas: list, cfg: dict):
        self.cfg = cfg
        self.n_cuentas = len(cuentas)
        self.real = tabla_de_comentarios(conv, familia)
        self.azar = barajar(self.real, cfg["c_semilla"])
        self.capas = {"real": {}, "azar": {}}

    def tareas_sin_narrativas(self) -> list:
        """Las capas T, R y P del set real y del barajado, como tareas sueltas: no dependen de las narrativas
        y se pueden correr en cualquier orden, por ejemplo mientras el modelo responde."""
        funciones = {"T": capa_texto, "R": capa_respuestas, "P": capa_publicacion}
        tareas = []
        for nombre, b in (("real", self.real), ("azar", self.azar)):
            for capa, funcion in funciones.items():
                def tarea(nombre=nombre, b=b, capa=capa, funcion=funcion):
                    if capa not in self.capas[nombre]:
                        self.capas[nombre][capa] = funcion(b, self.cfg)
                tareas.append(tarea)
        return tareas

    def decidir(self, pred: list):
        """{cuenta: operación} de las cuentas marcadas, las notas y los avisos."""
        for tarea in self.tareas_sin_narrativas():  # las que no se adelantaron
            tarea()
        narrativa = pl.Series("narrativa", pred, dtype=pl.String)
        for nombre, b in (("real", self.real), ("azar", self.azar)):
            self.capas[nombre]["S"] = capa_sincronia(b, narrativa, self.cfg)
        real, azar = self.capas["real"], self.capas["azar"]
        alarma, apagadas = {}, []
        for capa in CAPAS:
            nr, na = len(cuentas_de(capa, real[capa])), len(cuentas_de(capa, azar[capa]))
            salta = nr > 0 and na >= self.cfg["c_alarma_razon"] * nr
            alarma[capa] = {"real": nr, "barajado": na, "salta": salta}
            if salta and self.cfg["c_freno"]:
                apagadas.append(capa)
        marcadas_t, usa, info_t = real["T"]
        grupos = {capa: real[capa][0] for capa in ("S", "R", "P")}
        if "T" in apagadas:
            marcadas_t, usa = set(), usa.clear()
        for capa in ("S", "R", "P"):
            if capa in apagadas:
                grupos[capa] = []
        g = nx.Graph()
        g.add_nodes_from(marcadas_t)
        for comp in list(grupos["S"]) + list(grupos["R"]) + list(grupos["P"]):
            comp = sorted(comp)
            g.add_nodes_from(comp)
            g.add_edges_from(zip(comp, comp[1:]))
        for _, cuentas in usa.group_by("ficha").agg(pl.col("cuenta_id")).iter_rows():
            g.add_edges_from(zip(cuentas, cuentas[1:]))
        operaciones = sorted((sorted(c) for c in nx.connected_components(g)), key=lambda c: c[0])
        grupo = {cuenta: f"op{i:02d}" for i, op in enumerate(operaciones) for cuenta in op}
        avisos = [f"coordinación, capa {capa}: el set barajado al azar marca {a['barajado']} cuentas contra "
                  f"{a['real']} del set real; la capa no discrimina" + (" y se apagó" if capa in apagadas else "")
                  for capa, a in alarma.items() if a["salta"]]
        tamanos = sorted((len(op) for op in operaciones), reverse=True)
        notas = {"texto": info_t, "sincronia": real["S"][1], "respuestas": real["R"][1], "publicacion": real["P"][1],
                 "alarma": alarma, "capas_apagadas": apagadas,
                 "marcadas_por_capa": {"T": len(marcadas_t),
                                       **{capa: len(set().union(*grupos[capa])) for capa in ("S", "R", "P")}},
                 "cuentas_marcadas": len(grupo), "cuentas": self.n_cuentas,
                 "proporcion_marcada": round(len(grupo) / max(self.n_cuentas, 1), 4),
                 "operaciones": len(operaciones), "tamano_de_las_operaciones": tamanos[:20],
                 "proporcion_de_la_operacion_mayor": round((tamanos[0] if tamanos else 0) / max(self.n_cuentas, 1), 4)}
        return grupo, notas, avisos
