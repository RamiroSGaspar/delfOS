"""Acceso al modelo de IA: Claude Haiku 5.5, con pedidos en paralelo y caché en disco.

Reglas:
- **Modelo fijo** `claude-haiku-5-5`: cualquier otro se rechaza antes de llamar.
- **Clave:** de la variable `ANTHROPIC_API_KEY` o, si no está, del archivo
  `~/.config/qualydata/anthropic_api_key`. Nunca se imprime ni se escribe en ningún archivo.
- **Caché** (opcional, `--cache`): un archivo `.jsonl` con una línea por pedido, de la forma
  `{"huella_pedido", "fecha", "pedido", "respuesta"}`. La huella es el SHA-256 del pedido completo (modelo,
  tope de tokens, esfuerzo, sistema y mensajes), así que el mismo pedido da siempre la misma respuesta y
  no se vuelve a pagar. La caché no tiene secretos: solo pedidos y respuestas. Es el mismo formato que
  usaba la serie de experimentos, así que sus cachés sirven tal cual.
- **En paralelo:** `lanzar` manda una tanda de pedidos a la vez (hasta `modelo_hilos` simultáneos) y
  devuelve enseguida; `Tanda.resultados()` espera y devuelve las respuestas **en el orden de los pedidos**,
  sea cual sea el orden en que llegaron. Así el resultado no depende de la red.
- **Un pedido idéntico, una sola vez por corrida:** si se lanza un pedido igual a otro ya lanzado (aunque
  todavía no haya respondido), se usa esa misma respuesta. Es lo que permite anticipar pedidos sin pagarlos
  dos veces.
- **Si falla** (sin clave, sin conexión, una negativa del modelo), el resultado de ese pedido es un
  `ErrorModelo` y la etapa que lo pidió usa su respaldo. El pipeline nunca se corta por el modelo.
- **Costo:** USD 0,10 por millón de tokens de entrada y 0,50 por millón de salida (0,50 y 2,50 si el
  pedido pasa los 100.000 tokens de entrada). Una respuesta de la caché trae el costo que tuvo cuando se
  generó: es el costo equivalente de procesar el set, el que va a `costo.json`.
"""
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pipeline.registro import anotar

MODELO = "claude-haiku-5-5"
VARIABLE_CLAVE = "ANTHROPIC_API_KEY"
RUTA_CLAVE = Path.home() / ".config" / "qualydata" / "anthropic_api_key"
USD_ENTRADA = 0.10 / 1_000_000
USD_SALIDA = 0.50 / 1_000_000
LIMITE_PEDIDO_CORTO = 100_000
USD_ENTRADA_LARGO = 0.50 / 1_000_000
USD_SALIDA_LARGO = 2.50 / 1_000_000
ESFUERZOS = ("low", "medium", "high", "xhigh", "max")


class ErrorModelo(RuntimeError):
    """Un problema al usar el modelo, explicado en castellano. La etapa que lo recibe usa su respaldo."""


@dataclass(frozen=True)
class Pedido:
    """Un pedido al modelo: el texto del usuario, las instrucciones de sistema, el tope de tokens y el esfuerzo."""
    texto: str
    sistema: str
    max_tokens: int
    esfuerzo: str

    def parametros(self) -> dict:
        """Los parámetros de la API, en el mismo orden y forma que usaba la serie (la huella depende de esto)."""
        p = {"model": MODELO, "max_tokens": int(self.max_tokens), "output_config": {"effort": self.esfuerzo},
             "messages": [{"role": "user", "content": self.texto}]}
        if self.sistema:
            p["system"] = self.sistema
        return p

    def huella(self) -> str:
        texto = json.dumps(self.parametros(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(texto.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Respuesta:
    texto: str
    modelo: str  # el modelo que respondió
    tokens_entrada: int
    tokens_salida: int
    usd: float  # lo que costó generar esta respuesta, aunque ahora venga de la caché
    desde_cache: bool
    motivo_fin: str  # stop_reason de la API
    cortada: bool  # True si se quedó sin tokens (stop_reason max_tokens)

    @property
    def tokens(self) -> int:
        return self.tokens_entrada + self.tokens_salida


def costo_usd(tokens_entrada: int, tokens_salida: int) -> float:
    if tokens_entrada > LIMITE_PEDIDO_CORTO:
        return tokens_entrada * USD_ENTRADA_LARGO + tokens_salida * USD_SALIDA_LARGO
    return tokens_entrada * USD_ENTRADA + tokens_salida * USD_SALIDA


def leer_clave():
    """La clave de la API, o None si no hay. Nunca se imprime."""
    clave = os.environ.get(VARIABLE_CLAVE, "").strip()
    if clave:
        return clave
    try:
        return RUTA_CLAVE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _respuesta_de(guardada: dict, desde_cache: bool) -> Respuesta:
    return Respuesta(texto=guardada["texto"], modelo=guardada["modelo"], tokens_entrada=int(guardada["tokens_entrada"]),
                     tokens_salida=int(guardada["tokens_salida"]), usd=float(guardada["usd"]), desde_cache=desde_cache,
                     motivo_fin=guardada["motivo_fin"], cortada=guardada["motivo_fin"] == "max_tokens")


class Tanda:
    """Pedidos ya lanzados. `resultados()` espera y devuelve, en el orden de los pedidos, una Respuesta o un
    ErrorModelo por pedido."""

    def __init__(self, futuros: list):
        self._futuros = futuros
        self.inicio = time.perf_counter()

    def lista(self) -> bool:
        """Si ya llegaron todas las respuestas."""
        return all(f.done() for f in self._futuros)

    def resultados(self) -> list:
        salida = []
        for f in self._futuros:
            try:
                salida.append(f.result())
            except ErrorModelo as e:
                salida.append(e)
        return salida


class Modelo:
    """El acceso al modelo para una corrida. Con `activo=False` (la opción `--sin-modelo`) no llama nunca."""

    def __init__(self, cache=None, activo: bool = True, hilos: int = 8):
        self.activo = activo
        self.ruta_cache = Path(cache) if cache else None
        self._bloqueo = threading.Lock()
        self._cliente = None
        self._sin_clave_avisado = False
        self._cache = self._leer_cache() if self.ruta_cache else {}
        self._hilos = ThreadPoolExecutor(max_workers=max(1, int(hilos)), thread_name_prefix="modelo") if activo else None
        self._lanzados = {}  # huella -> futuro, en el orden en que se lanzó cada pedido distinto
        self.uso = {"pedidos": 0, "llamadas_api": 0, "respuestas_de_cache": 0, "errores": 0, "usd_gastado": 0.0,
                    "segundos_de_api": 0.0}

    # ------------------------------------------------------------------ uso público
    def lanzar(self, pedidos: list) -> Tanda:
        """Manda los pedidos en paralelo y devuelve enseguida. Un pedido ya lanzado en esta corrida no se
        vuelve a mandar: se usa el mismo resultado."""
        if not self.activo:
            raise ErrorModelo("el modelo está apagado (--sin-modelo)")
        futuros = []
        for p in pedidos:
            huella = p.huella()
            if huella not in self._lanzados:
                self._lanzados[huella] = self._hilos.submit(self.preguntar, p)
            futuros.append(self._lanzados[huella])
        return Tanda(futuros)

    def respuestas(self) -> list:
        """Las respuestas de todos los pedidos distintos de la corrida (de la caché o de la API), en el orden en
        que se lanzaron, aunque alguna no se haya usado. Es lo que costó procesar el set."""
        salida = []
        for f in self._lanzados.values():
            try:
                salida.append(f.result())
            except ErrorModelo:
                pass
        return salida

    def preguntar(self, pedido: Pedido) -> Respuesta:
        """Un pedido: de la caché si ya se hizo; si no, a la API. Lanza ErrorModelo si no se puede."""
        if not self.activo:
            raise ErrorModelo("el modelo está apagado (--sin-modelo)")
        if pedido.esfuerzo not in ESFUERZOS:
            raise ErrorModelo(f"esfuerzo tiene que ser uno de {ESFUERZOS}; se pidió {pedido.esfuerzo!r}")
        huella = pedido.huella()
        with self._bloqueo:
            self.uso["pedidos"] += 1
            guardada = self._cache.get(huella)
            if guardada is not None:
                self.uso["respuestas_de_cache"] += 1
                return _respuesta_de(guardada, desde_cache=True)
        try:
            return self._llamar(pedido, huella)
        except ErrorModelo:
            with self._bloqueo:
                self.uso["errores"] += 1
            raise

    def cerrar(self):
        if self._hilos is not None:
            self._hilos.shutdown(wait=True)

    # ------------------------------------------------------------------ interno
    def _leer_cache(self) -> dict:
        cache = {}
        if not self.ruta_cache.exists():
            return cache
        with open(self.ruta_cache, encoding="utf-8") as f:
            for linea in f:
                try:
                    fila = json.loads(linea)
                except json.JSONDecodeError:
                    continue  # una línea rota (un proceso cortado a mitad) se saltea
                if isinstance(fila, dict) and "huella_pedido" in fila and "respuesta" in fila:
                    cache[fila["huella_pedido"]] = fila["respuesta"]
        return cache

    def _guardar(self, huella: str, pedido: Pedido, guardada: dict):
        """Agrega la respuesta a la caché en disco (con el bloqueo tomado)."""
        self._cache[huella] = guardada
        if self.ruta_cache is None:
            return
        self.ruta_cache.parent.mkdir(parents=True, exist_ok=True)
        fila = {"huella_pedido": huella, "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
                "pedido": pedido.parametros(), "respuesta": guardada}
        with open(self.ruta_cache, "a+", encoding="utf-8") as f:
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:  # si quedó una línea a medias, se empieza una nueva
                f.seek(f.tell() - 1)
                if f.read(1) != "\n":
                    f.write("\n")
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")

    def _cliente_api(self):
        with self._bloqueo:
            if self._cliente is not None:
                return self._cliente
            clave = leer_clave()
            if not clave:
                if not self._sin_clave_avisado:
                    self._sin_clave_avisado = True
                    anotar(f"  modelo: no hay clave (ni {VARIABLE_CLAVE} ni ~/.config/qualydata/anthropic_api_key); "
                           "los pedidos que no están en la caché usan el respaldo de su etapa")
                raise ErrorModelo("no hay clave de la API")
            try:
                import anthropic
            except ImportError:
                raise ErrorModelo("falta el paquete anthropic (pip install -r requirements.txt)") from None
            self._cliente = (anthropic.Anthropic(api_key=clave, max_retries=3, timeout=120.0), anthropic)
            return self._cliente

    def _llamar(self, pedido: Pedido, huella: str) -> Respuesta:
        cliente, anthropic = self._cliente_api()
        inicio = time.perf_counter()
        try:
            r = cliente.messages.create(**pedido.parametros())
        except Exception as e:  # se traduce a un mensaje claro; la clave nunca aparece
            raise ErrorModelo(_mensaje_de_error(e, anthropic)) from None
        segundos = time.perf_counter() - inicio
        u = r.usage
        tokens_entrada = (u.input_tokens or 0) + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
        tokens_salida = u.output_tokens or 0
        usd = costo_usd(tokens_entrada, tokens_salida)
        texto = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        guardada = {"id": r.id, "modelo": r.model, "texto": texto, "motivo_fin": r.stop_reason,
                    "tokens_entrada": tokens_entrada, "tokens_salida": tokens_salida, "usd": usd}
        error = None
        if not str(r.model).startswith(MODELO):
            error = f"respondió otro modelo ({r.model}) en vez de {MODELO}"
        elif r.stop_reason == "refusal":
            error = "el modelo se negó a responder (stop_reason refusal)"
        with self._bloqueo:
            self.uso["llamadas_api"] += 1
            self.uso["usd_gastado"] += usd
            self.uso["segundos_de_api"] += segundos
            if error is None:
                self._guardar(huella, pedido, guardada)
        if error is not None:
            raise ErrorModelo(error)
        return _respuesta_de(guardada, desde_cache=False)


def _mensaje_de_error(e: Exception, anthropic) -> str:
    if isinstance(e, anthropic.BadRequestError):
        return f"la API rechazó el pedido por inválido (400): {e.message}"
    if isinstance(e, anthropic.AuthenticationError):
        return "la clave de la API no es válida o fue revocada (401)"
    if isinstance(e, anthropic.PermissionDeniedError):
        return f"la clave no tiene permiso para este pedido (403): {e.message}"
    if isinstance(e, anthropic.NotFoundError):
        return f"el modelo {MODELO} no existe o la cuenta no tiene acceso (404): {e.message}"
    if isinstance(e, anthropic.RateLimitError):
        return "la API limitó la cantidad de pedidos (429) y siguió limitando después de 3 reintentos"
    if isinstance(e, anthropic.APIStatusError):
        if e.status_code >= 500:
            return f"error del servidor de la API ({e.status_code}) después de 3 reintentos"
        return f"error de la API ({e.status_code}): {e.message}"
    if isinstance(e, anthropic.APITimeoutError):
        return "la API no respondió a tiempo (120 s por intento, 3 reintentos)"
    if isinstance(e, anthropic.APIConnectionError):
        return "no hay conexión con la API"
    return f"error inesperado al llamar al modelo: {type(e).__name__}"
