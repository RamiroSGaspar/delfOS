"""delfOS: la aplicación para analizar sets de comentarios sin usar la terminal.

    python -m delfos

Abre una ventana con la lista de proyectos. Un proyecto es un set de comentarios y su último análisis: se eligen
los datos y dónde guardarlo, se analiza con un botón y el resultado se lee en el tablero.

Es un servidor chico que escucha solo en esta computadora (127.0.0.1) y usa lo que trae Python: no suma
bibliotecas. El análisis lo hace `pipeline/` y el tablero lo arma `tablero/`; este paquete los corre y muestra el
resultado.
"""
