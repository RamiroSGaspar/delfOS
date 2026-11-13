"""P4 (normalización única), P5 (hashtags y emojis aparte) y P6 (relleno estadístico y núcleos).

Solo usa la biblioteca estándar: no depende de Polars ni de nada pesado.

**P4, normalización "unicode" (EXP-009, opción `unicode-idioma`).** Lleva cada texto a una forma común:
saca menciones, enlaces y hashtags; pasa a minúsculas; saca tildes y diéresis de las letras latinas,
griegas y cirílicas (en otras escrituras las marcas son parte de la letra y se conservan); conserva
letras de cualquier alfabeto, números (los de otras escrituras pasan a 0-9) y `%`; reduce a una cualquier
letra repetida 3 veces o más ("siii" pasa a "si"); y expande abreviaturas de chat del castellano (en otro
idioma no aparecen y no hacen nada).

**P5.** Antes de normalizar se guardan los hashtags (en minúsculas), los emojis y si el texto está todo en
mayúsculas. La coordinación usa los hashtags (capa T).

**P6 (congelado).** Un pedazo de hasta 6 palabras al comienzo, o de hasta 4 al final, es relleno si, al
sacarlo, lo que queda existe como texto completo en 25 textos distintos o más. Se aplica en 3 rondas (los
rellenos se apilan) y el núcleo conserva siempre 3 palabras como mínimo. No depende del idioma.
"""
import re
import unicodedata
from collections import defaultdict
from functools import lru_cache

# Abreviaturas generales de chat en castellano (excepción de idioma declarada en la ficha P4).
ABREVIATURAS = {"q": "que", "xq": "porque", "pq": "porque", "x": "por", "tmb": "tambien", "tb": "tambien",
                "pa": "para", "tdo": "todo", "d": "de", "k": "que"}

RE_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿←-⇿⬀-⯿️‍]")
SIN_EMOJI = ("️", "‍")  # el selector de variante y la unión de ancho cero no son emojis por sí solos
RE_HASHTAG = re.compile(r"#\w+")
RE_RUIDO_WEB = re.compile(r"@\w+|https?://\S+")
RE_REPETIDA = re.compile(r"([^\W\d_])\1{2,}")

ASCII_QUE_QUEDA = set("abcdefghijklmnopqrstuvwxyz0123456789%")
SIN_TILDES = ("LATIN", "GREEK", "CYRILLIC")


# ----------------------------------------------------------------------------- P4 · normalización
@lru_cache(maxsize=None)
def escritura(c: str) -> str:
    """La escritura de un carácter, por la primera palabra de su nombre Unicode ("LATIN", "HANGUL"...)."""
    nombre = unicodedata.name(c, "")
    if nombre.startswith("CJK"):
        return "CJK"
    return nombre.split(" ", 1)[0] if nombre else ""


@lru_cache(maxsize=None)
def clase(c: str) -> str:
    """Qué hacer con cada carácter después de descomponerlo (NFD): 'queda', 'marca', 'digito' o 'espacio'."""
    if c in ASCII_QUE_QUEDA or c.isspace():
        return "queda"
    categoria = unicodedata.category(c)
    if categoria[0] == "L":
        return "queda"
    if categoria[0] == "M":
        return "marca"
    if categoria == "Nd":
        return "digito"
    return "espacio"


def _limpiar_paso_a_paso(descompuesto: str) -> str:
    """La regla completa, carácter por carácter, sobre el texto ya descompuesto (NFD).

    Una marca (tilde, diéresis) queda solo si sigue a una letra de una escritura que no es latina, griega ni
    cirílica; sueltas (por ejemplo, el selector de variante después de un emoji) se borran.
    """
    salida = []
    marca_queda = False
    for c in descompuesto:
        k = clase(c)
        if k == "queda":
            salida.append(c)
            marca_queda = c.isalpha() and escritura(c) not in SIN_TILDES
        elif k == "marca":
            if marca_queda:
                salida.append(c)
        elif k == "digito":
            salida.append(str(unicodedata.decimal(c)))
            marca_queda = False
        else:
            salida.append(" ")
            marca_queda = False
    return "".join(salida)


# Para el camino rápido: qué se reemplaza por qué (str.translate), qué caracteres son marcas y después de
# qué letras una marca se conservaría. Se completan a medida que aparecen caracteres nuevos.
_REEMPLAZO = {}
_MARCAS = set()
_LETRAS_QUE_CONSERVAN_MARCAS = set()
_VISTOS = set()


def _registrar(c: str):
    k = clase(c)
    if k == "marca":
        _REEMPLAZO[ord(c)] = None  # se borra (solo en el camino rápido, donde ninguna marca queda)
        _MARCAS.add(c)
    elif k == "digito":
        _REEMPLAZO[ord(c)] = str(unicodedata.decimal(c))
    elif k == "espacio":
        _REEMPLAZO[ord(c)] = " "
    elif c.isalpha() and escritura(c) not in SIN_TILDES:
        _LETRAS_QUE_CONSERVAN_MARCAS.add(c)
    _VISTOS.add(c)


for _c in map(chr, range(128)):
    _registrar(_c)


def limpiar(texto: str) -> str:
    """Descompone (NFD), aplica la regla de cada carácter y recompone (NFC).

    Camino rápido: si el texto no tiene ninguna marca que se conserve (no tiene marcas, o no tiene letras
    después de las cuales una marca quedaría), la regla es la misma para cada carácter sin importar el
    anterior, y se aplica de una vez con `str.translate`. Si no, se recorre carácter por carácter. Los dos
    caminos dan exactamente lo mismo.
    """
    descompuesto = unicodedata.normalize("NFD", texto)
    if descompuesto.isascii():
        return descompuesto.translate(_REEMPLAZO)  # NFC no cambia un texto ASCII
    distintos = set(descompuesto)
    for c in distintos - _VISTOS:
        _registrar(c)
    if not distintos.isdisjoint(_MARCAS) and not distintos.isdisjoint(_LETRAS_QUE_CONSERVAN_MARCAS):
        return unicodedata.normalize("NFC", _limpiar_paso_a_paso(descompuesto))
    return unicodedata.normalize("NFC", descompuesto.translate(_REEMPLAZO))


def normalizar(texto: str) -> tuple:
    """P4 y P5 de un texto: (normalizado, emojis, hashtags separados por '|', si está todo en mayúsculas)."""
    hashtags = "|".join(h.lower() for h in RE_HASHTAG.findall(texto))
    emojis = "".join(e for e in RE_EMOJI.findall(texto) if e not in SIN_EMOJI)
    letras = list(filter(str.isalpha, texto))
    grita = len(letras) >= 8 and sum(map(str.isupper, letras)) / len(letras) > 0.7
    t = RE_HASHTAG.sub(" ", RE_RUIDO_WEB.sub(" ", texto)).lower()
    t = RE_REPETIDA.sub(r"\1", limpiar(t))
    norm = " ".join(ABREVIATURAS.get(w, w) for w in t.split())
    return norm, emojis, hashtags, grita


def normalizar_lote(textos: list) -> list:
    """`normalizar` sobre una lista (la función que corren los procesos de `pipeline.paralelo`)."""
    return [normalizar(t) for t in textos]


# ----------------------------------------------------------------------------- P6 · relleno y núcleos
def detectar_rellenos(textos, max_pre: int = 6, max_suf: int = 4, min_restos: int = 25, min_resto: int = 3):
    """Comienzos y finales que funcionan como relleno: {pedazo: textos distintos a los que se pega}.

    Un pedazo es relleno si, al sacarlo, lo que queda existe como texto completo en el set, y eso pasa con
    al menos `min_restos` textos distintos. Una afirmación con contenido no cumple esa condición: no se pega
    a decenas de textos ajenos.

    Los textos llegan con las palabras separadas por un solo espacio (así los deja P4 y así quedan los
    núcleos), de modo que sacar las primeras k palabras es cortar el texto después de su k-ésimo espacio.
    """
    conjunto = set(textos)
    pre, suf = defaultdict(set), defaultdict(set)
    for t in conjunto:
        espacios = [i for i, c in enumerate(t) if c == " "]
        n = len(espacios) + 1  # palabras
        for k in range(1, min(max_pre, n - min_resto) + 1):
            resto = t[espacios[k - 1] + 1:]
            if resto in conjunto:
                pre[t[:espacios[k - 1]]].add(resto)
        for k in range(1, min(max_suf, n - min_resto) + 1):
            corte = espacios[n - 1 - k]
            resto = t[:corte]
            if resto in conjunto:
                suf[t[corte + 1:]].add(resto)
    prefijos = {p: len(r) for p, r in pre.items() if len(r) >= min_restos}
    sufijos = {s: len(r) for s, r in suf.items() if len(r) >= min_restos}
    return prefijos, sufijos


def quitar_rellenos(texto: str, prefijos, sufijos, max_pre: int = 6, max_suf: int = 4, min_resto: int = 3):
    """Saca el relleno más largo de cada punta, una y otra vez. Devuelve (núcleo, muletillas, coletillas)."""
    tok = texto.split()
    quit_pre, quit_suf = [], []
    cambio = True
    while cambio:
        cambio = False
        for k in range(min(max_pre, len(tok) - min_resto), 0, -1):
            p = " ".join(tok[:k])
            if p in prefijos:
                quit_pre.append(p)
                tok = tok[k:]
                cambio = True
                break
        for k in range(min(max_suf, len(tok) - min_resto), 0, -1):
            s = " ".join(tok[-k:])
            if s in sufijos:
                quit_suf.append(s)
                tok = tok[:-k]
                cambio = True
                break
    return " ".join(tok), "|".join(quit_pre), "|".join(reversed(quit_suf))


def extraer_nucleos(normalizados, rondas: int = 3, min_restos: int = 25, max_pre: int = 6, max_suf: int = 4,
                    min_resto: int = 3):
    """P6 en varias rondas. Devuelve ({texto normalizado: (núcleo, muletillas, coletillas)}, muletillas, coletillas).

    En cada ronda se detectan los rellenos sobre los núcleos de la ronda anterior y se sacan de todos. Si
    una ronda no encuentra ningún relleno, se corta (en un set sin relleno, el núcleo es el texto normalizado).
    """
    actual = {t: (t, "", "") for t in set(normalizados)}
    todos_pre, todos_suf = {}, {}
    for _ in range(rondas):
        pre, suf = detectar_rellenos([v[0] for v in actual.values()], max_pre=max_pre, max_suf=max_suf,
                                     min_restos=min_restos, min_resto=min_resto)
        if not pre and not suf:
            break
        for p, n in pre.items():
            todos_pre[p] = max(n, todos_pre.get(p, 0))
        for s, n in suf.items():
            todos_suf[s] = max(n, todos_suf.get(s, 0))
        # Un texto solo puede perder un relleno si empieza con la primera palabra de alguna muletilla o
        # termina con la última palabra de alguna coletilla: los demás quedan igual sin probar nada.
        primeras = {p.split(" ", 1)[0] for p in pre}
        ultimas = {x.rsplit(" ", 1)[-1] for x in suf}
        nuevo = {}
        for t, (nuc, mul, col) in actual.items():
            if nuc.split(" ", 1)[0] not in primeras and nuc.rsplit(" ", 1)[-1] not in ultimas:
                nuevo[t] = (nuc, mul, col)
                continue
            n2, m2, c2 = quitar_rellenos(nuc, pre, suf, max_pre=max_pre, max_suf=max_suf, min_resto=min_resto)
            nuevo[t] = (n2, "|".join(x for x in (mul, m2) if x), "|".join(x for x in (c2, col) if x))
        actual = nuevo
    return actual, todos_pre, todos_suf
