# Auditoría del cron de extracción — cierre de los 6 puntos

- **Fecha:** 2026-09-30
- **Alcance:** `sicop_mcp/` (código que corre el ciclo), más la documentación de
  horario. Fuera de alcance: los datos crudos (prohibido por enforcement) y los
  informes históricos de `07_panel/` y `graphify-out/` (generados).
- **Origen:** contraste entre la skill `sicop_extraccion` y el cron real. De 11
  chequeos obligatorios de §7, 3 estaban plenos, 3 parciales y 5 ausentes del
  camino automático.

Regla de la skill que se respetó en todo: **toda afirmación va con el comando que
la produjo.**

---

## Punto 1 — A2 dentro del gate del cron

**Qué se hizo.** Se creó `sicop_mcp/sicop/a2.py`, que **reutiliza** la función
`a2()` del harness (`03_scripts/harness_actualizado/harness_sicop.py`) en lugar
de portarla. `control.run_tests()` ahora la invoca y traduce su resultado a
`ctl_test`:

- `BLOQUEADO` → `a2_bloqueado = FAIL` (detiene la publicación de gold).
- `REVISAR` / `CONFIABLE` → PASS + una fila por desvío con su severidad.
- `NO_EVALUADO` (harness o insumos ausentes) → filas `RESULTADO='NO_EVALUADO'`,
  nunca un PASS. Cubre inventario del zip, salto de magnitud y cobertura del cruce.

**Evidencia** (A2 completo sobre los datos reales de `Salidas/`, con estado
temporal para no tocar la línea base):

```
conjuntos esperados: 25
A2 veredicto: REVISAR | desvios: 5 | no_evaluados: 3 | 2.1s
   [REVISAR] duplicados: 11420917 filas duplicadas por clave natural
   [REVISAR] montos: 1 montos negativos
   [REVISAR] salto_magnitud: 377 precios fuera de 100× la mediana de su CL
   [INFO] cedula_institucional_como_proveedor: 358 líneas
   [INFO] linea_base: primera corrida: se crea línea base
```

**Mejora aplicada (2026-09-30).** El chequeo de salto de magnitud marcaba precios
de ₡1 frente a la mediana de su código (la skill §8 dice que los precios de 1 CRC
son simbólicos). Se filtraron los precios `<= 1` **antes** de calcular la mediana
y de marcar: el conteo bajó de **377 a 159** y los que quedan son anomalías de
magnitud reales (p. ej. ₡132.960.450 contra mediana ₡80.000). Cambio en
`harness_actualizado/harness_sicop.py` (copia del repo y copia viva del cron).

---

## Punto 2 — `registrar_esquema` / `registrar_cuarentena` y esquema como gate

**Qué se hizo.**
- `loader.load_csv()` ahora llama `control.registrar_esquema(conjunto, header)`:
  `ctl_esquema` deja de ser una tabla muerta.
- `control._chequeo_esquema()` combina (a) las `columnas_ausentes` del
  `manifiesto.json` y (b) `ctl_esquema` contra las columnas esperadas del
  extractor (`CONJUNTOS` + `PESADOS` = 25). Cualquier ausencia → **FAIL**
  (`esquema_columnas`).
- `control.registrar_cuarentena_desde_archivo()` vuelca `_cuarentena/*.csv` a
  `ctl_cuarentena` (idempotente por corrida+archivo); `ciclo.py` lo corre tras el
  extractor.

**Evidencia** (validación sobre datos reales):

```
columnas_ausentes (manifiesto): 0
columnas_ausentes (ctl_esquema): {}
chequeo_esquema: {}
```

Pruebas: `EsquemaYCUarentenaDBTest` (detección de columna ausente con
`ctl_esquema`, alta y no-duplicación de cuarentena).

---

## Punto 3 — conjuntos que faltaban

**Qué se hizo.**
- `bronze.BRONZE_SETS`: 23 → **25** (se agregaron `evaluacion_ofertas` y
  `lineas_sistema`).
- `loader.CORE_SETS`: 24 → **25** (se agregó `lineas_sistema`).
- Nuevo modelo `SicopLineasSistema` + migración `0008`.
- `retencion.py` incluye `sicop_lineas_sistema`.
- El extractor ya sacaba los 25 (el cron siempre pasa `--pesados`): lo que
  faltaba era broncearlos y cargarlos.

**Evidencia.** `manage.py makemigrations --check` → `No changes detected`.
`columnas_esperadas()` → 25 conjuntos con `ordenes_pedido` e `invitaciones`.

---

## Punto 4 — horario unificado (se conserva el horario muerto)

**Decisión del usuario:** mantener el horario real del cron por temas de carga
(**00:00 CR, domingo a viernes**), y corregir la documentación en vez de mover el
beat.

**Qué se hizo.** Se alineó la documentación al código real:
`sicop_mcp/README.md`, `config/settings.py` (comentarios), `sicop/ciclo.py`,
`sicop/tasks.py`, `sicop/mcp_server.py` (instrucciones y tools),
`sicop/atlas/tool_docs.py`, `management/commands/ciclo_diario.py`,
`sicop/vigilancia.py`, `sicop/resultado.py`, `PLAN_BASE_INTELIGENTE.md`,
`01_contexto/PLAN_CONSTRUCCION.md`, `08_kb/PLAN_CONSTRUCCION_2026-08-25.md`,
`01_contexto/SCH_RESULTADO_v1.md`, `08_kb/SCH_RESULTADO_v1.md`,
`04_verificaciones/ACTA_FASE0_2026.md`.

Semántica documentada: `00:00` CR procesa el ZIP que la fuente publicó **ayer a
las 08:00**; el ciclo corre en horario muerto para que la re-extracción pesada no
compita con la actividad normal. No se tocaron los informes históricos
(`07_panel/`, `SICOP_paquete_Alejandro_COMPLETO/`) ni los reportes generados
(`graphify-out/`).

---

## Punto 5 — sello sha256 de código + configuración por corrida

**Qué se hizo.**
- Nuevo módulo `sicop_mcp/sicop/sellos.py` (hash determinista, `comparar`,
  `verificar`; artefactos de código + config, se sellan solo los que existen).
- Nuevo modelo `CtlSello` + migración `0008`.
- `ciclo.py`: sella al arrancar (`sello`), reverifica tras el extractor
  (`sello_verificacion`); si algo cambió **no recarga, no broncea, no reconstruye
  silver y no marca la señal como atendida** (`sello_roto`).
- `loader.recargar_anio_afectado(..., sello_esperado=...)`: **rechaza el merge**
  con `RuntimeError` si el código/config no coincide con el del arranque.

**Evidencia.** Sello real de esta máquina:

```
sellos: ['harness_actualizado/sicop_loop.py', 'harness_actualizado/harness_sicop.py',
         'estado/watchlist.json', 'estado/politica_acciones.json']
```

Pruebas: `FuncionesDeSelloTest`, `MergeRechazaMezclaTest`, `SelloDBTest`.

---

## Punto 6 — decisión escrita sobre `inhibiciones` en la API

**Qué se hizo.** Decisión completa en
`04_verificaciones/DECISION_INHIBICIONES_API.md`. Resumen ejecutable:
- La base conserva el dato completo; la **API/MCP enmascaran** nombre y cédula por
  defecto (`SICOP_INHIBICIONES_NOMBRES` controla la excepción expresa).
- **Sin búsqueda libre por nombre** de funcionario.
- **Prueba de política P6** en el gate: si la minimización se revierte sin
  decisión, `pruebas_politica` falla.

**Evidencia.** `SerializerInhibicionesTest` y `PruebasPoliticaTest` (P6 = True).

---

## Verificación global

```bash
python manage.py test sicop.tests sicop.tests_loader_guard sicop.tests_gate
# TEST_EXIT=0  (37 tests, incluye 20 pruebas nuevas de los 6 puntos)
python manage.py makemigrations --check --dry-run
# No changes detected
python manage.py check
# System check identified no issues
```

**Notas de honestidad.**
- La migración `0008` también recoge tres modelos que existían **sin migración
  previa** (`DimEntidad`, `CtlTrampa`, `CtlRetencion`). Dejar la deriva habría
  vuelto imposible `makemigrations --check`. Si en el VPS esas tablas ya existían
  por DDL manual, el `migrate` fallará de forma visible y un operador lo resuelve
  (no hay borrado silencioso).
- El esquema como gate compara contra la config del extractor; por eso
  `a2.columnas_esperadas()` une `CONJUNTOS` + `PESADOS`. Si la fuente renombra un
  campo, el gate **bloquea y decide una persona** (no se adapta el parser a
  ciegas).
