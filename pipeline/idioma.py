"""Idioma de cada texto y del set, sin dependencias (P2, decisión 13; EXP-009, opción `unicode-idioma`).

No cambia ninguna narrativa, postura ni cuenta: solo alimenta el aviso de idioma del perfil de entrada (P2).

Por texto (sobre el texto original sin menciones, enlaces ni hashtags, con sus tildes):
1. La escritura dominante de sus letras, por el nombre Unicode de cada carácter. Hangul da `ko`; kana da
   `ja`; han sin kana, `zh`; griego, `el`; hebreo, `he`; tailandés, `th`. Cirílico, árabe y devanagari los
   comparten varias lenguas: dan `indeterminado-cirilico`, `indeterminado-arabe` e
   `indeterminado-devanagari`. Otra escritura: `indeterminado-otra`.
2. En alfabeto latino, palabras de función de 7 idiomas, escritas a mano de conocimiento general. Cada
   palabra del texto que está en la lista de un idioma le suma 1 dividido por la cantidad de idiomas que
   la comparten. Gana el idioma con 1 punto o más y al menos 1,5 veces el puntaje del segundo; si no,
   `indeterminado-latino`.
3. Sin letras (solo emojis, números o signos): `indeterminado`.

Para el set: la proporción de comentarios (no de textos) de cada idioma detectado. Si un idioma tiene el
80 % o más de los comentarios con idioma detectado, es el idioma del set; si no, `varios`.
"""
import re
from collections import Counter
from functools import lru_cache

from pipeline.texto import RE_HASHTAG, RE_RUIDO_WEB, escritura

PALABRAS = {
    "es": """el la los las de del que y en un una es por con para no se lo como más pero sus le ya o este esta
             son está hay muy todo todos nos ni porque cuando también fue ser sin sobre eso esto qué cómo yo mi
             me te tu su al les hace van va estos están nada ese esa donde tiene hasta si che""",
    "pt": """o a os as de do da dos das que e em um uma é não com para por mais mas se no na nos nas ao aos isso
             isto ele ela eles você muito também foi ser sem sobre está são pelo pela até já seu sua meu minha
             tem vai então porque quando onde esse essa""",
    "en": """the a an and of to in is it that this for with on are was be not you they we have has but or at by
             from what all will just no so do i my your their there about would can our""",
    "fr": """le la les de des du un une et est que qui en pour pas ne ce cette sur avec dans au aux il elle ils
             nous vous on mais ou plus sont été être tout très je mon ma ces leur fait""",
    "it": """il lo la i gli le di del della dei che e è un una per non con su sono come più ma anche questo
             questa nel nella alla al si ci mi ti perché quando tutto molto hanno ha""",
    "de": """der die das und ist nicht ein eine zu den von mit sich des auf für im dem auch es an wie sind war
             wird aber nur noch ich wir sie er bei aus oder kein werden hat""",
    "nl": """de het een en van is dat niet op te in zijn voor met die er maar ook als bij aan wat ze hij wij geen
             nog dit worden heeft""",
}
LISTAS = {idioma: set(texto.split()) for idioma, texto in PALABRAS.items()}
_CUANTOS = Counter(p for lista in LISTAS.values() for p in lista)
# Una sola búsqueda por palabra: palabra -> (idiomas que la tienen, peso de 1 dividido por cuántos son).
PALABRA = {p: (tuple(i for i, lista in LISTAS.items() if p in lista), 1 / n) for p, n in _CUANTOS.items()}

POR_ESCRITURA = {"HANGUL": "ko", "GREEK": "el", "HEBREW": "he", "THAI": "th",
                 "CYRILLIC": "indeterminado-cirilico", "ARABIC": "indeterminado-arabe",
                 "DEVANAGARI": "indeterminado-devanagari"}
NOMBRE_ESCRITURA = {"LATIN": "latino", "HANGUL": "hangul", "CJK": "han", "HIRAGANA": "kana", "KATAKANA": "kana",
                    "GREEK": "griego", "HEBREW": "hebreo", "THAI": "tailandes", "CYRILLIC": "cirilico",
                    "ARABIC": "arabe", "DEVANAGARI": "devanagari"}
CLAVE_DE_NOMBRE = {v: k for k, v in NOMBRE_ESCRITURA.items() if k not in ("HIRAGANA", "KATAKANA", "CJK")}
RE_PALABRA = re.compile(r"[^\W\d_]+")
RE_LETRA_ASCII = re.compile(r"[A-Za-z]")
RE_LETRA_NO_ASCII = re.compile(r"[^\W\d_A-Za-z]")
MIN_PUNTOS = 1.0
MIN_VENTAJA = 1.5
MIN_SET = 0.80
IDIOMA_ESPERADO = "es"  # el de la práctica


@lru_cache(maxsize=None)
def _nombre(c: str) -> str:
    return NOMBRE_ESCRITURA.get(escritura(c), "otra")


def escritura_dominante(texto: str) -> str:
    """'latino', 'hangul', 'kana', 'han', ... o '' si no tiene letras. Kana gana a han (el japonés usa los dos)."""
    if texto.isascii():
        return "latino" if RE_LETRA_ASCII.search(texto) else ""
    conteo = Counter(_nombre(c) for c in RE_LETRA_NO_ASCII.findall(texto))
    ascii_ = len(RE_LETRA_ASCII.findall(texto))
    if ascii_:
        conteo["latino"] += ascii_
    if not conteo:
        return ""
    if conteo.get("kana", 0) and conteo.get("han", 0):
        conteo["kana"] += conteo.pop("han")
    return conteo.most_common(1)[0][0]


def idioma_latino(texto: str) -> str:
    """El idioma por palabras de función, o 'indeterminado-latino'."""
    puntos = {}
    for palabra in RE_PALABRA.findall(texto.lower()):
        entrada = PALABRA.get(palabra)
        if entrada is not None:
            idiomas, peso = entrada
            for idioma in idiomas:
                puntos[idioma] = puntos.get(idioma, 0) + peso
    orden = sorted(puntos.items(), key=lambda x: -x[1])[:2]
    if not orden or orden[0][1] < MIN_PUNTOS:
        return "indeterminado-latino"
    if len(orden) > 1 and orden[0][1] < MIN_VENTAJA * orden[1][1]:
        return "indeterminado-latino"
    return orden[0][0]


def idioma_de_texto(texto: str) -> str:
    texto = RE_HASHTAG.sub(" ", RE_RUIDO_WEB.sub(" ", texto))  # menciones, enlaces y hashtags no cuentan
    esc = escritura_dominante(texto)
    if not esc:
        return "indeterminado"
    if esc == "latino":
        return idioma_latino(texto)
    if esc == "kana":
        return "ja"
    if esc == "han":
        return "zh"
    return POR_ESCRITURA.get(CLAVE_DE_NOMBRE.get(esc), "indeterminado-otra")


def idiomas_lote(textos: list) -> list:
    """`idioma_de_texto` sobre una lista (la función que corren los procesos de `pipeline.paralelo`)."""
    return [idioma_de_texto(t) for t in textos]


def idiomas_con_el_del_set(idiomas: list, idioma_set: str) -> list:
    """El idioma de cada texto, con el del set para los textos latinos sin idioma claro (si el set es de un
    idioma latino de la lista). Es lo que recibe la capa interpretativa (N11)."""
    if idioma_set not in LISTAS:
        return list(idiomas)
    return [idioma_set if i == "indeterminado-latino" else i for i in idiomas]


def idioma_del_set(idiomas: list, comentarios: list) -> dict:
    """El idioma del set y sus medidas para P2. `idiomas[i]` es el idioma del texto i y `comentarios[i]`,
    cuántos comentarios lo repiten."""
    conteo = Counter()
    for idioma, n in zip(idiomas, comentarios):
        conteo[idioma] += n
    total = sum(conteo.values())
    detectados = {i: n for i, n in conteo.items() if not i.startswith("indeterminado")}
    n_det = sum(detectados.values())
    proporcion = {i: n / n_det for i, n in sorted(detectados.items(), key=lambda x: -x[1])} if n_det else {}
    if proporcion and next(iter(proporcion.values())) >= MIN_SET:
        idioma_set = next(iter(proporcion))
    elif proporcion:
        idioma_set = "varios"
    else:
        idioma_set = "indeterminado"
    heredados = 0
    if idioma_set in LISTAS:
        # Los textos latinos sin idioma claro heredan el idioma del set (se cuentan aparte).
        heredados = sum(n for idioma, n in zip(idiomas, comentarios) if idioma == "indeterminado-latino")
    return {
        "idioma_del_set": idioma_set,
        "comentarios": total,
        "comentarios_con_idioma_detectado": n_det,
        "proporcion_detectada": {i: round(p, 4) for i, p in proporcion.items()},
        "comentarios_por_etiqueta": dict(sorted(conteo.items(), key=lambda x: -x[1])),
        "comentarios_que_heredan_el_idioma_del_set": heredados,
    }
