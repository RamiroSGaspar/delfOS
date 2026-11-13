"""Tablero: una página que muestra el resultado del pipeline para quien no va a leer los CSV.

Responde tres preguntas: qué circula, desde cuándo y quién lo empuja. Se arma con un comando:

    python -m tablero --datos <carpeta del set> --entrega <carpeta con los 4 archivos> [--salida <archivo.html>]

Lee el set y la entrega, calcula todo lo que se muestra (`tablero/resumen.py`) y escribe una sola página
(`tablero/pagina.py`) que se abre con doble clic: sin servidor, sin internet y sin bibliotecas nuevas. No
cambia ningún archivo de la entrega. El aspecto sale del sistema de diseño «delfOS · Teletipo», que está en
`tablero/sistema/`, y la marca, de `tablero/marca/`.
"""
