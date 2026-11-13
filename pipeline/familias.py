"""N1 · Familias: junta núcleos casi iguales (por ejemplo, por errores de tipeo).

**Congelado en 0,7 (decisión 1, EXP-004):** parecido coseno por pedazos de 3 y 4 letras (TF-IDF); dos
núcleos se unen si el parecido es de 0,7 o más y si tienen largo parecido (el más corto mide al menos el
75 % del más largo), para que una reacción suelta no se una a una afirmación que empieza igual. Las
familias son los componentes conexos de esas uniones.

En la práctica dio 882 familias y ninguna mezclaba narrativas. Con 0,6 se pierden 1,34 puntos de
agrupamiento y con 0,5 todo queda en una sola narrativa; con 0,8 se pierden 0,13.
"""
import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import connected_components
from sklearn.feature_extraction.text import TfidfVectorizer

UMBRAL_MINIMO = 0.5  # las aristas se calculan desde 0,5; las familias usan el umbral de la configuración
RAZON_LARGO = 0.75
BLOQUE = 1000


def aristas_similitud(nucleos: list, umbral_min: float = UMBRAL_MINIMO, bloque: int = BLOQUE,
                      razon_largo: float = RAZON_LARGO):
    """Pares de núcleos (i < j) con parecido >= umbral_min y largo parecido: (filas, columnas, parecido)."""
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 4), min_df=2, max_df=0.2, sublinear_tf=True,
                          dtype=np.float32)
    X = vec.fit_transform(nucleos)
    Xt = X.T.tocsr()
    largo = np.array([len(t) for t in nucleos])
    fi, co, si = [], [], []
    for i in range(0, X.shape[0], bloque):
        S = (X[i:i + bloque] @ Xt).tocoo()
        f, c = S.row + i, S.col
        m = (S.data >= umbral_min) & (f < c)
        m &= np.minimum(largo[f], largo[c]) >= razon_largo * np.maximum(largo[f], largo[c])
        fi.append(f[m])
        co.append(c[m])
        si.append(S.data[m])
    return np.concatenate(fi), np.concatenate(co), np.concatenate(si)


def familias_de_nucleos(nucleos: list, umbral: float):
    """La familia de cada núcleo y un aviso (o None).

    Salvaguarda: con muy pocos núcleos, TF-IDF puede no tener ningún pedazo de letras que cumpla min_df=2 y
    max_df=0,2 y corta con un ValueError. En ese caso N1 no une nada: cada núcleo queda en su familia.
    """
    try:
        fi, co, si = aristas_similitud(nucleos)
        aviso = None
    except ValueError as error:
        fi = co = np.array([], dtype=np.int32)
        si = np.array([], dtype=np.float32)
        aviso = f"N1 no pudo comparar los núcleos ({error}); cada núcleo queda en su propia familia"
    n = len(nucleos)
    m = si >= umbral
    adyacencia = sp.coo_matrix((np.ones(int(m.sum()), dtype=np.int8), (fi[m], co[m])), shape=(n, n))
    return connected_components(adyacencia, directed=False)[1], aviso
