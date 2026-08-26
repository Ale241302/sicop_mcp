"""resultado_decision (SCH_RESULTADO_v1): lo unico irreversible del sistema.

- Append-only: una decision no se edita, se cierra (observado_hasta) y se escribe otra.
- Bloque 2.2 (contexto congelado) obligatorio: sin build_id/snapshot_ts/modelo_version/features_hash
  la fila no se acepta (decision_eligible).
- El consolidado diario resuelve PENDIENTE cuando el ZIP del mes lo trae.
"""
import hashlib
import logging
from datetime import datetime

from django.utils import timezone

from .models import ResultadoDecision

logger = logging.getLogger(__name__)

REQUIRED_CONTEXT = ("build_id", "snapshot_ts", "modelo_version", "features_hash")
CANAL = ("INVITACION", "MONITOREO", "TERCERO")
DECISIONES = ("OFERTAR", "OFERTAR_MODIFICADO", "NO_OFERTAR")
MOTIVOS = ("PRECIO_INVIABLE", "SIN_PRODUCTO", "REQUISITO_INADMISIBLE", "PLAZO",
           "CLIENTE_MOROSO", "CAPACIDAD", "OTRO")
ESTADOS = ("PENDIENTE", "ADJUDICADO", "NO_ADJUDICADO", "DESIERTO", "INFRUCTUOSO",
           "ANULADO", "RECURRIDO")


def _h(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p or "").encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def registrar_resultado(nro_sicop, nro_linea, decision, build_id, snapshot_ts,
                        modelo_version, features_hash, features_json=None,
                        codigo_producto_cl=None, cl_origen="FUENTE",
                        institucion_cedula=None, institucion_nombre=None,
                        fecha_invitacion=None, canal_entrada="MONITOREO",
                        fecha_apertura=None, regimen=None,
                        n_oferentes_esperados=None, precio_ancla_pliego=None,
                        precio_recomendado=None, moneda_recomendada="CRC",
                        prob_exito_estimada=None, prob_ic_bajo=None, prob_ic_alto=None,
                        fecha_decision=None, decidido_por="AGENTE:SICOP",
                        motivo_no_ofertar=None, motivo_texto=None,
                        override=False, override_motivo=None,
                        corrida_id=None, **extra):
    """Registra una decision. Bloque de contexto obligatorio; append-only."""
    for f in REQUIRED_CONTEXT:
        if not locals().get(f):
            raise ValueError(f"decision_eligible: falta {f}")
    if canal_entrada not in CANAL:
        raise ValueError(f"canal_entrada invalido: {canal_entrada}")
    if decision not in DECISIONES:
        raise ValueError(f"decision invalida: {decision}")
    if motivo_no_ofertar and motivo_no_ofertar not in MOTIVOS:
        raise ValueError(f"motivo_no_ofertar invalido: {motivo_no_ofertar}")

    now = timezone.now()
    # append-only: cerrar la vigente previa
    ResultadoDecision.objects.filter(
        nro_sicop=nro_sicop, nro_linea=nro_linea, es_vigente=True
    ).update(observado_hasta=now, es_vigente=False)

    obj = ResultadoDecision(
        nro_sicop=nro_sicop, nro_linea=str(nro_linea),
        codigo_producto_cl=codigo_producto_cl, cl_origen=cl_origen,
        institucion_cedula=institucion_cedula, institucion_nombre=institucion_nombre,
        fecha_invitacion=fecha_invitacion, canal_entrada=canal_entrada,
        fecha_apertura=fecha_apertura, regimen=regimen,
        build_id=build_id, snapshot_ts=snapshot_ts, modelo_version=modelo_version,
        features_hash=features_hash, features_json=features_json,
        n_oferentes_esperados=n_oferentes_esperados, precio_ancla_pliego=precio_ancla_pliego,
        precio_recomendado=precio_recomendado, moneda_recomendada=moneda_recomendada,
        prob_exito_estimada=prob_exito_estimada, prob_ic_bajo=prob_ic_bajo,
        prob_ic_alto=prob_ic_alto,
        decision=decision, fecha_decision=fecha_decision or now, decidido_por=decidido_por,
        motivo_no_ofertar=motivo_no_ofertar, motivo_texto=motivo_texto,
        override=override, override_motivo=override_motivo,
        estado_resultado="PENDIENTE", fuente_resultado="SICOP_ZIP",
        observado_desde=now, es_vigente=True,
        hash_fila=_h(nro_sicop, nro_linea, decision, build_id, snapshot_ts,
                     features_hash, override),
        corrida_id=corrida_id,
    )
    obj.save()
    return obj


def consolidar_resultados(corrida_id=None):
    """Resuelve PENDIENTE del consolidado diario (06:00) usando el dato ya cargado.
    Rellena resultado/posicion/precio ganador SOLO donde se puede dirimir del ZIP."""
    from .models import FactAdjudicacion, FactOferta

    pendientes = list(ResultadoDecision.objects.filter(estado_resultado="PENDIENTE", es_vigente=True))
    ganador = {}
    for r in FactAdjudicacion.objects.values("NRO_SICOP", "NRO_LINEA", "CEDULA_PROVEEDOR",
                                              "PU_ADJUDICADO_CRC", "MONTO_ADJUDICADO_CRC").iterator():
        key = (r["NRO_SICOP"], r["NRO_LINEA"])
        ganador.setdefault(key, r)

    ofertantes = {}
    for r in FactOferta.objects.values("NRO_SICOP", "CEDULA_PROVEEDOR").iterator():
        ofertantes.setdefault(r["NRO_SICOP"], set()).add(r["CEDULA_PROVEEDOR"])

    resueltos = 0
    for d in pendientes:
        key = (d.nro_sicop, d.nro_linea)
        g = ganador.get(key)
        if not g:
            continue
        if g["CEDULA_PROVEEDOR"] == d.institucion_cedula:
            continue  # no es nuestro
        # estado del procedimiento
        d.cedula_ganador = g["CEDULA_PROVEEDOR"]
        d.precio_ganador_crc = g["PU_ADJUDICADO_CRC"]
        ofs = ofertantes.get(d.nro_sicop, set())
        d.n_oferentes_real = len(ofs)
        if g["CEDULA_PROVEEDOR"]:
            d.estado_resultado = "ADJUDICADO"
        d.fecha_observacion = timezone.now()
        d.corrida_id = corrida_id or d.corrida_id
        d.save()
        resueltos += 1
    print(f"consolidar_resultados: {resueltos}/{len(pendientes)} resueltos", flush=True)
    return resueltos
