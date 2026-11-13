"""El servidor de delfOS: escucha solo en esta computadora y atiende a la ventana de la aplicación.

Tiene dos resguardos, porque puede copiar archivos, correr el análisis y guardar la clave de IA:

- Solo acepta pedidos dirigidos a `127.0.0.1` o `localhost` en su puerto.
- Todo pedido lleva una contraseña de un solo uso, que se genera al arrancar y que solo conoce la página de la
  aplicación. Una página de internet abierta en otra pestaña no puede leerla ni mandarla.

No registra los pedidos ni sus contenidos.
"""
import base64
import hashlib
import html
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from pipeline import VERSION as VERSION_DEL_MOTOR
from tablero.pagina import (MARCA, TEMA_AL_ABRIR, estilo_del_sistema, leer_identidad, leer_textos, logotipo,
                            para_incrustar, simbolo_svg)

from delfos import analisis, clave, explorador, proyectos
from delfos.proyectos import ErrorDeProyecto
from delfos.rutas import RAIZ, carpeta_config, descargas

WEB = Path(__file__).parent / "web"
PUERTO = 8765
SIN_LATIDO_S = 300  # sin ninguna ventana abierta durante este tiempo, el servidor se cierra solo
MAX_CUERPO = 1 << 20
CODIGO = (".py", ".js", ".css", ".html", ".json", ".txt", ".svg")  # lo que cambia cuando cambia la aplicación
NAVEGADORES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
               "microsoft-edge-stable", "brave-browser")


def huella_del_codigo() -> str:
    """Una huella del código de la aplicación tal como está en el disco: cambia si cambia cualquier archivo."""
    h = hashlib.sha256()
    for carpeta in ("delfos", "tablero", "pipeline"):
        for ruta in sorted((RAIZ / carpeta).rglob("*")):
            if ruta.is_file() and ruta.suffix in CODIGO and "__pycache__" not in ruta.parts:
                h.update(ruta.relative_to(RAIZ).as_posix().encode("utf-8"))
                h.update(ruta.read_bytes())
    return h.hexdigest()[:12]


def _manejador(servidor):
    class Manejador(BaseHTTPRequestHandler):
        server_version = "delfOS"

        def log_message(self, *args):
            pass

        def responder(self, estado: int, cuerpo: bytes, tipo: str, extra: dict = None):
            self.send_response(estado)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for nombre, valor in (extra or {}).items():
                self.send_header(nombre, valor)
            self.end_headers()
            self.wfile.write(cuerpo)

        def json(self, contenido, estado: int = 200):
            self.responder(estado, json.dumps(contenido, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")

        def error(self, estado: int, mensaje: str):
            self.json({"error": mensaje}, estado)

        def _cuerpo(self) -> dict:
            largo = int(self.headers.get("Content-Length") or 0)
            if largo > MAX_CUERPO:
                raise ErrorDeProyecto("El pedido es demasiado grande.")
            try:
                contenido = json.loads(self.rfile.read(largo) or b"{}") if largo else {}
            except ValueError:
                raise ErrorDeProyecto("El pedido no se entiende.") from None
            return contenido if isinstance(contenido, dict) else {}

        def _atender(self, metodo: str):
            try:
                if (self.headers.get("Host") or "").lower() not in servidor.hosts:
                    return self.error(403, "Pedido rechazado.")
                url = urlsplit(self.path)
                consulta = {k: v[0] for k, v in parse_qs(url.query).items()}
                partes = [p for p in url.path.split("/") if p]
                if metodo == "GET" and not partes:
                    return self.responder(200, servidor.pagina(), "text/html; charset=utf-8")
                if metodo == "GET" and partes == ["favicon.ico"]:
                    return self.responder(204, b"", "image/x-icon")
                if metodo == "GET" and partes == ["api", "latido"]:
                    servidor.ultimo_latido = time.time()
                    return self.json({"delfos": True, "version": servidor.version, "pid": os.getpid(),
                                      "ocupada": analisis.hay_en_curso()})
                contrasena = self.headers.get("X-Delfos-Token") or consulta.get("t") or ""
                if not secrets.compare_digest(contrasena.encode(), servidor.token.encode()):
                    return self.error(403, "Pedido rechazado.")
                servidor.rutear(self, metodo, partes, consulta, self._cuerpo() if metodo == "POST" else {})
            except ErrorDeProyecto as e:
                self.error(400, str(e))
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:  # un error propio no tiene que dejar la ventana colgada
                traceback.print_exc()
                self.error(500, "Algo falló dentro de delfOS. Volvé a intentarlo.")

        def do_GET(self):
            self._atender("GET")

        def do_POST(self):
            self._atender("POST")

        def do_DELETE(self):
            self._atender("DELETE")

    return Manejador


class Servidor:
    def __init__(self, puerto: int = PUERTO):
        self.token = secrets.token_urlsafe(24)
        self.version = huella_del_codigo()  # el código con que arrancó: si después cambia en el disco, esta instancia quedó vieja
        try:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", puerto), _manejador(self))
        except OSError:  # el puerto está ocupado: cualquiera libre
            self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _manejador(self))
        self.httpd.daemon_threads = True
        self.puerto = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.puerto}/"
        self.hosts = {f"127.0.0.1:{self.puerto}", f"localhost:{self.puerto}"}
        self.ultimo_latido = time.time()

    # --- La página -------------------------------------------------------------------------------------

    def pagina(self) -> bytes:
        identidad = leer_identidad()
        partes = {
            "NOMBRE": html.escape(identidad["nombre"]), "LOGOTIPO": logotipo(identidad["nombre"]), "TEMA": TEMA_AL_ABRIR,
            "ICONO": base64.b64encode((MARCA / "icono.svg").read_bytes()).decode("ascii"),
            "SISTEMA": estilo_del_sistema(), "ESTILO": (WEB / "app.css").read_text(encoding="utf-8"),
            "CODIGO": (WEB / "app.js").read_text(encoding="utf-8"),
            "ARRANQUE": para_incrustar({"token": self.token, "nombre": identidad["nombre"],
                                        "pasos": list(analisis.PASOS), "consejos": leer_textos()["consejos"],
                                        "version_del_motor": VERSION_DEL_MOTOR, "simbolo": simbolo_svg(),
                                        "delfin": (MARCA / "delfin.txt").read_text(encoding="utf-8")})}
        plantilla = (WEB / "index.html").read_text(encoding="utf-8")
        return re.sub(r"__([A-Z]+)__", lambda m: partes[m.group(1)], plantilla).encode("utf-8")

    # --- Los pedidos -----------------------------------------------------------------------------------

    def _proyecto(self, proyecto_id: str) -> dict:
        proyecto = proyectos.leer(proyecto_id)
        corriendo = analisis.en_curso(proyecto_id)
        if corriendo:
            proyecto.update(estado="analizando", progreso=corriendo.como_dict())
        return proyecto

    def estado(self) -> dict:
        return {"clave": clave.estado(), "proyectos": [self._proyecto(p["id"]) for p in proyectos.listar()],
                "sugerencias": {"datos": str(descargas()), "base": str(proyectos.carpeta_base())}}

    def rutear(self, m, metodo: str, partes: list, consulta: dict, cuerpo: dict):
        if metodo == "GET" and len(partes) == 3 and partes[0] == "proyectos" and partes[2] in ("tablero.html", "exportar"):
            return self._tablero(m, partes[1], descargar=partes[2] == "exportar")
        if partes[0] != "api":
            return m.error(404, "No existe.")
        ruta = partes[1:]
        if metodo == "GET" and ruta == ["estado"]:
            return m.json(self.estado())
        if metodo == "GET" and ruta == ["carpetas"]:
            return m.json(explorador.listar(consulta.get("ruta", "")))
        if ruta == ["clave"] and metodo in ("POST", "DELETE"):
            if metodo == "POST":
                clave.guardar(cuerpo.get("clave", ""))
            else:
                clave.borrar()
            return m.json({"clave": clave.estado()})
        if metodo == "POST" and ruta == ["proyectos"]:
            creado = proyectos.crear(cuerpo.get("nombre", ""), cuerpo.get("datos", ""), cuerpo.get("base", ""))
            return m.json(self._proyecto(creado["id"]))
        if len(ruta) in (2, 3) and ruta[0] == "proyectos":
            proyecto_id, accion = ruta[1], ruta[2] if len(ruta) == 3 else ""
            if metodo == "GET" and not accion:
                return m.json(self._proyecto(proyecto_id))
            if metodo == "DELETE" and not accion:
                if analisis.en_curso(proyecto_id):
                    raise ErrorDeProyecto("Este proyecto se está analizando. Cancelá el análisis antes de quitarlo.")
                proyectos.quitar(proyecto_id)
                return m.json({"quitado": proyecto_id})
            if metodo == "POST" and accion == "analizar":
                analisis.iniciar(proyecto_id)
                return m.json(self._proyecto(proyecto_id))
            if metodo == "POST" and accion == "cancelar":
                analisis.cancelar(proyecto_id)
                return m.json(self._proyecto(proyecto_id))
            if metodo == "POST" and accion == "abrir-carpeta":
                abrir_carpeta(proyectos.carpeta_de(proyecto_id))
                return m.json({"abierta": True})
            if metodo == "GET" and accion == "comentarios":
                from delfos import comentarios  # carga Polars: recién cuando alguien abre el explorador
                carpeta = proyectos.carpeta_de(proyecto_id)
                if not (carpeta / "resultado" / "comentarios.csv").is_file():
                    raise ErrorDeProyecto("Este proyecto todavía no tiene un análisis.")
                return m.json(comentarios.buscar(carpeta, consulta))
        return m.error(404, "No existe.")

    def _tablero(self, m, proyecto_id: str, descargar: bool):
        proyecto = proyectos.leer(proyecto_id)
        try:
            contenido = (Path(proyecto["carpeta"]) / "tablero.html").read_bytes()
        except OSError:
            return m.error(404, "Este proyecto todavía no tiene un tablero.")
        extra = {}
        if descargar:
            nombre = quote(f"{proyectos.NOMBRE_APP} - {proyecto['nombre']}.html")
            extra["Content-Disposition"] = f"attachment; filename=\"tablero.html\"; filename*=UTF-8''{nombre}"
        m.responder(200, contenido, "text/html; charset=utf-8", extra)

    # --- La vida del servidor --------------------------------------------------------------------------

    def _vigilar(self):
        while True:
            time.sleep(15)
            if time.time() - self.ultimo_latido > SIN_LATIDO_S and not analisis.hay_en_curso():
                self.httpd.shutdown()
                return

    def servir(self, vigilar: bool = True):
        """Atiende hasta que lo cierren. Con `vigilar`, se cierra solo si ya no queda ninguna ventana abierta."""
        if vigilar:
            threading.Thread(target=self._vigilar, daemon=True).start()
        self.httpd.serve_forever()

    def cerrar(self):
        analisis.cancelar_todos()
        self.httpd.server_close()


def abrir_carpeta(carpeta: Path):
    if not carpeta.is_dir():
        raise ErrorDeProyecto("No se encuentra la carpeta del proyecto.")
    try:
        if sys.platform.startswith("win"):
            os.startfile(carpeta)
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(carpeta)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        raise ErrorDeProyecto("No se pudo abrir la carpeta.") from e


def _navegadores() -> list:
    """Los navegadores que pueden abrir una ventana propia: los del PATH y, en Windows, Chrome y Edge donde se instalan."""
    encontrados = [shutil.which(nombre) for nombre in NAVEGADORES]
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(variable)
        for relativa in ("Google/Chrome/Application/chrome.exe", "Microsoft/Edge/Application/msedge.exe"):
            if base and (Path(base) / relativa).is_file():
                encontrados.append(str(Path(base) / relativa))
    return [ruta for ruta in encontrados if ruta]


def abrir_ventana(url: str):
    """Abre la aplicación en una ventana propia si hay un navegador que lo permita; si no, en una pestaña."""
    for ruta in _navegadores():
        try:
            subprocess.Popen([ruta, f"--app={url}", "--window-size=1440,900"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return
        except OSError:
            continue
    webbrowser.open(url)


def _ruta_instancia() -> Path:
    return carpeta_config() / "servidor.json"


def instancia_abierta():
    """Un delfOS que ya está corriendo: su dirección, su proceso, si corre el código de ahora y si está analizando. O None."""
    try:
        puerto = int(json.loads(_ruta_instancia().read_text(encoding="utf-8"))["puerto"])
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/latido", timeout=1.5) as r:
            latido = json.loads(r.read())
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(latido, dict) or not latido.get("delfos"):
        return None
    return {"url": f"http://127.0.0.1:{puerto}/", "pid": latido.get("pid"), "ocupada": bool(latido.get("ocupada")),
            "al_dia": latido.get("version") == huella_del_codigo()}


def cerrar_instancia(instancia: dict) -> bool:
    """Cierra un delfOS que quedó corriendo con una versión anterior del código. Dice si se cerró."""
    pid = instancia.get("pid")
    if not isinstance(pid, int) or pid == os.getpid():
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    for _ in range(50):  # hasta 5 segundos
        time.sleep(0.1)
        try:
            urllib.request.urlopen(instancia["url"] + "api/latido", timeout=0.5).close()
        except OSError:
            return True
    return False


def anotar_instancia(servidor: Servidor):
    ruta = _ruta_instancia()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"puerto": servidor.puerto, "pid": os.getpid()}) + "\n", encoding="utf-8")


def borrar_instancia():
    """Borra la anotación de esta instancia. Si ya la reemplazó otra, la anotación es de la otra y se deja."""
    try:
        if json.loads(_ruta_instancia().read_text(encoding="utf-8")).get("pid") in (None, os.getpid()):
            _ruta_instancia().unlink(missing_ok=True)
    except (OSError, ValueError, AttributeError):
        pass
