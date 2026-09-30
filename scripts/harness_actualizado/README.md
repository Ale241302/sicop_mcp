# Harness de extracción SICOP

Copia **versionada** del harness de extracción/verificación de SICOP.

## Punto de entrada

`sicop_loop.py` es el extractor. Descarga los ZIP mensuales oficiales:
`https://dlsaobservatorioprod.blob.core.windows.net/fs-synapse-observatorio-produccion/Zip/{AAAAMM}.zip`
y produce los CSV anuales `{conjunto}_{anio}.csv` que alimentan Postgres.

Banderas principales:

| Bandera | Uso |
|---|---|
| `--year AAAA` | año a procesar (obligatorio) |
| `--months MM,MM` | sólo esos meses (por defecto, los 12) |
| `--pesados` | incluye `InvitacionProcedimiento` y `OrdenPedido` |
| `--replace` | con `--months`: reemplaza SOLO esos meses en el CSV anual (quita sus filas por `MES_ZIP`), re-descarga y reprocesa. Excluyente con `--force` |
| `--force` | reprocesa todo el año (reconstruye los CSV anuales; pesado) |
| `--base DIR` | **merge incremental**: antes de escribir, si el CSV anual de `--out` falta o es más chico, lo siembra desde `DIR` (p. ej. Salidas). Evita operar sobre una copia parcial |
| `--out DIR` | directorio de salida (en el ciclo diario: `/data/recuperacion`) |
| `--no-vigilancia` | no verificar reescrituras de meses ya en OK (corridas de desarrollo) |
| `--solo a,b` | sólo esos conjuntos |

## Despliegue (importante)

El harness **que corre en producción** NO se ejecuta desde este repo: vive en la VPS en
`/opt/sicop_data/scripts/harness_actualizado/` y el contenedor lo monta como `/data/scripts`
(ver `docker-compose.yml`, `SICOP_SCRIPTS_DIR`).

**Esta carpeta es la copia versionada (fuente de verdad para revisión).** Al cambiar el
extractor:

1. Editar y probar aquí.
2. Copiar a la VPS: `scp sicop_loop.py root@<vps>:/opt/sicop_data/scripts/harness_actualizado/` (con backup del vigente).
3. Verificar que el sha256 de la copia desplegada coincide con esta.
4. Reiniciar `celery-worker`/`celery-beat` si el cambio afecta al ciclo.

## Otros scripts

El resto de `.py` son utilidades de análisis/verificación usadas durante la construcción
(competencias, derivas, verificación de afirmaciones, etc.). No forman parte del ciclo diario.

## Uso desde el ciclo

`sicop/ciclo.py` y `sicop/tasks.py` (en el repo `sicop_mcp`) invocan el extractor con
`--base <SICOP_DATA_DIR>` para garantizar el merge incremental del CSV anual.
