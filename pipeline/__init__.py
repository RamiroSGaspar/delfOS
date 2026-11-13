"""Pipeline de narrativas y coordinación del desafío QualyData (Hackatón Argentina Space 2026).

Se corre con un solo comando:

    python -m pipeline --datos <carpeta> --salida <carpeta> [--sin-modelo] [--cache <archivo>]

Qué hace cada etapa y de qué experimento sale cada decisión: `docs/arquitectura.md`. Cómo se usa:
`docs/uso.md`. Este archivo no importa nada pesado a propósito: los procesos y las pruebas pueden
importar un módulo chico del paquete sin cargar Polars.
"""

VERSION = "1.0.0"
