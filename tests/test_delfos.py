"""La aplicación: los proyectos, el explorador de carpetas, la clave y el servidor, con un análisis de punta a
punta sobre un set diminuto. Corre sin clave (ver `conftest.py`): el motor usa sus respaldos y no gasta nada."""
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import pipeline.modelo as modelo
from conftest import conversacion, escribir_set
from delfos import clave, explorador, proyectos
from delfos.servidor import Servidor, anotar_instancia, cerrar_instancia, instancia_abierta

ARCHIVOS_DEL_SET = ["comentarios.csv.gz", "cuentas.csv.gz", "fuentes.csv", "publicaciones.csv.gz"]
OFICIALES = ["comentarios.csv", "costo.json", "cuentas.csv", "narrativas.csv"]


@pytest.fixture(autouse=True)
def lista_de_proyectos_aparte(monkeypatch, tmp_path):
    """La lista de proyectos de las pruebas nunca es la del usuario, tampoco donde `HOME` no manda (Windows)."""
    monkeypatch.setenv("DELFOS_CONFIG", str(tmp_path / "config"))


@pytest.fixture
def set_chico(tmp_path):
    return escribir_set(tmp_path / "descargas" / "set", conversacion()[0])


@pytest.fixture
def servidor():
    s = Servidor(0)
    threading.Thread(target=s.servir, kwargs={"vigilar": False}, daemon=True).start()
    yield s
    s.httpd.shutdown()
    s.cerrar()


def pedir(s, metodo, ruta, cuerpo=None, encabezados=None):
    pedido = urllib.request.Request(s.url.rstrip("/") + ruta, method=metodo,
                                    data=None if cuerpo is None else json.dumps(cuerpo).encode("utf-8"),
                                    headers={"X-Delfos-Token": s.token} if encabezados is None else encabezados)
    try:
        with urllib.request.urlopen(pedido, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def esperar(s, proyecto_id):
    for _ in range(900):
        p = json.loads(pedir(s, "GET", f"/api/proyectos/{proyecto_id}")[1])
        if p["estado"] != "analizando":
            return p
        time.sleep(0.1)
    raise AssertionError("el análisis no terminó")


def test_crear_un_proyecto_copia_los_datos_y_quitarlo_no_borra_nada(set_chico, tmp_path):
    p = proyectos.crear("Mi análisis: octubre", str(set_chico), str(tmp_path / "proyectos"))
    carpeta = Path(p["carpeta"])
    assert carpeta == (tmp_path / "proyectos" / "Mi análisis_ octubre").resolve()
    assert sorted(x.name for x in (carpeta / "datos").iterdir()) == ARCHIVOS_DEL_SET
    assert p["estado"] == "sin_analizar" and p["nombre"] == "Mi análisis: octubre"
    filas = {f["archivo"]: f["filas"] for f in p["ficha"]}
    assert filas["comentarios.csv.gz"] == len(conversacion()[0]) and filas["fuentes.csv"] == 1
    assert [x["id"] for x in proyectos.listar()] == [p["id"]]
    proyectos.quitar(p["id"])
    assert proyectos.listar() == [] and (carpeta / "proyecto.json").is_file()


def test_un_proyecto_pide_los_4_archivos_y_no_pisa_una_carpeta_con_cosas(set_chico, tmp_path):
    with pytest.raises(proyectos.ErrorDeProyecto, match="nombre"):
        proyectos.crear(" ", str(set_chico), str(tmp_path))
    proyectos.crear("uno", str(set_chico), str(tmp_path / "proyectos"))
    with pytest.raises(proyectos.ErrorDeProyecto, match="ya existe"):
        proyectos.crear("uno", str(set_chico), str(tmp_path / "proyectos"))
    (set_chico / "fuentes.csv").unlink()
    with pytest.raises(proyectos.ErrorDeProyecto, match="falta fuentes.csv"):
        proyectos.crear("dos", str(set_chico), str(tmp_path / "proyectos"))
    assert not (tmp_path / "proyectos" / "dos").exists()


def test_el_explorador_lista_carpetas_y_reconoce_un_set(set_chico):
    arriba = explorador.listar(str(set_chico.parent))
    assert [c["nombre"] for c in arriba["carpetas"]] == ["set"] and not arriba["set_completo"]
    assert arriba["carpetas"][0]["ruta"] == str(set_chico.resolve())
    adentro = explorador.listar(str(set_chico))
    assert adentro["set_completo"] and adentro["padre"] == arriba["ruta"]
    assert explorador.listar(str(set_chico / "todavia" / "no_existe"))["ruta"] == adentro["ruta"]


def test_la_clave_se_guarda_solo_para_el_usuario():
    assert clave.estado() == {"configurada": False, "origen": None}
    with pytest.raises(proyectos.ErrorDeProyecto):
        clave.guardar("esto no es una clave")
    clave.guardar("sk-ant-" + "x" * 30)
    assert clave.estado() == {"configurada": True, "origen": "archivo"}
    assert modelo.RUTA_CLAVE.stat().st_mode & 0o777 == 0o600
    clave.borrar()
    assert clave.estado() == {"configurada": False, "origen": None}


def test_el_servidor_rechaza_lo_que_no_viene_de_la_aplicacion(servidor):
    assert pedir(servidor, "GET", "/api/estado", encabezados={})[0] == 403  # sin la contraseña
    assert pedir(servidor, "GET", "/api/estado", encabezados={"X-Delfos-Token": "otra"})[0] == 403
    assert pedir(servidor, "GET", "/api/estado", encabezados={"X-Delfos-Token": servidor.token, "Host": "otro.sitio"})[0] == 403
    estado, latido = pedir(servidor, "GET", "/api/latido", encabezados={})
    assert estado == 200 and json.loads(latido) == {"delfos": True, "version": servidor.version, "pid": os.getpid(), "ocupada": False}
    estado, pagina = pedir(servidor, "GET", "/", encabezados={})
    assert estado == 200 and servidor.token in pagina.decode("utf-8") and not re.search(r"__[A-Z]+__", pagina.decode("utf-8"))
    estado, cuerpo = pedir(servidor, "GET", "/api/estado")
    assert estado == 200 and json.loads(cuerpo)["proyectos"] == []


def test_la_clave_por_el_servidor_nunca_vuelve(servidor):
    secreta = "sk-ant-" + "z" * 40
    estado, cuerpo = pedir(servidor, "POST", "/api/clave", {"clave": secreta})
    assert estado == 200 and json.loads(cuerpo) == {"clave": {"configurada": True, "origen": "archivo"}}
    for ruta in ("/api/estado", "/"):
        assert secreta not in pedir(servidor, "GET", ruta)[1].decode("utf-8")
    assert json.loads(pedir(servidor, "DELETE", "/api/clave")[1])["clave"]["configurada"] is False
    assert pedir(servidor, "POST", "/api/clave", {"clave": "mala"})[0] == 400


def test_de_los_datos_al_tablero(servidor, set_chico, tmp_path):
    estado, cuerpo = pedir(servidor, "POST", "/api/proyectos",
                           {"nombre": "Prueba", "datos": str(set_chico), "base": str(tmp_path / "proyectos")})
    assert estado == 200
    pid, carpeta = json.loads(cuerpo)["id"], Path(json.loads(cuerpo)["carpeta"])
    assert pedir(servidor, "GET", f"/proyectos/{pid}/tablero.html")[0] == 404
    assert json.loads(pedir(servidor, "POST", f"/api/proyectos/{pid}/analizar")[1])["estado"] == "analizando"
    assert pedir(servidor, "POST", f"/api/proyectos/{pid}/analizar")[0] == 400  # de a un análisis por vez
    p = esperar(servidor, pid)
    assert p["estado"] == "listo", p
    assert sorted(x.name for x in (carpeta / "resultado").iterdir()) == OFICIALES
    assert not list(carpeta.glob("*.nuevo*")) and (carpeta / "cache.jsonl").exists() is not None
    ultimo = p["ultimo_analisis"]
    assert ultimo["con_ia"] is False and ultimo["conteos"]["comentarios"] == len(conversacion()[0])

    estado, tablero = pedir(servidor, "GET", f"/proyectos/{pid}/tablero.html")
    datos = json.loads(re.search(r'<script id="datos" type="application/json">(.*?)</script>', tablero.decode("utf-8"), re.S).group(1))
    assert estado == 200 and datos["totales"]["comentarios"] == len(conversacion()[0])
    assert datos["informe"] is not None and "lectura" in datos["informe"]["tiempos"]  # el informe de esa misma corrida
    assert pedir(servidor, "GET", f"/proyectos/{pid}/tablero.html", encabezados={})[0] == 403

    ruido = json.loads(pedir(servidor, "GET", f"/api/proyectos/{pid}/comentarios?narrativa=ruido")[1])
    assert ruido["total"] == datos["totales"]["ruido"] and all(f["narrativa"] is None for f in ruido["filas"])
    busqueda = json.loads(pedir(servidor, "GET", f"/api/proyectos/{pid}/comentarios?texto=HOSPITAL&postura=apoya")[1])
    assert busqueda["total"] > 0 and all("hospital" in f["texto"] and f["postura"] == "apoya" for f in busqueda["filas"])

    # Volver a analizar reemplaza el resultado, y quitar el proyecto no borra sus archivos.
    pedir(servidor, "POST", f"/api/proyectos/{pid}/analizar")
    assert esperar(servidor, pid)["estado"] == "listo"
    assert pedir(servidor, "DELETE", f"/api/proyectos/{pid}")[0] == 200
    assert json.loads(pedir(servidor, "GET", "/api/estado")[1])["proyectos"] == [] and (carpeta / "tablero.html").is_file()


def test_cancelar_un_analisis_deja_el_proyecto_como_estaba(servidor, set_chico, tmp_path):
    cuerpo = pedir(servidor, "POST", "/api/proyectos",
                   {"nombre": "Para cancelar", "datos": str(set_chico), "base": str(tmp_path / "proyectos")})[1]
    pid, carpeta = json.loads(cuerpo)["id"], Path(json.loads(cuerpo)["carpeta"])
    pedir(servidor, "POST", f"/api/proyectos/{pid}/analizar")
    pedir(servidor, "POST", f"/api/proyectos/{pid}/cancelar")
    p = esperar(servidor, pid)
    assert p["estado"] == "sin_analizar" and p["ultimo_intento"] is None
    assert not (carpeta / "resultado").exists() and not list(carpeta.glob("*.nuevo*"))


def test_una_instancia_con_otro_codigo_no_esta_al_dia(servidor):
    assert instancia_abierta() is None  # todavía no se anotó ninguna
    anotar_instancia(servidor)
    abierta = instancia_abierta()
    assert abierta["al_dia"] and not abierta["ocupada"] and abierta["url"] == servidor.url and abierta["pid"] == os.getpid()
    servidor.version = "otra"  # como si el código hubiera cambiado en el disco después de arrancar
    assert instancia_abierta()["al_dia"] is False
    assert cerrar_instancia(instancia_abierta()) is False  # nunca se cierra a sí misma
