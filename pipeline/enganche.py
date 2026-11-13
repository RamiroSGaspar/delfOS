"""N11 · Enganche de la capa interpretativa (ficha N11, decisiones 11 a 14). Opcional: `--enganche <archivo>`.

Escribe una tabla con una fila por comentario con todo lo que la capa interpretativa (arquitectura A, función
comunicativa G y arquetipos) necesita **después** de que la narrativa y los lados están decididos. Se escribe
al final y no lo lee ningún paso del pipeline: la capa interpretativa no puede cambiar la narrativa, el lado,
la postura ni el origen. Va fuera de los 4 archivos oficiales y está apagado por defecto (EXP-017 corrió sin él).

Columnas, en este orden:
- Por comentario: `comentario_id`; `texto` (el original, intacto: decisión 12); `texto_id` (el mapa de texto a
  comentarios de P3: los comentarios con el mismo texto comparten `texto_id`); `nucleo` (P6); `familia` (N1,
  la del núcleo del propio comentario); `narrativa` (vacía si es ruido); `lado` (N7: 1 o -1, vacío si es
  ruido; qué lado apoya lo dice `postura`); `postura`; `respuesta_a` (el comentario padre, después de la
  lectura tolerante); `publicacion_id` y `titular`; `fuente_id` y `tipo_fuente`; `idioma` (del texto, con el
  del set para los textos latinos sin idioma claro, EXP-009).
- Por narrativa (repetido en cada comentario): `titulo_narrativa` y `origen_narrativa`.
- Por corrida (repetido en cada fila): `version_set` y `version_motor`.
"""
from pathlib import Path

import polars as pl

COLUMNAS = ["comentario_id", "texto", "texto_id", "nucleo", "familia", "narrativa", "lado", "postura", "respuesta_a",
            "publicacion_id", "titular", "fuente_id", "tipo_fuente", "idioma", "titulo_narrativa", "origen_narrativa",
            "version_set", "version_motor"]


def tabla_enganche(conv, familia, pred: list, signo, postura: list, publicaciones: pl.DataFrame, textos: pl.DataFrame,
                   idiomas: list, titulos: dict, origen: dict, version_set: str, version_motor: str) -> pl.DataFrame:
    """La tabla del enganche. `idiomas` va en el orden de `textos` (la tabla de textos distintos de P3)."""
    lado = [str(int(s)) if n else "" for n, s in zip(pred, signo.tolist())]
    df = conv.com.select("comentario_id", "texto", "texto_id", "nucleo", "respuesta_a", "publicacion_id").with_columns(
        pl.Series("familia", [f"f{int(f)}" for f in familia[conv.nuc]], dtype=pl.String),
        pl.Series("narrativa", pred, dtype=pl.String), pl.Series("lado", lado, dtype=pl.String),
        pl.Series("postura", postura, dtype=pl.String))
    pub = publicaciones.select("publicacion_id", "titular", "fuente_id", "tipo_fuente")
    df = df.join(pub, on="publicacion_id", how="left", maintain_order="left")
    idioma = pl.DataFrame({"texto_id": textos["texto_id"], "idioma": idiomas},
                          schema={"texto_id": pl.String, "idioma": pl.String})
    df = df.join(idioma, on="texto_id", how="left", maintain_order="left")
    narr = pl.DataFrame({"narrativa": list(titulos), "titulo_narrativa": [titulos[n][0] for n in titulos],
                         "origen_narrativa": [origen.get(n, "") for n in titulos]},
                        schema={"narrativa": pl.String, "titulo_narrativa": pl.String, "origen_narrativa": pl.String})
    df = df.join(narr, on="narrativa", how="left", maintain_order="left")
    df = df.with_columns(pl.lit(version_set).alias("version_set"), pl.lit(version_motor).alias("version_motor"))
    return df.select(COLUMNAS).with_columns(pl.col(c).fill_null("") for c in COLUMNAS)


def escribir(ruta, tabla: pl.DataFrame) -> dict:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tabla.write_csv(ruta)
    return {"archivo": str(ruta), "filas": tabla.height, "columnas": len(tabla.columns)}
