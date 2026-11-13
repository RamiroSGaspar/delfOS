"""La configuración del pipeline: un solo diccionario con los valores congelados.

Son los valores de `serie/EXP-017-set-final/config_final.json` (la candidata de la línea 1 más N12),
escritos acá con todo lo que esa configuración tomaba de la base de la serie. Cada clave dice qué elemento
de la arquitectura toca (P, N o C, los códigos de `docs/arquitectura.md`) y de dónde sale su valor.

Nada de esto se ajustó mirando el set final: la configuración quedó congelada antes de correrlo (EXP-017).
"""

CONFIG = {
    # ------------------------------------------------------------------ P6 · relleno estadístico y núcleos
    # Congelado: 6, 4, 25 y 3 vienen del prototipo (EXP-004); 3 rondas como en el prototipo.
    "p6_max_muletilla": 6,  # palabras máximas de un relleno al comienzo
    "p6_max_coletilla": 4,  # palabras máximas de un relleno al final
    "p6_min_restos": 25,  # textos distintos mínimos a los que se pega un relleno
    "p6_min_nucleo": 3,  # palabras mínimas que conserva el núcleo
    "p6_rondas": 3,  # rondas de detección (los rellenos se apilan)

    # ------------------------------------------------------------------ N1 · familias
    "n1_umbral": 0.7,  # parecido mínimo por pedazos de 3 y 4 letras (decisión 1, EXP-004)

    # ------------------------------------------------------------------ N2 · acompañamientos
    "n2_max_palabras": 4,  # un acompañamiento tiene 4 palabras o menos
    "n2_min_respuesta": 0.5,  # y aparece como respuesta en la mitad o más de sus apariciones
    "n2_max_pasos": 50,  # pasos máximos al subir por la cadena de respuestas

    # ------------------------------------------------------------------ N3 · familias ancladas
    "n3_min_implicacion": 0.02,  # 2 % de enlaces de respuesta (EXP-010, opción "n3-002"; la base usaba 5 %)
    "n3_min_enlaces": 2,  # y 2 enlaces como mínimo

    # ------------------------------------------------------------------ N4 · puente con Louvain
    "n4_semilla": 42,  # semilla fija de Louvain (reproducible)
    "n4_min_arista": 1,  # una respuesta alcanza para crear un enlace

    # ------------------------------------------------------------------ N8 · lado que apoya (EXP-011, opción (a))
    "n8_z_tope": 2.0,  # margen chico de "tope": |a - b| / raíz(a + b) < 2 va al modelo
    "n8_nucleos_por_lado": 10,  # núcleos que lee el modelo de cada lado
    "n8_max_caracteres": 300,  # largo máximo de cada texto del pedido
    "n8_esfuerzo": "low",
    "n8_max_tokens": 2048,

    # ------------------------------------------------------------------ N9 · origen (EXP-012: "3 en 3 horas")
    "n9_ventana_horas": 3,
    "n9_minimo": 3,

    # ------------------------------------------------------------------ N10 · título y frases clave (EXP-015)
    "n10_frases": 5,  # frases clave: los 5 núcleos más frecuentes del lado que apoya
    "n10_max_tokens": 2048,  # con 512 el modelo se quedaba sin texto (EXP-015, "haiku2")
    "n10_esfuerzo": "low",
    "n10_max_palabras_pedido": 12,
    "n10_max_palabras_aceptado": 20,

    # ------------------------------------------------------------------ N12 · plan B con el modelo (EXP-016)
    "n12_min_comentarios": 50,  # M: comentarios mínimos de una familia de ruido para ser candidata
    "n12_min_cuentas": 3,  # K: cuentas distintas mínimas
    "n12_lote": 40,  # familias por llamada
    "n12_max_tokens": 16000,
    "n12_esfuerzo": "medium",
    "n12_max_caracteres": 200,

    # ------------------------------------------------------------------ C · coordinación (EXP-013)
    # Umbrales de la base (EXP-003 y EXP-007).
    "c_repeticion_min": 2.0,  # capa T: repetición media por cuenta de una ficha
    "c_cuentas_min": 3,  # capa T: cuentas mínimas que usan la ficha
    "c_t_min": 0.2,  # capa T: proporción mínima de comentarios con texto propio
    "c_k_min": 4,  # capas S y P: publicaciones mínimas en las que coincide un par
    "c_exceso_min": 10.0,  # capa S: coincidencias sobre lo esperable por azar
    "c_tam_min": 3,  # capas S, R y P: cuentas mínimas de un grupo
    "c_ventana_s": 900,  # capas S y P: ventana de 15 minutos
    # Lo que suma EXP-013 ("respuestas-publicacion-freno").
    "c_excluir_vacio": True,  # el núcleo vacío no cuenta como ficha de texto
    "c_capa_r": True,  # capa R: respuestas entre cuentas
    "c_capa_p": True,  # capa P: sincronía por publicación (L2-3)
    "c_p_exceso_min": 5.0,  # capa P: exceso mínimo
    "c_freno": True,  # una capa cuya alarma salta se apaga
    "c_alarma_razon": 0.5,  # la alarma salta si el set barajado marca la mitad o más que el real
    "c_semilla": 13,  # semilla de la permutación del barajado

    # ------------------------------------------------------------------ modelo de IA
    "modelo": "claude-haiku-5-5",  # fijo: cualquier otro se rechaza antes de llamar
    "modelo_hilos": 16,  # pedidos al modelo en paralelo (los de N12 y N10 salen juntos)

    # ------------------------------------------------------------------ procesos
    "procesos": 4,  # procesos para el trabajo por texto (P4, P5 e idioma); no cambia el resultado
}
