"""Lo común de las pruebas: sets diminutos armados a mano y ninguna llamada real al modelo.

Todas las pruebas corren sin clave de la API (se borra `ANTHROPIC_API_KEY` y `HOME` apunta a una carpeta
vacía), así que nunca se llama a la API ni se gasta nada. Donde hace falta una respuesta del modelo, se usa una
respuesta armada a mano.
"""
import csv
import gzip
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

ZONA = timezone(timedelta(hours=-3))
T0 = datetime(2026, 9, 1, 8, 0, tzinfo=ZONA)

# Una conversación con dos narrativas que se responden entre sí, ruido, acompañamientos y familias de prueba.
X_AFIRMA = ["se robaron la plata de la obra", "la obra es un robo total", "nos vaciaron las arcas del puente"]
X_REFUTA = ["mentira la auditoria aprobo todo", "falso los papeles estan en regla", "no es cierto la obra avanza bien"]
Y_AFIRMA = ["el hospital no tiene medicos", "faltan enfermeros en la guardia", "cerraron la sala de pediatria"]
Y_REFUTA = ["en la guardia hay seis profesionales", "desmentido el servicio funciona normal",
            "pediatria atiende todos los dias"]
RUIDO = ["buen dia a todos", "que lindo dia de sol", "alguien sabe el horario del banco", "feliz cumple marta",
         "vendo bicicleta usada", "se perdio un perro marron", "gracias por la info", "hoy juega el club"]


@pytest.fixture(autouse=True)
def sin_clave(monkeypatch, tmp_path_factory):
    """Ninguna prueba puede llamar a la API: sin variable de la clave y con un HOME vacío."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path_factory.mktemp("home_sin_clave")))
    import pipeline.modelo as modelo
    monkeypatch.setattr(modelo, "RUTA_CLAVE", Path(str(tmp_path_factory.mktemp("sin_clave"))) / "no_existe")


def escribir_set(carpeta: Path, comentarios: list):
    """Los 4 archivos de entrada con el formato oficial. `comentarios`: dicts con id, texto, fecha, respuesta_a,
    y opcionalmente cuenta y publicacion."""
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "fuentes.csv").write_text("fuente_id,nombre,tipo\nf01,Diario de prueba,medio\n", encoding="utf-8")
    publicaciones = sorted({c.get("publicacion", "p001") for c in comentarios})
    with gzip.open(carpeta / "publicaciones.csv.gz", "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["publicacion_id", "fuente_id", "fecha", "titular"])
        w.writerows([p, "f01", T0.isoformat(), f"Titular de {p}"] for p in publicaciones)
    cuentas = sorted({c.get("cuenta", "u0001") for c in comentarios})
    with gzip.open(carpeta / "cuentas.csv.gz", "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cuenta_id", "usuario", "fecha_creacion", "seguidores", "siguiendo"])
        w.writerows([c, f"usuario_{c}", "2020-01-01", 10, 10] for c in cuentas)
    with gzip.open(carpeta / "comentarios.csv.gz", "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["comentario_id", "publicacion_id", "cuenta_id", "fecha", "texto", "respuesta_a", "me_gusta"])
        for c in comentarios:
            w.writerow([c["id"], c.get("publicacion", "p001"), c.get("cuenta", "u0001"), c["fecha"], c["texto"],
                        c.get("respuesta_a", ""), 0])
    return carpeta


def conversacion():
    """La conversación de las pruebas chicas del motor (las de la base de la serie) y las marcas de cada caso."""
    filas, k = [], [0]

    def agregar(texto, minutos, padre="", cuenta=None):
        k[0] += 1
        cid = f"c{k[0]:05d}"
        filas.append({"id": cid, "texto": texto, "fecha": (T0 + timedelta(minutes=minutos)).isoformat(),
                      "respuesta_a": padre, "cuenta": cuenta or f"u{k[0] % 40:04d}"})
        return cid

    suelto = agregar(X_AFIRMA[0], -600)  # N9: un comentario suelto 10 horas antes del arranque real
    raices = {}
    for nombre, afirma, refuta, desde in (("X", X_AFIRMA, X_REFUTA, 0), ("Y", Y_AFIRMA, Y_REFUTA, 60)):
        tops = [agregar(afirma[i % 3], desde + i) for i in range(30)]
        # Cada refutación responde a una de las afirmaciones: el grupo se responde mucho entre sí.
        respuestas = [agregar(refuta[i % 3], desde + 40 + i, padre=tops[i // 3]) for i in range(24)]
        raices[nombre] = (tops, respuestas)
    tops_x, resp_x = raices["X"]
    tops_y, resp_y = raices["Y"]
    agregar(Y_REFUTA[0], 200, padre=tops_x[0])  # N4: una sola respuesta une a X con Y
    tal_cual_r = agregar("tal cual", 210, padre=resp_x[0])  # N2 y N7: acompaña a una refutación
    for i in range(9):
        agregar("tal cual", 211 + i, padre=resp_x[i + 1] if i % 2 else tops_x[i])
    tal_cual_solo = agregar("tal cual", 230)  # N2: suelto, sin padre
    f100 = [agregar("que calor hace hoy en el pueblo", 300 + i) for i in range(99)]
    f100.append(agregar("que calor hace hoy en el pueblo", 400, padre=tops_x[1]))  # N3: una sola respuesta
    f10 = [agregar("el viento se llevo los techos", 500 + i, padre=tops_x[i % 30] if i < 10 else "") for i in range(100)]
    ruido = [agregar(t, 700 + i) for i, t in enumerate(RUIDO)]
    iguales = [agregar("comentario repetido tres veces igual", 800 + i) for i in range(3)]
    marcas = {"suelto": suelto, "tops_x": tops_x, "resp_x": resp_x, "tops_y": tops_y, "tal_cual_r": tal_cual_r,
              "tal_cual_solo": tal_cual_solo, "f100": f100, "f10": f10, "ruido": ruido, "iguales": iguales}
    return filas, marcas


@pytest.fixture(scope="session")
def conversacion_corrida(tmp_path_factory):
    """La conversación corrida hasta el puente, con la configuración congelada (sin modelo)."""
    from pipeline.acompanamientos import Conversacion
    from pipeline.configuracion import CONFIG
    from pipeline.familias import familias_de_nucleos
    from pipeline.lectura import leer
    from pipeline.preparacion import preparar
    from pipeline.puente import armar_narrativas

    filas, marcas = conversacion()
    carpeta = escribir_set(tmp_path_factory.mktemp("conversacion"), filas)
    lectura = leer(carpeta)
    com, textos, _, _ = preparar(lectura.comentarios, CONFIG)
    conv = Conversacion(com, max_palabras=CONFIG["n2_max_palabras"], min_respuesta=CONFIG["n2_min_respuesta"],
                        max_pasos=CONFIG["n2_max_pasos"], offset_s=lectura.offset_s)
    familia, _ = familias_de_nucleos(conv.nucleos, CONFIG["n1_umbral"])
    info = {}
    pred, signo, propia = armar_narrativas(conv, familia, CONFIG, info)
    return {"carpeta": carpeta, "lectura": lectura, "com": com, "textos": textos, "conv": conv, "familia": familia,
            "pred": pred, "signo": signo, "propia": propia, "info": info, "marcas": marcas}
