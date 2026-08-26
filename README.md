# sicop_mcp

Servidor de datos SICOP (contratacion publica de Costa Rica, datos abiertos 2020-2026)
expuesto como **API REST** y como **servidor MCP** para asistentes de IA.

- **Datos:** `Salidas/` del paquete SICOP (~4,3M filas cargadas en Postgres en 31 tablas:
  13 conjuntos por anio 2020-2026 + 18 tablas derivadas gold).
- **Stack:** Django 6 + DRF + Celery + Postgres + Redis. Mismo patron que mwt/consola-mwt-one.
- **Regla del dominio:** toda cifra de negocio de un proveedor declara su nivel de medicion
  (captacion = adjudicaciones · ejecucion = ordenes de pedido · entrega = recepciones).

## Arranque local

Requiere: Python 3.12+ (probado en 3.14), PostgreSQL 16/18 local, Redis (o el broker que uses).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# crear DB (una vez):
#   createuser -U postgres sicop -P
#   createdb -U postgres -O sicop sicop

python manage.py migrate
python manage.py load_sicop --sync     # carga los CSV de Salidas/ (SICOP_DATA_DIR en .env)
python manage.py runserver 127.0.0.1:8000
```

### Cargar datos via Celery (patron del stack)

```powershell
celery -A config worker -l info        # worker
python manage.py load_sicop            # encola una tarea por archivo
python manage.py load_sicop --only contratos --force
```

### Servidor MCP

```powershell
python -m sicop.mcp_server                            # stdio (para clientes MCP)
python -m sicop.mcp_server streamable-http --port 9010  # HTTP
```

Tools MCP (18): `sicop_ficha_proveedor` (ejecucion vs captacion), `sicop_mercado_familia`,
`sicop_competencia_procedimiento`, `sicop_producto`, `sicop_producto_historia` (serie de
precios por anio), `sicop_cara_a_cara` (dos proveedores), `sicop_expediente`,
`sicop_adjudicaciones`, `sicop_carteles_objetados`, `sicop_representantes`,
`sicop_representante_competencia`, `sicop_excepciones`, `sicop_sanciones`,
`sicop_precios_institucion`, `sicop_perdidas_baratas` (oferto mas barato y perdio),
`sicop_campo_buscar`, `sicop_regimen_evaluacion`, `sicop_resumen`.

Toda respuesta de negocio lleva el **sobre** (envelope del plan §5.4): `nivel_medicion`,
`cobertura_cruce` (0.626), `moneda` y `caveats`.

### API REST

| Recurso | Ejemplo |
|---|---|
| `/api/v1/adjudicaciones/?CEDULA_PROVEEDOR=3101029593&ANO=2026` | lineas adjudicadas |
| `/api/v1/proveedores/?cedula=3101029593` | agregado por proveedor (monto, lineas, instituciones) |
| `/api/v1/instituciones-agg/?cedula=4000042139` | agregado por institucion |
| `/api/v1/catalogo/?FAMILIA_UNSPSC=81112399` | catalogo de productos |
| `/api/v1/cartera/?CEDULA_PROVEEDOR=3101476018` | ejecucion vs captacion por anio |
| `/api/v1/desempeno/` | cumplimiento de entrega por proveedor |
| `/api/v1/competencia/?NRO_SICOP=...` | oferentes por linea |
| `/api/v1/carteles-objetados/` · `/api/v1/excepciones/` · `/api/v1/representantes/` · `/api/v1/ranking/` | capa gold |
| `/api/v1/cara-a-cara/?cedula_a=&cedula_b=` | comparacion directa de dos proveedores |
| `/api/v1/producto-historia/?codigo_cl=` | serie de precios ofertados por anio de un producto |
| `/api/v1/perdidas-baratas/?cedula=` | lineas donde oferto mas barato y perdio |
| `/api/v1/buscar/?termino=` | busqueda en catalogo, proveedores e instituciones |
| `/api/v1/regimen-evaluacion/?nro_sicop=` | factores y pesos de evaluacion de un procedimiento |
| `/api/v1/resumen/` · `/api/v1/estado-carga/` | diagnostico |

Filtros por igualdad con el nombre de columna exacto (`CEDULA_PROVEEDOR`, `NRO_SICOP`, `ANO`, ...)
y `?search=` en los recursos con texto.

## FASE 2 — ciclo diario (cron 06:00)

```bash
python manage.py ciclo_diario               # corrida manual del ciclo
celery -A config worker -l info             # worker (ya en tu stack)
celery -A config beat -l info               # cron: ciclo-diario 06:00 · vigilancia 06:05 · consolidar 06:15
```

- **Ciclo diario**: vigilancia de reescritura (mes en curso + 3 cerrados + 2 rotativos) → consolidar PENDIENTES
  de resultado → señales de la watchlist → cola priorizada → gold + tests-gate.
- **`resultado_decision`** (SCH_RESULTADO v1, `/api/v1/resultados/`, POST `/api/v1/resultado-registrar/`):
  grano `(nro_sicop, nro_linea, decision_id)`, **append-only**, contexto congelado obligatorio
  (`build_id/snapshot_ts/modelo_version/features_hash`), `override` como campo clave.
- **Señales** (`/api/v1/senales/`): cliente_participa/adjudicado/perdio, cartel_objetado, sancion_nueva,
  institucion_vigilada, perdio_por_poco (watchlist.json).
- **Vigilancia** (`/api/v1/vigilancia/`): ETag/Content-Length de los meses objetivo vs `ctl_mes_fuente`.

Tools MCP: `sicop_registrar_resultado`, `sicop_resultado`, `sicop_senales`, `sicop_vigilancia`,
`sicop_ciclo_diario`, `sicop_consolidar_resultados`.

## FASE 3 — enforcement físico + dos carriles + registro

- **Enforcement** (`/api/v1/politica/`): middleware que **bloquea con 403** cualquier request con
  rutas crudas (`/salidas/`, `.csv`, `.zip`, `file://`, `..\`) o secretos; pruebas de política
  (no SQL libre, no mezcla de monedas, no rutas crudas) → 5/5 PASS.
- **Dos carriles**: `SICOP_CARRIL=operacion` (canónico) o `SICOP_CARRIL=laboratorio`
  (toda respuesta etiquetada `NO_APTO_PARA_DECISION`, `decision_eligible:false`).
  El carril laboratorio agrega la tool `sicop_lab_sql` (**SQL read-only**, solo SELECT/WITH,
  max 200 filas, rechaza DELETE).
- **Registro de respuestas** (`/api/v1/registro/`, tool `sicop_registro`): cada llamada MCP y
  request API queda en `registro_respuesta` (agente, herramienta, params, build_id, conteo,
  carril, duración, status).

## FASE 4 — prueba (ficha ESOSA, backtest, holdout) + pendientes P1-P11

```bash
python manage.py fase4 --json        # ficha ESOSA desde gold + backtest + holdout (gate de muerte)
python manage.py pendientes --json   # P1-P7
```

- **Ficha ESOSA** (`/api/v1/prueba-fase4/?solo=ficha`, tool `sicop_ficha_esosa`): reproducida desde la capa
  canonica — **desempeno EXACTO** (98,6% / 577 lineas), captacion reproduce el patron (pico 2022, colapso 2023),
  competencia/cara-a-cara limitados a la cobertura del cruce (62,6%) hasta que cargue el recuperado.
- **Backtest** (tool `sicop_backtest_invitaciones`): replay de invitaciones pasadas (descuento necesario para ganar).
- **Holdout + gate de muerte** (tool `sicop_holdout`): entrenar <=2024, probar 2025-26; si el modelo no supera
  el ancla del pliego se descarta (queda memoria + vigilancia).
- **Pendientes**: `p1_conversion_cartera` (TC implicito 460-690 CRC/USD, BCCR oficial gate pendiente) ·
  `p3_catalogo_familias` (9.295 familias derivadas) · `p5_recurrente_vs_recurrido` · `p6_sanciones_vigencia`
  (1 sancionado ganando vigente) · `p7_tamano_historico` (1,04% cambio → **no SCD2**) · `p10_bronze_zip_miembro`
  (bronze desde zip, fila cruda literal). P11 `resultado_decision` cerrado en FASE 2.

## Extras del plan — Atlas, CGR, BCCR

- **Atlas** (`/atlas/`): app de navegación del corpus. Decisiones del plan respetadas:
  *ninguna cifra viaja sola* (cada pantalla muestra su sobre), *la calidad entra primero*
  (`/atlas/calidad/`: deriva por año, tests-gate, corridas, vigilancia, trampas),
  *trampas bloqueadas no documentadas* (la UI advierte sobre comparar monedas y precios
  cross-año sin CL), y *la app le pone cara al harness* (señales del día visibles).
  Pantallas: dashboard, buscar, proveedores, ficha de proveedor, producto (historia),
  procedimiento (expediente+competencia+régimen+invitados+recursos), mercado por familia.
- **Buscador CGR** (`/api/v1/cgr/?termino=`, tool `sicop_cgr_buscar`): PDFs de resoluciones
  de texto nativo. **USO DIRIGIDO, no barrido**; gate legal pendiente (términos CGR no leídos).
- **TC BCCR** (`/api/v1/bccr-tc/?fecha=`, tool `sicop_bccr_tc`): BCCR oficial (series 317/318)
  si `BCCR_TOKEN`/`BCCR_EMAIL` en `.env`; sin token devuelve el **TC implícito de la fuente**
  (mediana anual CRC/USD) marcado como tal.
- **Invitaciones**: 42,2M filas cargadas + `invitados_vs_ofertantes`.

## Docker (VPS)

```bash
docker compose up -d --build
# expone 8400 -> django (puerto libre, no choca con 8100 de consola-mwt-one), con Salidas montado en /data/salidas
```

## FASE 1 — capa canonica (bronze + silver + control)

```bash
python manage.py fase1                # bronze -> silver (6 hechos) -> tests-gate -> gold atomico
python manage.py fase1 --solo-tests   # solo correr los tests como gate
python manage.py recalcular_derivadas # producto_firma, recursos_desenlace, tiempos_por_etapa, precios_identicos, invitados_vs_ofertantes, regimen_evaluacion, ctl_deriva, catalogo_campo
```

- **Bronze** (`/api/v1/bronze/`): fila cruda inmutable + `HASH_FILA` + `CORRIDA_ID` + mes.
- **Silver — 6 hechos** (grano correcto, `DECIMAL(18,4)`, trio de moneda, bitemporalidad `OBSERVADO_DESDE/HASTA/ES_VIGENTE`):
  `/fact-requerimiento` (cartel, proc x linea x partida) · `/fact-oferta` (proc x oferta x linea) ·
  `/fact-adjudicacion` (acto x proc x linea x proveedor) · `/fact-contrato-linea` ·
  `/fact-orden` (**una fila por NRO_ORDEN**, `TOTAL_ORDEN` una sola vez, solo CRC sumable) ·
  `/fact-recepcion`.
- **Control** (`/api/v1/ctl-*`): corrida, mes fuente (hash zip), esquema, cuarentena, **tests como gate**.
- **catalogo_campo** (`/api/v1/catalogo-campo/`): diccionario de datos navegable (tipo, llenado, clave, trampa, unidad, regla de join).
- **Publicacion atomica**: gold no se publica si un test del gate falla (queda la version anterior).

Tools MCP: `sicop_fact_requerimiento/oferta/adjudicacion/contrato/orden/recepcion`, `sicop_catalogo_campo`,
`sicop_ctl_deriva`, `sicop_regimen`, `sicop_competencia_por_regimen`, `sicop_gold_status`.

## Datos

- **NIVEL DE MEDICION:** `cartera` compara `MONTO_EJECUTADO_CRC` (solo colones, dedupe por `NRO_ORDEN`)
  contra `MONTO_ADJUDICADO_CRC`. Medir por adjudicaciones subestima hasta 59x (caso SONDEL 2026: 64x).
- **Monedas:** las ordenes traen 5 monedas (CRC/USD/EUR/JPY/GBP); solo se suman colones.
- **Cobertura:** `competencia_por_linea` cubre el 62,6% del cruce oferta x oferente (documentado en el paquete).
- **Privacidad:** `inhibiciones` contiene funcionarios; no publicar consolidados sin decision expresa (Ley 8968).
- Limpieza: las celdas invalidas de montos/fechas se cargan como NULL (contadas en `estado-carga`).
