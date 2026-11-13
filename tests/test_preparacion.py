"""Pruebas chicas de la preparación: P1, P2, P3, P4, P5 y P6 (casos de las fichas de la sección 8)."""
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta

import polars as pl
import pytest

from conftest import T0, ZONA, escribir_set
from pipeline import texto
from pipeline.configuracion import CONFIG
from pipeline.lectura import leer
from pipeline.perfil import medir


# ----------------------------------------------------------------------------- P1 y P2
@pytest.fixture(scope="module")
def set_sucio(tmp_path_factory):
    filas = [{"id": "c001", "texto": "la obra esta parada hace meses", "fecha": "01/09/2026 10:00:00"},
             {"id": "c002", "texto": "mentira eso no es asi", "fecha": (T0 + timedelta(hours=3)).isoformat(),
              "respuesta_a": "c999"},
             {"id": "c003", "texto": "primer texto del id repetido", "fecha": (T0 + timedelta(hours=4)).isoformat()},
             {"id": "c003", "texto": "segundo texto del id repetido", "fecha": (T0 + timedelta(hours=5)).isoformat()}]
    # Relleno sin respuestas hasta 100 comentarios: las respuestas quedan en 0 %, menos de la mitad del 14 %.
    filas += [{"id": f"r{i:03d}", "texto": f"comentario de relleno numero {i}",
               "fecha": (T0 + timedelta(minutes=i)).isoformat()} for i in range(97)]
    return leer(escribir_set(tmp_path_factory.mktemp("sucio"), filas))


def test_p1_no_descarta_comentarios(set_sucio):
    ids = set_sucio.comentarios["comentario_id"].to_list()
    assert {"c001", "c002", "c003"} <= set(ids)
    assert ids.count("c003") == 1


def test_p1_fecha_en_otro_formato_con_la_zona_dominante(set_sucio):
    fila = set_sucio.comentarios.filter(pl.col("comentario_id") == "c001")
    assert fila["t"][0] == int(datetime(2026, 9, 1, 10, 0, tzinfo=ZONA).timestamp())


def test_p1_respuesta_a_inexistente_pasa_a_primer_nivel(set_sucio):
    assert set_sucio.comentarios.filter(pl.col("comentario_id") == "c002")["respuesta_a"][0] == ""


def test_p1_id_repetido_conserva_la_primera_fila(set_sucio):
    fila = set_sucio.comentarios.filter(pl.col("comentario_id") == "c003")
    assert fila["texto"][0] == "primer texto del id repetido"


def test_p1_anota_los_tres_problemas(set_sucio):
    problemas = [p["problema"] for p in set_sucio.problemas]
    for inicio in ("fechas sin zona", "respuestas a un comentario inexistente", "ids de comentario repetidos"):
        assert any(p.startswith(inicio) for p in problemas), problemas


def test_p2_avisa_pocas_respuestas_y_el_id_repetido(set_sucio):
    from pipeline.preparacion import preparar
    com, _, _, _ = preparar(set_sucio.comentarios, CONFIG)
    idioma = {"idioma_del_set": "es", "proporcion_detectada": {"es": 1.0}}
    perfil = medir(set_sucio, com, 50, idioma)
    assert any(a.startswith("medida 2") for a in perfil["avisos"])
    assert any("ids de comentario repetidos" in a for a in perfil["avisos"])


def test_p2_avisa_un_idioma_distinto(set_sucio):
    from pipeline.preparacion import preparar
    com, _, _, _ = preparar(set_sucio.comentarios, CONFIG)
    perfil = medir(set_sucio, com, 50, {"idioma_del_set": "pt", "proporcion_detectada": {"pt": 0.9, "es": 0.1}})
    assert any(a.startswith("idioma: el set está en pt") for a in perfil["avisos"])


# ----------------------------------------------------------------------------- P3
def test_p3_cada_texto_distinto_una_vez(conversacion_corrida):
    com, textos = conversacion_corrida["com"], conversacion_corrida["textos"]
    iguales = conversacion_corrida["marcas"]["iguales"]
    ids_de_texto = com.filter(pl.col("comentario_id").is_in(iguales))["texto_id"].unique().to_list()
    assert len(ids_de_texto) == 1
    assert textos.height == textos["texto"].n_unique()


# ----------------------------------------------------------------------------- P4 y P5
def test_p4_ejemplo_de_la_ficha():
    assert texto.normalizar("Q SE ROBARON la plataaa!! @juan https://x.co #obra")[0] == "que se robaron la plata"


def test_p4_conserva_otros_alfabetos():
    norm = texto.normalizar("Привет мир ЙОД")[0]
    assert norm == "привет мир иод"  # cirílico: se conserva y pierde la breve, como las tildes latinas
    assert texto.normalizar("한국어 텍스트")[0] == "한국어 텍스트"  # hangul: vuelve a sílabas
    assert texto.normalizar("नमस्ते दुनिया")[0] == "नमस्ते दुनिया"  # devanagari: las marcas son parte de la letra
    assert texto.normalizar("precio ٣٤ pesos")[0] == "precio 34 pesos"  # dígitos de otra escritura


@pytest.mark.parametrize("crudo", [
    "Qué lindo día, ¡señor! 😀👍🏽", "ÑANDÚ árbol pingüino", "नमस्ते दुनिया", "한국어 텍스트", "Привет, мир!",
    "café́ doble marca", "́marca suelta al comienzo", "ﬁ ligadura y ½ fracción y ² y Ⅻ", "ΣΊΣΥΦΟΣ",
    "mixto नमस्ते á", "ok", "", "tab\tsalto\nfin",
])
def test_p4_el_camino_rapido_da_lo_mismo_que_el_paso_a_paso(crudo):
    t = crudo.lower()
    paso_a_paso = unicodedata.normalize("NFC", texto._limpiar_paso_a_paso(unicodedata.normalize("NFD", t)))
    assert texto.limpiar(t) == paso_a_paso


def test_p5_guarda_hashtag_y_emoji():
    _, emojis, hashtags, _ = texto.normalizar("#LaObraEsUnRobo 😡")
    assert hashtags == "#laobraesunrobo"
    assert emojis == "😡"


def test_p5_marca_mayusculas():
    assert texto.normalizar("ESTO ES UN ESCANDALO TOTAL")[3] is True
    assert texto.normalizar("esto es un escandalo total")[3] is False


# ----------------------------------------------------------------------------- P6
def test_p6_muletilla_che():
    restos = [f"{a} {b} parada numero {i}" for i, (a, b) in enumerate(
        (a, b) for a in ("se robaron", "la obra", "el puente", "los fondos", "el municipio")
        for b in ("esta", "sigue", "quedo", "parece", "vive"))]
    textos = restos + [f"che {r}" for r in restos] + ["se robaron la plata", "che se robaron la plata"]
    nucleos, muletillas, _ = texto.extraer_nucleos(textos)
    assert "che" in muletillas
    assert nucleos["che se robaron la plata"][0] == "se robaron la plata"


def test_p6_sin_relleno_no_saca_nada():
    textos = [f"afirmacion distinta numero {i} con contenido" for i in range(40)]
    nucleos, muletillas, coletillas = texto.extraer_nucleos(textos)
    assert not muletillas and not coletillas
    assert all(nucleos[t][0] == t for t in textos)


def _detectar_con_listas(textos, max_pre=6, max_suf=4, min_restos=25, min_resto=3):
    """La forma original de detectar rellenos (con listas de palabras), para comparar con la de cortes."""
    conjunto = set(textos)
    pre, suf = defaultdict(set), defaultdict(set)
    for t in conjunto:
        tok = t.split()
        for k in range(1, min(max_pre, len(tok) - min_resto) + 1):
            if " ".join(tok[k:]) in conjunto:
                pre[" ".join(tok[:k])].add(" ".join(tok[k:]))
        for k in range(1, min(max_suf, len(tok) - min_resto) + 1):
            if " ".join(tok[:-k]) in conjunto:
                suf[" ".join(tok[-k:])].add(" ".join(tok[:-k]))
    return ({p: len(r) for p, r in pre.items() if len(r) >= min_restos},
            {s: len(r) for s, r in suf.items() if len(r) >= min_restos})


def test_p6_cortar_por_espacios_da_lo_mismo_que_unir_palabras():
    bases = [f"{a} {b} {c} {d}" for a in ("uno", "dos", "tres") for b in ("rojo", "azul", "verde")
             for c in ("alto", "bajo", "medio") for d in ("ayer", "hoy")]
    textos = bases + [f"che boludo {b}" for b in bases] + [f"{b} viste" for b in bases] + [f"y {b} eh" for b in bases]
    assert texto.detectar_rellenos(textos, min_restos=5) == _detectar_con_listas(textos, min_restos=5)
