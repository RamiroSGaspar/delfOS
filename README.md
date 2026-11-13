# delfOS

Solución al desafío de QualyData [*Narrativas y coordinación a escala*](https://github.com/qualydata-org/desafio-qualydata)
de la Hackathon Argentina Space 2026 (Centro de Convenciones de Salta, del 11 al 13 de noviembre de 2026).

delfOS lee un set de comentarios y responde tres preguntas: **qué narrativas circulan, desde cuándo y quién las
empuja**. Sobre el set final procesó 150.000 comentarios en 21,4 segundos, con USD 0,0044 de IA
(`entrega/costo.json`).

Tiene tres partes:

| Parte | Qué es |
|---|---|
| **El pipeline** (`pipeline/`) | El motor: lee el set y escribe los 4 archivos del formato oficial. Es lo que evalúa el desafío. |
| **El tablero** (`tablero/`) | Una página que muestra el resultado y explica cada cifra. |
| **La aplicación** (`delfos/`) | Una ventana para hacer todo sin la terminal: elegir los datos, analizar y leer el tablero. |

## Demo

| | |
|---|---|
| Video de demo | Pendiente: acá va el enlace |
| Presentación | Pendiente: acá va el enlace |

## Probarlo

**Sin instalar nada.** Con el repositorio descargado, abrí [`comunicacion_datos.html`](comunicacion_datos.html)
con doble clic: es el tablero del set final, con las tres respuestas en una pantalla.

**La aplicación, en dos comandos.** Hace falta Python 3.9 o superior:

```bash
./instalar.sh
./abrir.sh
```

En Windows, doble clic en `instalar.bat` y después en `abrir.bat`.

**El pipeline, con un comando.** Con los 4 archivos del set final en `datos/final/`:

```bash
source .venv/bin/activate
python -m pipeline --datos datos/final --salida salida/entrega --cache cache/set-final.jsonl
```

| Documento | Qué tiene |
|---|---|
| [`GUIA.md`](GUIA.md) | El paso a paso: instalar, conseguir los datos, usar la aplicación, correr el pipeline y comprobar que funciona. |
| [`COMO_FUNCIONA.md`](COMO_FUNCIONA.md) | Cómo trabaja delfOS por dentro, explicado en simple. |

## Resultados

Sobre el set final, según `entrega/`:

| | |
|---|---:|
| Comentarios procesados | 150.000 |
| Tiempo de proceso | 21,4 s |
| Memoria pico del proceso | 861 MiB |
| Costo de IA | USD 0,0044 |
| Costo de IA por cada 1.000 comentarios | USD 0,000029 |
| Narrativas detectadas | 12 |
| Comentarios con narrativa | 118.657 (79,1 %) |
| Cuentas con señales de coordinación | 21 de 12.002 (0,17 %), en 1 operación |

Equipo de esa corrida: Intel Core i5-10210U, 8 hilos, 15,3 GiB de memoria.

Sobre el set de práctica, con el evaluador oficial del desafío (`evaluacion/puntuar.py`): **53,22 de 55** puntos
automáticos (29,91 de narrativas y 23,31 de coordinación).

## Cómo correr el pipeline

El set final no está en el repositorio. Se descarga de
[Releases del desafío](https://github.com/qualydata-org/desafio-qualydata/releases/tag/set-final) y sus 4 archivos
van en `datos/final/`. Con el entorno activado (`source .venv/bin/activate`):

```bash
python -m pipeline --datos datos/final --salida salida/entrega --cache cache/set-final.jsonl
```

Escribe `comentarios.csv`, `narrativas.csv`, `cuentas.csv` y `costo.json` en `salida/entrega/`.

**Para repetir la entrega no hace falta clave.** [`cache/set-final.jsonl`](cache/set-final.jsonl) guarda las 16
respuestas que dio el modelo de IA en la corrida entregada: solo pedidos y respuestas, ningún secreto. Con ese
archivo, el comando da los tres CSV idénticos byte a byte a los de [`entrega/`](entrega/) y no llama a la API
(comprobado el 13/11/2026, en una corrida sin clave).

`entrega/` se generó con ese mismo comando, escribiendo directo en `entrega/` y guardando además el informe de la
corrida. Nada se editó a mano:

```bash
python -m pipeline --datos datos/final --salida entrega --cache cache/set-final.jsonl --informe salida/informe.json
```

**Qué esperar al volver a correrlo:**

- **Semillas fijas:** 42 en el corte de las narrativas en comunidades (Louvain) y 13 en el barajado de control de
  la coordinación.
- **Con la caché del repositorio**, `comentarios.csv`, `narrativas.csv` y `cuentas.csv` salen idénticos byte a
  byte a los de `entrega/`. `costo.json` cambia solo en los tiempos medidos y en las notas.
- **Sin la caché**, `comentarios.csv` y `cuentas.csv` salen igual de idénticos, con IA o sin IA. En
  `narrativas.csv`, las frases clave y las fechas de origen tampoco cambian. Lo único que puede cambiar es el
  `titulo`: el modelo de IA no redacta dos veces igual.

Las opciones del comando y la clave de IA están en [`GUIA.md`](GUIA.md).

## Dónde se guardan los datos y por qué

**Dónde.** Los 4 archivos del set (CSV con gzip) se leen una sola vez a tablas en memoria, con Polars y NumPy. No
hay base de datos ni ningún servicio que levantar. La salida son CSV en disco y, si se pide, la caché de respuestas
del modelo en un archivo JSONL.

**Por qué.** Se decidió midiendo la alternativa. Durante el evento se programó el mismo pipeline sobre Parquet con
DuckDB y se corrió en 7 sets de prueba:

| | CSV y tablas en memoria (la elegida) | Parquet con DuckDB |
|---|---|---|
| Archivos que produce | La referencia | Idénticos: el mismo SHA-256 en los 7 sets |
| Memoria pico | La referencia | Entre 4 % y 28 % más, según el set |
| Tiempo | La referencia | Entre 5 % y 50 % más, según el set |

- A este volumen, una base de datos suma memoria y tiempo y no cambia el resultado.
- Cada texto distinto se procesa una sola vez, así que la memoria crece con la cantidad de textos distintos y no
  con la de comentarios.
- Sin servicios que instalar, el pipeline corre igual en cualquier máquina con un comando.

La decisión vale para sets de hasta medio millón de comentarios.

## Cómo escalaría a millones de comentarios por día

Medido durante el evento en una notebook de 8 hilos y 15 GiB de memoria, con la versión anterior a la optimización
final:

- **El tiempo crece casi en línea con los comentarios.** Con 4 veces más comentarios (de 49.979 a 200.000), el
  tiempo creció 3,38 veces y la memoria 1,53 veces.
- **Una sola etapa crece más que en línea:** la que agrupa los textos casi iguales. Con 10 veces más textos base
  tarda 33 veces más.
- **El costo de IA depende de cuántas narrativas hay, no de cuántos comentarios.** Un título cuesta entre
  USD 0,00013 y USD 0,00037.

**Un millón de comentarios en un solo lote** (proyección a partir de esas medidas, no una corrida): alrededor de
1,5 minutos y 2,8 GB de memoria con la variedad de textos del set de práctica, y USD 0,012 de IA si hubiera 50
narrativas. Entra en la misma notebook.

**Diez millones en un solo lote** no entran en esa máquina: harían falta unos 28 GB. Hay dos caminos: partir el día
en lotes y correrlos en paralelo en varias máquinas, o un motor que trabaje sobre Parquet sin tener la tabla de
comentarios en memoria. El segundo es una propuesta: no está medido.

## Robustez

- **Un comando, de punta a punta.** Sin pasos manuales ni servicios que levantar.
- **Datos sucios.** La lectura no descarta comentarios: prueba varios formatos de fecha, deja la primera fila si un
  id se repite, pasa a primer nivel una respuesta a un comentario que no existe y completa vacía una columna que
  falta. Solo corta si falta el archivo de comentarios o su columna `comentario_id`. Cada problema queda anotado.
- **El modelo de IA nunca corta la corrida.** Si un pedido falla, o no hay clave, la etapa usa su respaldo.
- **El pipeline se controla solo.** En la coordinación compara el set real con el mismo set barajado al azar y
  apaga la señal que no distingue uno del otro. En el set final apagó una, y el aviso quedó en `entrega/costo.json`.
- **Pruebas automáticas.** `python -m pytest` corre 112 pruebas. Ninguna llama a la API ni gasta nada.

## Uso de IA

Claude Haiku 5.5, por la API de Anthropic, en tres lugares y siempre sobre grupos de comentarios, nunca de a uno:
decidir qué lado apoya cuando la estructura duda, redactar los títulos y revisar el ruido. En el set final fueron
16 pedidos, 19.879 tokens y USD 0,0044, que es lo que informa `entrega/costo.json`. El detalle está en
[`COMO_FUNCIONA.md`](COMO_FUNCIONA.md).

## Qué existía antes del evento

- **Bibliotecas públicas**, con las versiones de [`requirements.txt`](requirements.txt): Polars, NumPy, SciPy,
  scikit-learn, NetworkX, el cliente de Anthropic y pytest.
- **Un servicio público:** la API de Anthropic, con el modelo Claude Haiku 5.5.
- **Dos tipografías públicas:** JetBrains Mono y Source Serif 4. Están en `tablero/sistema/fonts/`.
- **La infraestructura de trabajo con agentes de IA:** los archivos de reglas `CLAUDE.md`, `AGENTS.md`,
  `opencode.json`, `.claude/` y `gestion/`, creados el 10/11/2026. No son código de la solución y no están en este
  repositorio.

Ningún código de la solución existía antes del evento: el pipeline, el tablero, la aplicación, el sistema de
diseño, la marca, las pruebas y la documentación se hicieron del 11 al 13 de noviembre de 2026.

## Qué hay en el repositorio

```
entrega/                 la salida del pipeline sobre el set final: los 4 archivos del formato oficial
cache/                   las respuestas del modelo de IA en la corrida entregada: con ellas se repite sin clave
comunicacion_datos.html  el tablero del set final: se abre con doble clic
pipeline/                el pipeline (python -m pipeline)
tablero/                 el tablero (python -m tablero), con su sistema de diseño y la marca
delfos/                  la aplicación (./abrir.sh)
tests/                   las pruebas automáticas (python -m pytest)
instalar.sh, abrir.sh    la instalación de una sola vez y el acceso a la aplicación (Linux y macOS)
instalar.bat, abrir.bat  lo mismo, para Windows
requirements.txt         las bibliotecas, con versiones fijadas
GUIA.md                  cómo instalarlo, usarlo y probarlo
COMO_FUNCIONA.md         cómo trabaja por dentro
```

No se suben `datos/` (los sets), `.venv/` (las bibliotecas instaladas) ni `salida/` (las corridas locales): están
en `.gitignore`.

## Equipo

- Tomás Gabriel Dazzi Maisenti
- Lisandro Nahuel Farfán Huebra
- Ramiro Sebastián Gaspar
