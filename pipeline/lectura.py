"""P1 · Lectura tolerante: lee los 4 archivos del set sin descartar comentarios por datos sucios.

Reglas (ficha P1):
- La fecha se lee probando varios formatos: primero el oficial (ISO con zona), después otros formatos con
  zona, después formatos sin zona (se toma la zona dominante del set) y por último segundos o milisegundos
  desde 1970. Si ninguno sirve, el comentario queda sin hora y se anota.
- Una respuesta a un comentario inexistente, o a sí misma, pasa a ser de primer nivel y se anota.
- Si un id de comentario se repite, queda la primera fila (en el orden del archivo) y se anota.
- Un texto vacío queda vacío y se anota. Una columna que falta se completa vacía y se anota.
Solo dos cosas cortan la corrida, porque sin ellas no hay nada que entregar: que no esté el archivo de
comentarios o que no tenga la columna `comentario_id`.

Conserva (decisión 11) la publicación con su titular, la fuente con su tipo y la versión del set. Los
datos de la cuenta no se usan como contexto.
"""
import hashlib
from dataclasses import dataclass
from pathlib import Path

import polars as pl

FORMATO_OFICIAL = "%Y-%m-%dT%H:%M:%S%z"
FORMATOS_CON_ZONA = [FORMATO_OFICIAL, "%Y-%m-%dT%H:%M:%S%.f%z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S%.f%z",
                     "%Y-%m-%dT%H:%M%z", "%Y-%m-%d %H:%M%z"]
FORMATOS_SIN_ZONA = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%.f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%.f",
                     "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M:%S",
                     "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"]
ZONA_POR_DEFECTO_S = -3 * 3600  # si ninguna fecha trae zona: la de los sets conocidos (-03:00)
ARCHIVOS = ("comentarios.csv.gz", "publicaciones.csv.gz", "fuentes.csv", "cuentas.csv.gz")
COLUMNAS_COMENTARIOS = ("comentario_id", "publicacion_id", "cuenta_id", "fecha", "texto", "respuesta_a")
EJEMPLOS = 5  # ids de ejemplo por problema


@dataclass
class Lectura:
    comentarios: pl.DataFrame  # comentario_id, publicacion_id, cuenta_id, fecha, texto, respuesta_a, t
    publicaciones: pl.DataFrame  # publicacion_id, fuente_id, titular, tipo_fuente
    cuentas: list  # ids de cuenta de cuentas.csv.gz, ordenados (si falta el archivo, los de los comentarios)
    problemas: list  # [{"problema", "cantidad", "ejemplos"}], solo los que aparecieron
    conteos: dict  # los conteos de integridad (todos, aunque sean 0), para el perfil de entrada (P2)
    offset_s: int  # zona horaria dominante del set, en segundos (-10800 es -03:00)
    version_set: str  # nombre de la carpeta del set más una huella de los 4 archivos


def buscar(carpeta: Path, nombre: str):
    """El archivo con ese nombre, o su versión con o sin .gz."""
    alternativa = nombre[:-3] if nombre.endswith(".gz") else nombre + ".gz"
    for ruta in (carpeta / nombre, carpeta / alternativa):
        if ruta.exists():
            return ruta
    return None


def leer_tabla(ruta):
    """Todo como texto, con UTF-8 tolerante y las filas con columnas de más recortadas."""
    if ruta is None:
        return None
    return pl.read_csv(ruta, infer_schema_length=0, encoding="utf8-lossy", truncate_ragged_lines=True)


def huella_del_set(carpeta: Path) -> str:
    total = hashlib.sha256()
    for nombre in ARCHIVOS:
        ruta = buscar(carpeta, nombre)
        h = hashlib.sha256()
        if ruta is not None:
            with open(ruta, "rb") as f:
                for bloque in iter(lambda: f.read(1 << 20), b""):
                    h.update(bloque)
        total.update(f"{nombre}:{h.hexdigest()};".encode())
    return total.hexdigest()


def zona_dominante(fechas: pl.Series) -> int:
    """La zona horaria más frecuente entre las fechas que la traen, en segundos."""
    z = (pl.DataFrame({"f": fechas}).select(pl.col("f").str.strip_chars().str.extract_groups(r"([+-])(\d{2}):?(\d{2})$"))
         .unnest("f").drop_nulls())
    if z.height == 0:
        return ZONA_POR_DEFECTO_S
    z.columns = ["signo", "h", "m"]
    seg = z.select((pl.when(pl.col("signo") == "-").then(-1).otherwise(1)
                    * (pl.col("h").cast(pl.Int64) * 3600 + pl.col("m").cast(pl.Int64) * 60)).alias("s"))["s"]
    return int(seg.mode().sort()[0])


def _leer_fechas_todas(fechas: pl.Series, offset_s: int) -> pl.DataFrame:
    """Prueba todos los formatos sobre cada fecha: t (segundos desde 1970, UTC) y cómo se leyó."""
    f = pl.col("f").str.strip_chars()
    con_zona = [f.str.to_datetime(fmt, strict=False).dt.epoch("s") for fmt in FORMATOS_CON_ZONA]
    sin_zona = [f.str.to_datetime(fmt, strict=False).dt.epoch("s") - offset_s for fmt in FORMATOS_SIN_ZONA]
    numero = pl.when(f.str.contains(r"^\d{13}$")).then(f.cast(pl.Int64, strict=False) // 1000).when(
        f.str.contains(r"^\d{9,10}$")).then(f.cast(pl.Int64, strict=False))
    df = pl.DataFrame({"f": fechas}).select(
        pl.coalesce(con_zona + sin_zona + [numero]).alias("t"),
        con_zona[0].is_not_null().alias("oficial"),
        pl.coalesce(con_zona).is_not_null().alias("con_zona"),
        pl.coalesce(sin_zona).is_not_null().alias("sin_zona"))
    return df.select("t", pl.when(pl.col("oficial")).then(pl.lit("oficial"))
                     .when(pl.col("con_zona")).then(pl.lit("otro formato con zona"))
                     .when(pl.col("sin_zona")).then(pl.lit("sin zona"))
                     .when(pl.col("t").is_not_null()).then(pl.lit("numero"))
                     .otherwise(pl.lit("sin leer")).alias("como"))


def leer_fechas(fechas: pl.Series, offset_s: int) -> pl.DataFrame:
    """t (segundos desde 1970, UTC) y cómo se leyó cada fecha.

    Primero se prueba solo el formato oficial, que en los sets conocidos lee todas las fechas; las que no
    lee pasan por todos los formatos. Da lo mismo que probar todos los formatos sobre todas las fechas
    (el formato oficial es el primero que se prueba), pero sin leer 18 veces cada fecha.
    """
    oficial = pl.DataFrame({"f": fechas}).select(
        pl.col("f").str.strip_chars().str.to_datetime(FORMATO_OFICIAL, strict=False).dt.epoch("s").alias("t"))
    faltan = oficial["t"].is_null()
    if not faltan.any():
        return oficial.with_columns(pl.lit("oficial").alias("como"))
    resto = _leer_fechas_todas(fechas.filter(faltan), offset_s)
    indice = pl.Series(range(len(fechas))).filter(faltan)
    t = oficial["t"].scatter(indice, resto["t"])
    como = pl.Series(["oficial"] * len(fechas), dtype=pl.String).scatter(indice, resto["como"])
    return pl.DataFrame({"t": t, "como": como})


def anotar(problemas: list, conteos: dict, clave: str, descripcion: str, ids: list):
    conteos[clave] = len(ids)
    if ids:
        problemas.append({"problema": descripcion, "cantidad": len(ids), "ejemplos": ids[:EJEMPLOS]})


def leer(carpeta) -> Lectura:
    carpeta = Path(carpeta)
    problemas, conteos = [], {}
    ruta = buscar(carpeta, "comentarios.csv.gz")
    if ruta is None:
        raise FileNotFoundError(f"no está comentarios.csv.gz (ni comentarios.csv) en {carpeta}")
    com = leer_tabla(ruta)
    if "comentario_id" not in com.columns:
        raise ValueError(f"{ruta.name} no tiene la columna comentario_id; tiene {com.columns}")
    faltan = [c for c in COLUMNAS_COMENTARIOS if c not in com.columns]
    if faltan:
        problemas.append({"problema": f"faltan columnas en {ruta.name}; se completan vacías", "cantidad": len(faltan),
                          "ejemplos": faltan})
        com = com.with_columns([pl.lit(None, dtype=pl.String).alias(c) for c in faltan])
    filas_leidas = com.height
    com = com.select(
        pl.col("comentario_id").str.strip_chars(), pl.col("publicacion_id").str.strip_chars().fill_null(""),
        pl.col("cuenta_id").str.strip_chars().fill_null(""), pl.col("fecha"), pl.col("texto").fill_null(""),
        pl.col("respuesta_a").str.strip_chars().fill_null(""))

    # Ids: sin id no se puede entregar el comentario; repetido, queda el primero.
    conteos["sin_id"] = com.filter(pl.col("comentario_id").is_null() | (pl.col("comentario_id") == "")).height
    if conteos["sin_id"]:
        problemas.append({"problema": "comentarios sin id (no se pueden entregar)", "cantidad": conteos["sin_id"],
                          "ejemplos": []})
    com = com.filter(pl.col("comentario_id").is_not_null() & (pl.col("comentario_id") != ""))
    repetidos = com.filter(pl.col("comentario_id").is_duplicated())["comentario_id"].unique(maintain_order=True)
    anotar(problemas, conteos, "ids_repetidos", "ids de comentario repetidos (queda la primera fila)",
           repetidos.to_list())
    com = com.unique(subset="comentario_id", keep="first", maintain_order=True)

    # Texto.
    anotar(problemas, conteos, "sin_texto", "comentarios sin texto",
           com.filter(pl.col("texto").str.strip_chars() == "")["comentario_id"].to_list())

    # Respuestas: a sí mismo o a un comentario inexistente, pasan a primer nivel.
    ids = com["comentario_id"]
    a_si_mismo = com.filter((pl.col("respuesta_a") != "") & (pl.col("respuesta_a") == pl.col("comentario_id")))
    inexistente = com.filter((pl.col("respuesta_a") != "") & ~pl.col("respuesta_a").is_in(ids.implode()))
    anotar(problemas, conteos, "respuestas_a_si_mismo", "respuestas a sí mismas (pasan a primer nivel)",
           a_si_mismo["comentario_id"].to_list())
    anotar(problemas, conteos, "respuestas_a_inexistente",
           "respuestas a un comentario inexistente (pasan a primer nivel)", inexistente["comentario_id"].to_list())
    malas = set(a_si_mismo["comentario_id"].to_list()) | set(inexistente["comentario_id"].to_list())
    if malas:
        com = com.with_columns(pl.when(pl.col("comentario_id").is_in(list(malas))).then(pl.lit(""))
                               .otherwise(pl.col("respuesta_a")).alias("respuesta_a"))

    # Fechas.
    offset_s = zona_dominante(com["fecha"].fill_null(""))
    lectura_fechas = leer_fechas(com["fecha"].fill_null(""), offset_s)
    com = com.with_columns(lectura_fechas["t"].alias("t"), lectura_fechas["como"].alias("_como"))
    for como, clave, descripcion in (
            ("sin leer", "fechas_sin_leer", "fechas que no se pudieron leer (el comentario queda sin hora)"),
            ("sin zona", "fechas_sin_zona", "fechas sin zona horaria (se tomó la zona dominante del set)"),
            ("otro formato con zona", "fechas_en_otro_formato", "fechas con zona en otro formato (se leyeron)"),
            ("numero", "fechas_numericas", "fechas en segundos o milisegundos desde 1970 (se leyeron)")):
        anotar(problemas, conteos, clave, descripcion,
               com.filter(pl.col("_como") == como)["comentario_id"].to_list())
    com = com.drop("_como")

    # Publicaciones y fuentes (para la capa interpretativa, decisión 11).
    pub = leer_tabla(buscar(carpeta, "publicaciones.csv.gz"))
    fue = leer_tabla(buscar(carpeta, "fuentes.csv"))
    if pub is None:
        problemas.append({"problema": "no está publicaciones.csv.gz: sin titulares ni fuentes", "cantidad": 1,
                          "ejemplos": []})
        pub = pl.DataFrame(schema={"publicacion_id": pl.String, "fuente_id": pl.String, "titular": pl.String})
    for c in ("publicacion_id", "fuente_id", "titular"):
        if c not in pub.columns:
            pub = pub.with_columns(pl.lit(None, dtype=pl.String).alias(c))
    pub = pub.select(pl.col("publicacion_id").str.strip_chars(), pl.col("fuente_id").str.strip_chars().fill_null(""),
                     pl.col("titular").fill_null("")).unique(subset="publicacion_id", keep="first", maintain_order=True)
    if fue is None or "fuente_id" not in fue.columns:
        problemas.append({"problema": "no está fuentes.csv o no tiene fuente_id: sin tipo de fuente", "cantidad": 1,
                          "ejemplos": []})
        fue = pl.DataFrame(schema={"fuente_id": pl.String, "tipo": pl.String})
    if "tipo" not in fue.columns:
        fue = fue.with_columns(pl.lit(None, dtype=pl.String).alias("tipo"))
    fue = fue.select(pl.col("fuente_id").str.strip_chars(), pl.col("tipo").fill_null("").alias("tipo_fuente")).unique(
        subset="fuente_id", keep="first", maintain_order=True)
    pub = pub.join(fue, on="fuente_id", how="left").with_columns(pl.col("tipo_fuente").fill_null(""))
    sin_pub = com.filter(~pl.col("publicacion_id").is_in(pub["publicacion_id"].implode()))
    anotar(problemas, conteos, "sin_publicacion_conocida", "comentarios de una publicación que no está en publicaciones",
           sin_pub["comentario_id"].to_list())

    # Cuentas.
    cue = leer_tabla(buscar(carpeta, "cuentas.csv.gz"))
    if cue is None or "cuenta_id" not in cue.columns:
        problemas.append({"problema": "no está cuentas.csv.gz o no tiene cuenta_id: se usan las cuentas de los comentarios",
                          "cantidad": 1, "ejemplos": []})
        cuentas = sorted(set(com["cuenta_id"].to_list()) - {""})
    else:
        cuentas = sorted(set(cue["cuenta_id"].str.strip_chars().drop_nulls().to_list()) - {""})
    sin_cuenta = com.filter(~pl.col("cuenta_id").is_in(pl.Series(cuentas, dtype=pl.String).implode()))
    anotar(problemas, conteos, "sin_cuenta_conocida", "comentarios de una cuenta que no está en cuentas",
           sin_cuenta["comentario_id"].to_list())

    conteos["filas_leidas"] = filas_leidas
    com = com.sort("t", "comentario_id", nulls_last=True)
    version = f"{carpeta.name} sha256:{huella_del_set(carpeta)[:12]}"
    return Lectura(comentarios=com, publicaciones=pub, cuentas=cuentas, problemas=problemas, conteos=conteos,
                   offset_s=offset_s, version_set=version)
