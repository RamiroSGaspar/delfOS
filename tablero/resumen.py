"""El resumen del tablero: todas las cifras que se muestran, calculadas desde el set y la entrega.

Nada está escrito a mano: sirve para cualquier set con el formato del desafío y para cualquier entrega con
el formato oficial (el ruido puede venir vacío o como `ninguna`). Los casos raros no cortan: una entrega
sin cuentas coordinadas, sin fechas legibles o con narrativas sin título dan un resumen igual.

Si además se le pasa el informe de la corrida (el archivo de `--informe` del pipeline), suma lo que solo sabe el
motor: los avisos, las medidas del set de entrada, las señales de coordinación, el uso de la IA y los tiempos.
"""
import calendar
import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from pipeline.lectura import buscar, leer, leer_tabla

TRAMOS_S = (3600, 3 * 3600, 6 * 3600, 12 * 3600, 86400)  # tamaños posibles de un tramo de los gráficos de tiempo
MAX_TRAMOS = 90  # se usa el tramo más chico que no pase de esta cantidad
EJEMPLOS = 3  # comentarios de ejemplo por lado de cada narrativa
TEXTOS_REPETIDOS = 5  # textos más repetidos de cada operación
LARGO_TEXTO = 280
RUIDO = ["", "ninguna"]
POSTURAS = ["apoya", "rechaza"]
ARCHIVOS_ENTREGA = ("comentarios.csv", "narrativas.csv", "cuentas.csv")
DATOS_DE_CUENTA = ("usuario", "fecha_creacion", "seguidores", "siguiendo")
CELDAS_DEL_PAJAR = (10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000)  # cuentas por celda, según el tamaño del set
MAX_CELDAS = 1500


def _limpio(columna: str) -> pl.Expr:
    return pl.col(columna).fill_null("").str.strip_chars()


def _con_columnas(tabla: pl.DataFrame, nombre: str, columnas: tuple) -> pl.DataFrame:
    faltan = [c for c in columnas if c not in tabla.columns]
    if faltan:
        raise ValueError(f"{nombre} no tiene las columnas {', '.join(faltan)}; tiene {tabla.columns}")
    return tabla


def leer_entrega(carpeta: Path):
    """Los tres CSV de la entrega, con el ruido como nulo y la postura solo `apoya` o `rechaza`."""
    faltan = [n for n in ARCHIVOS_ENTREGA if not (carpeta / n).exists()]
    if faltan:
        raise FileNotFoundError(f"faltan en {carpeta}: {', '.join(faltan)}")
    com = _con_columnas(leer_tabla(carpeta / "comentarios.csv"), "comentarios.csv",
                        ("comentario_id", "narrativa", "postura"))
    nar = _con_columnas(leer_tabla(carpeta / "narrativas.csv"), "narrativas.csv",
                        ("narrativa", "titulo", "frases_clave", "fecha_origen"))
    cue = _con_columnas(leer_tabla(carpeta / "cuentas.csv"), "cuentas.csv", ("cuenta_id", "grupo"))
    postura = _limpio("postura").str.to_lowercase()
    com = com.select(
        _limpio("comentario_id").alias("comentario_id"),
        pl.when(_limpio("narrativa").str.to_lowercase().is_in(RUIDO)).then(None).otherwise(_limpio("narrativa"))
        .alias("narrativa"),
        pl.when(postura.is_in(POSTURAS)).then(postura).alias("postura"),
        pl.lit(True).alias("en_entrega")).unique(subset="comentario_id", keep="first", maintain_order=True)
    com = com.with_columns(pl.when(pl.col("narrativa").is_not_null()).then(pl.col("postura")).alias("postura"))
    nar = nar.select([_limpio(c).alias(c) for c in ("narrativa", "titulo", "frases_clave", "fecha_origen")]).filter(
        pl.col("narrativa") != "").unique(subset="narrativa", keep="first", maintain_order=True)
    cue = cue.select(_limpio("cuenta_id").alias("cuenta_id"),
                     pl.when(_limpio("grupo") != "").then(_limpio("grupo")).alias("grupo")
                     ).unique(subset="cuenta_id", keep="first", maintain_order=True)
    return com, nar, cue


def _me_gusta(datos: Path) -> pl.DataFrame:
    tabla = leer_tabla(buscar(datos, "comentarios.csv.gz"))
    if "me_gusta" not in tabla.columns:
        return pl.DataFrame(schema={"comentario_id": pl.String, "me_gusta": pl.Int64})
    return tabla.select(_limpio("comentario_id").alias("comentario_id"),
                        _limpio("me_gusta").cast(pl.Int64, strict=False).fill_null(0).alias("me_gusta")
                        ).unique(subset="comentario_id", keep="first", maintain_order=True)


def fuentes(datos: Path) -> dict:
    """{fuente_id: (nombre, tipo)}."""
    tabla = leer_tabla(buscar(Path(datos), "fuentes.csv"))
    if tabla is None or "fuente_id" not in tabla.columns:
        return {}
    for c in ("nombre", "tipo"):
        if c not in tabla.columns:
            tabla = tabla.with_columns(pl.lit("").alias(c))
    return {f: (n, t) for f, n, t in tabla.select(_limpio("fuente_id"), _limpio("nombre"), _limpio("tipo")).iter_rows()}


def cuentas_del_set(datos: Path) -> pl.DataFrame:
    """Lo que el set trae de cada cuenta: usuario, fecha de creación, seguidores y siguiendo (como texto)."""
    tabla = leer_tabla(buscar(Path(datos), "cuentas.csv.gz"))
    if tabla is None or "cuenta_id" not in tabla.columns:
        return pl.DataFrame(schema={c: pl.String for c in ("cuenta_id", *DATOS_DE_CUENTA)})
    for c in DATOS_DE_CUENTA:
        if c not in tabla.columns:
            tabla = tabla.with_columns(pl.lit("").alias(c))
    return tabla.select([_limpio(c).alias(c) for c in ("cuenta_id", *DATOS_DE_CUENTA)]).unique(
        subset="cuenta_id", keep="first", maintain_order=True)


def _antiguedad(datos_de_cuentas: pl.DataFrame, cuentas: pl.DataFrame, inicio_local) -> dict:
    """{grupo: mediana de días entre la creación de la cuenta y el inicio del período}; "" son las no coordinadas."""
    if inicio_local is None or datos_de_cuentas.height == 0:
        return {}
    dia_inicio = datetime.fromtimestamp(inicio_local, timezone.utc).date()
    t = (datos_de_cuentas.select(
            "cuenta_id", pl.col("fecha_creacion").str.slice(0, 10).str.to_date("%Y-%m-%d", strict=False).alias("creada"))
         .drop_nulls().join(cuentas, on="cuenta_id", how="inner")
         .with_columns((pl.lit(dia_inicio) - pl.col("creada")).dt.total_days().alias("dias"),
                       pl.col("grupo").fill_null("")))
    return {g: d for g, d in t.group_by("grupo").agg(pl.col("dias").median()).iter_rows()}


def _origen_local(texto: str, offset_s: int):
    """La fecha de origen como segundos en la hora local del set, o None si no se puede leer."""
    try:
        d = datetime.fromisoformat(texto.strip().replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return calendar.timegm(d.timetuple()) if d.tzinfo is None else int(d.timestamp()) + offset_s


def _zona(offset_s: int) -> str:
    h, m = divmod(abs(offset_s) // 60, 60)
    return f"{'-' if offset_s < 0 else '+'}{h:02d}:{m:02d}"


def _corto(texto: str) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= LARGO_TEXTO else texto[:LARGO_TEXTO - 1].rstrip() + "…"


def _entero(texto):
    texto = (texto or "").strip()
    return int(texto) if texto.lstrip("-").isdigit() else None


def _series(tabla: pl.DataFrame, claves: list, cantidad: int) -> dict:
    """{clave: [comentarios por tramo]}, con la clave como tupla de las columnas que agrupan."""
    series = {}
    for *clave, tramo, n in tabla.drop_nulls("tramo").group_by([*claves, "tramo"]).len().iter_rows():
        series.setdefault(tuple(clave), [0] * cantidad)[int(tramo)] = n
    return series


def _ejemplos(tabla: pl.DataFrame) -> list:
    t = (tabla.filter(pl.col("texto").str.strip_chars() != "")
         .sort(["me_gusta", "t", "comentario_id"], descending=[True, False, False], nulls_last=True)
         .unique(subset="texto", keep="first", maintain_order=True).head(EJEMPLOS))
    return [{"texto": _corto(x), "me_gusta": m} for x, m in t.select("texto", "me_gusta").iter_rows()]


def _posturas() -> list:
    return [pl.len().alias("comentarios"), (pl.col("postura") == "apoya").sum().alias("apoya"),
            (pl.col("postura") == "rechaza").sum().alias("rechaza")]


def _pajar(cuentas: pl.DataFrame) -> dict:
    """Todas las cuentas en orden de id, de a varias por celda, y en qué celdas cae cada operación."""
    n = cuentas.height
    por_celda = next((k for k in CELDAS_DEL_PAJAR if n / k <= MAX_CELDAS), 10 ** len(str(n)))
    marcadas = {}
    for i, grupo in cuentas.sort("cuenta_id").with_row_index("i").drop_nulls("grupo").select("i", "grupo").iter_rows():
        marcadas.setdefault(grupo, set()).add(i // por_celda)
    return {"por_celda": por_celda, "celdas": -(-n // por_celda),
            "marcadas": {grupo: sorted(celdas) for grupo, celdas in sorted(marcadas.items())}}


def _informe(ruta) -> dict:
    """Lo que el tablero toma del informe de la corrida, o None si no hay informe o no se puede leer."""
    try:
        d = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    perfil, notas, conteos = d.get("perfil") or {}, d.get("notas") or {}, d.get("conteos") or {}
    coordinacion, lados = notas.get("coordinacion") or {}, (notas.get("lado_que_apoya") or {}).get("por_narrativa") or {}
    return {
        "version": d.get("version"), "sin_modelo": bool(d.get("sin_modelo")), "segundos": d.get("segundos"),
        "memoria_pico_mib": d.get("memoria_pico_mib"),
        "corrida": (conteos.get("comentarios_con_narrativa"), conteos.get("cuentas_marcadas"),
                    (d.get("costo") or {}).get("segundos")),
        "avisos": perfil.get("avisos") or [], "medidas": perfil.get("medidas") or {},
        "idioma": perfil.get("idioma_del_set"), "tiempos": d.get("tiempos") or {},
        "uso_modelo": d.get("uso_modelo") or {},
        "coordinacion": {k: coordinacion.get(k) for k in ("marcadas_por_capa", "capas_apagadas", "alarma")},
        "titulos": {n: bool(t.get("titulo")) and t.get("titulo") != t.get("titulo_base")
                    for n, t in (notas.get("titulos") or {}).items() if isinstance(t, dict)},
        "lados": {n: x.get("decide") for n, x in lados.items() if isinstance(x, dict)},
        "configuracion": d.get("configuracion") or {}}


def tabla_completa(datos, entrega):
    """El set unido a la entrega, una fila por comentario: lo leen el resumen y el explorador de comentarios."""
    datos, entrega = Path(datos), Path(entrega)
    lectura = leer(datos)
    ent_com, ent_nar, ent_cue = leer_entrega(entrega)
    cuentas = pl.DataFrame({"cuenta_id": lectura.cuentas}, schema={"cuenta_id": pl.String}).join(
        ent_cue, on="cuenta_id", how="left")
    df = (lectura.comentarios.select("comentario_id", "publicacion_id", "cuenta_id", "texto", "t")
          .join(ent_com, on="comentario_id", how="left")
          .join(lectura.publicaciones.select("publicacion_id", "fuente_id"), on="publicacion_id", how="left")
          .join(cuentas, on="cuenta_id", how="left")
          .join(_me_gusta(datos), on="comentario_id", how="left")
          .with_columns(pl.col("fuente_id").fill_null(""), pl.col("me_gusta").fill_null(0)))
    if df.height and not df["en_entrega"].is_not_null().any():
        raise ValueError(f"la entrega de {entrega} no corresponde al set de {datos}: ningún comentario coincide")
    return lectura, df, cuentas, ent_nar


def calcular(datos, entrega, informe=None, nombre=None) -> dict:
    datos, entrega = Path(datos), Path(entrega)
    lectura, df, cuentas, ent_nar = tabla_completa(datos, entrega)
    offset = lectura.offset_s
    en_entrega = int(df["en_entrega"].is_not_null().sum())

    # Los tramos de los gráficos de tiempo, en la hora local del set.
    con_hora = df["t"].drop_nulls()
    if con_hora.len():
        t0, t1 = int(con_hora.min()) + offset, int(con_hora.max()) + offset
        tam = next((s for s in TRAMOS_S if (t1 - t0) / s <= MAX_TRAMOS), None)
        tam = tam or 86400 * (int((t1 - t0) / 86400 / MAX_TRAMOS) + 1)
        inicio = t0 // tam * tam
        cantidad = (t1 - inicio) // tam + 1
        df = df.with_columns(((pl.col("t") + offset - inicio) // tam).alias("tramo"))
    else:
        t0 = t1 = inicio = None
        tam = cantidad = 0
        df = df.with_columns(pl.lit(None, dtype=pl.Int64).alias("tramo"))

    con = df.filter(pl.col("narrativa").is_not_null())
    total_fuente = dict(df.group_by("fuente_id").len().iter_rows())
    nombres = fuentes(datos)
    cuentas_grupo = dict(cuentas.drop_nulls("grupo").group_by("grupo").len().iter_rows())
    try:
        costo = json.loads((entrega / "costo.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        costo = None
    costo = costo if isinstance(costo, dict) else None
    del_motor = _informe(informe) if informe else None
    if del_motor and del_motor.pop("corrida") != (con.height, sum(cuentas_grupo.values()), (costo or {}).get("segundos")):
        del_motor = None  # el informe es de otra corrida: no se mezcla con esta entrega

    # Narrativas.
    por_narr = {r["narrativa"]: r for r in con.group_by("narrativa").agg(
        *_posturas(), pl.col("cuenta_id").n_unique().alias("cuentas"),
        pl.col("grupo").is_not_null().sum().alias("coordinados"), pl.col("t").min().alias("primero")
    ).iter_rows(named=True)}
    de_csv = {r["narrativa"]: r for r in ent_nar.iter_rows(named=True)}
    series = _series(con.with_columns(pl.col("postura").fill_null("sin_postura")), ["narrativa", "postura"], cantidad)
    fuentes_narr = {}
    for n, f, c in con.group_by(["narrativa", "fuente_id"]).len().iter_rows():
        fuentes_narr.setdefault(n, {})[f] = c
    partes = con.filter(pl.col("postura").is_not_null()).partition_by(["narrativa", "postura"], as_dict=True)
    narrativas = []
    for etiqueta in sorted(set(por_narr) | set(de_csv)):
        r, c = por_narr.get(etiqueta, {}), de_csv.get(etiqueta, {})
        comentarios, apoya, rechaza = r.get("comentarios", 0), r.get("apoya", 0), r.get("rechaza", 0)
        narrativas.append({
            "etiqueta": etiqueta, "titulo": c.get("titulo") or etiqueta, "sin_titulo": not c.get("titulo"),
            "frases": [f.strip() for f in (c.get("frases_clave") or "").split("|") if f.strip()],
            "origen": c.get("fecha_origen") or "", "origen_s": _origen_local(c.get("fecha_origen") or "", offset),
            "primero_s": None if r.get("primero") is None else r["primero"] + offset,
            "comentarios": comentarios, "apoya": apoya, "rechaza": rechaza,
            "sin_postura": comentarios - apoya - rechaza, "cuentas": r.get("cuentas", 0),
            "coordinados": r.get("coordinados", 0),
            "serie": {p: series.get((etiqueta, p), [0] * cantidad) for p in (*POSTURAS, "sin_postura")},
            "fuentes": fuentes_narr.get(etiqueta, {}),
            "ejemplos": {p: _ejemplos(partes[(etiqueta, p)]) if (etiqueta, p) in partes else [] for p in POSTURAS},
            "titulo_de_ia": del_motor["titulos"].get(etiqueta) if del_motor else None,
            "lado_lo_decide": del_motor["lados"].get(etiqueta) if del_motor else None})

    # Operaciones coordinadas.
    coord = df.filter(pl.col("grupo").is_not_null())
    datos_de_cuentas = cuentas_del_set(datos)
    antiguedad = _antiguedad(datos_de_cuentas, cuentas, t0)
    series_op = _series(coord, ["grupo"], cantidad)
    operaciones = []
    for grupo in sorted(cuentas_grupo):
        sub = coord.filter(pl.col("grupo") == grupo)
        empuja = sub.drop_nulls("narrativa").group_by("narrativa").agg(*_posturas()).sort(
            ["comentarios", "narrativa"], descending=[True, False])
        textos = (sub.filter(pl.col("texto").str.strip_chars() != "").group_by("texto")
                  .agg(pl.len().alias("veces"), pl.col("cuenta_id").n_unique().alias("cuentas"))
                  .sort(["veces", "texto"], descending=[True, False]).head(TEXTOS_REPETIDOS))
        una_por_una = (cuentas.filter(pl.col("grupo") == grupo).select("cuenta_id")
                       .join(datos_de_cuentas, on="cuenta_id", how="left")
                       .join(sub.group_by("cuenta_id").agg(pl.len().alias("comentarios"),
                                                          pl.col("narrativa").is_not_null().sum().alias("con_narrativa")),
                             on="cuenta_id", how="left")
                       .with_columns(pl.col("comentarios").fill_null(0), pl.col("con_narrativa").fill_null(0))
                       .sort(["comentarios", "cuenta_id"], descending=[True, False]))
        operaciones.append({
            "etiqueta": grupo, "cuentas": cuentas_grupo[grupo], "comentarios": sub.height,
            "cuentas_que_comentaron": sub["cuenta_id"].n_unique(),
            "por_cuenta": round(sub.height / cuentas_grupo[grupo], 2),
            "ruido": int(sub["narrativa"].is_null().sum()),
            "narrativas": [{"etiqueta": n, "comentarios": c, "apoya": a, "rechaza": x}
                           for n, c, a, x in empuja.iter_rows()],
            "textos": [{"texto": _corto(t), "veces": v, "cuentas": c} for t, v, c in textos.iter_rows()],
            "serie": series_op.get((grupo,), [0] * cantidad),
            "antiguedad_mediana_dias": antiguedad.get(grupo),
            "cuentas_una_por_una": [
                {"cuenta": c, "usuario": u or "", "creada": f or "", "seguidores": _entero(s), "siguiendo": _entero(g),
                 "comentarios": n, "con_narrativa": k} for c, u, f, s, g, n, k in una_por_una.iter_rows()]})

    genuinas = df.filter(pl.col("grupo").is_null())
    cuentas_genuinas = cuentas.height - sum(cuentas_grupo.values())
    serie_total = _series(df.with_columns(pl.when(pl.col("narrativa").is_null()).then(pl.lit("ruido"))
                                          .otherwise(pl.lit("con_narrativa")).alias("clase")), ["clase"], cantidad)
    return {
        "generado": datetime.now().astimezone().isoformat(timespec="seconds"),
        "set": lectura.version_set,
        "nombre": nombre or None,
        "totales": {
            "comentarios": df.height, "con_narrativa": con.height, "ruido": df.height - con.height,
            "narrativas": len(narrativas), "cuentas": cuentas.height,
            "cuentas_coordinadas": sum(cuentas_grupo.values()), "operaciones": len(operaciones),
            "comentarios_coordinados": coord.height, "publicaciones": lectura.publicaciones.height,
            "fuentes": len(nombres) or len(total_fuente), "sin_hora": df.height - con_hora.len(),
            "sin_entrega": df.height - en_entrega},
        "periodo": {"desde_s": t0, "hasta_s": t1, "zona": _zona(offset)},
        "tramos": {"segundos": tam, "inicio_s": inicio, "cantidad": cantidad},
        "serie_total": {c: serie_total.get((c,), [0] * cantidad) for c in ("con_narrativa", "ruido")},
        "narrativas": narrativas,
        "fuentes": [{"id": f, "nombre": nombres.get(f, (f or "sin fuente", ""))[0] or f,
                     "tipo": nombres.get(f, ("", ""))[1], "comentarios": total_fuente.get(f, 0)}
                    for f in sorted(set(nombres) | set(total_fuente)) if total_fuente.get(f, 0) or f in nombres],
        "operaciones": operaciones,
        "pajar": _pajar(cuentas),
        "genuinas": {"cuentas": cuentas_genuinas, "comentarios": genuinas.height,
                     "por_cuenta": round(genuinas.height / cuentas_genuinas, 2) if cuentas_genuinas else None,
                     "antiguedad_mediana_dias": antiguedad.get("")},
        "costo": costo,
        "problemas": [{"problema": p["problema"], "cantidad": p["cantidad"]} for p in lectura.problemas],
        "informe": del_motor,
    }
