# Cómo funciona delfOS

Una explicación general, sin entrar en el detalle técnico.

## En una frase

delfOS lee cientos de miles de comentarios y devuelve qué narrativas circulan, quién las apoya y quién las
rechaza, desde cuándo, y qué cuentas muestran señales de coordinación. Lo hace en menos de un minuto y por menos
de un centavo de dólar.

## Las tres partes

```
los 4 archivos del set
        │
        ▼
   EL PIPELINE ──────► los 4 archivos del resultado
   (el motor)                    │
                                 ▼
                            EL TABLERO ──────► una página que se lee sola
                                 ▲
                                 │
                          LA APLICACIÓN: elegir los datos, analizar y ver el tablero, sin la terminal
```

- **El pipeline** hace todo el análisis. Es lo único que decide el resultado.
- **El tablero** solo muestra: lee el resultado y lo explica. No cambia ningún dato.
- **La aplicación** junta las dos cosas en una ventana.

## La idea central: estructura primero, IA donde la estructura no llega

Leer comentario por comentario con un modelo de IA es lento y caro. delfOS hace al revés.

**Primero, la estructura de la conversación.** Cuando alguien responde a un comentario, habla de lo mismo aunque
use otras palabras. Siguiendo quién le responde a quién se arman las narrativas y sus dos lados: quien afirma y
quien refuta. Es rápido, no cuesta nada y no depende del idioma.

**Después, la IA en tres lugares chicos**, siempre sobre grupos de comentarios y nunca de a uno. Es lo que pide el
desafío: usar la IA "donde suma y no como único motor".

## El recorrido, paso a paso

1. **Leer y limpiar.** Se leen los 4 archivos. Los datos sucios (fechas en otro formato, ids repetidos, respuestas
   a comentarios que no existen) se arreglan y se anotan; no se descarta ningún comentario.
2. **Juntar los textos casi iguales.** Muchos comentarios dicen lo mismo con cambios mínimos. Se agrupan, y cada
   texto distinto se procesa una sola vez. Por eso es rápido.
3. **Armar las narrativas.** Los grupos de textos que se responden mucho entre sí forman una narrativa. No se parte
   de una lista de temas: la cantidad de narrativas sale sola de los datos. Lo que no entra en ninguna es ruido.
4. **Separar los dos lados.** Una respuesta con contenido queda del lado contrario al comentario que responde. Una
   respuesta corta que solo acompaña ("tal cual") queda del mismo lado.
5. **Decidir qué lado apoya.** Es el lado con más comentarios que no responden a nadie: quien abre la discusión
   afirma la idea. Si los dos lados están parejos, decide la IA.
6. **Fechar el origen.** El origen de una narrativa es su primer comentario al que le siguen al menos otros 2 en
   menos de 3 horas. Un comentario suelto, horas antes, no cuenta.
7. **Poner títulos.** La IA redacta un título por narrativa a partir de sus frases más repetidas.
8. **Revisar el ruido.** La IA mira los grupos grandes que quedaron como ruido, por si esconden una narrativa que
   nadie respondió.
9. **Buscar coordinación.** Ver más abajo.
10. **Escribir el resultado:** los 4 archivos del formato oficial.

## Dónde entra la IA

El modelo es Claude Haiku 5.5, el más chico y barato de Anthropic.

| Dónde | Qué hace | Si falla o no hay clave |
|---|---|---|
| El lado que apoya | Cuando los dos lados están parejos, lee ejemplos de cada uno y dice cuál afirma la idea | Decide la regla simple |
| Los títulos | Redacta un título legible. Se acepta solo si no agrega palabras que no estén en los comentarios | El título es la frase más repetida |
| La revisión del ruido | Busca narrativas que nadie respondió | Queda como ruido |

La IA nunca corta el análisis: cada lugar tiene su respaldo. En el set final fueron 16 pedidos y USD 0,0044 para
150.000 comentarios. El costo depende de cuántas narrativas hay, no de cuántos comentarios.

## Cómo se detecta la coordinación

Una ráfaga de comentarios no alcanza: en una publicación viral, mucha gente comenta a la vez. Lo que delata a una
operación es la repetición: las mismas cuentas, juntas, una y otra vez. delfOS busca cuatro señales:

| Señal | Qué mira |
|---|---|
| Texto propio | Pocas cuentas que repiten mucho un mismo texto o hashtag |
| Sincronía por narrativa | Pares de cuentas que comentan la misma narrativa con minutos de diferencia, muchas veces |
| Sincronía por publicación | Lo mismo, sobre las mismas publicaciones |
| Respuestas en grupo | Cuentas que se responden entre sí |

**El control.** Cada señal se prueba también con las cuentas mezcladas al azar. Si ahí marca casi lo mismo, la
señal no distingue nada en ese set: se apaga y queda avisado. En el set final se apagó una de las cuatro.

Las cuentas que comparten una señal forman una **operación**. El resultado dice "cuentas con señales de
coordinación": es conducta observada en el set. No identifica bots ni autoría y no prueba intención.

## El tablero y la aplicación

- **El tablero** es un solo archivo. Se abre con doble clic y no necesita internet ni servidor. Empieza con las
  respuestas, en una oración calculada con los datos, y cada cifra tiene su nota: qué muestra y cómo se obtiene.
- **La aplicación** corre solo en la propia computadora. Guarda cada proyecto en su carpeta, con los datos, el
  resultado y el tablero. Volver a analizar los mismos datos da lo mismo y no vuelve a gastar en IA.
- Las dos usan el mismo sistema de diseño, hecho por el equipo, con un tema claro y uno oscuro.

## Dónde se guardan los datos

En memoria, sin base de datos. Los archivos se leen una vez a tablas y el resultado se escribe en CSV. Se probó la
alternativa (Parquet con DuckDB): daba los mismos archivos con más memoria y más tiempo. El detalle y las medidas
están en el [`README.md`](README.md).

## Cómo sabemos que funciona

- **En el set de práctica**, que trae las respuestas correctas: 53,22 de 55 puntos automáticos con el evaluador
  oficial del desafío.
- **En otros 8 sets armados para romperlo** (otros temas, otro idioma, mucho ruido, una campaña de 600 cuentas, 500
  narrativas, 200.000 comentarios). Para elegir cada pieza se miró el promedio y también el peor caso.
- **En el set final**, que no trae respuestas: el formato es el oficial, dos corridas dan los mismos archivos y el
  resultado es legible. Son 12 narrativas, cada una con sus dos lados, y 3 de ellas nacen a mitad del período.

## Los límites

1. La estructura depende de que la gente se responda. Si un set casi no tiene respuestas, la revisión del ruido
   rescata una parte, pero no todo.
2. En el set final se encontró una operación de 21 cuentas. Sin las respuestas correctas no se puede saber si hay
   más.
3. El origen de cada narrativa es una estimación, no un dato del set.
4. Los títulos que redacta la IA cambian de una corrida a otra. Lo demás no cambia.
5. En Windows no se pudo probar.
