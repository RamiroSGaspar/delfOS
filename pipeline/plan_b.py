"""N12 · Plan B con el modelo, sobre lo que el puente dejó como ruido (EXP-016, decisión 18).

Qué hace: de las familias que el puente dejó como ruido, le pregunta al modelo a qué narrativa existente
pertenece cada una (o si es una narrativa nueva, o si es ruido), y agrega los comentarios de esas familias a
la narrativa que toca. Se engancha entre N5 (ruido) y N8 (lado que apoya), con el lado que apoya del puente.

1. **Familias candidatas, sin modelo:** las familias con comentarios sin narrativa que tienen al menos 50
   comentarios y 3 cuentas distintas (M y K, fijados antes de correr en EXP-016).
2. **El modelo, en lotes de hasta 40 familias por pedido.** Por familia recibe su núcleo más frecuente y
   hasta 3 variantes, y la lista de narrativas existentes con su título y 3 núcleos de ejemplo. Responde con
   JSON validado: `afirma` (una narrativa existente), `refuta` (ídem), `nueva` (con un id de grupo y la
   afirmación) o `ruido`.
3. **Aplicar:** `afirma` agrega la familia a esa narrativa del lado que apoya; `refuta`, del lado que
   rechaza; `nueva` crea narrativas nuevas (`x01`, `x02`...) con todas sus familias del lado que apoya;
   `ruido` no cambia nada.
4. **Regla de oro:** N12 nunca cambia la narrativa ni el lado de un comentario que el puente ya asignó:
   solo agrega comentarios que estaban como ruido.
5. **Si el modelo falla o responde algo inválido,** esas familias quedan como ruido. Sin modelo
   (`--sin-modelo`), N12 está apagado y la salida es la misma que con el modelo caído.
"""
import json
import re
from collections import Counter, defaultdict

from pipeline.modelo import ErrorModelo, Pedido
from pipeline.titulos import titulos_por_nucleos

SISTEMA = ("Leés comentarios de redes sociales en cualquier idioma y decidís a qué afirmación de la "
           "discusión pertenece cada grupo de comentarios repetidos. Respondés solo con un objeto JSON.")

PEDIDO = """Hay una conversación en redes sociales. Ya se armaron {n_narrativas} narrativas: cada una es una
afirmación que la gente de la conversación sostiene (la apoya) o rechaza (la desmiente). Un mismo grupo de
comentarios repetidos puede tener gente de los dos lados.

Quedaron comentarios que no se pudieron ubicar porque no hubo respuestas suficientes para saber de qué
narrativa hablan. Para cada grupo que te paso, decidí una sola cosa:

- "afirma": el grupo dice la misma afirmación que una de las narrativas existentes. Poné el id de esa narrativa.
- "refuta": el grupo contradice o desmiente una de las narrativas existentes. Poné el id de esa narrativa.
- "nueva": el grupo afirma algo que no está en ninguna narrativa existente y que es una afirmación (una
  denuncia, un reclamo, una propuesta o una advertencia). Si dos o más grupos dicen lo mismo, ponéles el
  mismo "grupo" y escribí la afirmación una sola vez, en el idioma de los comentarios, en una sola oración.
- "ruido": el grupo no afirma nada sobre los temas de la discusión: saludos, agradecimientos, preguntas,
  frases de cortesía, reacciones, emojis o comentarios sin contenido. Si dudás entre "ruido" y otra cosa,
  elegí "ruido".

Reglas:
- No inventes: usá "nueva" solo si el grupo afirma claramente algo.
- Cada grupo va a una sola narrativa existente, o a "nueva", o a "ruido".
- No hace falta que dos grupos distintos tengan la misma respuesta.

NARRATIVAS EXISTENTES:
{lineas_narrativas}

GRUPOS:
{lineas_grupos}

Respondé con un solo objeto JSON, sin texto antes ni después, con esta forma:
{{"decisiones": [{{"familia": "F01", "decision": "afirma", "narrativa": "n01"}}, {{"familia": "F02", "decision": "ruido"}}, {{"familia": "F03", "decision": "nueva", "grupo": "G1", "afirmacion": "La empresa ..."}}]}}"""

DECISIONES = {"afirma": "afirma", "affirms": "afirma", "afirma_narrativa": "afirma",
              "refuta": "refuta", "refutes": "refuta", "contradice": "refuta", "refuta_narrativa": "refuta",
              "nueva": "nueva", "new": "nueva", "nueva_narrativa": "nueva",
              "ruido": "ruido", "noise": "ruido", "ninguna": "ruido", "narrativa_nueva": "nueva"}


# ----------------------------------------------------------------------------- el pedido
def limpiar(texto: str, limite: int) -> str:
    """Un texto del pedido en una sola línea, recortado."""
    return " ".join((texto or "").split())[:limite]


def narrativas_existentes(nucleos: list, pred: list, postura: list, propia) -> list:
    """Las narrativas del puente, con su título por núcleos (N10 sin modelo) y hasta 3 núcleos de ejemplo
    (los más frecuentes de la narrativa, de cualquier lado, distintos del título)."""
    por_narr = defaultdict(Counter)
    for nucleo, n, es_propia in zip(nucleos, pred, propia):
        if n and es_propia:
            por_narr[n][nucleo] += 1
    titulos = titulos_por_nucleos(nucleos, pred, postura, propia, 5)
    salida = []
    for n in sorted(set(pred) - {""}):
        titulo, _ = titulos.get(n, (n, []))
        ejemplos = [t for t, _ in sorted(por_narr[n].items(), key=lambda x: (-x[1], x[0])) if t != titulo][:3]
        salida.append({"id": n, "titulo": titulo, "ejemplos": ejemplos})
    return salida


def grupos_candidatos(familia_de: list, pred: list, cuentas: list, nucleos: list, textos: list,
                      min_comentarios: int, min_cuentas: int) -> list:
    """Las familias con comentarios sin narrativa que son grandes: M comentarios y K cuentas distintas.
    Ordenadas de la más grande a la más chica; a igual tamaño, por id."""
    indices = defaultdict(list)
    for i, f in enumerate(familia_de):
        indices[f].append(i)
    salida = []
    for f, idx in indices.items():
        if len(idx) < min_comentarios or all(pred[i] for i in idx):
            continue
        n_cuentas = len({cuentas[i] for i in idx if cuentas[i]})
        if n_cuentas < min_cuentas:
            continue
        conteo = Counter(nucleos[i] for i in idx)
        mejores = sorted(conteo.items(), key=lambda x: (-x[1], x[0]))
        variantes = []
        for nuc, _ in mejores[:3]:
            originales = Counter(textos[i] for i in idx if nucleos[i] == nuc)
            variantes.append(sorted(originales.items(), key=lambda x: (-x[1], x[0]))[0][0])
        salida.append({"familia": f, "comentarios": len(idx), "cuentas": n_cuentas,
                       "comentarios_sin_narrativa": sum(1 for i in idx if not pred[i]),
                       "nucleo": mejores[0][0], "variantes": variantes})
    salida.sort(key=lambda d: (-d["comentarios"], d["familia"]))
    return salida


def armar_pedido(narrativas: list, grupos: list, limite: int) -> str:
    lineas_narrativas = []
    for n in narrativas:
        ejemplos = ", ".join(f'"{limpiar(e, limite)}"' for e in n["ejemplos"]) or "(sin ejemplos)"
        lineas_narrativas.append(f'{n["id"]} | titulo: "{limpiar(n["titulo"], limite)}" | ejemplos: {ejemplos}')
    lineas_grupos = []
    for g in grupos:
        variantes = ", ".join(f'"{limpiar(v, limite)}"' for v in g["variantes"]) or "(sin variantes)"
        lineas_grupos.append(f'F{g["familia"]:03d} | {g["comentarios"]} comentarios | {g["cuentas"]} cuentas | '
                             f'nucleo: "{limpiar(g["nucleo"], limite)}" | variantes: {variantes}')
    return PEDIDO.format(n_narrativas=len(narrativas), lineas_narrativas="\n".join(lineas_narrativas),
                         lineas_grupos="\n".join(lineas_grupos))


# ----------------------------------------------------------------------------- la respuesta
def extraer_json(texto: str):
    """El objeto JSON de la respuesta, si lo hay; None si no se puede leer."""
    t = (texto or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t).strip()
    if not t:
        return None
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    for abre, cierra in (("{", "}"), ("[", "]")):  # un objeto (o una lista) dentro de texto
        i, j = t.find(abre), t.rfind(cierra)
        if i >= 0 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except json.JSONDecodeError:
                pass
    return None


def leer_decisiones(respuesta: str, grupos: list, narrativas: list) -> tuple:
    """Las decisiones del modelo, validadas: (decisiones, inválidas). Una inválida deja su familia como ruido."""
    datos = extraer_json(respuesta)
    if datos is None:
        return [], [{"familia": g["familia"], "motivo": "la respuesta no es JSON"} for g in grupos]
    if isinstance(datos, list):
        lista = datos
    elif isinstance(datos, dict):
        lista = next((datos[k] for k in ("decisiones", "decisions", "grupos", "familias") if k in datos), None)
        if lista is None and all(isinstance(v, dict) for v in datos.values()):
            lista = list(datos.values())
    else:
        lista = None
    if not isinstance(lista, list):
        return [], [{"familia": g["familia"], "motivo": "la respuesta no trae la lista de decisiones"} for g in grupos]
    ids_familia = {g["familia"] for g in grupos}
    ids_narrativa = {n["id"] for n in narrativas}
    decisiones, invalidas, vistas = [], [], set()
    for item in lista:
        if not isinstance(item, dict):
            invalidas.append({"familia": None, "motivo": "una decisión no es un objeto"})
            continue
        familia = item.get("familia", item.get("familia_id", item.get("id")))
        if isinstance(familia, str) and familia.upper().startswith("F"):
            try:
                familia = int(familia[1:])
            except ValueError:
                pass
        if not isinstance(familia, int) or familia not in ids_familia:
            invalidas.append({"familia": familia, "motivo": "la familia no está en el lote"})
            continue
        if familia in vistas:
            invalidas.append({"familia": familia, "motivo": "la familia tiene dos decisiones"})
            continue
        vistas.add(familia)
        cruda = str(item.get("decision", item.get("decisión", item.get("tipo", "")))).strip().lower()
        decision = DECISIONES.get(cruda)
        if decision is None:
            invalidas.append({"familia": familia, "motivo": f"decisión desconocida: {cruda!r}"})
            continue
        if decision in ("afirma", "refuta"):
            narrativa = item.get("narrativa", item.get("narrativa_id", item.get("id_narrativa")))
            narrativa = str(narrativa).strip() if narrativa is not None else ""
            if narrativa not in ids_narrativa:
                invalidas.append({"familia": familia, "motivo": f"narrativa inexistente: {narrativa!r}"})
                continue
            decisiones.append({"familia": familia, "decision": decision, "narrativa": narrativa})
        elif decision == "nueva":
            grupo = item.get("grupo", item.get("grupo_id", item.get("id_grupo")))
            grupo = str(grupo).strip() if grupo is not None else ""
            if not grupo:
                invalidas.append({"familia": familia, "motivo": "la decisión nueva no trae id de grupo"})
                continue
            afirmacion = str(item.get("afirmacion", item.get("afirmación", item.get("afirmacion_grupo", ""))) or "")
            decisiones.append({"familia": familia, "decision": "nueva", "grupo": grupo,
                               "afirmacion": " ".join(afirmacion.split())})
        else:
            decisiones.append({"familia": familia, "decision": "ruido"})
    for g in grupos:
        if g["familia"] not in vistas:
            invalidas.append({"familia": g["familia"], "motivo": "la familia no tiene decisión"})
    return decisiones, invalidas


# ----------------------------------------------------------------------------- N12 en dos pasos
class PlanB:
    """`pedidos()` arma los lotes y `aplicar(respuestas)` agrega los comentarios que corresponden.
    Así los pedidos al modelo van en paralelo entre sí y con otras etapas."""

    def __init__(self, conv, familia, pred: list, signo, propia, lado_apoya: dict, cfg: dict):
        self.conv, self.pred, self.signo, self.propia = conv, pred, signo, propia
        self.lado_apoya, self.cfg = lado_apoya, cfg
        self.familia_de = familia[conv.nuc[conv.raiz]].tolist()
        com = conv.com
        self.grupos = grupos_candidatos(self.familia_de, pred, com["cuenta_id"].to_list(), com["nucleo"].to_list(),
                                        com["texto"].to_list(), cfg["n12_min_comentarios"], cfg["n12_min_cuentas"])
        self.lotes = [self.grupos[i:i + cfg["n12_lote"]] for i in range(0, len(self.grupos), cfg["n12_lote"])]
        self.narrativas = []
        if self.grupos:
            postura = [("apoya" if s == lado_apoya.get(n, 1) else "rechaza") if n else ""
                       for n, s in zip(pred, signo.tolist())]
            self.narrativas = narrativas_existentes(com["nucleo"].to_list(), pred, postura, propia)

    def pedidos(self) -> list:
        return [Pedido(armar_pedido(self.narrativas, lote, self.cfg["n12_max_caracteres"]), SISTEMA,
                       self.cfg["n12_max_tokens"], self.cfg["n12_esfuerzo"]) for lote in self.lotes]

    def aplicar(self, respuestas: list, uso: dict) -> dict:
        """Agrega los comentarios de ruido a las narrativas que decidió el modelo (modifica pred, signo y
        propia en el lugar) y devuelve las notas. `respuestas` va en el orden de `pedidos()`."""
        notas = {"familias_candidatas": len(self.grupos), "llamadas": 0, "lotes": [],
                 "conteo": {"afirma": 0, "refuta": 0, "nueva": 0, "ruido": 0, "invalidas": 0},
                 "narrativas_nuevas": {}, "comentarios_agregados": 0, "familias_con_comentarios_agregados": 0}
        decisiones = {}
        for lote, r in zip(self.lotes, respuestas):
            info = {"familias": [g["familia"] for g in lote], "errores": [], "cortada": False}
            validas, invalidas = [], []
            if isinstance(r, ErrorModelo):
                info["errores"].append(f"error del modelo: {r}")
            else:
                uso["llamadas"] += 1
                uso["tokens"] += r.tokens
                uso["usd"] += r.usd
                notas["llamadas"] += 1
                info.update({"desde_cache": r.desde_cache, "cortada": r.cortada})
                if r.cortada:
                    info["errores"].append("la respuesta se cortó")
                else:
                    validas, invalidas = leer_decisiones(r.texto, lote, self.narrativas)
            notas["lotes"].append(info)
            notas["conteo"]["invalidas"] += len(invalidas)
            for inv in invalidas:
                decisiones[str(inv["familia"])] = {"decision": "ruido", "motivo": inv["motivo"]}
            for d in validas:
                decisiones[str(d["familia"])] = {k: v for k, v in d.items() if k != "familia"}
                notas["conteo"][d["decision"]] += 1

        ruido_inicial = [not n for n in self.pred]
        indices = defaultdict(list)
        for i, f in enumerate(self.familia_de):
            indices[f].append(i)
        ids_existentes = {n["id"] for n in self.narrativas}
        nuevas = {}
        for g in self.grupos:
            f = g["familia"]
            d = decisiones.get(str(f), {"decision": "ruido"})
            destino, lado, nueva = None, 0, None
            if d.get("decision") == "afirma" and d.get("narrativa") in ids_existentes:
                destino, lado = d["narrativa"], self.lado_apoya.get(d["narrativa"], 1)
            elif d.get("decision") == "refuta" and d.get("narrativa") in ids_existentes:
                destino, lado = d["narrativa"], -self.lado_apoya.get(d["narrativa"], 1)
            elif d.get("decision") == "nueva":
                clave = d.get("grupo") or f"G{f}"
                if clave not in nuevas:
                    nuevas[clave] = {"id": f"x{len(nuevas) + 1:02d}", "afirmacion": d.get("afirmacion", ""),
                                     "familias": [], "comentarios": 0}
                nueva = nuevas[clave]
                destino, lado = nueva["id"], 1  # el lado que apoya
            if destino is None:
                continue
            agregados = 0
            for i in indices.get(f, []):
                if ruido_inicial[i]:  # la regla de oro: no se toca lo que el puente ya asignó
                    self.pred[i] = destino
                    self.signo[i] = lado
                    self.propia[i] = True
                    agregados += 1
            if agregados:
                notas["comentarios_agregados"] += agregados
                notas["familias_con_comentarios_agregados"] += 1
            if nueva is not None:
                nueva["familias"].append(f)
                nueva["comentarios"] += agregados
        notas["narrativas_nuevas"] = {v["id"]: {"grupo": k, "afirmacion": v["afirmacion"], "familias": v["familias"],
                                                "comentarios": v["comentarios"]} for k, v in nuevas.items()}
        notas["decisiones"] = decisiones
        notas["grupos"] = [{"familia": g["familia"], "comentarios": g["comentarios"], "cuentas": g["cuentas"],
                            "nucleo": g["nucleo"],
                            "decision": decisiones.get(str(g["familia"]), {}).get("decision", "ruido")}
                           for g in self.grupos]
        return notas
