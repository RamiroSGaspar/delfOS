"""Pruebas del acceso al modelo (caché, sin clave, pedidos repetidos) y de las etapas que lo usan: N8, N10 y N12.

Ninguna llama a la API: las respuestas se arman a mano o salen de una API falsa.
"""
import json
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest

from pipeline import modelo as m
from pipeline.configuracion import CONFIG
from pipeline.lados import LadoQueApoya, tope_y_conteos
from pipeline.plan_b import PlanB, leer_decisiones
from pipeline.titulos import SISTEMA as SISTEMA_N10
from pipeline.titulos import Titulos, armar_pedido


def respuesta(texto: str, cortada: bool = False, tokens=(100, 20), usd=0.00002) -> m.Respuesta:
    return m.Respuesta(texto=texto, modelo=m.MODELO, tokens_entrada=tokens[0], tokens_salida=tokens[1], usd=usd,
                       desde_cache=False, motivo_fin="max_tokens" if cortada else "end_turn", cortada=cortada)


def uso_vacio() -> dict:
    return {"llamadas": 0, "tokens": 0, "usd": 0.0}


# ----------------------------------------------------------------------------- el acceso al modelo
def test_la_huella_es_la_de_la_serie():
    """Un pedido de N10 de la caché de EXP-017 (núcleo "el puente se caiga en marzo") da la misma huella: los
    pedidos se arman igual que en la serie y su caché sirve tal cual."""
    pedido = m.Pedido(armar_pedido(["el puente se caiga en marzo"], 12), SISTEMA_N10, 2048, "low")
    assert pedido.huella() == "010603565b41c196eae3bbae16619c1778c131ca9430608381e9e75b5cd813cd"


def test_sin_clave_y_fuera_de_la_cache_es_un_error_que_no_corta(tmp_path):
    modelo = m.Modelo(tmp_path / "cache.jsonl")
    (resultado,) = modelo.lanzar([m.Pedido("hola", "", 10, "low")]).resultados()
    modelo.cerrar()
    assert isinstance(resultado, m.ErrorModelo)
    assert modelo.uso["errores"] == 1 and modelo.uso["llamadas_api"] == 0


def test_con_la_cache_no_hace_falta_clave(tmp_path):
    pedido = m.Pedido("hola", "sistema", 10, "low")
    guardada = {"id": "x", "modelo": m.MODELO, "texto": "listo", "motivo_fin": "end_turn", "tokens_entrada": 5,
                "tokens_salida": 1, "usd": 0.000001}
    ruta = tmp_path / "cache.jsonl"
    ruta.write_text(json.dumps({"huella_pedido": pedido.huella(), "pedido": pedido.parametros(),
                                "respuesta": guardada}) + "\nlínea rota sin json\n", encoding="utf-8")
    modelo = m.Modelo(ruta)
    (r,) = modelo.lanzar([pedido]).resultados()
    modelo.cerrar()
    assert r.texto == "listo" and r.desde_cache
    assert modelo.uso == {**modelo.uso, "respuestas_de_cache": 1, "llamadas_api": 0, "errores": 0}


def test_un_pedido_identico_no_se_repite_en_la_corrida(tmp_path):
    modelo = m.Modelo(None)
    pedido = m.Pedido("hola", "", 10, "low")
    modelo.lanzar([pedido, pedido]).resultados()
    modelo.lanzar([pedido]).resultados()
    modelo.cerrar()
    assert modelo.uso["pedidos"] == 1


def test_sin_modelo_no_se_puede_lanzar():
    modelo = m.Modelo(None, activo=False)
    with pytest.raises(m.ErrorModelo):
        modelo.lanzar([m.Pedido("hola", "", 10, "low")])


class _ApiFalsa:
    """Una API que responde siempre lo mismo, para probar el camino de la llamada sin red."""

    def __init__(self, texto="AFIRMA: A", modelo_respondio=m.MODELO + "-20261001", motivo="end_turn"):
        self.llamadas = 0
        self.messages = SimpleNamespace(create=self._crear)
        self._r = SimpleNamespace(id="msg_1", model=modelo_respondio, stop_reason=motivo,
                                  content=[SimpleNamespace(type="text", text=texto)],
                                  usage=SimpleNamespace(input_tokens=700, output_tokens=40,
                                                        cache_creation_input_tokens=0, cache_read_input_tokens=0))

    def _crear(self, **parametros):
        self.llamadas += 1
        assert parametros["model"] == m.MODELO
        return self._r


def test_la_respuesta_de_la_api_queda_en_la_cache_y_la_proxima_corrida_la_usa(tmp_path, monkeypatch):
    api = _ApiFalsa()
    monkeypatch.setattr(m.Modelo, "_cliente_api", lambda self: (api, None))
    ruta = tmp_path / "cache.jsonl"
    pedido = m.Pedido("¿qué grupo afirma?", "sistema", 2048, "low")
    modelo = m.Modelo(ruta)
    (r,) = modelo.lanzar([pedido]).resultados()
    modelo.cerrar()
    assert r.texto == "AFIRMA: A" and not r.desde_cache
    assert r.usd == pytest.approx(700 * 0.10 / 1e6 + 40 * 0.50 / 1e6)
    fila = json.loads(ruta.read_text(encoding="utf-8"))
    assert fila["huella_pedido"] == pedido.huella() and fila["pedido"] == pedido.parametros()
    assert "api_key" not in ruta.read_text(encoding="utf-8")
    otra = m.Modelo(ruta)
    (r2,) = otra.lanzar([pedido]).resultados()
    otra.cerrar()
    assert r2.desde_cache and r2.texto == r.texto and api.llamadas == 1


@pytest.mark.parametrize("api", [_ApiFalsa(modelo_respondio="otro-modelo"), _ApiFalsa(motivo="refusal")])
def test_otro_modelo_o_una_negativa_son_errores_y_no_van_a_la_cache(tmp_path, monkeypatch, api):
    monkeypatch.setattr(m.Modelo, "_cliente_api", lambda self: (api, None))
    ruta = tmp_path / "cache.jsonl"
    modelo = m.Modelo(ruta)
    (r,) = modelo.lanzar([m.Pedido("hola", "", 10, "low")]).resultados()
    modelo.cerrar()
    assert isinstance(r, m.ErrorModelo)
    assert not ruta.exists()


# ----------------------------------------------------------------------------- N8
def conversacion_pareja(a: int, b: int):
    """Una narrativa con a comentarios de primer nivel del lado 1 y b del lado -1."""
    textos = ["la planta contamina el arroyo"] * a + ["los analisis del agua dieron bien"] * b
    conv = SimpleNamespace(padre=np.full(a + b, -1), com=pl.DataFrame({"nucleo": textos, "texto": textos}))
    return conv, ["n00"] * (a + b), np.array([1] * a + [-1] * b)


def test_n8_tope_es_el_lado_con_mas_primer_nivel():
    conv, pred, signo = conversacion_pareja(5, 40)
    tope, conteo = tope_y_conteos(conv, pred, signo)
    assert tope == {"n00": -1} and conteo["n00"] == {1: 5, -1: 40}


def test_n8_con_margen_amplio_no_pregunta():
    conv, pred, signo = conversacion_pareja(5, 40)
    n8 = LadoQueApoya(conv, pred, signo, CONFIG)
    assert n8.pedidos() == []
    assert n8.decidir([], uso_vacio())[0] == {"n00": -1}


def test_n8_con_margen_chico_pregunta_en_los_dos_ordenes_y_decide_si_coinciden():
    conv, pred, signo = conversacion_pareja(20, 20)  # "tope" daría 1
    n8 = LadoQueApoya(conv, pred, signo, CONFIG)
    pedidos = n8.pedidos()
    assert len(pedidos) == 2
    assert "Grupo A:\n- la planta contamina el arroyo" in pedidos[0].texto
    assert "Grupo A:\n- los analisis del agua dieron bien" in pedidos[1].texto
    # El modelo dice que afirma el lado -1 en los dos órdenes: B en el primero y A en el segundo.
    uso = uso_vacio()
    lado, detalle = n8.decidir([respuesta("AFIRMA: B"), respuesta("AFIRMA: **A**")], uso)
    assert lado == {"n00": -1} and detalle["n00"]["decide"] == "modelo"
    assert uso["llamadas"] == 2 and uso["tokens"] == 240


@pytest.mark.parametrize("respuestas", [
    [respuesta("AFIRMA: A"), respuesta("AFIRMA: A")],  # no coinciden: en el segundo orden, A es el lado -1
    [m.ErrorModelo("sin clave"), m.ErrorModelo("sin clave")],
    [respuesta("AFIRMA: B", cortada=True), respuesta("AFIRMA: A")],
])
def test_n8_si_el_modelo_no_es_consistente_queda_tope(respuestas):
    conv, pred, signo = conversacion_pareja(20, 20)
    n8 = LadoQueApoya(conv, pred, signo, CONFIG)
    n8.pedidos()
    assert n8.decidir(respuestas, uso_vacio())[0] == {"n00": 1}


def test_n8_sin_modelo_es_tope():
    conv, pred, signo = conversacion_pareja(20, 18)
    n8 = LadoQueApoya(conv, pred, signo, CONFIG)
    assert n8.decidir(None)[0] == {"n00": 1}


# ----------------------------------------------------------------------------- N10 con modelo
def titulos_de_prueba():
    nucleos = ["se robaron la plata de la obra"] * 6 + ["la plata de la obra no aparece"] * 3 + ["es mentira"] * 5
    postura = ["apoya"] * 9 + ["rechaza"] * 5
    return Titulos(nucleos, ["n00"] * 14, postura, np.ones(14, dtype=bool), CONFIG)


@pytest.mark.parametrize("texto, aceptado", [
    ("Título: «Se robaron la plata de la obra»", "Se robaron la plata de la obra"),
    ("La plata de la obra no aparece: se la robaron", "La plata de la obra no aparece: se la robaron"),
])
def test_n10_acepta_el_titulo_que_no_inventa(texto, aceptado):
    t = titulos_de_prueba()
    assert len(t.pedidos()) == 1
    titulos, _ = t.decidir([respuesta(texto)], uso_vacio())
    assert titulos["n00"][0] == aceptado
    assert titulos["n00"][1] == ["se robaron la plata de la obra", "la plata de la obra no aparece"]


@pytest.mark.parametrize("r", [
    respuesta("El intendente se robó la plata de la obra"),  # agrega "intendente": no está en los núcleos
    respuesta(" ".join(["plata"] * 21)),  # más de 20 palabras
    respuesta("Se robaron la plata", cortada=True),
    respuesta(""),
    m.ErrorModelo("sin clave"),
])
def test_n10_si_el_titulo_no_sirve_queda_el_nucleo_mas_frecuente(r):
    titulos, _ = titulos_de_prueba().decidir([r], uso_vacio())
    assert titulos["n00"][0] == "se robaron la plata de la obra"


# ----------------------------------------------------------------------------- N12
@pytest.fixture
def plan_b(conversacion_corrida):
    """N12 sobre la conversación: la familia de "que calor hace hoy en el pueblo" (100 comentarios, uno
    heredado por respuesta y 99 de ruido) es la única candidata."""
    c = conversacion_corrida
    pred, signo, propia = list(c["pred"]), c["signo"].copy(), c["propia"].copy()
    lado = {n: 1 for n in set(pred) - {""}}
    plan = PlanB(c["conv"], c["familia"], pred, signo, propia, lado, CONFIG)
    return plan, c


def test_n12_candidatas_y_pedido(plan_b):
    plan, c = plan_b
    assert [g["comentarios"] for g in plan.grupos] == [100]
    (pedido,) = plan.pedidos()
    assert f'F{plan.grupos[0]["familia"]:03d} | 100 comentarios' in pedido.texto
    assert pedido.max_tokens == 16000 and pedido.esfuerzo == "medium"


def _decision(plan, decision: str, **extra) -> m.Respuesta:
    return respuesta(json.dumps({"decisiones": [{"familia": f'F{plan.grupos[0]["familia"]:03d}',
                                                 "decision": decision, **extra}]}))


def test_n12_afirma_agrega_el_ruido_del_lado_que_apoya_y_respeta_la_regla_de_oro(plan_b):
    plan, c = plan_b
    antes = list(plan.pred), plan.signo.copy()
    narrativa = c["pred"][c["conv"].pos[c["marcas"]["tops_x"][0]]]
    notas = plan.aplicar([_decision(plan, "afirma", narrativa=narrativa)], uso_vacio())
    assert notas["comentarios_agregados"] == 99
    pos = c["conv"].pos
    f100 = c["marcas"]["f100"]
    for cid in f100[:-1]:
        assert plan.pred[pos[cid]] == narrativa and plan.signo[pos[cid]] == 1 and plan.propia[pos[cid]]
    # La regla de oro: lo que el puente ya había asignado no cambia (ni la narrativa ni el lado).
    for i, (n, s) in enumerate(zip(*antes)):
        if n:
            assert plan.pred[i] == n and plan.signo[i] == s


def test_n12_refuta_va_del_lado_contrario(plan_b):
    plan, c = plan_b
    narrativa = c["pred"][c["conv"].pos[c["marcas"]["tops_x"][0]]]
    plan.aplicar([_decision(plan, "refuta", narrativa=narrativa)], uso_vacio())
    assert plan.signo[c["conv"].pos[c["marcas"]["f100"][0]]] == -1


def test_n12_nueva_crea_una_narrativa(plan_b):
    plan, c = plan_b
    notas = plan.aplicar([_decision(plan, "nueva", grupo="G1", afirmacion="Hace calor")], uso_vacio())
    assert list(notas["narrativas_nuevas"]) == ["x01"]
    assert plan.pred[c["conv"].pos[c["marcas"]["f100"][0]]] == "x01"


@pytest.mark.parametrize("cual", ["ruido", "error", "no es json", "narrativa inexistente"])
def test_n12_ruido_falla_o_respuesta_invalida_no_cambia_nada(plan_b, cual):
    plan, _ = plan_b
    antes = list(plan.pred), plan.signo.copy(), plan.propia.copy()
    r = {"ruido": _decision(plan, "ruido"), "error": m.ErrorModelo("sin clave"),
         "no es json": respuesta("no sé qué decir"),
         "narrativa inexistente": _decision(plan, "afirma", narrativa="n99")}[cual]
    plan.aplicar([r], uso_vacio())
    assert plan.pred == antes[0]
    assert np.array_equal(plan.signo, antes[1]) and np.array_equal(plan.propia, antes[2])


def test_n12_lee_json_dentro_de_texto_y_marca_invalidas():
    grupos = [{"familia": 7}, {"familia": 9}]
    narrativas = [{"id": "n00"}]
    texto = 'Acá va: ```json\n{"decisiones": [{"familia": "F007", "decision": "afirma", "narrativa": "n00"}]}\n```'
    decisiones, invalidas = leer_decisiones(texto, grupos, narrativas)
    assert decisiones == [{"familia": 7, "decision": "afirma", "narrativa": "n00"}]
    assert invalidas == [{"familia": 9, "motivo": "la familia no tiene decisión"}]
