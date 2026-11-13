"""Prueba de punta a punta chica: el comando sobre un set diminuto, el formato oficial de los 4 archivos, la
reproducibilidad, el respaldo sin modelo, el enganche (N11) y el reparto entre procesos."""
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from conftest import RAIZ, RUIDO, conversacion, escribir_set
from pipeline.corrida import ejecutar
from pipeline.enganche import COLUMNAS

OFICIALES = ("comentarios.csv", "narrativas.csv", "cuentas.csv")
CAMPOS_COSTO = ["comentarios_procesados", "segundos", "tokens_ia", "usd_ia", "usd_por_mil_comentarios", "hardware",
                "almacenamiento", "notas"]


def huellas(carpeta: Path) -> dict:
    return {n: hashlib.sha256((carpeta / n).read_bytes()).hexdigest() for n in OFICIALES}


def leer_csv(ruta: Path) -> list:
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def set_chico(tmp_path_factory):
    filas, marcas = conversacion()
    return escribir_set(tmp_path_factory.mktemp("set_chico"), filas), filas, marcas


@pytest.fixture(scope="module")
def corrida_por_comando(set_chico, tmp_path_factory):
    """El comando, como lo corre el jurado, sin modelo y sin clave."""
    carpeta, _, _ = set_chico
    salida = tmp_path_factory.mktemp("salida_comando")
    entorno = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    entorno["HOME"] = str(tmp_path_factory.mktemp("home"))
    r = subprocess.run([sys.executable, "-m", "pipeline", "--datos", str(carpeta), "--salida", str(salida),
                        "--sin-modelo", "--informe", str(salida.parent / "informe_comando.json")],
                       cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=300)
    return r, salida


def test_el_comando_termina_bien_y_deja_exactamente_los_4_archivos(corrida_por_comando):
    r, salida = corrida_por_comando
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in salida.iterdir()) == sorted([*OFICIALES, "costo.json"])
    assert "listo en" in r.stderr


def test_formato_de_comentarios(corrida_por_comando, set_chico):
    _, salida = corrida_por_comando
    _, filas, _ = set_chico
    comentarios = leer_csv(salida / "comentarios.csv")
    assert list(comentarios[0]) == ["comentario_id", "narrativa", "postura"]
    assert sorted(c["comentario_id"] for c in comentarios) == sorted(f["id"] for f in filas)
    for c in comentarios:
        assert (c["narrativa"] == "") == (c["postura"] == "")
        assert c["postura"] in ("", "apoya", "rechaza")


def test_formato_de_narrativas(corrida_por_comando):
    _, salida = corrida_por_comando
    narrativas = leer_csv(salida / "narrativas.csv")
    comentarios = leer_csv(salida / "comentarios.csv")
    assert list(narrativas[0]) == ["narrativa", "titulo", "frases_clave", "fecha_origen"]
    assert {n["narrativa"] for n in narrativas} == {c["narrativa"] for c in comentarios if c["narrativa"]}
    for n in narrativas:
        assert datetime.fromisoformat(n["fecha_origen"]).tzinfo is not None
        assert n["titulo"] and n["titulo"] == n["frases_clave"].split("|")[0]  # sin modelo, el núcleo más frecuente


def test_formato_de_cuentas_y_costo(corrida_por_comando, set_chico):
    _, salida = corrida_por_comando
    _, filas, _ = set_chico
    cuentas = leer_csv(salida / "cuentas.csv")
    assert list(cuentas[0]) == ["cuenta_id", "grupo"]
    assert sorted(c["cuenta_id"] for c in cuentas) == sorted({f["cuenta"] for f in filas})
    costo = json.loads((salida / "costo.json").read_text(encoding="utf-8"))
    assert list(costo) == CAMPOS_COSTO
    assert costo["comentarios_procesados"] == len(filas)
    assert costo["tokens_ia"] == 0 and costo["usd_ia"] == 0 and costo["segundos"] > 0


def test_es_reproducible(corrida_por_comando, set_chico, tmp_path):
    _, salida = corrida_por_comando
    carpeta, _, _ = set_chico
    ejecutar(carpeta, tmp_path / "otra", sin_modelo=True)
    assert huellas(tmp_path / "otra") == huellas(salida)


def test_con_el_modelo_caido_da_lo_mismo_que_sin_modelo(corrida_por_comando, set_chico, tmp_path):
    """Sin clave, todos los pedidos fallan y cada etapa usa su respaldo: N8 queda en "tope", N10 en el núcleo
    más frecuente y N12 no agrega nada (ficha N12, prueba (b))."""
    _, salida = corrida_por_comando
    carpeta, _, _ = set_chico
    informe = ejecutar(carpeta, tmp_path / "caido", sin_modelo=False, cache=tmp_path / "cache.jsonl")
    assert informe["notas"]["plan_b"]["familias_candidatas"] >= 1
    assert informe["uso_modelo"]["errores"] >= 1 and informe["uso_modelo"]["llamadas_api"] == 0
    assert huellas(tmp_path / "caido") == huellas(salida)


def test_n11_enganche_con_todas_las_columnas_y_sin_cambiar_la_entrega(corrida_por_comando, set_chico, tmp_path):
    _, salida = corrida_por_comando
    carpeta, filas, marcas = set_chico
    ejecutar(carpeta, tmp_path / "con_enganche", sin_modelo=True, enganche=tmp_path / "enganche.csv")
    assert huellas(tmp_path / "con_enganche") == huellas(salida)
    enganche = leer_csv(tmp_path / "enganche.csv")
    assert list(enganche[0]) == COLUMNAS
    assert len(enganche) == len(filas)
    por_id = {e["comentario_id"]: e for e in enganche}
    assert por_id[marcas["ruido"][0]]["texto"] == RUIDO[0]  # el texto original, intacto
    iguales = {por_id[c]["texto_id"] for c in marcas["iguales"]}
    assert len(iguales) == 1  # el mapa de texto a comentarios
    con_narrativa = por_id[marcas["tops_x"][0]]
    assert con_narrativa["lado"] in ("1", "-1") and con_narrativa["titulo_narrativa"]
    assert con_narrativa["titular"] == "Titular de p001" and con_narrativa["tipo_fuente"] == "medio"


def test_el_reparto_entre_procesos_da_lo_mismo():
    from pipeline.paralelo import Repartidor
    from pipeline.texto import normalizar_lote
    textos = [f"¡Qué TEXTO número {i}!! @alguien #Etiqueta 😀 siii" for i in range(300)]
    repartidor = Repartidor(2)
    try:
        en_procesos = repartidor.lanzar(normalizar_lote, textos).resultados()
    finally:
        repartidor.cerrar()
    assert en_procesos == normalizar_lote(textos)


def test_sin_carpeta_de_datos_avisa_y_sale_con_error(tmp_path):
    r = subprocess.run([sys.executable, "-m", "pipeline", "--datos", str(tmp_path / "no_existe"),
                        "--salida", str(tmp_path / "s")], cwd=RAIZ, capture_output=True, text=True, timeout=60)
    assert r.returncode == 2 and "no existe la carpeta de datos" in r.stderr
