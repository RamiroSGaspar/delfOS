"""El tablero: el resumen sale bien contado de un set y una entrega armados a mano, la página es un solo archivo
sin nada de afuera, y los casos raros (sin cuentas coordinadas, sin fechas, una entrega de otro set) no la rompen."""
import csv
import json
import re
from datetime import timedelta
from pathlib import Path

import pytest

from conftest import T0, escribir_set
from tablero.__main__ import main
from tablero.pagina import armar, leer_identidad
from tablero.resumen import calcular

PELIGROSO = "cierro </script><b>la etiqueta"
#        id     cuenta  texto             narrativa  postura    (None: el comentario no está en la entrega)
FILAS = [("c01", "u1", "mismo texto", "nA", "apoya"), ("c02", "u2", "dos", "nA", "apoya"),
         ("c03", "u3", "tres", "nA", "rechaza"), ("c04", "u1", "mismo texto", "nA", "apoya"),
         ("c05", "u4", "cinco", "nB", "apoya"), ("c06", "u2", "seis", "nB", "rechaza"),
         ("c07", "u5", PELIGROSO, "", ""), ("c08", "u5", "ocho", "ninguna", ""),
         ("c09", "u3", "nueve", "", "apoya"), ("c10", "u1", "diez", None, None)]


def escribir_csv(ruta: Path, encabezado: list, filas: list):
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(encabezado)
        w.writerows(filas)


def armar_caso(carpeta: Path, fechas=None, grupos=None):
    """Un set de 10 comentarios, uno por hora, y su entrega: 2 narrativas con comentarios, 1 sin, y 1 operación."""
    datos = escribir_set(carpeta / "datos", [
        {"id": i, "cuenta": c, "texto": t, "respuesta_a": "",
         "fecha": fechas[k] if fechas else (T0 + timedelta(hours=k)).isoformat()}
        for k, (i, c, t, _, _) in enumerate(FILAS)])
    entrega = carpeta / "resultado" / "entrega"
    entrega.mkdir(parents=True)
    escribir_csv(entrega / "comentarios.csv", ["comentario_id", "narrativa", "postura"],
                 [(i, n, p) for i, _, _, n, p in FILAS if n is not None])
    escribir_csv(entrega / "narrativas.csv", ["narrativa", "titulo", "frases_clave", "fecha_origen"],
                 [("nA", "Título A", "uno|dos", T0.isoformat()), ("nC", "Título C", "", "")])
    grupos = {"u1": "op1", "u2": "op1"} if grupos is None else grupos
    escribir_csv(entrega / "cuentas.csv", ["cuenta_id", "grupo"], [(f"u{k}", grupos.get(f"u{k}", "")) for k in range(1, 6)])
    (entrega / "costo.json").write_text(json.dumps({"comentarios_procesados": 10, "segundos": 1.5, "tokens_ia": 0,
                                                    "usd_ia": 0}), encoding="utf-8")
    return datos, entrega


@pytest.fixture(scope="module")
def caso(tmp_path_factory):
    datos, entrega = armar_caso(tmp_path_factory.mktemp("tablero"))
    return datos, entrega, calcular(datos, entrega)


def test_los_totales(caso):
    t = caso[2]["totales"]
    assert (t["comentarios"], t["con_narrativa"], t["ruido"], t["narrativas"]) == (10, 6, 4, 3)
    assert (t["cuentas"], t["cuentas_coordinadas"], t["operaciones"], t["comentarios_coordinados"]) == (5, 2, 1, 5)
    assert (t["sin_entrega"], t["sin_hora"]) == (1, 0)


def test_el_ruido_vacio_o_ninguna_no_lleva_postura(caso):
    """`ninguna` y el vacío son ruido, y un ruido con postura no cuenta como postura de nadie."""
    narrativas = {n["etiqueta"]: n for n in caso[2]["narrativas"]}
    assert set(narrativas) == {"nA", "nB", "nC"}
    assert sum(n["apoya"] + n["rechaza"] for n in narrativas.values()) == 6


def test_cada_narrativa(caso):
    a, b, c = caso[2]["narrativas"]
    assert (a["comentarios"], a["apoya"], a["rechaza"], a["cuentas"], a["coordinados"]) == (4, 3, 1, 3, 3)
    assert (a["titulo"], a["frases"], a["sin_titulo"]) == ("Título A", ["uno", "dos"], False)
    assert (b["comentarios"], b["apoya"], b["rechaza"], b["cuentas"], b["coordinados"]) == (2, 1, 1, 2, 1)
    assert (b["titulo"], b["sin_titulo"], b["origen_s"]) == ("nB", True, None)  # sin fila en narrativas.csv
    assert (c["comentarios"], c["titulo"]) == (0, "Título C")  # en narrativas.csv y sin comentarios
    assert [e["texto"] for e in a["ejemplos"]["apoya"]] == ["mismo texto", "dos"]  # sin repetir textos


def test_el_tiempo(caso):
    r = caso[2]
    a = r["narrativas"][0]
    assert r["tramos"]["segundos"] == 3600 and r["tramos"]["cantidad"] == 10
    assert a["serie"]["apoya"] == [1, 1, 0, 1, 0, 0, 0, 0, 0, 0]
    assert a["serie"]["rechaza"] == [0, 0, 1, 0, 0, 0, 0, 0, 0, 0]
    assert a["origen_s"] == r["tramos"]["inicio_s"] == r["periodo"]["desde_s"]  # el origen es el primer comentario
    assert r["periodo"]["zona"] == "-03:00"
    assert sum(r["serie_total"]["con_narrativa"]) == 6 and sum(r["serie_total"]["ruido"]) == 4


def test_la_operacion(caso):
    (op,) = caso[2]["operaciones"]
    assert (op["etiqueta"], op["cuentas"], op["comentarios"], op["ruido"], op["por_cuenta"]) == ("op1", 2, 5, 1, 2.5)
    assert op["narrativas"] == [{"etiqueta": "nA", "comentarios": 3, "apoya": 3, "rechaza": 0},
                                {"etiqueta": "nB", "comentarios": 1, "apoya": 0, "rechaza": 1}]
    assert op["textos"][0] == {"texto": "mismo texto", "veces": 2, "cuentas": 1}
    assert sum(op["serie"]) == 5
    g = caso[2]["genuinas"]
    assert (g["cuentas"], g["comentarios"], g["por_cuenta"]) == (3, 5, 1.67)
    assert caso[2]["pajar"] == {"por_celda": 10, "celdas": 1, "marcadas": {"op1": [0]}}  # 5 cuentas entran en una celda


def test_la_pagina_es_un_solo_archivo(caso):
    pagina = armar(caso[2])
    for de_afuera in ("<link", "@import", "src="):
        assert de_afuera not in pagina
    # La única dirección de la página es el nombre del formato SVG, que no se descarga.
    assert set(re.findall(r"https?://[^\"'\s)]+", pagina)) <= {"http://www.w3.org/2000/svg"}
    assert pagina.count("url(") == pagina.count('url("data:') == 2  # las dos fuentes, adentro de la página
    assert pagina.count("</script>") == 4  # tema, datos, textos y código: el texto de un comentario no cierra la etiqueta
    datos = re.search(r'<script id="datos" type="application/json">(.*?)</script>', pagina, re.S).group(1)
    assert json.loads(datos) == caso[2]
    assert not re.search(r"__[A-Z]+__", pagina.replace(datos, ""))


def test_el_aspecto_sale_del_sistema_de_diseno(caso):
    pagina = armar(caso[2], {**leer_identidad(), "nombre": "Otro <nombre>"})
    assert 'aria-label="Otro &lt;nombre&gt;"' in pagina and "<title>Otro &lt;nombre&gt; · tablero</title>" in pagina
    assert '[data-theme="papel"]' in pagina and '[data-theme="oscuro"]' in pagina  # los dos temas van en la página
    assert pagina.count("@font-face") == 2 and "JetBrains Mono" in pagina and "Source Serif 4" in pagina
    assert ".tt-ventana" in pagina and ".tt-estado" in pagina  # los componentes del sistema


def test_sin_cuentas_coordinadas_y_sin_fechas(tmp_path):
    datos, entrega = armar_caso(tmp_path, fechas=["no es una fecha"] * len(FILAS), grupos={})
    r = calcular(datos, entrega)
    assert r["operaciones"] == [] and r["totales"]["cuentas_coordinadas"] == 0
    assert r["tramos"]["cantidad"] == 0 and r["totales"]["sin_hora"] == 10 and r["periodo"]["desde_s"] is None
    assert r["narrativas"][0]["serie"]["apoya"] == []
    assert "<html" in armar(r)


def test_una_entrega_de_otro_set_se_rechaza(tmp_path):
    datos, entrega = armar_caso(tmp_path)
    escribir_csv(entrega / "comentarios.csv", ["comentario_id", "narrativa", "postura"], [("otro", "nA", "apoya")])
    with pytest.raises(ValueError, match="no corresponde"):
        calcular(datos, entrega)


def test_el_comando(tmp_path, capsys):
    datos, entrega = armar_caso(tmp_path)
    assert main(["--datos", str(datos), "--entrega", str(entrega)]) == 0
    assert (entrega.parent / "tablero.html").exists()  # al lado de la entrega, no adentro
    assert sorted(p.name for p in entrega.iterdir()) == ["comentarios.csv", "costo.json", "cuentas.csv", "narrativas.csv"]
    assert main(["--datos", str(tmp_path / "no_existe"), "--entrega", str(entrega)]) == 2
    (entrega / "cuentas.csv").unlink()
    assert main(["--datos", str(datos), "--entrega", str(entrega)]) == 2
    assert "faltan" in capsys.readouterr().err


def test_las_cuentas_de_la_operacion_una_por_una(caso):
    (op,) = caso[2]["operaciones"]
    assert [(c["cuenta"], c["usuario"], c["creada"], c["seguidores"], c["comentarios"], c["con_narrativa"])
            for c in op["cuentas_una_por_una"]] == [("u1", "usuario_u1", "2020-01-01", 10, 3, 2),
                                                    ("u2", "usuario_u2", "2020-01-01", 10, 2, 2)]


def test_el_informe_suma_lo_del_motor_solo_si_es_de_la_misma_corrida(tmp_path):
    datos, entrega = armar_caso(tmp_path)
    informe = {"conteos": {"comentarios_con_narrativa": 6, "cuentas_marcadas": 2}, "costo": {"segundos": 1.5},
               "perfil": {"avisos": ["un aviso"], "medidas": {"respuestas": {"valor": 0.1, "practica": 0.14}}},
               "tiempos": {"lectura": 0.5}, "uso_modelo": {"pedidos": 0},
               "notas": {"titulos": {"nA": {"titulo": "Título A", "titulo_base": "uno"}},
                         "lado_que_apoya": {"por_narrativa": {"nA": {"decide": "tope"}}},
                         "coordinacion": {"marcadas_por_capa": {"T": 2}, "capas_apagadas": ["R"]}}}
    ruta = tmp_path / "informe.json"
    ruta.write_text(json.dumps(informe), encoding="utf-8")
    r = calcular(datos, entrega, ruta)
    assert r["informe"]["avisos"] == ["un aviso"] and r["informe"]["coordinacion"]["capas_apagadas"] == ["R"]
    a, b, _ = r["narrativas"]
    assert (a["titulo_de_ia"], a["lado_lo_decide"], b["titulo_de_ia"]) == (True, "tope", None)
    assert "<html" in armar(r)
    informe["costo"]["segundos"] = 99  # el informe de otra corrida no se mezcla
    ruta.write_text(json.dumps(informe), encoding="utf-8")
    assert calcular(datos, entrega, ruta)["informe"] is None
    assert calcular(datos, entrega)["informe"] is None and calcular(datos, entrega, tmp_path / "no_existe")["informe"] is None
