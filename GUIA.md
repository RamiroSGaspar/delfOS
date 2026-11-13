# Guía: instalar, usar y probar delfOS

Todo se hace desde la carpeta del repositorio. Está probado en Linux, con Python 3.12.

1. [Qué hace falta](#1-qué-hace-falta)
2. [Instalar](#2-instalar)
3. [Conseguir los datos](#3-conseguir-los-datos)
4. [Usar la aplicación](#4-usar-la-aplicación)
5. [Usar la terminal](#5-usar-la-terminal)
6. [Qué archivos salen](#6-qué-archivos-salen)
7. [Comprobar que funciona](#7-comprobar-que-funciona)
8. [Si algo falla](#8-si-algo-falla)

## 1. Qué hace falta

- **Python 3.9 o superior.** Para comprobarlo: `python3 --version`.
- **Internet, una sola vez**, para instalar las bibliotecas. Ocupan unos 550 MB.
- **Chrome, Chromium o Edge**, si se quiere la aplicación en ventana propia. Sin ellos se abre en una pestaña del
  navegador.
- **Una clave de Anthropic, opcional.** Sin clave todo funciona; cambian solo los títulos de las narrativas.

Si no tenés Python:

| Sistema | Cómo instalarlo |
|---|---|
| Ubuntu, Debian o Mint | `sudo apt install python3 python3-venv python3-pip` |
| Fedora | `sudo dnf install python3` |
| Arch o Manjaro | `sudo pacman -S python` |
| macOS | `brew install python`, o el instalador de [python.org](https://www.python.org/downloads/) |
| Windows | El instalador de [python.org](https://www.python.org/downloads/), marcando "Add python.exe to PATH" |

## 2. Instalar

Se hace una sola vez.

**Linux y macOS:**

```bash
./instalar.sh
```

**Windows:** doble clic en `instalar.bat`.

El instalador arma el entorno de Python dentro de la carpeta (`.venv/`) e instala las bibliotecas de
`requirements.txt`. En Linux deja además "delfOS" en el menú de aplicaciones. No instala nada fuera de la carpeta.

**A mano**, sin el instalador, es lo mismo en tres pasos:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Conseguir los datos

delfOS trabaja con una carpeta que tenga los 4 archivos de un set, con el formato del desafío:

| Archivo | Qué tiene |
|---|---|
| `comentarios.csv.gz` | Los comentarios |
| `publicaciones.csv.gz` | Las publicaciones que se comentan |
| `fuentes.csv` | Las fuentes de esas publicaciones |
| `cuentas.csv.gz` | Las cuentas que comentan |

El **set final** se descarga de
[Releases del desafío](https://github.com/qualydata-org/desafio-qualydata/releases/tag/set-final). Para los
comandos de esta guía, sus 4 archivos van en `datos/final/`, dentro de la carpeta del repositorio. Para la
aplicación pueden estar en cualquier carpeta.

## 4. Usar la aplicación

**Abrirla.** En Linux y macOS:

```bash
./abrir.sh
```

En Windows, doble clic en `abrir.bat`. En Linux también está "delfOS" en el menú de aplicaciones.

**Crear un proyecto.** Un proyecto es un set de comentarios y su análisis.

1. Tocá **Agregar datos**.
2. En "Los datos", tocá **Elegir carpeta** y buscá la carpeta con los 4 archivos. Cuando la encontrás, dice "Esta
   carpeta tiene los 4 archivos del set". Tocá **Elegir esta carpeta**.
3. Poné un nombre y tocá **Crear proyecto**. Los datos se copian al proyecto; los originales no se tocan.

**Analizar.** Tocá **Analizar comentarios**. La pantalla muestra los pasos por los que va el análisis y se puede
cancelar. Con el set final tarda menos de medio minuto.

**Leer el tablero.** Al terminar aparece solo.

- El **Resumen** responde tres preguntas, cada una en su ventana: qué circula, quién lo empuja y desde cuándo.
- **Tocá cualquier cifra, fila, gráfico o tabla:** a la derecha aparece su nota, con qué muestra y cómo se obtiene.
- **Elegí una narrativa:** se resalta en todas las ventanas a la vez.
- Las demás pestañas muestran el detalle: **Qué circula**, **Desde cuándo**, **Quién lo empuja**, **Dónde
  circula**, **Comentarios** (uno por uno, con filtros) y **La corrida** (tiempo y costo).
- Arriba a la derecha, **[ ] Oscuro** cambia el tema.

**Los menús:**

| Menú | Qué tiene |
|---|---|
| Archivo | Proyecto nuevo, abrir la carpeta del proyecto, exportar el tablero y quitar el proyecto de la lista |
| Análisis | Analizar o volver a analizar, y cancelar |
| Ver | El tema y las pestañas del tablero |
| Ayuda | Cómo leer el tablero y la clave de IA |

**La clave de IA, opcional.** En el menú Ayuda, "Clave de IA". Se pega una vez, se guarda en la computadora fuera
de los proyectos y no se vuelve a mostrar. Con clave, la IA redacta los títulos de las narrativas. Sin clave, el
título es la frase más repetida de cada narrativa.

**Dónde quedan los proyectos.** Cada uno en su carpeta, dentro de `Documentos/delfOS/`, con los datos, los 4
archivos del resultado y el tablero. "Quitar de la lista" no borra esa carpeta.

**Cerrarla.** Cerrá la ventana. Si la abriste desde la terminal, Ctrl+C.

La aplicación corre solo en la propia computadora y los datos no salen de ella. La única excepción: si hay clave,
el análisis le manda al modelo de IA frases y comentarios de ejemplo de cada narrativa.

## 5. Usar la terminal

Antes de cualquier comando, activá el entorno. En Linux y macOS: `source .venv/bin/activate`. En Windows:
`.venv\Scripts\activate`.

**El pipeline:**

```bash
python -m pipeline --datos datos/final --salida salida/entrega --cache cache/set-final.jsonl
```

Termina con una línea que empieza con "listo en". Con la caché del repositorio no necesita clave ni llama a la
API, y da el mismo resultado que `entrega/`.

| Opción | Qué hace |
|---|---|
| `--datos` (obligatoria) | La carpeta con los 4 archivos del set. |
| `--salida` (obligatoria) | La carpeta donde se escribe el resultado. Se crea sola. |
| `--cache` | Un archivo con las respuestas de la IA. Si la respuesta ya está, no se vuelve a pedir ni a pagar. |
| `--sin-modelo` | Corre sin IA, a propósito. Funciona sin clave y sin conexión. |
| `--informe` | Guarda un archivo con el registro de la corrida: avisos, tiempos por etapa y uso de la IA. |

**Con otro set, o sin la caché**, el pipeline le pregunta al modelo de IA si encuentra una clave. La busca en la
variable `ANTHROPIC_API_KEY` o en el archivo `~/.config/qualydata/anthropic_api_key`. Si no la encuentra, corre
igual.

**El tablero**, a partir de un resultado:

```bash
python -m tablero --datos datos/final --entrega salida/entrega
```

Escribe `salida/tablero.html`: un solo archivo, que se abre con doble clic y no necesita internet. Con
`--informe <archivo>` suma los avisos del análisis y los tiempos por etapa.

## 6. Qué archivos salen

Son los 4 del formato oficial del desafío:

| Archivo | Qué tiene |
|---|---|
| `comentarios.csv` | Una fila por comentario: su narrativa y su postura (`apoya` o `rechaza`). El ruido va con las dos vacías. |
| `narrativas.csv` | Una fila por narrativa: el título, las frases clave y la fecha de origen. |
| `cuentas.csv` | Una fila por cuenta: la operación a la que pertenece, o vacío si no está en ninguna. |
| `costo.json` | Cuánto se procesó, cuánto tardó, cuánto costó la IA y en qué equipo corrió. |

## 7. Comprobar que funciona

**Las pruebas automáticas.** Corren en menos de un minuto, sin clave y sin gastar nada:

```bash
python -m pytest
```

**Que el resultado es el entregado.** Después de correr el pipeline con la caché del repositorio (sección 5), estos
tres comandos no tienen que mostrar nada. Si no muestran nada, los archivos son idénticos byte a byte:

```bash
cmp salida/entrega/comentarios.csv entrega/comentarios.csv
cmp salida/entrega/narrativas.csv entrega/narrativas.csv
cmp salida/entrega/cuentas.csv entrega/cuentas.csv
```

`costo.json` no se compara: lleva los tiempos medidos, que cambian en cada corrida.

## 8. Si algo falla

| Qué pasa | Qué hacer |
|---|---|
| El instalador dice que no encuentra Python | Instalalo con la tabla de la sección 1 y volvé a correrlo. |
| En Ubuntu o Debian, falla al crear el entorno | Falta un paquete: `sudo apt install python3-venv`. |
| `./instalar.sh` dice "permiso denegado" | Corré `bash instalar.sh`. Lo mismo con `bash abrir.sh`. |
| La aplicación se abre en una pestaña y no en una ventana | Es normal si no hay Chrome, Chromium o Edge. Funciona igual. |
| La aplicación no abre nada | Corré `./abrir.sh` desde la terminal: muestra la dirección, para abrirla en el navegador. |
| El pipeline dice que falta un archivo | Revisá que la carpeta de `--datos` tenga los 4 archivos de la sección 3. |
| Los títulos salen en minúsculas y entre comillas | No hay clave de IA, o la IA no pasó el control de ese título. El resto del resultado no cambia. |

**Windows.** No se pudo probar en una máquina con Windows. Se revisó el código del pipeline, se sacó lo único que
dependía de Linux (la medición de la memoria, que en Windows figura en 0) y las pruebas simulan esa falta.
`instalar.bat` y `abrir.bat` no están probados.
