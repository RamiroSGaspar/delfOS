"""N10 · Título y frases clave de cada narrativa (EXP-015, opción "haiku3").

**Sin modelo (el respaldo):** el título es el núcleo más frecuente del lado que apoya y las frases clave,
los 5 más frecuentes (se cuentan los comentarios propios, no los heredados por respuesta; a igual
frecuencia, orden alfabético). Si el lado que apoya no tiene comentarios propios, el título es la etiqueta
de la narrativa y no hay frases clave.

**Con modelo:** el modelo redacta el título con esas 5 frases clave: una línea, en el mismo idioma, 12
palabras o menos, sin inventar nada. El título del modelo se acepta solo si:
- la respuesta no se cortó, no está vacía y tiene 20 palabras o menos, y
- **no agrega palabras de contenido** que no estén en los núcleos del lado que apoya (criterio L3 de
  EXP-015: palabras de 4 letras o más que no son funcionales; tolera la flexión comparando la raíz de las
  palabras de 7 letras o más).
Si no, queda el título sin modelo. Las frases clave son siempre las de los núcleos.
"""
import re
import unicodedata
from collections import Counter, defaultdict

from pipeline.modelo import ErrorModelo, Pedido
from pipeline.texto import ABREVIATURAS, RE_HASHTAG, RE_RUIDO_WEB

SISTEMA = ("Redactás titulares para discusiones en redes sociales. Los comentarios pueden estar en "
           "cualquier idioma: escribís el titular en el mismo idioma de los comentarios que recibís.")

PEDIDO = """Estos son los comentarios más frecuentes de una misma discusión. Forman el lado que apoya una afirmación.

Núcleos:
{lineas}

Escribí UN titular que diga la afirmación que sostienen esos comentarios.
Reglas:
- en el mismo idioma de los núcleos;
- una sola línea, sin comillas, sin etiquetas y sin puntos suspensivos;
- {max_palabras} palabras o menos;
- no inventes nada: usá solo las palabras de los núcleos;
- no nombres cuentas, hashtags ni lugares.

Respondé solo con el titular."""

PREFIJOS = re.compile(r"^\s*(titulo|título|title|afirmacion|afirmación)\s*[:\-]\s*", re.IGNORECASE)
COMILLAS = "\"'“”«»‘’"

# Palabras funcionales del criterio L3 (EXP-015): no cuentan como contenido.
FUNCIONALES = set("""de la el los las un una unos unas y o u que en con por para se lo su sus al del es son
está están hay no si ya mas más como cuando donde este esta esto esos esa eso sin sobre entre desde hasta
tras ante bajo cada todo toda todos todas otro otra otros otras a e le les mi mis tu tus nuestro nuestra me te
nos os cual quien cuan mientras aunque pero sino salvo segun según durante contra hacia mediante muy
tambien tampoco ahora antes despues después entonces aqui alli allí algo alguien nada nadie
cual sea ser estar tener hacer decir ir ver dar saber querer poder poner salir venir traer llegar pasar
deber parecer quedar creer hablar trabajar ganar perder seguir conocer vivir dejar pedir tomar recibir pagar
cambiar terminar empezar entrar esperar buscar encontrar contar llamar escribir leer correr dormir comer
beber jugar estudiar enseñar aprender necesitar ayudar tratar usar sentir atender avisar sacar bajar subir
tirar mover publicar revisar mejorar eliminar demostrar uno dos tres mucho poco menos otra vez
tiene tienen hace hacen dice dicen queda quedan deja dejan pide piden tomo toman sale salen viene vienen
llega llegan pasa pasan gano gana pierde pierden sigue siguen cambia cambian termina terminan
puede pueden debe deben quiero quieren podia puede habia sera seran fue fueron""".split())


# ----------------------------------------------------------------------------- sin modelo
def titulos_por_nucleos(nucleos: list, pred: list, postura: list, propia, n_frases: int = 5) -> dict:
    """{narrativa: (título, [frases clave])}: los núcleos más frecuentes de los comentarios propios del lado
    que apoya."""
    por_narr = defaultdict(Counter)
    for n, p, t, es_propia in zip(pred, postura, nucleos, propia):
        if n and p == "apoya" and es_propia:
            por_narr[n][t] += 1
    salida = {}
    for n in sorted(set(pred) - {""}):
        mejores = [t for t, _ in sorted(por_narr[n].items(), key=lambda x: (-x[1], x[0]))[:n_frases]]
        salida[n] = (mejores[0] if mejores else n, mejores)
    return salida


# ----------------------------------------------------------------------------- criterio L3
def palabras_latinas(texto: str) -> list:
    """Las palabras del texto con la normalización latina del prototipo (solo letras de la a a la z):
    es la que usa el criterio L3 de EXP-015 para comparar el título con los núcleos."""
    t = RE_HASHTAG.sub(" ", RE_RUIDO_WEB.sub(" ", texto or "")).lower()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9%\s]", " ", t)
    t = re.sub(r"([a-z])\1{2,}", r"\1", t)
    return [ABREVIATURAS.get(w, w) for w in t.split()]


def palabras_de_contenido(texto: str) -> list:
    return [p for p in palabras_latinas(texto) if len(p) >= 4 and p not in FUNCIONALES]


def raiz(palabra: str) -> str:
    return palabra[:-2] if len(palabra) >= 7 else palabra


def fuera_del_universo(palabras: list, universo: set) -> list:
    """Las palabras que los núcleos del lado que apoya no cubren (L3)."""
    raices = {raiz(p) for p in universo}
    fuera = []
    for palabra in palabras:
        if palabra in universo:
            continue
        if len(palabra) >= 7 and raiz(palabra) in raices:
            continue
        fuera.append(palabra)
    return sorted(set(fuera))


# ----------------------------------------------------------------------------- con modelo
def armar_pedido(frases: list, max_palabras: int) -> str:
    lineas = "\n".join(f"{i + 1}. {n}" for i, n in enumerate(frases))
    return PEDIDO.format(lineas=lineas, max_palabras=max_palabras)


def limpiar(respuesta: str) -> str:
    """La primera línea útil de la respuesta, sin comillas ni prefijos."""
    for linea in (respuesta or "").splitlines():
        t = linea.strip()
        if not t:
            continue
        t = PREFIJOS.sub("", t).strip()
        t = t.strip(COMILLAS).strip()
        return " ".join(t.split())
    return ""


class Titulos:
    """N10 en dos pasos: `pedidos()` arma lo que hay que preguntar y `decidir(respuestas)` elige cada título."""

    def __init__(self, nucleos: list, pred: list, postura: list, propia, cfg: dict):
        self.cfg = cfg
        self.base = titulos_por_nucleos(nucleos, pred, postura, propia, cfg["n10_frases"])
        self.al_modelo = [n for n in sorted(self.base) if self.base[n][1]]
        self.universo = {}
        for n, p, nucleo in zip(pred, postura, nucleos):
            if n and p == "apoya":
                self.universo.setdefault(n, set()).update((nucleo or "").split())

    def pedidos(self) -> list:
        return [Pedido(armar_pedido(self.base[n][1], self.cfg["n10_max_palabras_pedido"]), SISTEMA,
                       self.cfg["n10_max_tokens"], self.cfg["n10_esfuerzo"]) for n in self.al_modelo]

    def decidir(self, respuestas: list = None, uso: dict = None):
        """{narrativa: (título, [frases clave])} y el detalle. Sin respuestas (sin modelo), los de los núcleos."""
        titulos = dict(self.base)
        detalle = {n: {"titulo_base": t, "titulo": t, "al_modelo": False} for n, (t, _) in self.base.items()}
        for n, r in zip(self.al_modelo, respuestas or []):
            titulo_base, frases = self.base[n]
            d = detalle[n]
            d["al_modelo"] = True
            if isinstance(r, ErrorModelo):
                d["motivo"] = f"error del modelo: {r}"
                continue
            if uso is not None:
                uso["llamadas"] += 1
                uso["tokens"] += r.tokens
                uso["usd"] += r.usd
            titulo = limpiar(r.texto)
            motivo = None
            if r.cortada:
                motivo = "la respuesta se cortó"
            elif not titulo:
                motivo = "el modelo no devolvió un título"
            elif len(titulo.split()) > int(self.cfg["n10_max_palabras_aceptado"]):
                motivo = f"el título tiene {len(titulo.split())} palabras"
            if motivo is None:
                fuera = fuera_del_universo(palabras_de_contenido(titulo), self.universo.get(n, set()))
                if fuera:
                    motivo = f"el título agrega palabras que no están en los núcleos: {', '.join(fuera)}"
            if motivo:
                titulo = titulo_base
            d.update({"titulo": titulo, "motivo": motivo, "desde_cache": r.desde_cache})
            titulos[n] = (titulo, frases)
        return titulos, detalle
