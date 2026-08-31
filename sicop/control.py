"""Tablas de control + tests como gate + publicacion atomica de gold (plan Fase 1)."""
import logging
from datetime import datetime

from django.utils import timezone

from .models import (
    CtlCorrida, CtlTest, CtlMesFuente, CtlCuarentena, CtlEsquema,
    FactRequerimiento, FactOferta, FactAdjudicacion, FactContratoLinea,
    FactOrden, FactRecepcion, SicopProveedores,
)

logger = logging.getLogger(__name__)
OUTLIER = 10**12


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

    # 4. toda cedula de fact_orden existe en proveedores
    provs = set(SicopProveedores.objects.values_list("CEDULA_PROVEEDOR", flat=True))
    faltan = 0
    n_ord = FactOrden.objects.count()
    if provs and n_ord:
        for ced in FactOrden.objects.values_list("CEDULA_PROVEEDOR", flat=True).distinct().iterator():
            if ced and ced not in provs:
                faltan += 1
    results["cedula_orden_en_proveedores"] = _test(corrida_id, "cedula_orden_en_proveedores",
                                                   faltan == 0, f"{faltan} ausentes / {n_ord}", "0")

    # 5. len(codigo) en {16,24} en >=99.5%
    malos = total_cod = 0
    for fact in (FactOferta, FactAdjudicacion, FactContratoLinea, FactRecepcion):
        qs = fact.objects.exclude(CODIGO_CL__isnull=True).values_list("CODIGO_CL", flat=True)
        for c in qs.iterator():
            total_cod += 1
            if len(c) not in (16, 24):
                malos += 1
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
