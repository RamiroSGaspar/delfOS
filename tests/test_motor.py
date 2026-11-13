"""Pruebas chicas del motor de narrativas sin modelo: N1, N2, N3, N4, N5, N7, N9 y N10."""
from datetime import datetime, timedelta

import numpy as np

from conftest import T0
from pipeline.familias import familias_de_nucleos
from pipeline.origen import origenes
from pipeline.titulos import titulos_por_nucleos

RELLENO_N1 = ["el intendente viajo a china en enero", "suben las tarifas del colectivo", "llueve fuerte en el valle",
              "corte de luz en el barrio norte", "inauguraron la plaza nueva ayer", "paro docente el lunes",
              "precio del pan por las nubes", "falta agua en la escuela", "el rio crecio dos metros",
              "nuevo horario del mercado", "festival de musica en marzo", "cortaron la ruta nacional",
              "el club gano el clasico", "vacunacion en la sala", "caminos rurales destruidos",
              "cerro la fabrica textil", "hay dengue en la zona", "becas para estudiantes", "obras de cloacas",
              "reclamo por el transporte"]


# ----------------------------------------------------------------------------- N1
def test_n1_errores_de_tipeo_en_la_misma_familia_y_temas_distintos_no():
    familia, aviso = familias_de_nucleos(["se robaron la plata", "se robaron la palta", "la obra esta parada"]
                                         + RELLENO_N1, 0.7)
    assert aviso is None
    assert familia[0] == familia[1]
    assert familia[0] != familia[2]


def test_n1_con_muy_pocos_nucleos_cae_en_la_salvaguarda():
    familia, aviso = familias_de_nucleos(["uno dos tres", "cuatro cinco seis"], 0.7)
    assert aviso is not None
    assert len(set(familia)) == 2


# ----------------------------------------------------------------------------- N2 a N5 y N7
def _accesos(c):
    pos = c["conv"].pos
    return (lambda cid: c["pred"][pos[cid]]), (lambda cid: int(c["signo"][pos[cid]]))


def test_n4_dos_grupos_unidos_por_una_sola_respuesta_son_dos_narrativas(conversacion_corrida):
    pred, _ = _accesos(conversacion_corrida)
    m = conversacion_corrida["marcas"]
    x, y = pred(m["tops_x"][2]), pred(m["tops_y"][2])
    assert x and y and x != y
    assert len(set(conversacion_corrida["pred"]) - {""}) == 2


def test_n5_lo_que_no_responde_ni_es_respondido_es_ruido(conversacion_corrida):
    pred, _ = _accesos(conversacion_corrida)
    assert all(pred(c) == "" for c in conversacion_corrida["marcas"]["ruido"])


def test_n7_la_respuesta_que_contradice_va_al_lado_contrario(conversacion_corrida):
    pred, signo = _accesos(conversacion_corrida)
    conv = conversacion_corrida["conv"]
    r = conversacion_corrida["marcas"]["resp_x"][0]
    padre = conv.ids[conv.padre[conv.pos[r]]]
    assert pred(r) == pred(padre)
    assert signo(r) == -signo(padre)


def test_n2_tal_cual_hereda_narrativa_y_lado(conversacion_corrida):
    pred, signo = _accesos(conversacion_corrida)
    m = conversacion_corrida["marcas"]
    r = m["resp_x"][0]
    assert pred(m["tal_cual_r"]) == pred(r)
    assert signo(m["tal_cual_r"]) == signo(r)
    assert conversacion_corrida["conv"].acomp[conversacion_corrida["conv"].idx_nucleo["tal cual"]]


def test_n2_tal_cual_suelto_no_hereda_nada(conversacion_corrida):
    pred, _ = _accesos(conversacion_corrida)
    assert pred(conversacion_corrida["marcas"]["tal_cual_solo"]) == ""


def test_n3_familia_con_una_sola_respuesta_no_entra_al_puente(conversacion_corrida):
    pred, _ = _accesos(conversacion_corrida)
    f100 = conversacion_corrida["marcas"]["f100"]
    assert sum(pred(c) != "" for c in f100) == 1  # solo la respuesta, que hereda de su padre


def test_n3_familia_con_diez_respuestas_entra(conversacion_corrida):
    pred, _ = _accesos(conversacion_corrida)
    assert all(pred(c) != "" for c in conversacion_corrida["marcas"]["f10"])


# ----------------------------------------------------------------------------- N9
def test_n9_un_comentario_suelto_no_fecha_el_origen(conversacion_corrida):
    c = conversacion_corrida
    origen = origenes(c["conv"], c["pred"], c["propia"])
    x = c["pred"][c["conv"].pos[c["marcas"]["tops_x"][2]]]
    assert datetime.fromisoformat(origen[x]) >= T0


class _ConversacionFalsa:
    """Lo mínimo que usa N9: horas, fechas y zona."""

    def __init__(self, minutos: list):
        import polars as pl
        self.t = np.array([(T0 + timedelta(minutes=m)).timestamp() for m in minutos])
        self.com = pl.DataFrame({"fecha": [(T0 + timedelta(minutes=m)).isoformat() for m in minutos]})
        self.offset_s = -3 * 3600


def test_n9_un_arranque_lento_no_se_atrasa_mas_de_tres_horas():
    # Arranca a las 0 h y va de a poco: el primer grupo de 3 en 3 horas empieza a los 150 minutos.
    minutos = [0, 150, 300, 310, 320, 330]
    conv = _ConversacionFalsa(minutos)
    origen = origenes(conv, ["n00"] * len(minutos), np.ones(len(minutos), dtype=bool))
    atraso = datetime.fromisoformat(origen["n00"]) - T0
    assert atraso == timedelta(minutes=150)
    assert atraso <= timedelta(hours=3)


def test_n9_con_comentarios_espaciados_usa_el_primero():
    minutos = [0, 400, 800, 1200]  # nunca 3 en 3 horas
    conv = _ConversacionFalsa(minutos)
    origen = origenes(conv, ["n00"] * 4, np.ones(4, dtype=bool))
    assert datetime.fromisoformat(origen["n00"]) == T0


# ----------------------------------------------------------------------------- N10 (sin modelo)
def test_n10_el_titulo_es_el_nucleo_mas_frecuente_del_lado_que_apoya():
    nucleos = ["se robaron la plata"] * 10 + ["la plata no esta"] * 3 + ["mentira todo"] * 20
    postura = ["apoya"] * 13 + ["rechaza"] * 20
    titulos = titulos_por_nucleos(nucleos, ["n00"] * 33, postura, np.ones(33, dtype=bool))
    assert titulos["n00"] == ("se robaron la plata", ["se robaron la plata", "la plata no esta"])


def test_n10_sin_comentarios_propios_que_apoyan_el_titulo_es_la_etiqueta():
    titulos = titulos_por_nucleos(["algo"] * 3, ["n00"] * 3, ["apoya"] * 3, np.zeros(3, dtype=bool))
    assert titulos["n00"] == ("n00", [])
