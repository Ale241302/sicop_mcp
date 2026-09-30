"""Tablas de control + tests como gate + publicacion atomica de gold (plan Fase 1)."""
import csv
import json
import logging
import os
from datetime import datetime

from django.utils import timezone

from .models import (
    CtlCorrida, CtlTest, CtlMesFuente, CtlCuarentena, CtlEsquema,
    FactRequerimiento, FactOferta, FactAdjudicacion, FactContratoLinea,
    FactOrden, FactRecepcion, SicopProveedores,
)

logger = logging.getLogger(__name__)
OUTLIER = 10**12
# RESULTADO de un chequeo que NO pudo correr (no es PASS ni FAIL): la skill §0
# exige que "un chequeo que no corre sea distinguible de uno que pasa".
NO_EVALUADO = "NO_EVALUADO"


def registrar_corrida(corrida_id, alcance, notas=""):
    CtlCorrida.objects.create(CORRIDA_ID=corrida_id, ESTADO="EN_CURSO", ALCANCE=alcance,
                              NOTAS=notas, INICIADO_EN=timezone.now())


def cerrar_corrida(corrida_id, estado, notas=""):
    CtlCorrida.objects.filter(CORRIDA_ID=corrida_id).update(
        ESTADO=estado, CERRADO_EN=timezone.now(), NOTAS=notas)


def _test(corrida_id, name, ok, obtenido, umbral):
    CtlTest.objects.create(CORRIDA_ID=corrida_id, TEST=name,
                           RESULTADO="PASS" if ok else "FAIL",
                           VALOR_OBTENIDO=str(obtenido), UMBRAL=umbral)
    return ok


def _test_resultado(corrida_id, name, resultado, obtenido, umbral):
    """Registra un chequeo con resultado explicito (REVISAR / NO_EVALUADO / ...).

    Se usa para lo que no es ni PASS ni FAIL: desvíos que piden revisión humana
    y chequeos que no pudieron correr. Ambos quedan consultables en `ctl_test`,
    nunca confundibles con un PASS.
    """
    CtlTest.objects.create(CORRIDA_ID=corrida_id, TEST=name,
                           RESULTADO=resultado, VALOR_OBTENIDO=str(obtenido)[:2000],
                           UMBRAL=umbral)


def resumen_resultados(corrida_id):
    """{RESULTADO: n} de los chequeos de una corrida (para las notas de cierre)."""
    from django.db.models import Count

    return {r: n for r, n in CtlTest.objects.filter(CORRIDA_ID=corrida_id)
            .values_list("RESULTADO").annotate(n=Count("id"))}


def _columnas_ausentes_manifiesto():
    """Columnas que el extractor marcó como ausentes del CSV (manifiesto.json)."""
    from django.conf import settings

    p = os.path.join(settings.SICOP_DATA_DIR, "manifiesto.json")
    if not os.path.exists(p):
        return None
    try:
        man = json.loads(open(p, encoding="utf-8").read())
    except (json.JSONDecodeError, OSError):
        return None
    aus = {}
    for _mes, m in (man.get("meses") or {}).items():
        if m.get("estado") != "OK":
            continue
        for cname, cs in (m.get("conjuntos") or {}).items():
            for c in (cs.get("columnas_ausentes") or []):
                aus.setdefault(cname, set()).add(c)
    return {k: sorted(v) for k, v in aus.items()}


def _columnas_ausentes_esquema():
    """Compara lo visto por el loader (ctl_esquema) contra lo esperado (§7)."""
    from . import a2

    esperadas = a2.columnas_esperadas() if a2 else {}
    if not esperadas:
        return None
    vistas = {r["TABLA"]: (r["COLUMNAS_VISTAS"] or "").split(",")
              for r in CtlEsquema.objects.all().values("TABLA", "COLUMNAS_VISTAS")}
    aus = {}
    for conjunto, cols in esperadas.items():
        v = vistas.get(conjunto)
        if not v or v == [""]:
            continue  # conjunto no cargado todavia: no es ausencia de columna
        faltan = [c for c in cols if c and c not in v]
        if faltan:
            aus[conjunto] = faltan
    return aus


def _chequeo_esquema():
    """BLOQUEADO si falta cualquier columna esperada (§7). None = no evaluable."""
    man = _columnas_ausentes_manifiesto()
    esq = _columnas_ausentes_esquema()
    if man is None and esq is None:
        return None
    aus = {}
    for fuente in (man or {}, esq or {}):
        for k, v in fuente.items():
            aus.setdefault(k, set()).update(v)
    return {k: sorted(v) for k, v in aus.items()}


def registrar_cuarentena_desde_archivo(corrida_id, qdir):
    """Vuelca la cuarentena del extractor a `ctl_cuarentena` (idempotente).

    El extractor archiva crudas las filas que no puede reconstruir en
    `<salida>/_cuarentena/<conjunto>_<anio>.csv` (columnas CONJUNTO,
    MES_PUBLICACION, MOTIVO, N_CAMPOS, CAMPOS_CRUDOS). Antes ese directorio no
    llegaba a la base: la cuarentena existía en disco pero no era consultable.

    `qdir` puede ser el directorio `_cuarentena` o un archivo concreto.
    Devuelve el número de filas archivadas.
    """
    if not qdir or not os.path.exists(qdir):
        return 0
    if os.path.isdir(qdir):
        archivos = [os.path.join(qdir, f) for f in sorted(os.listdir(qdir))
                    if f.endswith(".csv")]
    else:
        archivos = [qdir]
    n = 0
    for archivo in archivos:
        base = os.path.basename(archivo)
        CtlCuarentena.objects.filter(CORRIDA_ID=corrida_id, ARCHIVO=base).delete()
        with open(archivo, encoding="utf-8-sig", newline="") as fh:
            for i, row in enumerate(csv.DictReader(fh), 1):
                motivo = row.get("MOTIVO") or ""
                ncampos = row.get("N_CAMPOS")
                if ncampos:
                    motivo = f"{motivo} (n_campos={ncampos})"
                registrar_cuarentena(
                    corrida_id, row.get("CONJUNTO"), base, i, motivo,
                    row.get("CAMPOS_CRUDOS"))
                n += 1
    return n


def run_tests(corrida_id):
    """Tests como gate (plan §3.5). Todos deben pasar para publicar gold."""
    from django.db.models import Count

    results = {}

    # 1. clave unica: requerimiento sin duplicados INTRA-anio (la repeticion cross-anio
    #    por snapshot es legitima). Umbral: <2% de claves repetidas.
    n = FactRequerimiento.objects.count()
    dup = 0
    if n:
        dup = sum(1 for g in FactRequerimiento.objects.values("NRO_SICOP", "NUMERO_LINEA", "NUMERO_PARTIDA")
                  .annotate(c=Count("id")) if g["c"] > 1)
    tasa = dup / n * 100 if n else 0
    results["clave_unica_requerimiento"] = _test(corrida_id, "clave_unica_requerimiento",
                                                 tasa < 2, f"{tasa:.2f}% repetidas ({dup})", "<2% (cross-anio legitimo)")

    # 2. no mezclar monedas: toda fila no-CRC con TOTAL_ORDEN_CRC DEBE tener
    #    TC_APLICADO (conversion explicita y auditable). CRC sin TC = mezcla
    #    silenciosa de monedas (prohibido). Antes no se convertia nada no-CRC;
    #    desde 2026-08-31 fact_orden convierte con TC implicito por mes.
    sin_tc = (FactOrden.objects.exclude(TOTAL_ORDEN_CRC__isnull=True)
              .exclude(MONEDA_ORDEN__isnull=True).exclude(MONEDA_ORDEN__in=["", "CRC"])
              .filter(TC_APLICADO__isnull=True).count())
    results["no_mezcla_monedas_orden"] = _test(corrida_id, "no_mezcla_monedas_orden",
                                               sin_tc == 0, f"{sin_tc} no-CRC con CRC sin TC", "0 (toda conversion con TC)")

    # 3. match cartel<->oferta en [30%, 95%] (cobertura real 39.6% con el cruce completo)
    n_requer = FactRequerimiento.objects.values("NRO_SICOP").distinct().count()
    n_ofer = FactOferta.objects.values("NRO_SICOP").distinct().count()
    match = (n_ofer / n_requer * 100) if n_requer else None
    results["match_cartel_oferta"] = _test(corrida_id, "match_cartel_oferta",
                                           match is not None and 30 <= match <= 95,
                                           f"{match:.1f}%" if match else "n/a", "30-95%")

    # 4. toda cedula de fact_orden existe en proveedores.
    #    NOTA: se hace con agregado SQL (NOT EXISTS), NO con .iterator() sobre
    #    fact_orden: el cursor server-side del iterator muere si la conexion se
    #    reconecto tras el gold largo ("cursor _django_curs_ does not exist").
    from django.db import connection as _conn

    n_ord = FactOrden.objects.count()
    faltan = 0
    if n_ord:
        with _conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM ("
                "  SELECT DISTINCT o.\"CEDULA_PROVEEDOR\" FROM fact_orden o"
                "  WHERE o.\"CEDULA_PROVEEDOR\" IS NOT NULL AND o.\"CEDULA_PROVEEDOR\" <> ''"
                "  AND NOT EXISTS (SELECT 1 FROM sicop_proveedores p"
                "                  WHERE p.\"CEDULA_PROVEEDOR\" = o.\"CEDULA_PROVEEDOR\")"
                ") t")
            faltan = cur.fetchone()[0] or 0
    results["cedula_orden_en_proveedores"] = _test(corrida_id, "cedula_orden_en_proveedores",
                                                   faltan == 0, f"{faltan} ausentes / {n_ord}", "0")

    # 5. len(codigo) en {16,24} en >=99.5% (agregado, sin iterator)
    malos = total_cod = 0
    for fact in (FactOferta, FactAdjudicacion, FactContratoLinea, FactRecepcion):
        qs = fact.objects.exclude(CODIGO_CL__isnull=True)
        for r in qs.values("CODIGO_CL").annotate(n=Count("id")):
            total_cod += r["n"]
            if len(r["CODIGO_CL"]) not in (16, 24):
                malos += r["n"]
    pct = (100 - malos / total_cod * 100) if total_cod else 100
    results["len_codigo_16_24"] = _test(corrida_id, "len_codigo_16_24",
                                        pct >= 99.5, f"{pct:.2f}%", ">=99.5%")

    # 6. outliers de orden: los 4 conocidos (>1e12) estan reportados y NO se suman
    n_out = FactOrden.objects.filter(ES_OUTLIER="S").count()
    results["sin_outliers_orden"] = _test(corrida_id, "sin_outliers_orden",
                                          n_out <= 5, f"{n_out} outliers (reportados, no sumados)",
                                          "<=5 (los 4 conocidos del corpus)")

    # 7. adjudicacion dividida sobrevive
    n_adj = FactAdjudicacion.objects.count()
    divididas = 0
    if n_adj:
        divididas = sum(1 for g in FactAdjudicacion.objects.values("NRO_SICOP", "NRO_LINEA")
                        .annotate(c=Count("CEDULA_PROVEEDOR", distinct=True)) if g["c"] > 1)
    results["adjudicacion_dividida"] = _test(corrida_id, "adjudicacion_dividida",
                                             True, f"{divididas} divididas", "existen (test informativo)")

    # 8. orden multilinea sobrevive
    n_multi = FactOrden.objects.filter(N_LINEAS__gt=1).count()
    results["orden_multilinea"] = _test(corrida_id, "orden_multilinea",
                                        True, f"{n_multi} multilinea", "existen (test informativo)")

    # 9. esquema: cualquier columna esperada ausente -> BLOQUEADO (§7). Antes se
    #    detectaba en el manifiesto pero no bloqueaba; ahora es gate.
    aus = _chequeo_esquema()
    if aus is None:
        _test_resultado(corrida_id, "esquema_columnas", NO_EVALUADO,
                        "sin manifiesto ni ctl_esquema (no se pudo comparar)",
                        "0 columnas ausentes")
    else:
        results["esquema_columnas"] = _test(
            corrida_id, "esquema_columnas", not aus,
            ", ".join(f"{k}:{','.join(v[:6])}" for k, v in sorted(aus.items())) or "ninguna",
            "0 columnas ausentes")

    # 10. A2 del harness (skill §7): inventario del zip, salto de magnitud,
    #     cobertura del cruce y no_evaluados. BLOQUEADO detiene; REVISAR y
    #     NO_EVALUADO se registran sin bloquear (pero nunca como PASS).
    from . import a2 as _a2

    ra2 = _a2.evaluar()
    ver = ra2.get("veredicto")
    if ver == "BLOQUEADO":
        results["a2_bloqueado"] = _test(corrida_id, "a2_bloqueado", False,
                                        ra2.get("motivo") or "A2 BLOQUEADO",
                                        "CONFIABLE/REVISAR")
    elif ver in ("CONFIABLE", "REVISAR"):
        results["a2_bloqueado"] = _test(corrida_id, "a2_bloqueado", True, ver,
                                        "CONFIABLE/REVISAR")
    else:
        _test_resultado(corrida_id, "a2_bloqueado", NO_EVALUADO,
                        ra2.get("motivo") or "A2 no corrio", "correr")
    for d in ra2.get("desvios") or []:
        _test_resultado(corrida_id, f"a2_{d.get('chequeo')}",
                        d.get("severidad") or "REVISAR", d.get("detalle"),
                        "REVISAR/BLOQUEADO")
    for ne in ra2.get("no_evaluados") or []:
        _test_resultado(corrida_id, f"a2_no_eval_{ne.get('chequeo')}",
                        NO_EVALUADO, ne.get("motivo"), "correr")

    failed = [k for k, v in results.items() if not v]
    return results, failed


def publicar_gold(corrida_id):
    """Publica gold de forma atomica: corre los gates; si fallan, gold no se publica."""
    results, failed = run_tests(corrida_id)
    if failed:
        cerrar_corrida(corrida_id, "BLOQUEADO", f"tests fallidos: {','.join(failed)}")
        return False, failed
    cerrar_corrida(corrida_id, "PUBLICADO")
    return True, []


def registrar_mes_fuente(aaaamm, hash_zip, tamano, corrida_id):
    CtlMesFuente.objects.update_or_create(
        AAAAMM=aaaamm,
        defaults={"HASH_ZIP": hash_zip, "TAMANO_BYTES": tamano,
                  "PROCESADO_EN": timezone.now(), "CORRIDA_ID": corrida_id})


def registrar_esquema(tabla, columnas, corrida_id=None):
    now = timezone.now()
    CtlEsquema.objects.update_or_create(
        TABLA=tabla,
        defaults={"COLUMNAS_VISTAS": ",".join(columnas), "ULTIMA_VEZ": now,
                  "PRIMERA_VEZ": CtlEsquema.objects.filter(TABLA=tabla).first().PRIMERA_VEZ if CtlEsquema.objects.filter(TABLA=tabla).exists() else now})


def registrar_cuarentena(corrida_id, tabla, archivo, linea, motivo, fila_cruda):
    CtlCuarentena.objects.create(CORRIDA_ID=corrida_id, TABLA=tabla, ARCHIVO=archivo,
                                 LINEA=linea, MOTIVO=motivo, FILA_CRUDA=fila_cruda)
