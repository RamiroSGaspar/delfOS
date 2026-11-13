# El sistema de diseño: delfOS · Teletipo

Es la identidad visual de delfOS, versión 0.3.1 del 13/11/2026: papel claro y tinta, con un tema Oscuro en azul
noche. La hizo el equipo durante la hackatón. El tablero y la aplicación toman de acá todo su aspecto.

| Archivo | Qué es |
|---|---|
| `tokens.css` | Los valores: los colores de los dos temas (Papel y Oscuro), los espaciados y las dos tipografías. |
| `bundle.css` | Los componentes: ventana, menú, barra de estado, pestañas, botón, tabla, sello, recibo y terminal. |
| `vistas.css` | Las piezas de las vistas: la mesa de trabajo, el árbol y las filas que se eligen. |
| `fonts/` | JetBrains Mono, para todo lo calculado, y Source Serif 4, para lo que se lee. |
| `Licencias/` | Las licencias de las dos fuentes (SIL Open Font License 1.1). |

Los tres CSS están tal cual salieron del sistema. Lo propio del tablero está en `tablero/tablero.css` y lo propio
de la aplicación, en `delfos/web/app.css`: los dos usan solo los valores de `tokens.css`.

**Qué se usa y qué no.** Del sistema se usan los temas, las tipografías, las tintas por autoría, las
ventanas, las barras y la escritura. Los gráficos de glifos (la sábana, las barras de postura y la chispa) se
reemplazaron por gráficos dibujados con el mismo aspecto, porque se leen sin entrenamiento; los signos quedan como
marcas (`◆` coordinación, `[!]` aviso). La cursiva de Source Serif 4 no se incluye: no se usa.

**La marca** (el logotipo, el símbolo y el delfín en caracteres) está en `tablero/marca/`. Se compone con la
tinta del tema, sin colores propios.

**Las fuentes van adentro de cada página**, en base64 (`tablero/pagina.py`): el tablero sigue siendo un solo
archivo que abre sin internet.
