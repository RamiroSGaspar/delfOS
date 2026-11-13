"""Lo que Windows no tiene: sin la carpeta `/proc` y sin el módulo `resource`, la corrida tiene que terminar y dar
exactamente la misma entrega. Lo único que se pierde es la medición de la memoria."""
import json
import pathlib
import sys

from conftest import conversacion, escribir_set
from pipeline import escritura
from pipeline.corrida import ejecutar

OFICIALES = ("comentarios.csv", "narrativas.csv", "cuentas.csv")


def como_en_windows(monkeypatch):
    leer = pathlib.Path.read_text

    def sin_proc(self, *args, **kwargs):
        if str(self).startswith("/proc/"):
            raise FileNotFoundError(str(self))
        return leer(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", sin_proc)
    monkeypatch.setitem(sys.modules, "resource", None)  # `import resource` falla, como donde el módulo no existe


def test_la_memoria_se_mide_donde_se_puede_y_queda_en_cero_donde_no(monkeypatch):
    assert escritura.memoria_pico_mib() > 0
    como_en_windows(monkeypatch)
    assert escritura.memoria_pico_mib() == 0.0
    assert "hilos" in escritura.hardware()


def test_la_corrida_termina_y_entrega_lo_mismo(monkeypatch, tmp_path):
    carpeta = escribir_set(tmp_path / "set", conversacion()[0])
    ejecutar(carpeta, tmp_path / "normal", sin_modelo=True)
    como_en_windows(monkeypatch)
    informe = ejecutar(carpeta, tmp_path / "sin_medir", sin_modelo=True)
    for nombre in OFICIALES:
        assert (tmp_path / "sin_medir" / nombre).read_bytes() == (tmp_path / "normal" / nombre).read_bytes()
    costo = json.loads((tmp_path / "sin_medir" / "costo.json").read_text(encoding="utf-8"))
    assert len(costo) == 8 and "memoria pico 0 MiB" in costo["notas"] and informe["memoria_pico_mib"] == 0.0
