"""N8 · Lado que apoya: en cada narrativa ya partida en dos lados (N7), decide cuál apoya la afirmación.

**Opción (a) de EXP-011, "tope" más modelo.** "Tope" es el lado con más comentarios de primer nivel (los
que no responden a nadie): en una discusión, la afirmación se publica y la refutación responde. Cuando
"tope" tiene margen chico (z = |a - b| / raíz(a + b) < 2), se le pregunta al modelo qué lado afirma, con
los 10 núcleos más frecuentes de cada lado, **en los dos órdenes** (A y B, después B y A). Solo si las dos
respuestas coinciden decide el modelo; si no, o si el modelo falla, queda "tope".

Sin modelo (`--sin-modelo`), N8 es "tope" en todas las narrativas.

Límite con la capa interpretativa (decisión 16): las funciones comunicativas no deciden el lado que apoya.
"""
import math
import re
import unicodedata
from collections import Counter, defaultdict

from pipeline.modelo import ErrorModelo, Pedido

SISTEMA = "Leés comentarios de redes sociales en cualquier idioma y respondés solo con el formato que se te pide."
RESPUESTA = re.compile(r"AFIRMA\s*:\s*\**\s*([AB])\b", re.IGNORECASE)
ENLACE = re.compile(r"(?:https?://|www\.)\S+")
MENCION = re.compile(r"@\w+")


def texto_unicode(texto: str) -> str:
    """El texto original en minúsculas, sin marcas diacríticas, enlaces ni menciones. Conserva cualquier alfabeto."""
    t = MENCION.sub(" ", ENLACE.sub(" ", texto or ""))
    t = unicodedata.normalize("NFD", t.casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", t)


def tope_y_conteos(conv, pred: list, signo):
    """"Tope" por narrativa y los comentarios de primer nivel de cada lado: ({n: lado}, {n: {1: a, -1: b}})."""
    primer_nivel = (conv.padre < 0).tolist()
    suma, conteo = {}, defaultdict(lambda: {1: 0, -1: 0})
    for i, (n, s) in enumerate(zip(pred, signo.tolist())):
        if n and s != 0:
            suma.setdefault(n, 0)
            if primer_nivel[i]:
                suma[n] += s
                conteo[n][s] += 1
    tope = {n: 1 if total >= 0 else -1 for n, total in suma.items()}
    return tope, conteo


def z_tope(a: int, b: int) -> float:
    """Prueba binomial (aproximación normal) de que los dos lados tienen la misma cantidad de primer nivel."""
    return abs(a - b) / math.sqrt(a + b) if a + b > 0 else 0.0


def textos_del_lado(idx: list, lado: int, signo: list, padre: list, nucleos: list, textos: list, cfg: dict) -> list:
    """Los núcleos más frecuentes del lado entre sus comentarios de primer nivel (o entre todos, si no tiene),
    cada uno con su texto original más frecuente. Un núcleo vacío se reemplaza por el texto sin tildes.
    `idx` son los comentarios de la narrativa; las demás listas van por comentario."""
    elegidos = ([i for i in idx if signo[i] == lado and padre[i] < 0]
                or [i for i in idx if signo[i] == lado])
    claves, originales = Counter(), defaultdict(Counter)
    for i in elegidos:
        original = " ".join((textos[i] or "").split())
        clave = nucleos[i] or texto_unicode(original).strip() or original
        claves[clave] += 1
        originales[clave][original] += 1
    mejores = sorted(claves.items(), key=lambda x: (-x[1], x[0]))[:cfg["n8_nucleos_por_lado"]]
    return [sorted(originales[c].items(), key=lambda x: (-x[1], x[0]))[0][0][:cfg["n8_max_caracteres"]]
            for c, _ in mejores]


def armar_pedido(textos_a: list, textos_b: list) -> str:
    lineas = ["Los comentarios de abajo son de una misma discusión en redes sociales y están separados en dos grupos. "
              "Un grupo afirma una idea (una denuncia, un reclamo, una propuesta o una advertencia) y el otro grupo la "
              "rechaza: la desmiente, la discute o dice que es falsa. Los comentarios pueden estar en cualquier idioma "
              "y están ordenados del más repetido al menos repetido.", "", "Grupo A:"]
    lineas += [f"- {t}" for t in textos_a]
    lineas += ["", "Grupo B:"]
    lineas += [f"- {t}" for t in textos_b]
    lineas += ["", "¿Qué grupo afirma la idea? Respondé con una sola línea: AFIRMA: A o AFIRMA: B"]
    return "\n".join(lineas)


def leer_respuesta(texto: str):
    hallados = RESPUESTA.findall(texto or "")
    return hallados[-1].upper() if hallados else None


class LadoQueApoya:
    """N8 en dos pasos, para que los pedidos al modelo vayan en paralelo con otras etapas:
    `pedidos()` arma lo que hay que preguntar y `decidir(respuestas)` aplica las respuestas."""

    def __init__(self, conv, pred: list, signo, cfg: dict):
        self.conv, self.pred, self.signo, self.cfg = conv, pred, signo, cfg
        self.tope, self.conteo = tope_y_conteos(conv, pred, signo)
        self.dudosas = [n for n in sorted(self.tope)
                        if z_tope(self.conteo[n][1], self.conteo[n][-1]) < cfg["n8_z_tope"]]
        self._ordenes = []  # (narrativa, primero, segundo), uno por pedido

    def pedidos(self) -> list:
        """Dos pedidos por narrativa de margen chico: A y B en un orden y en el otro."""
        pedidos = []
        if not self.dudosas:
            return pedidos
        signo, padre = self.signo.tolist(), self.conv.padre.tolist()
        nucleos, textos = self.conv.com["nucleo"].to_list(), self.conv.com["texto"].to_list()
        indices = defaultdict(list)
        for i, n in enumerate(self.pred):
            if n:
                indices[n].append(i)
        for n in self.dudosas:
            grupos = {s: textos_del_lado(indices[n], s, signo, padre, nucleos, textos, self.cfg) for s in (1, -1)}
            for primero, segundo in ((1, -1), (-1, 1)):
                self._ordenes.append((n, primero, segundo))
                pedidos.append(Pedido(armar_pedido(grupos[primero], grupos[segundo]), SISTEMA,
                                      self.cfg["n8_max_tokens"], self.cfg["n8_esfuerzo"]))
        return pedidos

    def decidir(self, respuestas: list = None, uso: dict = None):
        """El lado que apoya de cada narrativa y el detalle. Sin respuestas (sin modelo), "tope" en todas.

        `respuestas` va en el orden de `pedidos()`; cada una es una Respuesta o un ErrorModelo. Lo que usó el
        modelo se suma a `uso` (tokens y USD) en ese mismo orden.
        """
        votos = defaultdict(list)
        detalle_modelo = defaultdict(list)
        for (n, primero, segundo), r in zip(self._ordenes, respuestas or []):
            if isinstance(r, ErrorModelo):
                votos[n].append(None)
                detalle_modelo[n].append({"orden": [primero, segundo], "error": str(r)})
                continue
            if uso is not None:
                uso["llamadas"] += 1
                uso["tokens"] += r.tokens
                uso["usd"] += r.usd
            letra = None if r.cortada else leer_respuesta(r.texto)
            voto = {"A": primero, "B": segundo}.get(letra)
            votos[n].append(voto)
            detalle_modelo[n].append({"orden": [primero, segundo], "letra": letra, "lado": voto,
                                      "desde_cache": r.desde_cache, "cortada": r.cortada})
        lado, detalle = {}, {}
        for n in sorted(self.tope):
            a, b = self.conteo[n][1], self.conteo[n][-1]
            d = {"primer_nivel_lado_1": a, "primer_nivel_lado_menos_1": b, "z_tope": round(z_tope(a, b), 3),
                 "tope": self.tope[n], "al_modelo": n in self.dudosas and respuestas is not None}
            lado[n] = self.tope[n]
            if d["al_modelo"]:
                v = votos[n]
                consistente = len(v) == 2 and v[0] is not None and v[0] == v[1]
                if consistente:
                    lado[n] = v[0]
                d.update({"respuestas": detalle_modelo[n], "consistente": consistente,
                          "decide": "modelo" if consistente else "tope (el modelo no fue consistente)"})
            else:
                d["decide"] = "tope"
            d.update({"lado_que_apoya": lado[n], "cambia_respecto_de_tope": lado[n] != self.tope[n]})
            detalle[n] = d
        return lado, detalle
