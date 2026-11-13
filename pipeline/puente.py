"""N3 (familias ancladas), N4 (puente con Louvain), N5 (ruido por estructura) y N7 (dos lados).

Es el corazón de la arquitectura A: las narrativas y sus dos lados se arman **por estructura**, con las
respuestas entre familias, y nunca por significado (agrupar por estructura dio 0,997 de B-cubed contra
0,116 por significado, EXP-007).

- **N3 (congelado):** una familia entra al puente solo si participa de la conversación: los enlaces de
  respuesta con contenido en los que participa son el 2 % o más de sus comentarios y son 2 o más. Sin esto,
  un texto genérico que aparece una vez como respuesta arrastra a todas sus copias (EXP-004; el 2 % sale de
  EXP-010, opción "n3-002").
- **N4:** el grafo une familias ancladas que se responden, con peso igual a la cantidad de respuestas, y
  Louvain (semilla 42) lo corta en comunidades: cada comunidad es una narrativa. Con la mitad de las
  respuestas ocultas, Louvain mantuvo 13 narrativas y los componentes conexos colapsaron a una (EXP-007).
  El freno que volvía a componentes conexos se descartó (EXP-010).
- **N7:** una respuesta con contenido va al lado contrario de su padre y un acompañamiento (N2), al mismo
  lado. En la práctica, el 99,8 % de 22.504 respuestas con contenido contradice a su padre.
- **N5:** lo que, después del puente y de la herencia por respuestas, no quedó en ninguna narrativa es ruido.
"""
from collections import Counter

import networkx as nx
import numpy as np


def familias_ancladas(conv, fam_raiz: np.ndarray, n_fam: int, min_implicacion: float, min_enlaces: int):
    """N3: por familia, si está anclada. Devuelve (anclada, tamaño de cada familia, hijos, familia del hijo,
    familia del padre) para las respuestas con contenido."""
    tam = np.bincount(fam_raiz, minlength=n_fam)
    hijos = np.where(conv.contenido)[0]
    a, b = fam_raiz[hijos], fam_raiz[conv.padre[hijos]]
    implicacion = np.zeros(n_fam)
    np.add.at(implicacion, a, 1)
    np.add.at(implicacion, b, 1)
    anclada = (implicacion / np.maximum(tam, 1) >= min_implicacion) & (implicacion >= min_enlaces)
    return anclada, tam, hijos, a, b, implicacion


def grafo_del_puente(a: np.ndarray, b: np.ndarray, anclada: np.ndarray, min_arista: int) -> nx.Graph:
    """N4: el grafo de familias ancladas que se responden, con peso igual a la cantidad de respuestas.

    Las aristas entran en el orden en que aparece cada par por primera vez (en el orden de los comentarios):
    Louvain y los lados dependen de ese orden, y así es reproducible.
    """
    pares = Counter(zip(np.minimum(a, b).tolist(), np.maximum(a, b).tolist()))
    g = nx.Graph()
    for (x, y), w in pares.items():
        if x != y and w >= min_arista and anclada[x] and anclada[y]:
            g.add_edge(x, y, weight=w)
    return g


def comunidades(g: nx.Graph, tam: np.ndarray, semilla: int) -> list:
    """N4: las comunidades de Louvain, de la más grande a la más chica (en comentarios)."""
    partes = nx.community.louvain_communities(g, weight="weight", seed=semilla)
    partes.sort(key=lambda c: -sum(tam[f] for f in c))
    return partes


def dos_lados(g: nx.Graph, tam: np.ndarray) -> dict:
    """N7: el lado (1 o -1) de cada familia del puente. Las familias unidas por respuestas con contenido
    quedan en lados opuestos: se arranca por la familia más grande de cada componente y se vota."""
    color = {}
    for componente in nx.connected_components(g):
        inicio = max(componente, key=lambda f: tam[f])
        color[inicio] = 1
        for _, f in nx.bfs_edges(g, inicio):
            voto = sum(d["weight"] * color[v] for v, d in g[f].items() if v in color)
            color[f] = -1 if voto >= 0 else 1
        for _ in range(5):
            for f in componente:
                voto = sum(d["weight"] * color[v] for v, d in g[f].items())
                if voto != 0:
                    color[f] = -1 if voto > 0 else 1
    return color


def heredar(conv, pred: list, signo: np.ndarray, propia: np.ndarray):
    """N2 y N7: cada respuesta hereda la narrativa de su padre, con el mismo lado si acompaña y el contrario
    si tiene contenido. Se recorre por hora (los sin hora, al final), así las cadenas se propagan.
    Devuelve (comentarios sin narrativa propia que heredan, comentarios propios que cambian de narrativa)."""
    sin_propia = cambian = 0
    orden = np.argsort(conv.t, kind="stable")
    padre = conv.padre.tolist()
    acompana = conv.acomp[conv.nuc].tolist()
    for i in orden[conv.padre[orden] >= 0].tolist():
        p = padre[i]
        if pred[p]:
            sin_propia += not propia[i]
            cambian += bool(propia[i]) and pred[i] != pred[p]
            pred[i] = pred[p]
            signo[i] = signo[p] if acompana[i] else -signo[p]
    return sin_propia, cambian


def armar_narrativas(conv, familia: np.ndarray, cfg: dict, info: dict):
    """N3, N4, N5 y N7. Devuelve (narrativa por comentario, lado por comentario, si la narrativa es propia).

    La narrativa vacía ("") es ruido (N5). "Propia" quiere decir que sale de la familia del comentario y no
    de la herencia por respuesta.
    """
    fam_raiz = familia[conv.nuc[conv.raiz]]
    n_fam = int(familia.max()) + 1 if len(familia) else 0
    anclada, tam, hijos, a, b, implicacion = familias_ancladas(
        conv, fam_raiz, n_fam, cfg["n3_min_implicacion"], cfg["n3_min_enlaces"])
    g = grafo_del_puente(a, b, anclada, cfg["n4_min_arista"])
    info.update({"familias": n_fam, "familias_con_comentarios": int((tam > 0).sum()),
                 "respuestas_con_contenido": int(len(hijos)), "familias_con_algun_enlace": int((implicacion > 0).sum()),
                 "familias_ancladas": int(anclada.sum()), "aristas_del_puente": g.number_of_edges(),
                 "familias_en_el_puente": g.number_of_nodes()})
    n = len(conv.ids)
    if g.number_of_edges() == 0:
        info.update({"comunidades": 0, "comentarios_propios": 0, "heredados_sin_narrativa_propia": 0,
                     "heredados_que_cambian_de_narrativa": 0})
        return [""] * n, np.zeros(n, dtype=int), np.zeros(n, dtype=bool)
    partes = comunidades(g, tam, cfg["n4_semilla"])
    etiqueta = {f: f"n{k:02d}" for k, parte in enumerate(partes) for f in parte}
    color = dos_lados(g, tam)
    pred = [etiqueta.get(f, "") for f in fam_raiz.tolist()]
    signo = np.array([color.get(f, 0) for f in fam_raiz.tolist()])
    propia = np.array([p != "" for p in pred])
    sin_propia, cambian = heredar(conv, pred, signo, propia)
    info.update({"comunidades": len(partes), "comentarios_propios": int(propia.sum()),
                 "heredados_sin_narrativa_propia": int(sin_propia), "heredados_que_cambian_de_narrativa": int(cambian)})
    return pred, signo, propia
