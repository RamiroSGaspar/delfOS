"""La página del tablero: un solo archivo HTML con el resumen, los textos, el estilo y el código adentro.

Se abre con doble clic: no pide servidor, internet ni bibliotecas. El aspecto es el del sistema de diseño
«delfOS · Teletipo», que está en `tablero/sistema/`: los dos temas (Papel y Oscuro), las dos tipografías y los
componentes. Las fuentes van adentro de la página, en base64. La marca está en `tablero/marca/` y los textos de
las notas y de los consejos, en `tablero/textos.json`.
"""
import base64
import html
import json
import re
from functools import lru_cache
from pathlib import Path

AQUI = Path(__file__).parent
SISTEMA = AQUI / "sistema"
MARCA = AQUI / "marca"
#           familia            archivo                                    formato     tipo           pesos
FUENTES = (("JetBrains Mono", "JetBrainsMono-Variable.ttf", "truetype", "font/ttf", "100 800"),
           ("Source Serif 4", "source-serif-4-latin-opsz-normal.woff2", "woff2", "font/woff2", "200 900"))
# El tema se pone antes de dibujar la página, para que no parpadee: Papel, salvo que la persona haya elegido Oscuro.
TEMA_AL_ABRIR = ('try{document.documentElement.setAttribute("data-theme",'
                 'localStorage.getItem("delfos-tema")==="oscuro"?"oscuro":"papel")}catch(e){}')


def leer_identidad(ruta=None) -> dict:
    return json.loads(Path(ruta or AQUI / "identidad.json").read_text(encoding="utf-8"))


def leer_textos(ruta=None) -> dict:
    return json.loads(Path(ruta or AQUI / "textos.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def estilo_del_sistema() -> str:
    """El CSS del sistema de diseño en un solo texto, con las fuentes adentro: la página no pide ningún archivo."""
    fuentes = []
    for familia, archivo, formato, tipo, pesos in FUENTES:
        datos = base64.b64encode((SISTEMA / "fonts" / archivo).read_bytes()).decode("ascii")
        fuentes.append(f'@font-face {{ font-family: "{familia}"; src: url("data:{tipo};base64,{datos}") '
                       f'format("{formato}"); font-weight: {pesos}; font-style: normal; font-display: block; }}')
    tokens = [linea for linea in (SISTEMA / "tokens.css").read_text(encoding="utf-8").splitlines()
              if not linea.startswith("@font-face")]  # las fuentes ya van arriba, incrustadas
    return "\n".join([*fuentes, *tokens, (SISTEMA / "bundle.css").read_text(encoding="utf-8"),
                      (SISTEMA / "vistas.css").read_text(encoding="utf-8")])


def simbolo_svg() -> str:
    """El símbolo de la marca, para poner dentro de una página: se dibuja con la tinta del tema."""
    return (MARCA / "simbolo.svg").read_text(encoding="utf-8").strip()


def logotipo(nombre: str) -> str:
    """El logotipo compuesto en tipo: la delta, el nombre y sus dos últimas letras en video inverso."""
    cuerpo, final = html.escape(nombre[:-2]), html.escape(nombre[-2:])
    return (f'<span class="marca" role="img" aria-label="{html.escape(nombre)}"><span aria-hidden="true">'
            f'<span class="marca__delta">δ</span> {cuerpo}<span class="marca__os">{final}</span></span></span>')


def para_incrustar(contenido) -> str:
    """JSON listo para ir dentro de una etiqueta: con "<" escapado, ningún texto puede cerrarla."""
    return json.dumps(contenido, ensure_ascii=False).replace("<", "\\u003c")


def armar(resumen: dict, identidad: dict = None, textos: dict = None) -> str:
    identidad = identidad or leer_identidad()
    partes = {
        "NOMBRE": html.escape(identidad["nombre"]), "LOGOTIPO": logotipo(identidad["nombre"]),
        "TEMA": TEMA_AL_ABRIR, "SISTEMA": estilo_del_sistema(),
        "ESTILO": (AQUI / "tablero.css").read_text(encoding="utf-8"),
        "CODIGO": (AQUI / "tablero.js").read_text(encoding="utf-8"),
        "DATOS": para_incrustar(resumen), "TEXTOS": para_incrustar((textos or leer_textos())["notas"]),
    }
    plantilla = (AQUI / "plantilla.html").read_text(encoding="utf-8")
    return re.sub(r"__([A-Z]+)__", lambda m: partes[m.group(1)], plantilla)


def escribir(resumen: dict, ruta, identidad: dict = None) -> Path:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(armar(resumen, identidad), encoding="utf-8")
    return ruta
