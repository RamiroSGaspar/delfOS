"""N2 · Acompañamientos, sobre la estructura de la conversación.

`Conversacion` arma, una sola vez, las tablas en memoria que usan todas las etapas del motor: los
comentarios ordenados por hora, el padre de cada uno (si responde a otro), su núcleo y su raíz.

**N2 (congelado, EXP-004):** un núcleo es acompañamiento ("tal cual", "exacto") si tiene 4 palabras o menos
y aparece como respuesta en la mitad o más de sus apariciones. Un acompañamiento hereda la narrativa y el
lado del comentario al que responde: para encontrarlo se sube por la cadena de respuestas saltando
acompañamientos, hasta 50 pasos. La regla no depende del idioma: usa largo y posición, no palabras.
"""
from collections import Counter

import numpy as np
import polars as pl


class Conversacion:
    """Los comentarios y su estructura, en el orden de la tabla preparada (por hora y por id).

    - `ids`, `pos`: el id de cada comentario y la posición de cada id.
    - `t`: la hora en segundos desde 1970 (NaN si no tiene).
    - `padre`: la posición del comentario al que responde, o -1.
    - `nucleos`: los núcleos distintos, ordenados; `nuc`: el índice del núcleo de cada comentario.
    - `acomp`: por núcleo, si es acompañamiento (N2).
    - `raiz`: por comentario, de quién hereda (él mismo si no es acompañamiento).
    - `contenido`: por comentario, si es una respuesta con contenido (no es acompañamiento).
    - `offset_s`: la zona horaria dominante del set (P1), para escribir fechas ISO con zona.
    """

    def __init__(self, com: pl.DataFrame, max_palabras: int = 4, min_respuesta: float = 0.5, max_pasos: int = 50,
                 offset_s: int = -3 * 3600):
        self.com = com
        self.offset_s = offset_s
        self.max_pasos = max_pasos
        self.ids = com["comentario_id"].to_list()
        self.pos = {c: i for i, c in enumerate(self.ids)}
        self.t = com["t"].cast(pl.Float64).fill_null(float("nan")).to_numpy()
        self.padre = np.array([self.pos.get(r, -1) if r else -1 for r in com["respuesta_a"].to_list()],
                              dtype=np.int64)
        nucleo_de = com["nucleo"].to_list()
        cuenta = Counter(nucleo_de)
        self.nucleos = sorted(cuenta)
        self.idx_nucleo = {t: i for i, t in enumerate(self.nucleos)}
        self.nuc = np.array([self.idx_nucleo[t] for t in nucleo_de], dtype=np.int64)
        self.n_com = np.array([cuenta[t] for t in self.nucleos])
        resp = np.zeros(len(self.nucleos), dtype=np.int64)
        np.add.at(resp, self.nuc[self.padre >= 0], 1)
        self.largo = np.array([len(t.split()) for t in self.nucleos])
        # Acompañamiento: núcleo corto que aparece sobre todo como respuesta. Hereda de su padre.
        self.acomp = (self.largo <= max_palabras) & (resp / np.maximum(self.n_com, 1) >= min_respuesta)
        self.raiz = self._raices()
        self.contenido = (self.padre >= 0) & ~self.acomp[self.nuc]  # respuestas que no son acompañamiento

    def _raices(self) -> np.ndarray:
        """Por comentario, el primer antecesor que no es acompañamiento (hasta `max_pasos` pasos)."""
        raiz = np.arange(len(self.ids))
        padre = self.padre.tolist()
        es_acomp = self.acomp[self.nuc].tolist()
        for i in np.flatnonzero((self.padre >= 0) & self.acomp[self.nuc]).tolist():
            j, pasos = i, 0
            while padre[j] >= 0 and es_acomp[j] and pasos < self.max_pasos:
                j, pasos = padre[j], pasos + 1
            raiz[i] = j
        return raiz
