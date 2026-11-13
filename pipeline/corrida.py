"""La corrida de punta a punta: lee el set, arma narrativas, posturas, orígenes, títulos y operaciones, y
escribe los 4 archivos oficiales.

El orden lógico es el de la arquitectura (`docs/arquitectura.md`):

    P1 lectura → P3 a P6 preparación → N2 acompañamientos → N1 familias → N3, N4, N5 y N7 puente
    → N8 lado que apoya → N12 plan B → N9 origen → N10 títulos → C coordinación → P2 perfil → escritura

Dos cosas van en paralelo, sin cambiar ningún resultado (cada etapa recibe exactamente lo mismo que en el
orden lógico):
- El trabajo por texto (P4, P5 y el idioma del set) se reparte entre varios procesos (`pipeline.paralelo`).
- Los pedidos al modelo (N8, N12 y N10) salen todos juntos y, mientras el modelo responde, se adelanta
  trabajo que no depende de su respuesta: las capas T, R y P de la coordinación, y la capa S con el perfil.
"""
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from pipeline import VERSION
from pipeline.acompanamientos import Conversacion
from pipeline.configuracion import CONFIG
from pipeline.coordinacion import Coordinacion
from pipeline.escritura import escribir_costo, escribir_csv, hardware, memoria_pico_mib
from pipeline.familias import familias_de_nucleos
from pipeline import enganche as n11
from pipeline.idioma import idioma_del_set, idiomas_con_el_del_set, idiomas_lote
from pipeline.lados import LadoQueApoya
from pipeline.lectura import leer
from pipeline.modelo import MODELO, Modelo
from pipeline.origen import origenes
from pipeline.paralelo import MINIMO_DE_TEXTOS, Repartidor
from pipeline.perfil import medir, resumen
from pipeline.plan_b import PlanB
from pipeline.preparacion import preparar, textos_distintos
from pipeline.texto import normalizar_lote
from pipeline.puente import armar_narrativas
from pipeline.registro import anotar
from pipeline.titulos import Titulos

ALMACENAMIENTO = ("Los 4 archivos del set (CSV con gzip) se leen una vez a tablas en memoria (Polars y NumPy); "
                  "sin base de datos. La salida son CSV en disco y la caché del modelo, un archivo JSONL")


def miles(n) -> str:
    return f"{int(n):,}".replace(",", ".")


class Reloj:
    """Mide el tiempo de cada etapa y el tiempo esperando al modelo."""

    def __init__(self):
        self.tiempos = {}

    @contextmanager
    def etapa(self, nombre: str):
        inicio = time.perf_counter()
        try:
            yield
        finally:
            self.tiempos[nombre] = round(self.tiempos.get(nombre, 0.0) + time.perf_counter() - inicio, 3)

    def esperar(self, tanda, pendientes: list = None, etapa_pendientes: str = None):
        """Los resultados de una tanda de pedidos (o None si no hubo tanda).

        Mientras la tanda no está lista, corre tareas de `pendientes` (que no dependen del modelo), de a una,
        y vuelve a mirar: apenas llegan las respuestas, devuelve, así la etapa siguiente sale enseguida. El
        tiempo que queda sin nada para hacer se anota como espera del modelo.
        """
        if tanda is None:
            return None
        while pendientes and not tanda.lista():
            with self.etapa(etapa_pendientes):
                pendientes.pop(0)()
        with self.etapa("espera_del_modelo"):
            return tanda.resultados()


def ejecutar(carpeta_datos, carpeta_salida, sin_modelo: bool = False, cache=None, inicio: float = None,
             enganche=None, procesos: int = None) -> dict:
    """Corre el pipeline y escribe la entrega en `carpeta_salida`. Devuelve el informe de la corrida.

    `enganche`: si se pasa una ruta, escribe ahí la tabla de N11 para la capa interpretativa (fuera de los 4
    archivos oficiales). `procesos`: cuántos procesos usar para el trabajo por texto (por defecto, los de la
    configuración); quien llame a esta función desde un script propio tiene que protegerlo con
    `if __name__ == "__main__":`, como pide todo programa que arranca procesos en Python.
    """
    inicio = time.perf_counter() if inicio is None else inicio
    cfg = CONFIG
    carpeta_datos, carpeta_salida = Path(carpeta_datos), Path(carpeta_salida)
    reloj = Reloj()
    modelo = Modelo(cache, activo=not sin_modelo, hilos=cfg["modelo_hilos"])
    repartidor = None
    uso = {"llamadas": 0, "tokens": 0, "usd": 0.0}  # lo que suman las respuestas usadas (va a costo.json)
    notas = {}
    anotar(f"pipeline {VERSION} · datos: {carpeta_datos} · salida: {carpeta_salida} · "
           + ("sin modelo" if sin_modelo else f"modelo: {MODELO}" + (f" con caché {cache}" if cache else " sin caché")))
    try:
        # P1 · lectura tolerante.
        with reloj.etapa("lectura"):
            lectura = leer(carpeta_datos)
        anotar(f"  lectura: {miles(lectura.comentarios.height)} comentarios, {miles(len(lectura.cuentas))} cuentas, "
               f"{len(lectura.problemas)} problemas de lectura")

        # P3 a P6 · cada texto distinto una vez: normalización, hashtags y emojis, relleno y núcleos. La
        # normalización y el idioma de cada texto se reparten entre procesos; el idioma se usa recién en P2.
        with reloj.etapa("preparacion"):
            crudos = textos_distintos(lectura.comentarios)
            procesos = cfg["procesos"] if procesos is None else procesos
            repartidor = Repartidor(procesos if len(crudos) >= MINIMO_DE_TEXTOS else 1)
            tarea_normalizar = repartidor.lanzar(normalizar_lote, crudos)
            tarea_idioma = repartidor.lanzar(idiomas_lote, crudos)
            com, textos, muletillas, coletillas = preparar(lectura.comentarios, cfg, crudos,
                                                           tarea_normalizar.resultados())
        notas["preparacion"] = {"textos_distintos": textos.height, "normalizados_distintos": textos["norm"].n_unique(),
                                "muletillas": len(muletillas), "coletillas": len(coletillas)}

        # N2 · acompañamientos (y la estructura de la conversación que usan todas las etapas).
        with reloj.etapa("acompanamientos"):
            conv = Conversacion(com, max_palabras=cfg["n2_max_palabras"], min_respuesta=cfg["n2_min_respuesta"],
                                max_pasos=cfg["n2_max_pasos"], offset_s=lectura.offset_s)
        notas["preparacion"].update({"nucleos": len(conv.nucleos), "nucleos_de_acompanamiento": int(conv.acomp.sum())})

        # N1 · familias.
        with reloj.etapa("familias"):
            familia, aviso_n1 = familias_de_nucleos(conv.nucleos, cfg["n1_umbral"])
        tam = np.bincount(familia) if len(familia) else np.array([0])
        notas["familias"] = {"familias": int(len(tam)), "familias_de_un_nucleo": int((tam == 1).sum()),
                             "salvaguarda": aviso_n1}

        # N3, N4, N5 y N7 · el puente: narrativas, ruido y dos lados.
        notas["puente"] = {}
        with reloj.etapa("puente"):
            pred, signo, propia = armar_narrativas(conv, familia, cfg, notas["puente"])
        anotar(f"  puente: {notas['puente']['comunidades']} narrativas, "
               f"{miles(sum(1 for n in pred if n))} comentarios con narrativa")

        # La coordinación sin narrativas (capas T, R y P, del set real y del barajado) queda como trabajo
        # pendiente: se adelanta mientras el modelo responde.
        with reloj.etapa("coordinacion"):
            coordinacion = Coordinacion(conv, familia, lectura.cuentas, cfg)
            pendientes = coordinacion.tareas_sin_narrativas()

        # N8 · lado que apoya, sobre el puente.
        with reloj.etapa("lado_que_apoya"):
            n8 = LadoQueApoya(conv, pred, signo, cfg)
            tanda_n8 = modelo.lanzar(n8.pedidos()) if modelo.activo and n8.dudosas else None
        respuestas_n8 = reloj.esperar(tanda_n8, pendientes, "coordinacion")
        with reloj.etapa("lado_que_apoya"):
            lado_apoya, detalle_n8 = n8.decidir(respuestas_n8 if modelo.activo else None, uso)
        notas["lado_que_apoya"] = {"narrativas_al_modelo": len(n8.dudosas) if modelo.activo else 0,
                                   "cambian_respecto_de_tope": sorted(n for n, d in detalle_n8.items()
                                                                      if d["cambia_respecto_de_tope"]),
                                   "por_narrativa": detalle_n8}

        # N12 · plan B con el modelo sobre lo que quedó como ruido. Junto con sus pedidos salen, anticipados,
        # los de los títulos (N10) armados sin N12: N12 solo agrega comentarios que eran ruido, así que en
        # general no cambia los núcleos de ningún título y esos pedidos son idénticos a los definitivos (el
        # modelo no repite un pedido idéntico: los definitivos usan la misma respuesta).
        nucleos = com["nucleo"].to_list()
        plan_b, tanda_n12 = None, None
        if modelo.activo:
            with reloj.etapa("plan_b"):
                plan_b = PlanB(conv, familia, pred, signo, propia, lado_apoya, cfg)
                tanda_n12 = modelo.lanzar(plan_b.pedidos()) if plan_b.lotes else None
            if tanda_n12 is not None:
                with reloj.etapa("titulos"):
                    postura_sin_n12 = [("apoya" if s == lado_apoya.get(n, 1) else "rechaza") if n else ""
                                       for n, s in zip(pred, signo.tolist())]
                    anticipados = Titulos(nucleos, pred, postura_sin_n12, propia, cfg)
                    if anticipados.al_modelo:
                        modelo.lanzar(anticipados.pedidos())
        respuestas_n12 = reloj.esperar(tanda_n12, pendientes, "coordinacion")
        if plan_b is not None:
            with reloj.etapa("plan_b"):
                notas["plan_b"] = plan_b.aplicar(respuestas_n12 or [], uso)
            anotar(f"  plan B (N12): {plan_b and len(plan_b.grupos)} familias candidatas, "
                   f"{notas['plan_b']['comentarios_agregados']} comentarios agregados")
        else:
            notas["plan_b"] = {"activo": False}

        # Postura de cada comentario, con el lado que apoya.
        with reloj.etapa("lados"):
            postura = [("apoya" if s == lado_apoya.get(n, 1) else "rechaza") if n else ""
                       for n, s in zip(pred, signo.tolist())]

        # N9 · origen.
        with reloj.etapa("origen"):
            origen = origenes(conv, pred, propia, minimo=cfg["n9_minimo"], ventana_s=int(cfg["n9_ventana_horas"] * 3600))

        # N10 · títulos. Los pedidos salen ya; mientras, la capa S de la coordinación y el perfil.
        with reloj.etapa("titulos"):
            titulos_n10 = Titulos(nucleos, pred, postura, propia, cfg)
            tanda_n10 = modelo.lanzar(titulos_n10.pedidos()) if modelo.activo and titulos_n10.al_modelo else None
        with reloj.etapa("coordinacion"):
            grupo, notas["coordinacion"], avisos_coordinacion = coordinacion.decidir(pred)

        # P2 · perfil de entrada (necesita la cantidad de núcleos y el idioma). Solo avisa.
        with reloj.etapa("idioma"):
            conteo = lectura.comentarios["texto"].value_counts()
            por_texto = dict(zip(conteo["texto"].to_list(), conteo["count"].to_list()))
            idioma = idioma_del_set(tarea_idioma.resultados(), [por_texto.get(t, 0) for t in crudos])
        with reloj.etapa("perfil"):
            perfil = medir(lectura, com, len(conv.nucleos), idioma)
            perfil["avisos"] += avisos_coordinacion
        respuestas_n10 = reloj.esperar(tanda_n10)
        with reloj.etapa("titulos"):
            titulos, detalle_n10 = titulos_n10.decidir(respuestas_n10 if modelo.activo else None, uso)
        notas["titulos"] = detalle_n10

        # Escritura de los 3 CSV oficiales.
        with reloj.etapa("escritura"):
            escribir_csv(carpeta_salida, conv.ids, pred, postura, titulos, origen, lectura.cuentas, grupo)

        # N11 · enganche de la capa interpretativa (opcional): se escribe después de todo y nadie lo lee.
        if enganche:
            with reloj.etapa("enganche"):
                tabla = n11.tabla_enganche(
                    conv, familia, pred, signo, postura, lectura.publicaciones, textos,
                    idiomas_con_el_del_set(tarea_idioma.resultados(), idioma["idioma_del_set"]), titulos, origen,
                    lectura.version_set, f"pipeline {VERSION}")
                notas["enganche"] = n11.escribir(enganche, tabla)
    finally:
        modelo.cerrar()
        if repartidor is not None:
            repartidor.cerrar()

    # costo.json, con el tiempo total del comando y lo que costó el modelo: todas las respuestas distintas de
    # la corrida (las usadas y las anticipadas que no se usaron), vengan de la caché o de la API.
    distintas = modelo.respuestas() if modelo.activo else []
    tokens_ia = sum(r.tokens for r in distintas)
    usd_ia = sum(r.usd for r in distintas)
    n = len(conv.ids)
    narrativas = sorted(set(pred) - {""})
    con_narrativa = sum(1 for x in pred if x)
    segundos = round(time.perf_counter() - inicio, 3)
    memoria = round(memoria_pico_mib(), 1)
    etapas = ", ".join(f"{k} {v:.2f}".replace(".", ",") for k, v in reloj.tiempos.items())
    if sin_modelo:
        sobre_modelo = "Sin modelo de IA (--sin-modelo): N8 por \"tope\", N10 por núcleos y N12 apagado."
    else:
        sobre_modelo = (f"Modelo {MODELO} en N8 (lado que apoya, solo con margen chico), N12 (plan B sobre el ruido) "
                        f"y N10 (títulos): {len(distintas)} pedidos distintos ({uso['llamadas']} respuestas usadas), "
                        f"{modelo.uso['respuestas_de_cache']} de la caché y {modelo.uso['llamadas_api']} llamadas a "
                        f"la API en esta corrida (USD {modelo.uso['usd_gastado']:.6f} gastados ahora; tokens_ia y "
                        f"usd_ia son el costo de todos los pedidos, vengan o no de la caché).")
    costo = {
        "comentarios_procesados": n,
        "segundos": segundos,
        "tokens_ia": tokens_ia,
        "usd_ia": round(usd_ia, 6),
        "usd_por_mil_comentarios": round(1000 * usd_ia / max(n, 1), 6),
        "hardware": hardware(),
        "almacenamiento": ALMACENAMIENTO,
        "notas": (f"Pipeline {VERSION}: narrativas por estructura (núcleos, familias y puente por respuestas con "
                  f"Louvain), lado que apoya, origen \"3 en 3 horas\" y coordinación en cuatro capas con alarma por "
                  f"barajado. {sobre_modelo} Segundos: tiempo de pared del comando, de la lectura a la escritura; "
                  f"memoria pico {memoria:.0f} MiB. Etapas en segundos: {etapas}. "
                  + resumen(perfil["avisos"])),
    }
    escribir_costo(carpeta_salida, costo)

    conteos = {"comentarios": n, "narrativas": len(narrativas), "comentarios_con_narrativa": con_narrativa,
               "ruido": n - con_narrativa, "cuentas": len(lectura.cuentas), "cuentas_marcadas": len(grupo),
               "operaciones": len(set(grupo.values()))}
    anotar(f"  narrativas: {conteos['narrativas']} · con narrativa: {miles(con_narrativa)} · ruido: "
           f"{miles(conteos['ruido'])} · cuentas marcadas: {conteos['cuentas_marcadas']} · operaciones: "
           f"{conteos['operaciones']}")
    for aviso in perfil["avisos"]:
        anotar(f"  aviso: {aviso}")
    anotar(f"  listo en {segundos:.1f} s · memoria pico {memoria:.0f} MiB · modelo: {uso['llamadas']} respuestas "
           f"usadas ({modelo.uso['respuestas_de_cache']} de la caché, {modelo.uso['llamadas_api']} a la API, "
           f"{modelo.uso['errores']} errores)")
    return {"version": VERSION, "datos": str(carpeta_datos), "salida": str(carpeta_salida), "sin_modelo": sin_modelo,
            "cache": str(cache) if cache else None, "segundos": segundos, "memoria_pico_mib": memoria,
            "tiempos": reloj.tiempos, "conteos": conteos, "costo": costo, "uso_modelo": {**uso, **modelo.uso},
            "perfil": perfil, "notas": notas, "configuracion": cfg}
