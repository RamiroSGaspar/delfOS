"""P2 · Perfil de entrada: mide seis cosas del set y avisa si se aparta del de práctica. **Solo avisa**: el
pipeline sigue igual (decisión 2). Los avisos van al registro de la corrida y un resumen, a las notas de
`costo.json`.

Las seis medidas, con su valor en práctica y el paso que cuida:
1. Integridad: ids repetidos, comentarios sin texto, fechas sin leer, respuestas a un comentario
   inexistente. Umbrales absolutos: cualquier id repetido; más del 0,1 % de fechas sin leer; más del 1 % de
   respuestas a un comentario inexistente; más del 1 % de comentarios sin texto. Los textos que quedan
   vacíos al normalizar (en práctica, el 1,08 %: comentarios de solo emojis, EXP-008) avisan por encima del
   doble del valor de práctica.
2. Respuestas sobre comentarios: 14,0 % (28.054 de 200.000). Cuida el puente.
3. Textos distintos sobre comentarios: 56,2 % (112.340 de 200.000). Cuida el costo.
4. Núcleos sobre textos distintos: 6,0 % (6.691 de 112.340). Cuida P6 y las familias.
5. Comentarios en la publicación más grande (6.793) y de la cuenta más activa (305). Cuida la sincronía.
6. Comentarios, cuentas y días (200.000, 15.991 y 14). No avisa: se informa.
Medidas 2 a 5: avisan si el valor queda por debajo de la mitad o por encima del doble del de práctica.
Además (decisión 13), avisa si el idioma del set no es el de la práctica (castellano).
"""
import polars as pl

PRACTICA = {
    "respuestas": 28054 / 200000,
    "textos_distintos": 112340 / 200000,
    "nucleos_sobre_textos": 6691 / 112340,
    "max_comentarios_publicacion": 6793,
    "max_comentarios_cuenta": 305,
    "vacios_al_normalizar": 2159 / 200000,
}
CUIDA = {
    "respuestas": "el puente por respuestas (N3 y N4)",
    "textos_distintos": "el costo de procesar (P3)",
    "nucleos_sobre_textos": "el relleno (P6) y las familias (N1)",
    "max_comentarios_publicacion": "la sincronía de la coordinación",
    "max_comentarios_cuenta": "la sincronía de la coordinación",
}
NOMBRE = {
    "respuestas": "medida 2, respuestas sobre comentarios",
    "textos_distintos": "medida 3, textos distintos sobre comentarios",
    "nucleos_sobre_textos": "medida 4, núcleos sobre textos distintos",
    "max_comentarios_publicacion": "medida 5, comentarios en la publicación más grande",
    "max_comentarios_cuenta": "medida 5, comentarios de la cuenta más activa",
}
PROPORCIONES = ("respuestas", "textos_distintos", "nucleos_sobre_textos")
IDIOMA_ESPERADO = "es"


def pct(x: float) -> str:
    return f"{100 * x:.1f} %".replace(".", ",")


def entero(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def medir(lectura, com: pl.DataFrame, n_nucleos: int, idioma: dict) -> dict:
    """Las seis medidas, la de idioma y los avisos. `com` son los comentarios ya preparados (con `norm`)."""
    n = com.height
    c = lectura.conteos
    vacios = com.filter((pl.col("texto").str.strip_chars() != "") & (pl.col("norm") == "")).height
    textos = com["texto"].n_unique()
    integridad = {"comentarios": n, **{k: c.get(k, 0) for k in (
        "ids_repetidos", "sin_id", "sin_texto", "fechas_sin_leer", "fechas_sin_zona", "fechas_en_otro_formato",
        "fechas_numericas", "respuestas_a_inexistente", "respuestas_a_si_mismo", "sin_publicacion_conocida",
        "sin_cuenta_conocida")}, "vacios_al_normalizar": vacios}
    t = com["t"].drop_nulls()
    dias = 0 if t.is_empty() else int((t.max() + lectura.offset_s) // 86400 - (t.min() + lectura.offset_s) // 86400 + 1)
    respuestas = int((com["respuesta_a"] != "").sum())
    valores = {
        "respuestas": respuestas / max(n, 1),
        "textos_distintos": textos / max(n, 1),
        "nucleos_sobre_textos": n_nucleos / max(textos, 1),
        "max_comentarios_publicacion": int(com.group_by("publicacion_id").len()["len"].max() or 0),
        "max_comentarios_cuenta": int(com.group_by("cuenta_id").len()["len"].max() or 0),
    }
    avisos = []
    # Medida 1: integridad, con umbrales absolutos.
    if c.get("ids_repetidos", 0):
        avisos.append(f"medida 1, integridad: {entero(c['ids_repetidos'])} ids de comentario repetidos "
                      "(quedó la primera fila de cada uno)")
    for clave, umbral, texto in (("fechas_sin_leer", 0.001, "fechas que no se pudieron leer"),
                                 ("respuestas_a_inexistente", 0.01, "respuestas a un comentario inexistente"),
                                 ("sin_texto", 0.01, "comentarios sin texto")):
        if c.get(clave, 0) / max(n, 1) > umbral:
            avisos.append(f"medida 1, integridad: {pct(c[clave] / n)} de {texto} ({entero(c[clave])}), "
                          f"por encima del umbral de {pct(umbral)}")
    if vacios / max(n, 1) > 2 * PRACTICA["vacios_al_normalizar"]:
        avisos.append(f"medida 1, integridad: {pct(vacios / n)} de los comentarios ({entero(vacios)}) quedan vacíos al "
                      f"normalizar, contra {pct(PRACTICA['vacios_al_normalizar'])} en práctica: puede ser otro alfabeto "
                      "o idioma (P4 conserva letras de cualquier alfabeto: son textos sin letras)")
    # Medidas 2 a 5: banda de la mitad al doble del valor de práctica.
    for clave, valor in valores.items():
        ref = PRACTICA[clave]
        if valor < ref / 2 or valor > 2 * ref:
            fmt = pct if clave in PROPORCIONES else entero
            lado = "menos de la mitad" if valor < ref / 2 else "más del doble"
            avisos.append(f"{NOMBRE[clave]}: {fmt(valor)}, contra {fmt(ref)} en práctica ({lado}); "
                          f"cuida {CUIDA[clave]}")
    # Idioma (decisión 13).
    idioma_set = idioma["idioma_del_set"]
    if idioma_set != IDIOMA_ESPERADO:
        reparto = ", ".join(f"{i} {pct(p)}" for i, p in list(idioma["proporcion_detectada"].items())[:6])
        if idioma_set == "varios":
            texto = (f"idioma: el set tiene varios idiomas ({reparto} de los comentarios con idioma detectado), "
                     f"contra {IDIOMA_ESPERADO} en práctica")
        else:
            texto = (f"idioma: el set está en {idioma_set} ({reparto} de los comentarios con idioma detectado), "
                     f"contra {IDIOMA_ESPERADO} en práctica")
        avisos.append(texto + "; cuida lo que depende del idioma: las abreviaturas de P4 y la capa interpretativa")
    medidas = {
        "integridad": integridad,
        **{clave: {"valor": round(float(v), 6), "practica": round(float(PRACTICA[clave]), 6)}
           for clave, v in valores.items()},
        "volumen": {"comentarios": n, "cuentas": len(lectura.cuentas), "dias": dias},
        "idioma": idioma,
    }
    medidas["respuestas"]["cantidad"] = respuestas
    medidas["textos_distintos"]["cantidad"] = int(textos)
    medidas["nucleos_sobre_textos"]["nucleos"] = int(n_nucleos)
    return {"avisos": avisos, "medidas": medidas, "idioma_del_set": idioma_set,
            "problemas_de_lectura": lectura.problemas, "version_set": lectura.version_set}


def resumen(avisos: list) -> str:
    """Una línea para las notas de costo.json."""
    if not avisos:
        return "Perfil de entrada (P2): sin avisos."
    return f"Perfil de entrada (P2): {len(avisos)} avisos: " + "; ".join(a.split(":")[0] for a in avisos) + "."
