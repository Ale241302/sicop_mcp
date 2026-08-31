# -*- coding: utf-8 -*-
"""Documentacion enriquecida del MCP: guia por tool.

Para cada tool: para que sirve, como preguntarle, que devuelve, como NO usarla
(anti-patrones reales de la data SICOP) y casos de uso. Se renderiza en /atlas/mcp/.
"""

# categoria -> lista de tools (orden de presentacion)
CATEGORIAS = [
    ("Proveedores y competencia", [
        "sicop_ficha_proveedor", "sicop_mercado_familia", "sicop_cara_a_cara",
        "sicop_perdidas_baratas", "sicop_precios_institucion", "sicop_representantes",
        "sicop_representante_competencia", "sicop_sanciones", "sicop_excepciones",
        "sicop_proveedor_dim", "sicop_ordenes_proveedor", "sicop_campo_buscar",
    ]),
    ("Productos y catalogo", [
        "sicop_producto", "sicop_producto_historia", "sicop_producto_firma",
    ]),
    ("Procedimientos (licitaciones)", [
        "sicop_buscar_procedimiento", "sicop_verificar_procedimiento",
        "sicop_competencia_procedimiento", "sicop_expediente", "sicop_lineas_procedimiento",
        "sicop_regimen_evaluacion", "sicop_regimen", "sicop_tiempos_por_etapa",
        "sicop_recursos_procedimiento", "sicop_recursos_desenlace", "sicop_precios_identicos",
        "sicop_invitaciones_procedimiento", "sicop_invitaciones_proveedor",
        "sicop_invitados_vs_ofertantes", "sicop_carteles_objetados",
    ]),
    ("Hechos: captacion / ejecucion / entrega", [
        "sicop_fact_requerimiento", "sicop_fact_oferta", "sicop_fact_adjudicacion",
        "sicop_fact_contrato", "sicop_fact_orden", "sicop_fact_recepcion",
    ]),
    ("Calidad del dato y series temporales", [
        "sicop_mes_publicacion", "sicop_ctl_deriva", "sicop_catalogo_campo",
        "sicop_competencia_por_regimen", "sicop_bccr_tc",
    ]),
    ("Auto-gestion del sistema (IA operadora)", [
        "sicop_diagnostico", "sicop_resumen", "sicop_gold_status", "sicop_corrida_pasos",
        "sicop_reconciliar", "sicop_reparar_mes", "sicop_ciclo_diario",
        "sicop_politica", "sicop_carril",
    ]),
    ("Decisiones y senales", [
        "sicop_senales", "sicop_resultado", "sicop_registrar_resultado",
    ]),
    ("Monitoreo y auditoria", [
        "sicop_actividad_mcp", "sicop_registro", "sicop_vigilancia",
    ]),
    ("Analisis avanzado (Fase 4) y externo", [
        "sicop_ficha_esosa", "sicop_backtest_invitaciones", "sicop_holdout",
        "sicop_pendientes", "sicop_cgr_buscar",
    ]),
]

DOCS = {
    # ---------------- PROVEEDORES Y COMPETENCIA ----------------
    "sicop_ficha_proveedor": {
        "para": "Ficha completa de un proveedor: que adjudico por anio, cuanto ejecuta (ordenes) vs capta (adjudicaciones), desempeno de entrega y familias top.",
        "preguntar": "¿Ficha de la empresa 3101029593?",
        "args": '{"cedula": "3101029593"}',
        "respuesta": "Adjudicaciones por anio, cartera de ejecucion (monto y nro de ordenes), desempeno de entrega (lineas cumplidas) y familias UNSPSC top.",
        "no_usar": [
            "No buscar por NOMBRE: el parametro es la cedula exacta (10 digitos), no 'SONDEL'.",
            "La captacion (adjudicaciones) subestima al proveedor hasta 59x: usa la cartera de EJECUCION (ordenes) para dimensionar negocio real.",
            "Es una consulta pesada (~3s): no la pidas en loop; si necesitas muchas fichas, pedi los hechos directos (sicop_fact_*) que son mas baratos.",
        ],
        "casos": "Evaluar un competidor antes de ofertar; dimensionar el negocio real de un proveedor; encontrar familias donde concentra su captacion.",
    },
    "sicop_mercado_familia": {
        "para": "Estructura de mercado de una familia UNSPSC (8 digitos): quien gana, cuantos adjudicatarios, concentracion.",
        "preguntar": "¿Quienes ganan en la familia 81112399 (mantenimiento de UPS)?",
        "args": '{"familia_unspsc": "81112399"}',
        "respuesta": "Adjudicatarios top (monto y %), nro de procedimientos, productos del catalogo de esa familia y desempeno.",
        "no_usar": [
            "La familia debe ser de 8 digitos (81112399), no el CL de 16 ni el codigo de 24.",
            "El analisis es a nivel captacion: para ejecucion real usa sicop_ordenes_proveedor por cada adjudicatario.",
        ],
        "casos": "Descubrir quien domina una categoria antes de entrar; medir concentracion (top 1/3) para riesgo de dependencia.",
    },
    "sicop_cara_a_cara": {
        "para": "Compara dos proveedores en las lineas donde AMBOS ofertaron: victorias, veces mas barato, familias compartidas.",
        "preguntar": "Compara ESOSA (3101086562) contra SONDEL (3101095926).",
        "args": '{"cedula_a": "3101086562", "cedula_b": "3101095926"}',
        "respuesta": "Lineas donde compiten, quien gano mas, quien oferto mas barato (y por cuanto), familias donde se cruzan.",
        "no_usar": [
            "Necesita las DOS cedulas: sin una, no compara.",
            "Solo cubre procedimientos donde ambos ofertaron: si uno no oferto ahi, no aparece (no es el universo completo).",
        ],
        "casos": "Preparar una oferta contra tu competidor directo; encontrar familias donde le ganas por precio.",
    },
    "sicop_perdidas_baratas": {
        "para": "Lineas donde ofertaste MAS BARATO que el ganador y aun asi perdiste. Cola de revision (no conclusion).",
        "preguntar": "¿Donde ofertamos mas barato que el ganador y perdimos?",
        "args": '{"cedula": "3101095926"}',
        "respuesta": "Lineas con tu precio vs el del ganador, el delta y el procedimiento.",
        "no_usar": [
            "Es una SENAL, no una conclusion: perder barato puede deberse a regimen MIXTO (no solo precio) o requisitos tecnicos. Verifica con sicop_regimen_evaluacion.",
            "No la uses para afirmar corrupcion sin revisar el caso.",
        ],
        "casos": "Detectar donde pierdes por precio pese a ser mas barato; priorizar que regimenes te conviene atacar.",
    },
    "sicop_precios_institucion": {
        "para": "Quien paga de mas por el mismo producto (marca+modelo+firma): ratio max/min entre instituciones.",
        "preguntar": "¿Quien paga de mas por la UPS modelo X?",
        "args": '{"familia_unspsc": "461816", "marca": "APC"}',
        "respuesta": "Por producto (marca+modelo+anio): precio por institucion y el ratio maximo/minimo.",
        "no_usar": [
            "Necesita familia (8 digitos) o marca/modelo: sin anio cruza todo el historico (filtrar por anio para comparar iguales).",
            "Compara en la moneda declarada: si mezclas USD y CRC sin convertir, el ratio es basura.",
        ],
        "casos": "Detectar sobreprecios entre instituciones; negociar con mejor referencia de mercado.",
    },
    "sicop_representantes": {
        "para": "Representantes legales con 2+ empresas adjudicatarias (posible colusion estructural).",
        "preguntar": "¿Que representante legal aparece en varias empresas que ganan?",
        "args": '{}',
        "respuesta": "Representantes con varias empresas, monto total adjudicado y familias.",
        "no_usar": [
            "Es una SEÑAL de revision, no una prueba de colusion: compartir representante es legal si las empresas no compiten en las mismas lineas.",
        ],
        "casos": "Revision de riesgo en proveedores que se presentan como competidores pero comparten representante.",
    },
    "sicop_representante_competencia": {
        "para": "Lineas donde 2+ oferentes comparten representante legal (cola de revision).",
        "preguntar": "¿Hay lineas donde ofertan empresas con el mismo representante?",
        "args": '{"cedula_representante": "3101XXXXXX"}',
        "respuesta": "Lineas con oferentes que comparten representante.",
        "no_usar": ["Idem sicop_representantes: señal, no conclusion."],
        "casos": "Auditoria interna de competencia aparente.",
    },
    "sicop_sanciones": {
        "para": "Sanciones a un proveedor: inhabilitaciones y multas de procedimientos administrativos.",
        "preguntar": "¿Tiene sanciones el proveedor 3101095926?",
        "args": '{"cedula": "3101095926"}',
        "respuesta": "Sanciones con institucion, producto y resolucion.",
        "no_usar": [
            "La tabla de sanciones es pequeña (pocas filas): ausencia de sanción no implica historial limpio (solo cubre lo que publica SICOP).",
        ],
        "casos": "Debida diligencia antes de contratar con un proveedor.",
    },
    "sicop_excepciones": {
        "para": "Procedimientos por excepcion (proveedor unico, emergencia, capacitacion) agrupados por adjudicatario.",
        "preguntar": "¿Que adjudico por excepcion el proveedor X?",
        "args": '{"cedula": "3101XXXXXX"}',
        "respuesta": "Procedimientos por excepcion con montos.",
        "no_usar": ["Las excepciones son legales (Ley 7494): su presencia no es irregular por si sola."],
        "casos": "Ver cuanto se contrata sin competencia con un proveedor.",
    },
    "sicop_proveedor_dim": {
        "para": "Registro del proveedor: tipo, tamaño, zona, fechas de constitucion/expira.",
        "preguntar": "¿Que tamaño y tipo tiene el proveedor 3101029593?",
        "args": '{"cedula": "3101029593"}',
        "respuesta": "TIPO_PROVEEDOR, TAMAÑO_PROVEEDOR, zona geografica y fechas de registro.",
        "no_usar": ["El dato de tamaño puede estar vacio para algunos proveedores (llenado de la fuente)."],
        "casos": "Filtrar por PYME/mediana en estrategia de oferta.",
    },
    "sicop_ordenes_proveedor": {
        "para": "Ordenes de pedido de un proveedor (nivel EJECUCION). Solo CRC sumable; monedas no-CRC convertidas con TC.",
        "preguntar": "¿Cuantas ordenes ejecuto SONDEL en 2025?",
        "args": '{"cedula": "3101095926", "anio": "2025", "limit": 50}',
        "respuesta": "Ordenes con TOTAL_ORDEN (deduplicado por NRO_ORDEN), total CRC de la muestra y estimado convertido.",
        "no_usar": [
            "TOTAL_ORDEN viene REPLICADO por linea en la tabla cruda: este tool deduplica, pero si sumas el campo crudo directo inflas ~3,5x.",
            "Para comparar contra la fuente, usa las monedas separadas o el TOTAL_ORDEN_CRC_EST (convertido con TC del dia).",
        ],
        "casos": "Dimensionar la ejecucion real de un proveedor (la que factura), no solo la captacion.",
    },
    "sicop_campo_buscar": {
        "para": "Busqueda por termino en catalogo de productos (descripcion/marca/modelo), proveedores e instituciones.",
        "preguntar": "Busca 'UPS' en el catalogo.",
        "args": '{"termino": "UPS"}',
        "respuesta": "Productos, proveedores e instituciones que matchean el termino.",
        "no_usar": ["Es una busqueda de texto, no un filtro de familia: para estructurar usa sicop_mercado_familia o sicop_producto."],
        "casos": "Arrancar una investigacion cuando solo conoces el nombre del producto.",
    },

    # ---------------- PRODUCTOS ----------------
    "sicop_producto": {
        "para": "Ficha de un producto del catalogo por CODIGO_PRODUCTO_CL (16 digitos): descripcion, marca, modelo, quien lo provee y compra.",
        "preguntar": "¿Que producto es el 5311160192296606 y quien lo vende?",
        "args": '{"codigo_cl": "5311160192296606"}',
        "respuesta": "Descripcion, marca/modelo, proveedores y compradores.",
        "no_usar": [
            "El codigo debe ser de 16 digitos (CL). El de 24 es el producto completo con correlativo.",
            "Algunos CL (ej. 2023/2024) tienen llenado parcial en la fuente: si da vacio, puede ser hueco declarado de esa familia.",
        ],
        "casos": "Identificar quien abastece un producto puntual.",
    },
    "sicop_producto_historia": {
        "para": "Historia de un producto: secuencia de precios ofertados por anio (mediana/min/max), adjudicaciones, proveedores top.",
        "preguntar": "¿Como evoluciono el precio del producto 5311160192296606?",
        "args": '{"codigo_cl": "5311160192296606"}',
        "respuesta": "Precios por anio (mediana/min/max), proveedores y quien paga mas.",
        "no_usar": [
            "Los precios USD ya vienen convertidos con el TC de la fila; no vuelvas a convertir.",
            "No compares el precio de distintos anios sin ajustar por inflacion (la serie es nominal).",
        ],
        "casos": "Ver la tendencia de precio de un insumo para decidir cuando comprar.",
    },
    "sicop_producto_firma": {
        "para": "Firma de SKU (CL + marca + modelo + atributos): identifica el producto exacto, no el generico.",
        "preguntar": "¿Cuales son las variantes (marca/modelo) del CL 5311160192296606?",
        "args": '{"codigo_cl": "5311160192296606"}',
        "respuesta": "Firmas de SKU con marca/modelo/atributos.",
        "no_usar": ["Es granularidad SKU: para nivel familia usa sicop_mercado_familia."],
        "casos": "Comparar el mismo SKU entre compradores.",
    },

    # ---------------- PROCEDIMIENTOS ----------------
    "sicop_buscar_procedimiento": {
        "para": "Traduce el numero HUMANO del procedimiento (el que sale en carteles y correos, ej '2023LE-000016-0000200001') al NRO_SICOP.",
        "preguntar": "El cartel dice 2023LE-000016-0000200001, ¿cual es su NRO_SICOP?",
        "args": '{"numero_procedimiento": "2023LE-000016-0000200001"}',
        "respuesta": "NRO_SICOP, NRO_PROCEDIMIENTO, institucion, tipo y fecha.",
        "no_usar": [
            "Es LA puerta de entrada: NINGUNA otra tool acepta el numero humano. Usalo primero y luego sicop_verificar_procedimiento.",
        ],
        "casos": "El correo/cartel trae el numero humano y necesitas investigar la licitacion.",
    },
    "sicop_verificar_procedimiento": {
        "para": "Verifica si una licitacion (NRO_SICOP) esta COMPLETA en la base: cartel, lineas, ofertas, adjudicaciones, firme, contratos, ordenes, recepciones.",
        "preguntar": "¿Esta completa la licitacion 20230802921 en la base?",
        "args": '{"nro_sicop": "20230802921"}',
        "respuesta": "Conteo por tramo (cartel/ofertas/adjudicacion/contrato/orden/recepcion) con la fuente.",
        "no_usar": [
            "Si un tramo da 0, PRIMERO verificá si la fuente lo publico (muchos procedimientos de contratacion directa NO publican cartel con lineas: es hueco de fuente, no error de carga).",
            "No lo uses para sacar conclusiones de negocio: es una herramienta de integridad.",
        ],
        "casos": "Antes de concluir 'falta la licitacion X', confirma con esta tool que efectivamente falta (o que es de fuente).",
    },
    "sicop_competencia_procedimiento": {
        "para": "Oferentes por linea de un procedimiento: quien oferto, a que precio, quien gano y el delta contra el ganador.",
        "preguntar": "¿Quien oferto en 20230802921 y a que precio?",
        "args": '{"nro_sicop": "20230802921"}',
        "respuesta": "Por linea: oferentes, precios, ganador y delta.",
        "no_usar": [
            "Solo cubre las lineas ofertadas: si el regimen es MIXTO, el que gana no es necesariamente el mas barato (revisa sicop_regimen_evaluacion).",
        ],
        "casos": "Entender contra quien competiste en una licitacion concreta.",
    },
    "sicop_expediente": {
        "para": "Trazabilidad de un procedimiento: que tramos tiene completos (cartel, ofertas, acto firme, adjudicado, contrato, garantia, recibido).",
        "preguntar": "¿En que estado esta el expediente 20230802921?",
        "args": '{"nro_sicop": "20230802921"}',
        "respuesta": "Flags T_* (S/N) de cada tramo + numero de tramos.",
        "no_usar": ["La trazabilidad derivada cubre el corpus completo (reconstruida 2026-08): los conteos vienen de tablas crudas si el procedimiento no esta en la tabla de trazabilidad."],
        "casos": "Seguimiento de ciclo de vida de una licitacion.",
    },
    "sicop_lineas_procedimiento": {
        "para": "Cadena de linea completa: cartel (pidio), ofertadas, adjudicadas, contratadas, recibidas.",
        "preguntar": "¿Que pidio el cartel de 20230802921 y como avanzo cada linea?",
        "args": '{"nro_sicop": "20230802921"}',
        "respuesta": "Por linea: lo pedido, lo ofertado, lo adjudicado, lo contratado, lo recibido.",
        "no_usar": [
            "El join cartel<->oferta usa prefijo de 16 digitos del codigo: no compares codigos de distinta longitud como iguales.",
        ],
        "casos": "Seguir un producto puntual desde el pedido hasta la entrega.",
    },
    "sicop_regimen_evaluacion": {
        "para": "Factores y pesos de evaluacion de un procedimiento (que define si gana el mas barato o un criterio mixto).",
        "preguntar": "¿Como evaluan el procedimiento 20251200067?",
        "args": '{"nro_sicop": "20251200067"}',
        "respuesta": "Factores de evaluacion con su peso.",
        "no_usar": [
            "IMPORTANTE: si el regimen es MIXTO, 'perder siendo mas barato' es NORMAL y no indica anomalia. Verifica el regimen antes de cualquier conclusion.",
        ],
        "casos": "Decidir si conviene ofertar en un procedimiento (si pesa mucho el precio vs la experiencia).",
    },
    "sicop_regimen": {
        "para": "Regimen normalizado por procedimiento: PRECIO_PURO / MIXTO / SIN_PRECIO con factores y pesos.",
        "preguntar": "¿Es PRECIO_PURO o MIXTO el 20251200067?",
        "args": '{"nro_sicop": "20251200067"}',
        "respuesta": "Clasificacion normalizada + factores.",
        "no_usar": ["Es el resumen normalizado de sicop_regimen_evaluacion: usa el que mejor se ajuste."],
        "casos": "Estratificar analisis de competencia por tipo de regimen.",
    },
    "sicop_tiempos_por_etapa": {
        "para": "Plazos reales entre etapas de un procedimiento (dias publicacion->apertura->adjudicacion->contrato->recepcion).",
        "preguntar": "¿Cuanto tardo en adjudicarse el 20240317151?",
        "args": '{"nro_sicop": "20240317151"}',
        "respuesta": "Fechas de cada etapa y dias entre ellas (una fila por procedimiento).",
        "no_usar": [
            "La tabla gold traia una fila por linea (duplicada): ya se deduplica, no cuentes filas como tramos.",
        ],
        "casos": "Medir demoras institucionales; benchmark de plazos.",
    },
    "sicop_recursos_procedimiento": {
        "para": "Recursos de objecion de un procedimiento con su desenlace.",
        "preguntar": "¿Hubo recursos de objecion en 20230802921?",
        "args": '{"nro_sicop": "20230802921"}',
        "respuesta": "Recursos con recurrente, resultado y si prospero.",
        "no_usar": ["Los recursos con RESULTADO vacio se cuentan como no prospero: no citar tasa sin denominador."],
        "casos": "Identificar licitaciones disputadas.",
    },
    "sicop_recursos_desenlace": {
        "para": "Recursos con desenlace (recurrente, resultado, PROSPERO, institucion).",
        "preguntar": "¿Cuantos recursos prosperaron contra la CCSS?",
        "args": '{"cedula": "4000042147"}',
        "respuesta": "Recursos con su resultado.",
        "no_usar": ["Filtra por cedula de institucion o nro_sicop: sin filtro es un barrido."],
        "casos": "Medir la tasa de exito de objeciones contra una institucion.",
    },
    "sicop_precios_identicos": {
        "para": "Lineas con 2+ oferentes al mismo precio exacto (cola de revision).",
        "preguntar": "¿Hay precios identicos entre oferentes?",
        "args": '{"limit": 50}',
        "respuesta": "Lineas donde coinciden precios exactos.",
        "no_usar": [
            "Es una SEÑAL de revision: coincidencias de precios pueden ser coincidencia legitima (precio de lista). No es prueba.",
        ],
        "casos": "Barrido de riesgo de colusion en precios.",
    },
    "sicop_invitaciones_procedimiento": {
        "para": "Quien fue invitado a un procedimiento de contratacion directa (direccionamiento ex-ante).",
        "preguntar": "¿A quienes invitaron en 20230802921?",
        "args": '{"nro_sicop": "20230802921"}',
        "respuesta": "Proveedores invitados con su cedula.",
        "no_usar": ["Invitar a pocos es legal en contratacion directa (la ley define los minimos): no es irregular por si solo."],
        "casos": "Entender por que ofertaron (o no) los que ofertaron.",
    },
    "sicop_invitaciones_proveedor": {
        "para": "Procedimientos donde un proveedor fue invitado (invitaciones_pendientes).",
        "preguntar": "¿A cuantas licitaciones invitaron a nuestro proveedor?",
        "args": '{"cedula": "3101095926"}',
        "respuesta": "Procedimientos con fecha de invitacion.",
        "no_usar": ["No confundir invitado con ofertante: usa sicop_invitados_vs_ofertantes para la tasa."],
        "casos": "Descubrir oportunidades donde tu proveedor ya fue considerado.",
    },
    "sicop_invitados_vs_ofertantes": {
        "para": "Invitados vs ofertantes (tasa de respuesta) de un procedimiento.",
        "preguntar": "¿Cuantos invitados ofertaron en 20230802921?",
        "args": '{"nro_sicop": "20230802921"}',
        "respuesta": "Nro de invitados, nro de ofertantes y tasa.",
        "no_usar": ["Una tasa baja puede ser normal (proveedor sin interes): no es indicio de direccionamiento."],
        "casos": "Medir que tan abierta fue una contratacion directa.",
    },
    "sicop_carteles_objetados": {
        "para": "Carteles objetados (cola de revision): monto estimado, institucion, si se adjudico despues.",
        "preguntar": "¿Que carteles fueron objetados?",
        "args": '{"limit": 50}',
        "respuesta": "Carteles objetados con su desenlace.",
        "no_usar": ["La objecion puede resolverse y adjudicarse igual: revisa el desenlace antes de concluir."],
        "casos": "Seguir licitaciones que tuvieron objeciones.",
    },

    # ---------------- HECHOS ----------------
    "sicop_fact_requerimiento": {
        "para": "Hecho de requerimiento (cartel): lo que se pidio por linea (grano procedimiento x linea x partida). Nivel: CAPTACION.",
        "preguntar": "¿Que pidio el cartel de 20230802921?",
        "args": '{"nro_sicop": "20230802921"}',
        "respuesta": "Lineas del cartel con cantidad, precio estimado y codigo CL.",
        "no_usar": ["El precio estimado es el ESTIMADO del cartel, no el ofertado: no lo confundas con precio de venta."],
        "casos": "Saber que se pidio antes de que se oferte.",
    },
    "sicop_fact_oferta": {
        "para": "Hecho de oferta: quien oferto, a que precio (CRC) y en que linea. Nivel: CAPTACION (lineas ofertadas).",
        "preguntar": "¿Quien oferto en 20180800315 y a cuanto?",
        "args": '{"nro_sicop": "20180800315"}',
        "respuesta": "Por linea: oferente, cantidad, precio CRC (USD convertido con TC de la fila).",
        "no_usar": [
            "Los precios USD ya vienen convertidos a CRC (PU_OFERTADO_CRC): no vuelvas a convertir ni los sumes en USD con CRC.",
            "Puede faltar el proveedor en algunas ofertas (CEDULA_PROVEEDOR null): no son duplicados.",
        ],
        "casos": "Analisis de precios ofertados por linea.",
    },
    "sicop_fact_adjudicacion": {
        "para": "Hecho de adjudicacion: quien gano, por cuanto (CRC), en que linea. Nivel: CAPTACION.",
        "preguntar": "¿Quien gano y por cuanto en 20230802921?",
        "args": '{"nro_sicop": "20230802921"}',
        "respuesta": "Lineas adjudicadas con monto CRC y proveedor.",
        "no_usar": [
            "Es CAPTACION: la factura real es la ejecucion (sicop_fact_orden). No dimensiones negocio solo por adjudicaciones.",
            "Las adjudicaciones divididas (una linea a varios) sobreviven como filas separadas.",
        ],
        "casos": "Medir captacion por proveedor/institucion/familia.",
    },
    "sicop_fact_contrato": {
        "para": "Hecho de contrato por linea: precio contratado (CRC) y descripcion (marca/modelo).",
        "preguntar": "¿Que lineas contrato el CE201901000208 y a cuanto?",
        "args": '{"nro_contrato": "CE201901000208"}',
        "respuesta": "Lineas del contrato con precio CRC (USD convertido con TC de la fila).",
        "no_usar": [
            "Algunos contratos NO tienen lineas publicadas por la fuente (hueco declarado): fact_contrato devuelve 0 y es correcto.",
            "Puedes filtrar por nro_sicop si no conoces el numero de contrato.",
        ],
        "casos": "Bajar de contrato a producto/linea.",
    },
    "sicop_fact_orden": {
        "para": "Hecho de EJECUCION: UNA fila por orden con TOTAL_ORDEN (solo CRC sumable).",
        "preguntar": "¿Que ordenes se ejecutaron del procedimiento 20230802921?",
        "args": '{"nro_sicop": "20230802921", "limit": 10}',
        "respuesta": "Ordenes con TOTAL_ORDEN_CRC (convertido) y estado.",
        "no_usar": [
            "NUNCA sumes TOTAL_ORDEN_ORIG por fila: la tabla cruda replica el total por linea (infla 3,5x). Este hecho ya deduplica.",
            "Las ordenes marcadas ES_OUTLIER=S (montos absurdos de la fuente) NO deben sumarse.",
            "Si pasas nro_sicop, filtra por ese campo (no confundas con nro_orden).",
        ],
        "casos": "Nivel de ejecucion: la cifra que realmente se paga.",
    },
    "sicop_fact_recepcion": {
        "para": "Hecho de RECEPCION por linea: cantidad recibida, estado y dias de adelanto/atraso. Nivel: ENTREGA.",
        "preguntar": "¿Que recibio el contrato CE201901000208?",
        "args": '{"nro_contrato": "CE201901000208"}',
        "respuesta": "Lineas recibidas con cantidad, estado y dias.",
        "no_usar": [
            "Muchas recepciones no tienen proveedor atribuible (la fuente no trae contrato): la entrega por proveedor es cota inferior.",
        ],
        "casos": "Medir cumplimiento de entrega.",
    },

    # ---------------- CALIDAD Y SERIES ----------------
    "sicop_mes_publicacion": {
        "para": "Mes de publicacion REAL por procedimiento (derivado de FECHA_PUBLICACION del cartel). Corrige la trampa de MES_PUBLICACION.",
        "preguntar": "¿Cuantos procedimientos se publicaron en mayo 2020 (serie correcta)?",
        "args": '{"mes": "202005"}',
        "respuesta": "Procedimientos con MES_REAL, MES_PRIMERA_VISTA (el crudo) y flag DESFASADO.",
        "no_usar": [
            "CRITICO: MES_PUBLICACION de las tablas crudas NO es el mes de publicacion real (es el primer zip donde se vio la fila; ~21% desfasados). Para series temporales usa ESTA tool o el campo MES_REAL.",
        ],
        "casos": "Toda serie mensual/estacionalidad correcta.",
    },
    "sicop_ctl_deriva": {
        "para": "Mapa de deriva de esquema por anio: presente y llenado de cada campo. Regla: ninguna serie multianual sin declarar sus huecos.",
        "preguntar": "¿Cual es el llenado de PROD_ID_CL por anio?",
        "args": '{"conjunto": "adjudicaciones"}',
        "respuesta": "Por campo/anio: % de llenado y presencia.",
        "no_usar": [
            "Antes de construir una serie multianual, consulta la deriva: campos como CODIGO_PRODUCTO_CL tienen llenado parcial en 2020/2023/2024.",
        ],
        "casos": "Declarar huecos antes de analizar series por producto.",
    },
    "sicop_catalogo_campo": {
        "para": "Diccionario de datos navegable: tipo, llenado, clave, trampa, unidad y regla de join por campo.",
        "preguntar": "¿Que trampas tiene el campo PRECIO_UNITARIO?",
        "args": '{"tabla": "contratadas", "campo": "precio"}',
        "respuesta": "Por campo: trampa documentada, unidad, regla de join.",
        "no_usar": [
            "El filtro es por texto parcial (ej. 'contratadas' matchea 'sicop_lineas_contratadas'): si pones el nombre exacto de la tabla con 'sicop_' tambien funciona.",
        ],
        "casos": "Entender un campo antes de usarlo en un analisis.",
    },
    "sicop_competencia_por_regimen": {
        "para": "Metricas de competencia re-estratificadas por regimen de evaluacion: gana el mas barato por regimen.",
        "preguntar": "¿En los regimenes PRECIO_PURO siempre gana el mas barato?",
        "args": '{}',
        "respuesta": "Por regimen: % de veces que gana el mas barato.",
        "no_usar": ["Solo tiene sentido con PRECIO_PURO: en MIXTO no se espera que gane el mas barato siempre."],
        "casos": "Validar la competencia real del mercado.",
    },
    "sicop_bccr_tc": {
        "para": "Tipo de cambio CRC/USD del dia guardado (se consulta UNA vez en la manana; el resto del dia se lee de ahi).",
        "preguntar": "¿Cual es el tipo de cambio de hoy?",
        "args": '{}',
        "respuesta": "TC compra/venta y fuente (BCCR oficial o implicito de la fuente).",
        "no_usar": [
            "No golpea la API del BCCR por pregunta: usa el guardado del dia. Para historico de TC, usa el implicito por mes de la fuente (via fact_orden TC_APLICADO).",
        ],
        "casos": "Convertir montos USD a CRC en una respuesta.",
    },

    # ---------------- AUTO-GESTION ----------------
    "sicop_diagnostico": {
        "para": "Diagnostico de salud del sistema: que necesita atencion (tests fallidos, meses con huecos, ultima corrida, recencia, senales).",
        "preguntar": "¿Como esta la base?",
        "args": '{}',
        "respuesta": "Tests fallidos, ultima corrida, meses sin lineas_cartel, senales pendientes.",
        "no_usar": [
            "Es el PUNTO DE ENTRADA de cualquier gestion: correlo primero antes de reparar algo.",
        ],
        "casos": "Un agente decide que reparar/gestionar.",
    },
    "sicop_resumen": {
        "para": "Estado de la base: tablas cargadas y filas (diagnostico).",
        "preguntar": "¿Cuantas filas tiene la base?",
        "args": '{}',
        "respuesta": "Conteos por tabla (cacheado 6h).",
        "no_usar": ["Los conteos estan cacheados: no esperes que reflejen cambios en el minuto."],
        "casos": "Verificacion rapida de volumen.",
    },
    "sicop_gold_status": {
        "para": "Estado del gold: corridas y tests como gate (publicacion atomica).",
        "preguntar": "¿Cual fue el resultado de la ultima corrida?",
        "args": '{}',
        "respuesta": "Ultimas corridas con estado y los tests PASS/FAIL.",
        "no_usar": ["Una corrida BLOQUEADO tiene tests fallidos: no publiques sobre ella."],
        "casos": "Confirmar que una reparacion quedo bien (gate).",
    },
    "sicop_corrida_pasos": {
        "para": "Log estructurado del pipeline por corrida (tc_dia, vigilancia, extractor, recarga, bronze, silver, gold, tests).",
        "preguntar": "¿Que paso en la ultima corrida del ciclo?",
        "args": '{}',
        "respuesta": "Por paso: estado, detalle, filas, duracion.",
        "no_usar": ["Es lectura, no ejecucion: para disparar el ciclo usa sicop_ciclo_diario."],
        "casos": "Monitorear una reparacion en curso (async).",
    },
    "sicop_reconciliar": {
        "para": "Reconciliacion: meses donde la fuente publico ZIP pero la base esta vacia (hueco real).",
        "preguntar": "¿Hay meses con huecos?",
        "args": '{"solo_reporte": true}',
        "respuesta": "Huecos reales + quirks verificados (NO reparables).",
        "no_usar": [
            "Los meses 202005/202008/202108 aparecen como 'quirks' verificados: NO los repares (la fuente no publica lineas bajo esos meses).",
            "Con solo_reporte=False encola reparaciones: usalo con criterio, no en bucle.",
        ],
        "casos": "Detectar huecos de carga reales.",
    },
    "sicop_reparar_mes": {
        "para": "REPARA un mes: modo liviano por defecto (NO re-descarga: reutiliza la extraccion ya presente), broncea, reconstruye silver+gold y corre el gate.",
        "preguntar": "Repara el mes 202608.",
        "args": '{"aaaamm": "202608"}',
        "respuesta": "Corrida encolada (async): monitorea con sicop_corrida_pasos.",
        "no_usar": [
            "Por defecto es liviano (no re-descarga ~200GB). reextraer=True SOLO si sabes que la fuente cambio de verdad.",
            "No repares quirks (202005/202008/202108) ni meses futuros.",
            "Las reparaciones se serializan con lock: no dispares varias a la vez.",
        ],
        "casos": "Llenar un hueco de carga real detectado por sicop_reconciliar.",
    },
    "sicop_ciclo_diario": {
        "para": "EJECUTA el ciclo diario de las 06:00: vigilancia + consolidar + senales + cola + gold.",
        "preguntar": "Corre el ciclo diario.",
        "args": '{}',
        "respuesta": "Resultado del ciclo (async).",
        "no_usar": [
            "El cron de las 06:00/18:00 CR ya lo corre: solo dispáralo manualmente si necesitas un ciclo fuera de horario.",
        ],
        "casos": "Forzar un ciclo para reflejar un cambio de la fuente.",
    },
    "sicop_politica": {
        "para": "Pruebas de politica (enforcement): ruta cruda, SQL libre, mezcla de monedas. Si alguna falla, la entrega falla.",
        "preguntar": "¿Pasan las pruebas de politica?",
        "args": '{}',
        "respuesta": "Resultado de cada prueba (P1-P5).",
        "no_usar": ["Es el gate de integridad: si falla, no se publica."],
        "casos": "Confirmar que no hay SQL libre ni acceso crudo.",
    },
    "sicop_carril": {
        "para": "Carril actual del MCP: operacion (canonico) o laboratorio (NO_APTO_PARA_DECISION).",
        "preguntar": "¿En que carril estoy?",
        "args": '{}',
        "respuesta": "Carril y si la decision es elegible.",
        "no_usar": ["En laboratorio ninguna respuesta es apta para decision."],
        "casos": "Saber si un agente puede tomar decisiones.",
    },

    # ---------------- DECISIONES ----------------
    "sicop_senales": {
        "para": "Cola de senales del dia (watchlist): tipo, prioridad, nro_sicop, evidencia.",
        "preguntar": "¿Que senales hay hoy?",
        "args": '{}',
        "respuesta": "Senales con prioridad y evidencia.",
        "no_usar": ["Son alertas de revision, no conclusiones."],
        "casos": "El agente decide que revisar hoy.",
    },
    "sicop_resultado": {
        "para": "Decisiones registradas (SCH_RESULTADO): grano nro_sicop x nro_linea.",
        "preguntar": "¿Que decisiones registramos sobre 20230802921?",
        "args": '{"nro_sicop": "20230802921"}',
        "respuesta": "Decisiones con estado.",
        "no_usar": ["Es lectura del historial de decisiones."],
        "casos": "Auditar que decidio el modelo/sistema.",
    },
    "sicop_registrar_resultado": {
        "para": "REGISTRA una decision de oferta/participacion (append-only, contexto congelado obligatorio).",
        "preguntar": "Registra que NO ofertamos en la linea 1 de 20230802921.",
        "args": '{"nro_sicop": "20230802921", "nro_linea": "1", "decision": "NO_OFERTAR", "build_id": "...", "modelo_version": "...", "features_hash": "..."}',
        "respuesta": "Confirmacion del registro.",
        "no_usar": [
            "Es append-only: no puedes borrar ni editar una decision. Registra con el contexto correcto.",
            "Exige build_id, modelo_version y features_hash (contexto congelado): no los inventes.",
        ],
        "casos": "Persistir cada decision de oferta para auditoria.",
    },

    # ---------------- MONITOREO ----------------
    "sicop_actividad_mcp": {
        "para": "Actividad reciente del MCP: quien pidio que (agente), por hora, tools top y las ultimas llamadas.",
        "preguntar": "¿Que le han pedido al MCP hoy?",
        "args": '{"horas": 24}',
        "respuesta": "Total de llamadas, por hora, tools top, ultimas llamadas con duracion.",
        "no_usar": ["No muestra el prompt natural de la IA (eso vive en el cliente): muestra las tools que llamo."],
        "casos": "Monitorear el uso desde claude.ai u otros clientes.",
    },
    "sicop_registro": {
        "para": "Auditoria de respuestas: agente, herramienta, params, build_id, conteo, carril.",
        "preguntar": "¿Cual fue la ultima respuesta registrada?",
        "args": '{"limit": 20}',
        "respuesta": "Registro de respuestas.",
        "no_usar": ["Es el log crudo: para resumen usa sicop_actividad_mcp."],
        "casos": "Auditoria tecnica.",
    },
    "sicop_vigilancia": {
        "para": "Ultimos chequeos de reescritura de la fuente (meses objetivo).",
        "preguntar": "¿Detecto la fuente alguna reescritura?",
        "args": '{}',
        "respuesta": "Chequeos por mes con resultado.",
        "no_usar": ["Un cambio detectado dispara re-extraccion en el ciclo: no la fuerces a mano."],
        "casos": "Saber si la fuente reescribio algo.",
    },

    # ---------------- AVANZADO ----------------
    "sicop_ficha_esosa": {
        "para": "FASE 4 (prueba del plan): rehace la ficha del competidor ESOSA vs SONDEL desde la capa canonica.",
        "preguntar": "Rehace la ficha de ESOSA vs SONDEL.",
        "args": '{}',
        "respuesta": "Ficha comparativa.",
        "no_usar": ["Es una prueba/analisis de Fase 4, no una tool de consulta general."],
        "casos": "Validar el pipeline canonico.",
    },
    "sicop_backtest_invitaciones": {
        "para": "FASE 4: replay de invitaciones pasadas (con cuanto descuento se gana).",
        "preguntar": "¿Con cuanto descuento se ganaba en las invitaciones pasadas?",
        "args": '{}',
        "respuesta": "Resultado del backtest.",
        "no_usar": ["Es un modelo/experimento: sus numeros no son dato observado de la fuente."],
        "casos": "Calibrar descuentos.",
    },
    "sicop_holdout": {
        "para": "FASE 4: holdout temporal (<=2024 vs 2025-26) + gate de muerte del modelo.",
        "preguntar": "¿Pasa el modelo el holdout?",
        "args": '{}',
        "respuesta": "Metricas en train/test temporal.",
        "no_usar": ["Es el gate de validacion del modelo, no para consultas."],
        "casos": "Evitar sobreajuste.",
    },
    "sicop_pendientes": {
        "para": "Pendientes del traspaso (p1_conversion_cartera, p3_catalogo_familias, p5_recurrente_vs_recurrido, p6_sanciones_vigencia, p7_tamano_historico).",
        "preguntar": "¿Que queda pendiente del traspaso?",
        "args": '{}',
        "respuesta": "Estado de cada pendiente.",
        "no_usar": ["Es una lista de tareas, no una consulta de datos."],
        "casos": "Seguimiento de roadmap.",
    },
    "sicop_cgr_buscar": {
        "para": "Buscador CGR: PDFs de resoluciones por termino (ej. un NRO_SICOP). USO DIRIGIDO, no barrido.",
        "preguntar": "Busca resoluciones de la CGR sobre 20230802921.",
        "args": '{"termino": "20230802921"}',
        "respuesta": "Resoluciones con enlace.",
        "no_usar": [
            "Es USO DIRIGIDO: no lo barran en loop (la CGR limita). No hay gate legal completo: usalo como complemento.",
        ],
        "casos": "Encontrar la resolucion legal de un procedimiento.",
    },
}
