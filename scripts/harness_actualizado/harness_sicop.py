#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
harness_sicop.py — Orquestador del HARNESS_SICOP (DRAFT v0.1).

Deterministic First -> LLM Fallback -> Human Gate.

Agentes:
  A1 Colector   (código)  sicop_loop.py: 15 conjuntos + 6 derivadas + manifiesto
  A2 Control    (código + LLM si desvío) 6 chequeos deterministas -> control.json
  A3 Vigía      (código)  9 reglas -> novedades.json (modo --sembrar)
  A4 Analista   (LLM)     tareas_a4.json -> analisis.json
  A5 Auditor    (LLM)     tarea_a5.json -> auditoria.json (adversarial)
  A6 Redactor   (LLM)     tarea_a6.json -> informe.md
  A7 Ejecutor   (código)  auditoria.json + politica_acciones.json -> ejecutado.json
  H  Gate       (persona) sólo ante lo irreversible

Contratos: JSON en <estado>/ (por defecto salida/estado). Bitácora append-only:
<estado>/bitacora.jsonl.

Uso:
  python3 scripts/harness_sicop.py run
  python3 scripts/harness_sicop.py a1 [--force]
  python3 scripts/harness_sicop.py a2
  python3 scripts/harness_sicop.py a2-clasificar      # tras correr el motor
  python3 scripts/harness_sicop.py sembrar
  python3 scripts/harness_sicop.py a3
  python3 scripts/harness_sicop.py a4-preparar        # -> tareas_a4.json (motor pendiente)
  python3 scripts/harness_sicop.py a4-integrar        # valida analisis_motor.json
  python3 scripts/harness_sicop.py a5-preparar / a5-integrar
  python3 scripts/harness_sicop.py a6-preparar / a6-integrar
  python3 scripts/harness_sicop.py a7
  python3 scripts/harness_sicop.py estado             # estado del harness
  python3 scripts/harness_sicop.py bitacora [n]       # últimas n entradas
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sicop_loop  # noqa: E402  (A1: el colector)

# ---------------------------------------------------------------------------
# Rutas y helpers
# ---------------------------------------------------------------------------

HOY = datetime.now()

DEFAULT_WATCHLIST = {
    "_comentario": "Configuración del agente A3 (Vigía). La edita una persona, nunca un agente. v2: tres correcciones surgidas de la primera corrida real con A5 auditando (2026-08-23): 1) plazo_por_vencer exige PERMITE_RECURSOS=Si y DESIERTO=N; 2) oferta_unica renombrada a oferente_unico_en_cruce; 3) política explícita por veredicto de A5.",
    "version": 2,
    "actualizado": "2026-08-23",
    "proveedores_vigilados": [
        {"cedula": "3101285799", "alias": "CLAI PAYMENTS", "motivo": "cliente del despacho",
         "prioridad": "alta"},
        {"cedula": "9000012669", "alias": "DCN DIVING BV", "motivo": "cliente del despacho",
         "prioridad": "alta"},
    ],
    "instituciones_vigiladas": [
        {"cedula": "4000042139", "alias": "ICE", "motivo": "volumen alto"},
    ],
    "objetos_gasto_vigilados": [],
    "reglas": {
        "cliente_participa": {"activa": True, "prioridad": "alta"},
        "cliente_adjudicado": {"activa": True, "prioridad": "alta"},
        "cliente_perdio": {"activa": True, "prioridad": "alta",
                           "nota": "dispara plazo de recurso — revisar de inmediato"},
        "cartel_objetado_nuevo": {"activa": True, "prioridad": "media"},
        "sancion_nueva": {"activa": True, "prioridad": "alta"},
        "excepcion_concentrada": {"activa": True, "prioridad": "media",
                                  "umbral_lineas": 5, "ventana_dias": 90,
                                  "causales": ["Proveedor único",
                                               "Contratación por emergencia"]},
        "institucion_vigilada": {"activa": True, "prioridad": "media"},
        "plazo_por_vencer": {"activa": True, "prioridad": "alta", "dias_aviso": 5,
                             "nota": "el cómputo real del plazo lo hace el abogado. Sólo "
                                     "dispara si PERMITE_RECURSOS=Si y DESIERTO=N — sin ese "
                                     "filtro la regla marca actos que no admiten impugnación "
                                     "(detectado por A5 el 2026-08-23)",
                             "requiere_permite_recursos": True, "excluir_desierto": True},
        "oferente_unico_en_cruce": {"activa": False, "prioridad": "baja",
                                    "cobertura_minima_pct": 50,
                                    "nota": "antes se llamaba 'oferta_unica'. A5 observó que "
                                            "ese nombre es una calificación con carga "
                                            "jurídica presentada como descripción: la "
                                            "ausencia de otros oferentes en el cruce no "
                                            "prueba ausencia real. El hallazgo debe decir "
                                            "'un solo oferente identificado por el cruce'"},
    },
    "umbrales_control": {"filas_nuevas_factor_max": 3.0,
                         "caida_cobertura_puntos": 5.0,
                         "dias_sin_publicacion_para_avisar": 3},
    "informe": {"diario_solo_si_hay_novedades": True, "semanal_siempre": True,
                "dia_semanal": "lunes", "max_novedades_por_informe": 12},
    "politica_hallazgos": {
        "SOSTENIDO": {"ejecuta_acciones": True, "entra_al_informe": True},
        "DEBIL": {"ejecuta_acciones": False, "entra_al_informe": True,
                  "seccion": "PARA MIRAR",
                  "nota": "no se ejecuta nada, pero no se descarta: el humano lo ve marcado"},
        "REFUTADO": {"ejecuta_acciones": False, "entra_al_informe": False,
                     "nota": "se archiva con el motivo del auditor en bitacora.jsonl"},
    },
}

DEFAULT_POLITICA = {
    "acciones_por_tipo": {
        "cliente_perdio": ["priorizar", "preparar_borrador", "agendar",
                           "notificar_interno", "actualizar_expediente"],
        "plazo_por_vencer": ["priorizar", "preparar_borrador", "agendar",
                             "notificar_interno"],
        "cliente_adjudicado": ["archivar", "actualizar_expediente"],
        "cliente_participa": ["archivar", "notificar_interno"],
        "cartel_objetado_nuevo": ["priorizar", "notificar_interno"],
        "sancion_nueva": ["priorizar", "notificar_interno", "actualizar_expediente"],
        "excepcion_concentrada": ["archivar", "notificar_interno"],
        "institucion_vigilada": ["archivar"],
        "oferente_unico_en_cruce": ["archivar"],
    },
    "irreversibles": ["presentar_recurso", "enviar_a_cliente", "firmar",
                      "publicar", "comunicar_externo"],
}

PRIORIDAD = {
    "cliente_participa": "alta", "cliente_adjudicado": "alta",
    "cliente_perdio": "alta", "cartel_objetado_nuevo": "media",
    "sancion_nueva": "alta", "excepcion_concentrada": "media",
    "institucion_vigilada": "media", "plazo_por_vencer": "alta",
    "oferente_unico_en_cruce": "baja",
}

LIMITES_TEXTO = (
    "Los datos abiertos de SICOP no traen marca ni modelo del bien (sólo "
    "CODIGO_PRODUCTO/CODIGO_PRODUCTO_CL). El cruce oferta-oferente tiene cobertura "
    "parcial (62,6% en 2026, 8 meses); una estadística sobre cobertura baja no es "
    "representativa. Una concentración alta o una excepción puede tener explicaciones "
    "legítimas (mercado con un solo oferente, especialización técnica, convenio marco). "
    "Este harness produce datos y preguntas, no conclusiones; no emite conclusiones "
    "jurídicas ni recomienda acciones legales. Todo hallazgo debe declarar período "
    "cubierto, fecha de corte, archivo de origen y cobertura del cruce cuando aplique."
    " Sobre plazos de recurso: desde el 2026-04-06 rige la circular "
    "MH-DCoP-CIR-0010-2026 de Hacienda (hora límite 23:59, excepto Grupo ICE; "
    "conversión de moneda extranjera a colones en contratos; renombra dos campos de "
    "monto). El harness marca que un plazo corre — el cómputo y la aplicabilidad de "
    "la circular los resuelve el abogado."
)

ESTRUCTURA_INFORME = [
    "LO QUE REQUIERE DECISIÓN HOY",
    "LO NUEVO",
    "PARA MIRAR",
    "NO SE PUDO VERIFICAR",
    "SIN CAMBIOS",
    "ESTADO DEL SISTEMA",
]


def leer_json(path: Path, default=None):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default
    return default


def log(agente: str, msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {agente:<10} {msg}", flush=True)


def escribir_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def hash_archivo(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def hash_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()[:16]


def bitacora(estado: Path, agente: str, evento: str, entrada: str = None,
             salida: str = None, modelo: str = None, effort: str = None,
             tokens: int = None, extra: dict = None) -> None:
    reg = {"ts": datetime.now().isoformat(timespec="seconds"), "agente": agente,
           "evento": evento, "entrada_hash": entrada, "salida_hash": salida,
           "modelo": modelo, "effort": effort, "tokens": tokens}
    if extra:
        reg.update(extra)
    estado.mkdir(parents=True, exist_ok=True)
    with open(estado / "bitacora.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")


def estimar_tokens(*textos) -> int:
    """Estimación de tokens para llamadas a un motor externo (no reporta
    conteo real): ~4 caracteres por token. Marcado como estimado en la bitácora."""
    return sum(len(t) for t in textos) // 4


# ---------------------------------------------------------------------------
# A0 · GUARDAVÍA (código — corre siempre y primero; y otra vez al cierre)
#
# Regla única: UN ARTEFACTO DERIVADO NO PUEDE SOBREVIVIR A SU INSUMO.
# Nace del caso real del 2026-08-23: un informe.md decía CONFIABLE mientras el
# control.json vigente decía REVISAR — el informe era de otra corrida. En disco
# los dos archivos se ven igual de válidos. El sello de `corrida` protege la
# cadena A3→A7 DURANTE la corrida; A0 protege lo ya escrito en disco.
# ---------------------------------------------------------------------------

# artefacto -> de qué depende. Si el insumo es más nuevo, el derivado está vencido.
PROCEDENCIA = {
    "control.json": ["../manifiesto.json"],
    "novedades.json": ["control.json", "watchlist.json"],
    "tareas_a4.json": ["novedades.json"],
    "analisis.json": ["tareas_a4.json"],
    "tarea_a5.json": ["analisis.json"],
    "auditoria.json": ["analisis.json"],
    "informe.md": ["auditoria.json", "control.json"],
    "ejecutado.json": ["auditoria.json"],
    "pendiente_aprobacion.json": ["auditoria.json"],
}


def a0_guardavia(estado: Path, datos: Path, marcar: bool = True) -> dict:
    """Verifica que ningún artefacto sea más viejo que aquello de lo que se deriva.

    marcar=True renombra el vencido a `<nombre>.VENCIDO-<hora>` (o `.HUERFANO-<hora>`
    si lo que falla es un insumo AUSENTE) en vez de borrarlo: un artefacto vencido es
    evidencia de lo que pasó. Tres mecanismos: precedencia por fecha, insumo ausente
    (un derivado no puede sobrevivir a la desaparición de su respaldo), y coherencia
    de corrida (dos `corrida` distintas conviviendo en estado/).

    Refinamiento de flujo (v0.6): `informe.md` sólo exige `auditoria.json` como
    insumo si hubo novedades que auditar — en el flujo sin novedades (incluido el
    informe semanal) la auditoría legítimamente nunca existe y el informe depende de
    `control.json` + `novedades.json`."""
    log("A0", "verificando coherencia del estado…")
    vencidos, huerfanos, ok = [], [], []

    def insumos_de(art: str):
        ins = list(PROCEDENCIA[art])
        if art == "informe.md" and "auditoria.json" in ins:
            nov_p = estado / "novedades.json"
            if nov_p.exists():
                nov = leer_json(nov_p, {}) or {}
                if not (nov.get("novedades") or []) and nov.get("total", 0) == 0:
                    # día tranquilo (o siembra): la auditoría legítimamente nunca
                    # existió; el informe deriva de control+novedades.
                    ins = [i for i in ins if i != "auditoria.json"]
            # conservador (v0.7 de la referencia): si novedades.json NO existe,
            # no hay evidencia de día tranquilo → se exige todo.
        return ins

    for art in PROCEDENCIA:
        ruta = estado / art
        if not ruta.exists():
            continue
        t_art = ruta.stat().st_mtime
        peor, t_peor, ausentes = None, None, []
        insumos = insumos_de(art)
        for ins in insumos:
            r_ins = (datos / ins[3:]) if ins.startswith("../") else (estado / ins)
            if not r_ins.exists():
                ausentes.append(ins)
                continue
            t_ins = r_ins.stat().st_mtime
            if t_ins > t_art and (t_peor is None or t_ins > t_peor):
                peor, t_peor = ins, t_ins
        # insumo ausente: el derivado existe pero su respaldo no — nadie puede
        # verificar de dónde salió. Tan grave como uno más nuevo, y por otra puerta.
        # (v0.6 de la referencia: antes el veredicto salía COHERENTE igual.)
        if ausentes:
            item = {"artefacto": art, "insumos_ausentes": ausentes,
                    "insumos_exigidos": insumos,
                    "artefacto_ts": datetime.fromtimestamp(t_art)
                                   .isoformat(timespec="seconds"),
                    "motivo": "el artefacto existe pero su respaldo no"}
            if marcar:
                sello = datetime.fromtimestamp(t_art).strftime("%Y%m%dT%H%M%S")
                destino = estado / f"{art}.HUERFANO-{sello}"
                try:
                    ruta.replace(destino)
                    item["movido_a"] = destino.name
                except OSError as e:
                    item["error_al_mover"] = str(e)
            huerfanos.append(item)
            continue
        if peor:
            desfase = int(t_peor - t_art)
            item = {"artefacto": art, "insumo_mas_nuevo": peor,
                    "desfase_segundos": desfase,
                    "artefacto_ts": datetime.fromtimestamp(t_art)
                                   .isoformat(timespec="seconds"),
                    "insumo_ts": datetime.fromtimestamp(t_peor)
                                 .isoformat(timespec="seconds")}
            if marcar:
                sello = datetime.fromtimestamp(t_art).strftime("%Y%m%dT%H%M%S")
                destino = estado / f"{art}.VENCIDO-{sello}"
                try:
                    ruta.replace(destino)
                    item["movido_a"] = destino.name
                except OSError as e:
                    item["error_al_mover"] = str(e)
            vencidos.append(item)
        else:
            ok.append(art)

    # coherencia de corrida: todo lo que declare 'corrida' debe declarar la misma
    corridas = {}
    for art in PROCEDENCIA:
        ruta = estado / art
        if art.endswith(".json") and ruta.exists():
            c = (leer_json(ruta, {}) or {}).get("corrida")
            if c:
                corridas.setdefault(c, []).append(art)

    salida = {"ts": datetime.now().isoformat(timespec="seconds"),
              "veredicto": ("COHERENTE" if (not vencidos and not huerfanos
                                            and len(corridas) <= 1)
                            else "DESFASADO"),
              "vencidos": vencidos, "huerfanos": huerfanos, "coherentes": ok,
              "corridas_presentes": corridas,
              "regla": "un artefacto derivado no puede sobrevivir a su insumo"}
    escribir_json(estado / "coherencia.json", salida)
    bitacora(estado, "A0", f"guardavía ({salida['veredicto']})",
             salida=hash_archivo(estado / "coherencia.json"),
             extra={"vencidos": len(vencidos), "huerfanos": len(huerfanos)})
    for v in vencidos:
        log("A0", f"VENCIDO · {v['artefacto']} es {v['desfase_segundos']}s más "
                  f"viejo que {v['insumo_mas_nuevo']}"
                  + (f" → {v['movido_a']}" if v.get("movido_a") else ""))
    for h in huerfanos:
        log("A0", f"HUÉRFANO · {h['artefacto']} existe pero falta "
                  f"{', '.join(h['insumos_ausentes'])}"
                  + (f" → {h['movido_a']}" if h.get("movido_a") else ""))
    if len(corridas) > 1:
        log("A0", f"DESFASADO · conviven {len(corridas)} corridas distintas")
    if salida["veredicto"] == "COHERENTE":
        log("A0", f"COHERENTE · {len(ok)} artefactos al día")
    return salida


def filas_conjunto(out: Path, year: int, conjunto: str):
    path = out / f"{conjunto}_{year}.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def filas_derivada(out: Path, nombre: str):
    """Las tablas derivadas no llevan sufijo de año (competencia_por_linea.csv, …)."""
    path = out / f"{nombre}.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fecha_iso(s: str):
    s = (s or "").strip()
    if len(s) >= 10:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# A1 · COLECTOR (código — sicop_loop.py)
# ---------------------------------------------------------------------------

def a1(out: Path, year: int, force: bool, estado: Path, pesados: bool = False) -> int:
    bitacora(estado, "A1", "inicio")
    argv = ["--year", str(year), "--out", str(out)]
    if force:
        argv.append("--force")
    if pesados:
        argv.append("--pesados")
    rc = sicop_loop.main(argv)
    bitacora(estado, "A1", "fin",
             salida=hash_archivo(out / "manifiesto.json"))
    return rc


# ---------------------------------------------------------------------------
# A2 · CONTROL (código + LLM si hay desvío)
# ---------------------------------------------------------------------------

def metricas_actuales(out: Path, year: int) -> dict:
    man = leer_json(out / "manifiesto.json", {})
    meses = man.get("meses", {})
    por_conjunto = {}
    for nombre in sicop_loop.CONJUNTOS:
        path = out / f"{nombre}_{year}.csv"
        if path.exists():
            with open(path, encoding="utf-8-sig", newline="") as f:
                por_conjunto[nombre] = sum(1 for _ in f) - 1
        else:
            por_conjunto[nombre] = 0
    col_aus = {}
    dups = defaultdict(int)
    montos_nn = montos_neg = 0
    for mo, m in meses.items():
        if m.get("estado") != "OK":
            continue
        for cname, cs in m.get("conjuntos", {}).items():
            if cs.get("columnas_ausentes"):
                col_aus.setdefault(cname, []).extend(cs["columnas_ausentes"])
            dups[cname] += cs.get("duplicados", 0)
            montos_nn += cs.get("montos_no_numericos", 0)
            montos_neg += cs.get("montos_negativos", 0)
    cruce = man.get("cruce", {})
    return {
        "fecha": man.get("fecha_ultima_corrida", ""),
        "por_conjunto": por_conjunto,
        "columnas_ausentes": col_aus,
        "duplicados": dict(dups),
        "montos_no_numericos": montos_nn,
        "montos_negativos": montos_neg,
        "sha256_por_mes": {mo: m.get("sha256") for mo, m in meses.items()
                           if m.get("estado") == "OK"},
        "cruce": {"cobertura": cruce.get("cobertura"),
                  "filas_competencia": cruce.get("filas_competencia")},
        "inventario": leer_json(out / "inventario_zip.json", {}),
    }


def chequeo_salto_magnitud(out: Path, year: int):
    """Cada precio contra la mediana de su propio CODIGO_PRODUCTO_CL (agrupar por
    producto es obligatorio: un tornillo y una grúa difieren legítimamente por
    órdenes de magnitud). Umbral 100×: el error de digitación puede ser de dos
    ceros (CICAP-UCR 2019: ₡49,5 millones como ₡49,5 mil millones).

    Precios de ₡1 (o menos) se excluyen ANTES de calcular la mediana y de marcar:
    la skill §8 los declara simbólicos o 'por definir'. Incluirlos ensuciaba el
    chequeo con cientos de falsos positivos (precio=1 vs mediana=720.750)."""
    path = out / "competencia_por_linea.csv"
    if not path.exists():
        return None, "falta competencia_por_linea.csv"
    grupos = defaultdict(list)
    filas = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            filas.append(r)
            cod = (r.get("CODIGO_PRODUCTO_CL") or "").strip()
            p = sicop_loop.parse_number(r.get("PRECIO_UNITARIO_CRC") or "")
            if p is not None and p > 1 and cod:
                grupos[cod].append(p)
    if not grupos:
        return None, "sin precios con CODIGO_PRODUCTO_CL para agrupar"
    medianas = {c: sorted(v)[len(v) // 2] for c, v in grupos.items()}
    saltos = 0
    ej = []
    for r in filas:
        cod = (r.get("CODIGO_PRODUCTO_CL") or "").strip()
        p = sicop_loop.parse_number(r.get("PRECIO_UNITARIO_CRC") or "")
        med = medianas.get(cod)
        if p is None or p <= 1 or med is None or med <= 0:
            continue
        if p > 100 * med or p < med / 100:
            saltos += 1
            if len(ej) < 3:
                ej.append(f"{r.get('NRO_SICOP')} L{r.get('NRO_LINEA')} {cod} "
                          f"precio={p:.2f} mediana={med:.2f}")
    if saltos:
        return {"chequeo": "salto_magnitud", "severidad": "REVISAR",
                "detalle": f"{saltos} precios fuera de 100× la mediana de su "
                           f"CODIGO_PRODUCTO_CL (ej: {'; '.join(ej)})"}, None
    return None, None


def chequeo_cedula_institucional(out: Path, year: int):
    """Prefijo 4000 en CEDULA_PROVEEDOR — MARCA, no interpreta (una institución
    puede contratar con otra). Caso testigo: 4000042146 = Consejo Nacional de
    Producción, la misma entidad que CICAP-UCR nombra con procedimientos
    duplicados."""
    ceds = defaultdict(int)
    lineas = 0
    for conj in ("adjudicaciones", "contratos", "ofertas"):
        path = out / f"{conj}_{year}.csv"
        if not path.exists():
            continue
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                c = (r.get("CEDULA_PROVEEDOR") or "").strip()
                if c.startswith("4000"):
                    ceds[c] += 1
                    lineas += 1
    if ceds:
        det = "; ".join(f"{c} ({n})" for c, n in
                        sorted(ceds.items(), key=lambda kv: -kv[1])[:6])
        return {"chequeo": "cedula_institucional_como_proveedor",
                "severidad": "INFO",
                "detalle": f"{lineas} líneas con cédula institucional (prefijo 4000) "
                           f"como proveedor — marca, no interpreta: {det}"}, None
    return None, None


def chequeos(actual: dict, base: dict, out: Path, year: int) -> tuple:
    desvios = []
    no_eval = []
    # 1 · esquema (cualquier columna ausente -> BLOQUEADO)
    for cname, aus in actual["columnas_ausentes"].items():
        if aus:
            desvios.append({"chequeo": "esquema", "severidad": "BLOQUEADO",
                            "detalle": f"{cname}: columnas ausentes "
                                       f"{', '.join(aus[:5])}"})
    # 6 · duplicados por clave natural (cualquiera -> REVISAR)
    tot_dups = sum(actual["duplicados"].values())
    if tot_dups > 0:
        top = ", ".join(f"{k}={v}" for k, v in
                        sorted(actual["duplicados"].items(),
                               key=lambda kv: -kv[1])[:4])
        desvios.append({"chequeo": "duplicados", "severidad": "REVISAR",
                        "detalle": f"{tot_dups} filas duplicadas por clave natural "
                                   f"(sets: {top})"})
    # 4 · montos negativos o no numéricos (cualquiera -> REVISAR)
    if actual["montos_no_numericos"] > 0:
        desvios.append({"chequeo": "montos", "severidad": "REVISAR",
                        "detalle": f"{actual['montos_no_numericos']} montos no "
                                   f"numéricos"})
    if actual["montos_negativos"] > 0:
        desvios.append({"chequeo": "montos", "severidad": "REVISAR",
                        "detalle": f"{actual['montos_negativos']} montos negativos"})
    # 7 · regresión de inventario (aparece/desaparece un archivo -> BLOQUEADO)
    inv = actual.get("inventario", {})
    inv_base = (base or {}).get("inventario", {})
    if inv:
        for mo in sorted(inv):
            b = inv_base.get(mo)
            if b and b.get("archivos") != inv[mo].get("archivos"):
                desvios.append({"chequeo": "inventario_zip",
                                "severidad": "BLOQUEADO",
                                "detalle": f"{mo}: cambió el inventario del zip "
                                           f"({b.get('n')} → {inv[mo].get('n')} "
                                           "archivos) — apareció o desapareció "
                                           "un archivo"})
    else:
        no_eval.append({"chequeo": "inventario_zip",
                        "motivo": "falta inventario_zip.json (A1 no procesó meses)"})
    # 8 · salto de magnitud (precio vs mediana de su propio producto, 100×)
    try:
        d, motivo = chequeo_salto_magnitud(out, year)
        if d:
            desvios.append(d)
        elif motivo:
            no_eval.append({"chequeo": "salto_magnitud", "motivo": motivo})
    except Exception as e:  # noqa: BLE001
        no_eval.append({"chequeo": "salto_magnitud",
                        "motivo": f"no pudo correr: {type(e).__name__}: {e}"})
    # 9 · cédula institucional como proveedor (marca, INFO)
    try:
        d, motivo = chequeo_cedula_institucional(out, year)
        if d:
            desvios.append(d)
    except Exception as e:  # noqa: BLE001
        no_eval.append({"chequeo": "cedula_institucional_como_proveedor",
                        "motivo": f"no pudo correr: {type(e).__name__}: {e}"})
    if base:
        # 5 · hash de un mes ya registrado cambió -> REVISAR
        for mo, h in actual["sha256_por_mes"].items():
            bh = base.get("sha256_por_mes", {}).get(mo)
            if bh and bh != h:
                desvios.append({"chequeo": "hash", "severidad": "REVISAR",
                                "detalle": f"{mo}: la fuente reescribió el zip "
                                           f"({bh} -> {h})"})
        # 2 · filas nuevas del día
        delta = {c: actual["por_conjunto"].get(c, 0) -
                    base.get("por_conjunto", {}).get(c, 0)
                 for c in actual["por_conjunto"]}
        tot_delta = sum(delta.values())
        if tot_delta == 0:
            desvios.append({"chequeo": "filas_nuevas", "severidad": "REVISAR",
                            "detalle": "0 filas nuevas en esta corrida"})
        elif tot_delta < 0:
            desvios.append({"chequeo": "filas_nuevas", "severidad": "REVISAR",
                            "detalle": f"pérdida de {abs(tot_delta)} filas vs línea base"})
        # 3 · cobertura del cruce cae más de 5 puntos -> REVISAR
        cb = base.get("cruce", {}).get("cobertura")
        ca = actual["cruce"].get("cobertura")
        if cb and ca is not None and (cb - ca) > 0.05:
            desvios.append({"chequeo": "cobertura_cruce", "severidad": "REVISAR",
                            "detalle": f"cobertura {ca * 100:.1f}% vs base "
                                       f"{cb * 100:.1f}%"})
    else:
        desvios.append({"chequeo": "linea_base", "severidad": "INFO",
                        "detalle": "primera corrida: se crea línea base"})
        for c in ("hash", "filas_nuevas", "cobertura_cruce"):
            no_eval.append({"chequeo": c,
                            "motivo": "sin línea base en la primera corrida"})
    if any(d["severidad"] == "BLOQUEADO" for d in desvios):
        veredicto = "BLOQUEADO"
    elif any(d["severidad"] == "REVISAR" for d in desvios):
        veredicto = "REVISAR"
    else:
        veredicto = "CONFIABLE"
    return desvios, veredicto, no_eval


def a2(out: Path, year: int, estado: Path) -> dict:
    bitacora(estado, "A2", "inicio")
    actual = metricas_actuales(out, year)
    base = leer_json(estado / "linea_base.json", None)
    desvios, veredicto, no_eval = chequeos(actual, base, out, year)
    control = {"fecha": datetime.now().isoformat(timespec="seconds"),
               "veredicto": veredicto, "desvios": desvios,
               "no_evaluados": no_eval,
               "resumen": {k: actual[k] for k in ("por_conjunto", "cruce",
                                                  "montos_no_numericos",
                                                  "montos_negativos")},
               "motor_a2": None}
    escribir_json(estado / "control.json", control)
    if veredicto == "REVISAR":
        # payload cerrado para el motor (LLM económico)
        escribir_json(estado / "tareas_a2.json", {
            "pregunta": "Dados estos desvíos de la corrida de hoy y el histórico, "
                        "¿es variación normal (continuar) o hay que parar?",
            "desvios": desvios,
            "historico": {"por_conjunto": (base or {}).get("por_conjunto", {}),
                          "cruce": (base or {}).get("cruce", {})},
            "formato_salida": {"continuar": "bool", "motivo": "str",
                               "confianza": "0-1"},
        })
        bitacora(estado, "A2", "REVISAR — motor pendiente",
                 entrada=hash_obj(desvios),
                 salida=hash_archivo(estado / "tareas_a2.json"))
    elif veredicto == "BLOQUEADO":
        bitacora(estado, "A2", "BLOQUEADO — se detiene la cadena",
                 entrada=hash_obj(desvios))
    # al cierre: actualiza la línea base
    escribir_json(estado / "linea_base.json", actual)
    bitacora(estado, "A2", "fin", entrada=hash_obj(desvios),
             salida=hash_archivo(estado / "control.json"))
    print(f"A2: {veredicto} · {len(desvios)} desvíos · "
          f"{len(no_eval)} no evaluados")
    for d in desvios:
        print(f"   [{d['severidad']}] {d['chequeo']}: {d['detalle']}")
    for d in no_eval:
        print(f"   [NO EVALUADO] {d['chequeo']}: {d['motivo']}")
    return control


def a2_clasificar(estado: Path) -> None:
    """Integra la clasificación del motor (a2_clasificacion.json)."""
    cl = leer_json(estado / "a2_clasificacion.json", None)
    control = leer_json(estado / "control.json", {})
    if cl is None:
        print("No hay a2_clasificacion.json — correr el motor primero.")
        return
    control["motor_a2"] = cl
    if cl.get("continuar"):
        control["veredicto"] = "CONFIABLE"
        control["nota"] = (f"liberado por clasificación ({cl.get('confianza')}); "
                           f"motivo: {cl.get('motivo')}")
        print(f"A2: liberado por el motor — continuar ({cl.get('confianza')})")
    else:
        control["veredicto"] = "BLOQUEADO_HUMANO"
        control["nota"] = (f"el motor pidió parar ({cl.get('confianza')}); "
                           f"motivo: {cl.get('motivo')}")
        print("A2: el motor pidió parar — la cadena se detiene (gate humano).")
    escribir_json(estado / "control.json", control)
    bitacora(estado, "A2", "clasificación del motor integrada",
             entrada=hash_archivo(estado / "a2_clasificacion.json"),
             salida=hash_archivo(estado / "control.json"),
             modelo="deepseek-v4-flash", effort="medio")


# ---------------------------------------------------------------------------
# A3 · VIGÍA (código — 9 reglas)
# ---------------------------------------------------------------------------

def regla_cliente_participa(out, year, provs):
    """Proveedor vigilado aparece en ofertas."""
    res = {}
    for r in filas_conjunto(out, year, "ofertas"):
        c = (r.get("CEDULA_PROVEEDOR") or "").strip()
        if c in provs:
            k = (c, r["NRO_SICOP"], r["NRO_OFERTA"])
            res[k] = {"tabla": "ofertas_2026.csv",
                      "filas": [{x: r.get(x, "") for x in
                                 ("NRO_SICOP", "NRO_OFERTA", "CEDULA_PROVEEDOR",
                                  "FECHA_PRESENTA_OFERTA", "TIPO_OFERTA")}]}
    return res


def regla_cliente_adjudicado(out, year, provs):
    res = {}
    for r in filas_conjunto(out, year, "adjudicaciones"):
        c = (r.get("CEDULA_PROVEEDOR") or "").strip()
        if c in provs:
            k = (c, r["NRO_SICOP"], r["LINEA"])
            res[k] = {"tabla": "adjudicaciones_2026.csv",
                      "filas": [{x: r.get(x, "") for x in
                                 ("NRO_SICOP", "LINEA", "CEDULA_PROVEEDOR",
                                  "NOMBRE_PROVEEDOR", "MONTO_ADJU_LINEA_CRC",
                                  "FECHA_ADJUD_FIRME", "MES_PUBLICACION")}]}
    return res


def regla_cliente_perdio(out, year, provs):
    """Ofertó el vigilado y otro ganó esa línea (corre plazo de recurso)."""
    comp = filas_derivada(out, "competencia_por_linea")
    ganadas = {(r["NRO_SICOP"], r["NRO_LINEA"]) for r in comp
               if r.get("ES_ADJUDICATARIO") == "S"}
    res = {}
    for r in comp:
        c = (r.get("CEDULA_PROVEEDOR") or "").strip()
        if c in provs and r.get("ES_ADJUDICATARIO") == "N" \
                and (r["NRO_SICOP"], r["NRO_LINEA"]) in ganadas:
            k = (c, r["NRO_SICOP"], r["NRO_LINEA"])
            res[k] = {"tabla": "competencia_por_linea.csv",
                      "filas": [{x: r.get(x, "") for x in
                                 ("NRO_SICOP", "NRO_OFERTA", "NRO_LINEA",
                                  "CEDULA_PROVEEDOR", "PRECIO_UNITARIO_OFERTADO",
                                  "PRECIO_UNITARIO_CRC", "ES_ADJUDICATARIO",
                                  "MES_PUBLICACION")}]}
    return res


def regla_cartel_objetado(out, year):
    res = {}
    for r in filas_derivada(out, "carteles_objetados"):
        k = (r["NRO_SICOP"],)
        res[k] = {"tabla": "carteles_objetados.csv",
                  "filas": [{x: r.get(x, "") for x in
                             ("NRO_SICOP", "NOMBRE_INSTITUCION", "MONTO_EST",
                              "SE_ADJUDICO", "MES_PUBLICACION")}]}
    return res


def regla_sancion_nueva(out, year):
    res = {}
    for r in filas_derivada(out, "sanciones_proveedores"):
        k = (r["NRO_SICOP"],)
        res[k] = {"tabla": "sanciones_proveedores.csv",
                  "filas": [{x: r.get(x, "") for x in
                             ("NRO_SICOP", "CEDULAS_PROVEEDOR",
                              "NOMBRES_PROVEEDOR", "NOMBRE_INSTITUCION",
                              "FECHA_NOTIFICACION")}]}
    return res


def regla_excepcion_concentrada(out, year, min_lineas, causales=None):
    """Proveedor que supera el umbral de líneas por la misma causal. Si la
    watchlist lista causales, sólo se vigilan esas (coincidencia por substring)."""
    def coincide(causal, lista):
        c = causal.lower()
        return any(x.lower() in c for x in lista)
    res = {}
    for r in filas_derivada(out, "excepciones_por_adjudicatario"):
        causal = r.get("CAUSAL_EXCEPCION") or ""
        if causales and not coincide(causal, causales):
            continue
        try:
            n = int(r.get("LINEAS_ADJUDICADAS") or 0)
        except ValueError:
            n = 0
        if n >= min_lineas:
            k = (r["CEDULA_PROVEEDOR"], r["CAUSAL_EXCEPCION"])
            res[k] = {"tabla": "excepciones_por_adjudicatario.csv",
                      "filas": [{x: r.get(x, "") for x in
                                 ("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR",
                                  "CAUSAL_EXCEPCION", "PROCEDIMIENTOS",
                                  "LINEAS_ADJUDICADAS", "MONTO_CRC")}]}
    return res


def regla_institucion_vigilada(out, year, insts):
    res = {}
    if not insts:
        return res
    for r in filas_conjunto(out, year, "adjudicaciones"):
        ci = (r.get("CEDULA") or "").strip()
        if ci in insts:
            k = (ci, r["NRO_SICOP"])
            res[k] = {"tabla": "adjudicaciones_2026.csv",
                      "filas": [{x: r.get(x, "") for x in
                                 ("NRO_SICOP", "CEDULA", "INSTITUCION",
                                  "CEDULA_PROVEEDOR", "MONTO_ADJU_LINEA_CRC")}]}
    return res


def regla_plazo_por_vencer(out, year, dias, requiere_permite_recursos=True,
                           excluir_desierto=True):
    """Adjudicación en firme reciente. Corrección v2 (detectada por A5 el
    2026-08-23): sin el filtro PERMITE_RECURSOS=Si y DESIERTO=N la regla marca
    actos que no admiten impugnación. El harness marca que el plazo corre; el
    cómputo procesal lo hace el abogado."""
    res = {}
    corte = HOY - timedelta(days=int(dias))
    for r in filas_conjunto(out, year, "adjudicaciones_firme"):
        fa = fecha_iso(r.get("FECHA_ADJ_FIRME"))
        if fa is None or fa < corte:
            continue
        permite = (r.get("PERMITE_RECURSOS") or "").strip()
        if requiere_permite_recursos and permite.upper() != "SI":
            continue
        # la fuente usa DESIERTO = Y/N (verificado en los 8 meses: 43.131 N, 1 Y)
        if excluir_desierto and (r.get("DESIERTO") or "").strip().upper() == "Y":
            continue
        k = (r["NRO_SICOP"], r["NRO_ACTO"])
        res[k] = {"tabla": "adjudicaciones_firme_2026.csv",
                  "filas": [{x: r.get(x, "") for x in
                             ("NRO_SICOP", "NRO_ACTO", "FECHA_ADJ_FIRME",
                              "PERMITE_RECURSOS", "DESIERTO")}]}
    return res


def regla_oferente_unico_en_cruce(out, year, cobertura_min_pct, cobertura_actual):
    """Un solo oferente identificado por el cruce (antes 'oferta_unica'). El
    hallazgo describe el dato del cruce; con cobertura parcial no puede
    afirmarse 'oferta única' real. La regla sólo dispara si la cobertura del
    cruce acumulado alcanza el mínimo configurado."""
    if cobertura_actual is None or cobertura_actual * 100 < cobertura_min_pct:
        return {}
    comp = filas_derivada(out, "competencia_por_linea")
    por_linea = defaultdict(list)
    for r in comp:
        por_linea[(r["NRO_SICOP"], r["NRO_LINEA"])].append(r)
    res = {}
    for (sicop, linea), rows in por_linea.items():
        oferentes = {r["CEDULA_PROVEEDOR"] for r in rows}
        if len(oferentes) == 1 and any(r.get("ES_ADJUDICATARIO") == "S"
                                       for r in rows):
            k = (sicop, linea)
            res[k] = {"tabla": "competencia_por_linea.csv",
                      "filas": [{x: rows[0].get(x, "") for x in
                                 ("NRO_SICOP", "NRO_LINEA", "CEDULA_PROVEEDOR",
                                  "PRECIO_UNITARIO_OFERTADO", "PRECIO_UNITARIO_CRC",
                                  "ES_ADJUDICATARIO", "MES_PUBLICACION")}]}
    return res


def a3(out: Path, year: int, estado: Path, sembrar: bool = False) -> dict:
    watch = leer_json(estado / "watchlist.json", DEFAULT_WATCHLIST)
    if watch is None:
        watch = DEFAULT_WATCHLIST
    visto = leer_json(estado / "visto.json", {}) or {}
    provs = {p.get("cedula", "") for p in watch.get("proveedores_vigilados", [])
             if p.get("cedula")}
    insts = {p.get("cedula", "") for p in watch.get("instituciones_vigiladas", [])
             if p.get("cedula")}
    cfg_reglas = watch.get("reglas", {})
    cobertura = leer_json(out / "manifiesto.json", {}).get("cruce", {}).get(
        "cobertura")

    def parametros(regla, **defectos):
        cfg = cfg_reglas.get(regla, {})
        return {k: cfg.get(k, v) for k, v in defectos.items()}

    def fabrica(regla):
        """Devuelve la función de la regla con sus parámetros de la watchlist."""
        if regla == "cliente_participa":
            return lambda: regla_cliente_participa(out, year, provs)
        if regla == "cliente_adjudicado":
            return lambda: regla_cliente_adjudicado(out, year, provs)
        if regla == "cliente_perdio":
            return lambda: regla_cliente_perdio(out, year, provs)
        if regla == "cartel_objetado_nuevo":
            return lambda: regla_cartel_objetado(out, year)
        if regla == "sancion_nueva":
            return lambda: regla_sancion_nueva(out, year)
        if regla == "excepcion_concentrada":
            p = parametros(regla, umbral_lineas=5, causales=None)
            return lambda: regla_excepcion_concentrada(
                out, year, int(p["umbral_lineas"]), p["causales"])
        if regla == "institucion_vigilada":
            return lambda: regla_institucion_vigilada(out, year, insts)
        if regla == "plazo_por_vencer":
            p = parametros(regla, dias_aviso=5, requiere_permite_recursos=True,
                           excluir_desierto=True)
            return lambda: regla_plazo_por_vencer(
                out, year, int(p["dias_aviso"]), bool(p["requiere_permite_recursos"]),
                bool(p["excluir_desierto"]))
        if regla == "oferente_unico_en_cruce":
            p = parametros(regla, cobertura_minima_pct=50)
            return lambda: regla_oferente_unico_en_cruce(
                out, year, float(p["cobertura_minima_pct"]), cobertura)
        return None

    novedades = []
    total_visto = 0
    for regla in ("cliente_participa", "cliente_adjudicado", "cliente_perdio",
                  "cartel_objetado_nuevo", "sancion_nueva",
                  "excepcion_concentrada", "institucion_vigilada",
                  "plazo_por_vencer", "oferente_unico_en_cruce"):
        cfg = cfg_reglas.get(regla, {})
        if cfg.get("activa") is False:
            print(f"   {regla}: inactiva en la watchlist — se omite")
            continue
        fn = fabrica(regla)
        if fn is None:
            continue
        actual = fn()
        claves = set(actual)
        # JSON no distingue tuplas de listas: se reconvierten a tuplas
        prev = {tuple(k) for k in visto.get(regla, [])}
        delta = claves - prev
        total_visto += len(claves)
        prioridad = cfg.get("prioridad", PRIORIDAD.get(regla, "media"))
        if sembrar:
            pass  # se marca todo como visto, sin notificar
        else:
            for k in sorted(delta):
                nid = f"{regla}:{'|'.join(k)}"
                novedades.append({"id": nid, "regla": regla,
                                  "prioridad": prioridad,
                                  "clave": list(k),
                                  "evidencia": actual[k],
                                  "cobertura_cruce": cobertura})
        visto[regla] = sorted(claves)
        print(f"   {regla}: {len(claves)} en la fuente · "
              f"{len(delta)} nuevas")
    escribir_json(estado / "visto.json", visto)
    res = {"fecha": datetime.now().isoformat(timespec="seconds"),
           "corrida": f"{HOY:%Y%m%d-%H%M%S}",
           "sembrar": sembrar, "total": len(novedades),
           "cobertura_cruce": cobertura, "novedades": novedades}
    escribir_json(estado / "novedades.json", res)
    if sembrar:
        bitacora(estado, "A3", f"siembra completada ({total_visto} marcas)")
        print(f"A3 (siembra): {total_visto} marcas en visto.json — nada notificado")
    elif not novedades:
        bitacora(estado, "A3", "sin novedades — cadena termina (cero tokens)")
        print("A3: sin novedades — la cadena termina acá (cero tokens).")
    else:
        bitacora(estado, "A3", f"{len(novedades)} novedades",
                 salida=hash_archivo(estado / "novedades.json"))
        print(f"A3: {len(novedades)} novedades → A4")
    return res


# ---------------------------------------------------------------------------
# A4 · ANALISTA (payload cerrado; el motor es externo)
# ---------------------------------------------------------------------------

def a4_preparar(out: Path, year: int, estado: Path) -> None:
    nov = leer_json(estado / "novedades.json", {"novedades": []})
    man = leer_json(out / "manifiesto.json", {})
    corrida = nov.get("corrida")
    if not corrida:
        # paridad v0.7 de la referencia: sin sello de corrida no se preparan tareas.
        # Un payload sin corrida propagaría artefactos sin trazabilidad aguas abajo.
        log("A4", "ABORTADO — novedades.json no tiene 'corrida'. "
                  "Re-correr A3 antes de preparar tareas.")
        bitacora(estado, "A4", "ABORTADO — novedades sin corrida")
        return
    tareas = []
    for nv in nov.get("novedades", []):
        tareas.append({
            "novedad_id": nv["id"], "regla": nv["regla"],
            "prioridad": nv["prioridad"], "clave": nv["clave"],
            "fecha_corte": HOY.strftime("%Y-%m-%d"),
            "periodo": "enero-diciembre 2026 (8 meses con datos)",
            "cobertura_cruce": nv.get("cobertura_cruce"),
            "evidencia": nv.get("evidencia", {}),
            "limites": LIMITES_TEXTO,
            "instrucciones": ("Describe qué ocurrió (1-2 frases, descriptivo, sin "
                              "calificar), con la evidencia recortada. Cada afirmación "
                              "debe tener una fila concreta que la respalde. Si falta "
                              "contexto, decláralo en falta_contexto; no inventes."),
            "formato_salida": {"que_ocurrio": "str",
                               "evidencia": [{"tabla": "str", "fila_clave": "str",
                                              "campo": "str", "valor": "str"}],
                               "cobertura_declarada": "str",
                               "puede_afirmarse": ["str"],
                               "no_puede_afirmarse": ["str"],
                               "falta_contexto": ["str"]},
        })
    escribir_json(estado / "tareas_a4.json",
                  {"total": len(tareas), "corrida": corrida, "tareas": tareas})
    bitacora(estado, "A4", f"payload preparado ({len(tareas)} tareas)",
             salida=hash_archivo(estado / "tareas_a4.json"))
    print(f"A4: {len(tareas)} tareas en tareas_a4.json — motor pendiente")


def a4_integrar(estado: Path) -> None:
    motor = leer_json(estado / "analisis_motor.json", {"hallazgos": []})
    tareas = leer_json(estado / "tareas_a4.json", {})
    validos = []
    descartados = 0
    for h in motor.get("hallazgos", []):
        ev = h.get("evidencia", [])
        if not ev:
            descartados += 1
            bitacora(estado, "A4", f"hallazgo sin evidencia descartado: "
                                   f"{h.get('novedad_id')}")
            continue
        validos.append(h)
    res = {"fecha": datetime.now().isoformat(timespec="seconds"),
           "corrida": tareas.get("corrida"),
           "total": len(validos), "descartados_sin_evidencia": descartados,
           "hallazgos": validos}
    escribir_json(estado / "analisis.json", res)
    tok = estimar_tokens(
        (estado / "tareas_a4.json").read_text(encoding="utf-8"),
        (estado / "analisis_motor.json").read_text(encoding="utf-8"))
    bitacora(estado, "A4", f"integración ({len(validos)} válidos, "
                           f"{descartados} descartados)",
             entrada=hash_archivo(estado / "analisis_motor.json"),
             salida=hash_archivo(estado / "analisis.json"),
             modelo="deepseek-v4-flash", effort="medio-alto", tokens=tok,
             extra={"tokens_origen": "estimado (motor externo)",
                    "tokens_estimado": True})
    print(f"A4: {len(validos)} hallazgos válidos · {descartados} descartados "
          f"por falta de evidencia · tokens≈{tok}")


# ---------------------------------------------------------------------------
# A5 · AUDITOR (payload adversarial; el motor es externo)
# ---------------------------------------------------------------------------

def a5_preparar(estado: Path) -> None:
    analisis = leer_json(estado / "analisis.json", {"hallazgos": []})
    tareas = []
    for h in analisis.get("hallazgos", []):
        tareas.append({
            "hallazgo_id": h.get("novedad_id"),
            "afirmaciones": [h.get("que_ocurrio", "")] +
                            h.get("puede_afirmarse", []),
            "evidencia": h.get("evidencia", []),
            "preguntas_fijas": [
                "¿Cada afirmación tiene una fila concreta que la respalde?",
                "¿Hay alguna conclusión jurídica disfrazada de descripción?",
                "¿Se declaró la cobertura donde correspondía?",
                "¿La causal de excepción se presenta como concentración o como "
                "irregularidad?",
                "¿Existe una explicación legítima que el hallazgo no consideró?",
                "¿El período y la fecha de corte están declarados?",
            ],
            "limites": LIMITES_TEXTO,
            "mandato": ("Tu trabajo es intentar tumbar el hallazgo. Ante la duda, "
                        "DEBIL. Un hallazgo REFUTADO no llega al informe; uno DEBIL "
                        "llega marcado como tal."),
            "formato_salida": {"veredicto": "SOSTENIDO|DEBIL|REFUTADO",
                               "motivo": "str"},
        })
    escribir_json(estado / "tarea_a5.json", {"total": len(tareas),
                                             "corrida": analisis.get("corrida"),
                                             "tareas": tareas})
    bitacora(estado, "A5", f"payload adversarial preparado ({len(tareas)})",
             salida=hash_archivo(estado / "tarea_a5.json"))
    print(f"A5: {len(tareas)} tareas en tarea_a5.json — motor pendiente")


def a5_integrar(estado: Path) -> None:
    motor = leer_json(estado / "auditoria_motor.json", {"resultados": []})
    tarea = leer_json(estado / "tarea_a5.json", {})
    validos = []
    for r in motor.get("resultados", []):
        v = r.get("veredicto")
        if v not in ("SOSTENIDO", "DEBIL", "REFUTADO"):
            continue
        validos.append(r)
    res = {"fecha": datetime.now().isoformat(timespec="seconds"),
           "corrida": tarea.get("corrida"),
           "total": len(validos), "resultados": validos}
    escribir_json(estado / "auditoria.json", res)
    tok = estimar_tokens(
        (estado / "tarea_a5.json").read_text(encoding="utf-8"),
        (estado / "auditoria_motor.json").read_text(encoding="utf-8"))
    bitacora(estado, "A5", f"integración ({len(validos)} veredictos)",
             entrada=hash_archivo(estado / "auditoria_motor.json"),
             salida=hash_archivo(estado / "auditoria.json"),
             modelo="deepseek-v4-flash", effort="alto", tokens=tok,
             extra={"tokens_origen": "estimado (motor externo)",
                    "tokens_estimado": True})
    for r in validos:
        print(f"   {r.get('hallazgo_id')}: {r.get('veredicto')} — "
              f"{r.get('motivo', '')[:90]}")
    print(f"A5: tokens≈{tok}")


# ---------------------------------------------------------------------------
# A6 · REDACTOR (payload; el motor es externo)
# ---------------------------------------------------------------------------

def a6_preparar(out: Path, year: int, estado: Path) -> None:
    aud = leer_json(estado / "auditoria.json", {"resultados": []})
    control = leer_json(estado / "control.json", {})
    man = leer_json(out / "manifiesto.json", {})
    nov = leer_json(estado / "novedades.json", {"novedades": []})
    sostenidos = [r for r in aud.get("resultados", [])
                  if r["veredicto"] == "SOSTENIDO"]
    debiles = [r for r in aud.get("resultados", [])
               if r["veredicto"] == "DEBIL"]
    meses = {mo: m["estado"] for mo, m in man.get("meses", {}).items()}
    payload = {
        "fecha_corte": HOY.strftime("%Y-%m-%d"),
        "corrida": aud.get("corrida"),
        "periodo": "enero-diciembre 2026 (8 meses con datos)",
        "cobertura_cruce": nov.get("cobertura_cruce"),
        "veredicto_control": control.get("veredicto"),
        "no_evaluados": control.get("no_evaluados", []),
        "estado_meses": meses,
        "hallazgos_sostenidos": sostenidos,
        "hallazgos_debiles": debiles,
        "estructura": ESTRUCTURA_INFORME,
        "tono": ("Informe del despacho para leer en tres minutos. Sin jerga. "
                 "Plazos primero. NO agregar hallazgos que no vinieron de la "
                 "auditoría. NO suavizar un DEBIL. NO omitir la cobertura del "
                 "cruce. La sección SIN CAMBIOS lista qué se revisó y no movió. "
                 "La sección NO SE PUDO VERIFICAR lista los chequeos que no "
                 "pudieron correr (no_evaluados de A2): un chequeo que no corrió "
                 "no es un chequeo que pasó."),
        "formato": ("Encabezado con fecha de corte, meses cubiertos y cobertura "
                    "del cruce; luego las secciones en el orden de la estructura."),
    }
    escribir_json(estado / "tarea_a6.json", payload)
    bitacora(estado, "A6", "payload preparado",
             salida=hash_archivo(estado / "tarea_a6.json"))
    print(f"A6: payload en tarea_a6.json ({len(sostenidos)} sostenidos, "
          f"{len(debiles)} débiles) — motor pendiente")


def a6_integrar(estado: Path) -> None:
    motor = estado / "informe_motor.md"
    if not motor.exists():
        print("No hay informe_motor.md — correr el motor primero.")
        return
    texto = motor.read_text(encoding="utf-8")
    faltan = [s for s in ESTRUCTURA_INFORME if s not in texto]
    if faltan:
        print(f"A6: el informe del motor no tiene las secciones: {faltan}")
        bitacora(estado, "A6", f"informe rechazado (faltan: {faltan})")
        return
    (estado / "informe.md").write_text(texto, encoding="utf-8")
    tok = estimar_tokens(
        (estado / "tarea_a6.json").read_text(encoding="utf-8"), texto)
    bitacora(estado, "A6", "informe integrado",
             entrada=hash_archivo(motor),
             salida=hash_archivo(estado / "informe.md"),
             modelo="deepseek-v4-flash", effort="medio", tokens=tok,
             extra={"tokens_origen": "estimado (motor externo)",
                    "tokens_estimado": True})
    print(f"A6: informe.md integrado y validado · tokens≈{tok}")


# ---------------------------------------------------------------------------
# A7 · EJECUTOR (código — sin modelo)
# ---------------------------------------------------------------------------

def ejecutar_accion(accion: str, nv: dict, estado: Path) -> str:
    nid = nv["id"]
    regla = nv["regla"]
    ev = nv.get("evidencia", {}).get("filas", [{}])
    if accion == "archivar":
        return "novedad archivada (ya vista; queda en visto.json)"
    if accion == "priorizar":
        # cola ordenada por prioridad y monto
        monto = ""
        for f in ev:
            for campo in ("MONTO_EST", "MONTO_CRC", "PRECIO_CRC",
                          "MONTO_ADJU_LINEA_CRC"):
                if f.get(campo):
                    monto = f[campo]
                    break
        reg = {"ts": datetime.now().isoformat(timespec="seconds"),
               "novedad_id": nid, "regla": regla,
               "prioridad": nv["prioridad"], "monto_referencia": monto}
        with open(estado / "cola_priorizada.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        return f"priorizada ({nv['prioridad']}, monto ref {monto})"
    if accion == "agendar":
        reg = {"ts": datetime.now().isoformat(timespec="seconds"),
               "novedad_id": nid, "regla": regla,
               "fecha_limite": "a computar por el abogado",
               "responsable": "por asignar"}
        with open(estado / "calendario.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        return "plazo agendado (el cómputo procesal lo hace el abogado)"
    if accion == "preparar_borrador":
        (estado / "borradores").mkdir(parents=True, exist_ok=True)
        lines = [f"# Borrador — {nid}", "",
                 f"- Regla: {regla} · Prioridad: {nv['prioridad']}",
                 f"- Fecha de corte: {HOY.strftime('%Y-%m-%d')}",
                 f"- Cobertura del cruce: {nv.get('cobertura_cruce')}", "",
                 "## Evidencia", ""]
        for f in ev:
            lines.append("- " + "; ".join(f"{k}={v}" for k, v in f.items()))
        lines += ["", "> Borrador preparado por el sistema; NO presentado. "
                      "Requiere revisión y firma humana."]
        p = estado / "borradores" / f"{nid.replace(':', '_').replace('|', '_')}.md"
        p.write_text("\n".join(lines), encoding="utf-8")
        return f"borrador listo en {p.name}"
    if accion == "notificar_interno":
        reg = {"ts": datetime.now().isoformat(timespec="seconds"),
               "novedad_id": nid, "canal": "canal interno",
               "mensaje": f"[{nv['prioridad'].upper()}] {regla}: {nid}"}
        with open(estado / "notificaciones.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        return "notificación interna registrada"
    if accion == "actualizar_expediente":
        (estado / "expedientes").mkdir(parents=True, exist_ok=True)
        reg = {"ts": datetime.now().isoformat(timespec="seconds"),
               "novedad_id": nid, "regla": regla,
               "evidencia": nv.get("evidencia", {})}
        with open(estado / "expedientes" / f"{nid.split(':')[0]}.jsonl", "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        return "expediente interno actualizado"
    return f"acción '{accion}' sin implementación"


def a7(out: Path, year: int, estado: Path) -> None:
    aud = leer_json(estado / "auditoria.json", {"resultados": []})
    pol = leer_json(estado / "politica_acciones.json", DEFAULT_POLITICA)
    if pol is None:
        pol = DEFAULT_POLITICA
    watch = leer_json(estado / "watchlist.json", DEFAULT_WATCHLIST)
    if watch is None:
        watch = DEFAULT_WATCHLIST
    pol_hallazgos = watch.get("politica_hallazgos", {})
    nov = leer_json(estado / "novedades.json", {"novedades": []})
    mapa = {nv["id"]: nv for nv in nov.get("novedades", [])}
    irreversibles = set(pol.get("irreversibles", []))
    ejecutado, pendiente = [], []

    # guard de corrida: A7 jamás ejecuta sobre una auditoría de otra corrida
    corr_aud = aud.get("corrida")
    corr_nov = nov.get("corrida")
    if corr_aud and corr_nov and corr_aud != corr_nov:
        bitacora(estado, "A7",
                 f"auditoría de otra corrida ({corr_aud} vs novedades {corr_nov}) "
                 "— no se ejecuta nada")
        escribir_json(estado / "ejecutado.json",
                      {"fecha": datetime.now().isoformat(timespec="seconds"),
                       "acciones": [], "nota": "omitido: auditoría de corrida anterior"})
        print(f"A7: OMITIDO — auditoría de la corrida {corr_aud}, novedades de la "
              f"corrida {corr_nov}. Re-correr A4→A5 antes de ejecutar.")
        return
    if not corr_aud:
        bitacora(estado, "A7",
                 "auditoría sin corrida (legacy) — no se puede verificar frescura; "
                 "no se ejecuta nada")
        escribir_json(estado / "ejecutado.json",
                      {"fecha": datetime.now().isoformat(timespec="seconds"),
                       "acciones": [], "nota": "omitido: auditoría sin corrida (legacy)"})
        print("A7: OMITIDO — auditoria.json no tiene corrida (archivo de antes del "
              "guard). Re-correr A4→A5.")
        return

    # política v2 por veredicto de A5: SOSTENIDO ejecuta; DEBIL no ejecuta
    # (va al informe marcado); REFUTADO no entra al informe y se archiva con
    # el motivo del auditor en la bitácora.
    for r in aud.get("resultados", []):
        v = r.get("veredicto")
        cfg = pol_hallazgos.get(v, {})
        nv = mapa.get(r.get("hallazgo_id"))
        if v == "REFUTADO":
            bitacora(estado, "A7",
                     f"REFUTADO archivado con motivo del auditor: "
                     f"{r.get('hallazgo_id')} — {r.get('motivo', '')[:120]}")
            continue
        if not cfg.get("ejecuta_acciones", v == "SOSTENIDO"):
            continue
        if nv is None:
            continue
        for acc in pol.get("acciones_por_tipo", {}).get(nv["regla"], []):
            if acc in irreversibles:
                pendiente.append({"novedad_id": nv["id"], "accion": acc,
                                  "borrador": (f"estado/borradores/"
                                               f"{nv['id'].replace(':', '_')}.md"),
                                  "motivo": "requiere aprobación humana"})
            else:
                resultado = ejecutar_accion(acc, nv, estado)
                ejecutado.append({"novedad_id": nv["id"], "accion": acc,
                                  "objeto": nv["regla"], "resultado": resultado})
    escribir_json(estado / "ejecutado.json",
                  {"fecha": datetime.now().isoformat(timespec="seconds"),
                   "acciones": ejecutado})
    escribir_json(estado / "pendiente_aprobacion.json",
                  {"fecha": datetime.now().isoformat(timespec="seconds"),
                   "pendientes": pendiente})
    bitacora(estado, "A7", f"{len(ejecutado)} acciones ejecutadas · "
                           f"{len(pendiente)} pendientes de aprobación",
             salida=hash_archivo(estado / "ejecutado.json"))
    print(f"A7: {len(ejecutado)} acciones ejecutadas · "
          f"{len(pendiente)} irreversibles en pendiente_aprobacion.json")


# ---------------------------------------------------------------------------
# Cadena / orquestador
# ---------------------------------------------------------------------------

def run(out: Path, year: int, estado: Path, force: bool, no_marcar: bool = False,
        pesados: bool = False) -> int:
    # A0 corre SIEMPRE y PRIMERO: un estado desfasado invalida cualquier paso
    coh = a0_guardavia(estado, out, marcar=not no_marcar)
    if coh["veredicto"] == "DESFASADO" and no_marcar:
        print("DESFASADO y --no-marcar: no se retiran los vencidos — se detiene.")
        return 1
    print("== A1 COLECTOR ==")
    if a1(out, year, force, estado, pesados) != 0:
        print("A1 falló — la cadena se detiene.")
        return 1
    print("\n== A2 CONTROL ==")
    control = a2(out, year, estado)
    if control["veredicto"] == "BLOQUEADO":
        print("BLOQUEADO: cambio de esquema — se detiene y se notifica al humano.")
        return 2
    if control["veredicto"] == "REVISAR":
        print("REVISAR: correr el motor (a2_clasificacion.json) y luego "
              "`harness_sicop.py a2-clasificar`.")
        return 3
    print("\n== A3 VIGÍA ==")
    nov = a3(out, year, estado)
    if nov["total"] == 0:
        print("Fin del día — cero tokens.")
        return 0
    print("\n== A4 ANALISTA (preparar) ==")
    a4_preparar(out, year, estado)
    print("Motor pendiente: leer tareas_a4.json -> analisis_motor.json -> "
          "a4-integrar.")
    # y de cierre: que la corrida no haya dejado ella misma un desfase
    final = a0_guardavia(estado, out, marcar=False)
    if final["veredicto"] != "COHERENTE":
        print("ATENCIÓN — la corrida terminó DESFASADA (ver coherencia.json).")
    return 0


def estado_resumen(estado: Path) -> None:
    archivos = ["linea_base.json", "control.json", "watchlist.json", "visto.json",
                "novedades.json", "tareas_a2.json", "tareas_a4.json",
                "analisis.json", "tarea_a5.json", "auditoria.json",
                "tarea_a6.json", "informe.md", "ejecutado.json",
                "pendiente_aprobacion.json", "bitacora.jsonl"]
    print("== ESTADO DEL HARNESS ==")
    for a in archivos:
        p = estado / a
        if p.exists():
            try:
                n = sum(1 for _ in p.open(encoding="utf-8"))
            except OSError:
                n = 0
            print(f"  [x] {a} ({n:,} líneas)")
        else:
            print(f"  [ ] {a}")
    nov = leer_json(estado / "novedades.json", {})
    if nov:
        print(f"novedades: {nov.get('total', 0)} · siembra: {nov.get('sembrar')}")
    aud = leer_json(estado / "auditoria.json", {})
    if aud:
        print("veredictos:", {v: sum(1 for r in aud.get('resultados', [])
                                     if r.get('veredicto') == v)
                              for v in ('SOSTENIDO', 'DEBIL', 'REFUTADO')})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="HARNESS_SICOP orquestador")
    ap.add_argument("--out", default="salida")
    ap.add_argument("--estado", default=None,
                    help="directorio de estado (default: <out>/estado)")
    ap.add_argument("--year", type=int, default=2026)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--pesados", action="store_true",
                    help="incluye InvitacionProcedimiento y OrdenPedido (~14 GB "
                         "descomprimidos en total, 2020-2026)")
    ap.add_argument("--no-marcar", action="store_true",
                    help="A0 informa los artefactos vencidos pero no los retira; "
                         "si hay alguno, la corrida se detiene")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("a0")
    sub.add_parser("coherencia")
    sub.add_parser("a1")
    sub.add_parser("a2")
    sub.add_parser("a2-clasificar")
    sub.add_parser("a3")
    sub.add_parser("sembrar")
    sub.add_parser("a4-preparar")
    sub.add_parser("a4-integrar")
    sub.add_parser("a5-preparar")
    sub.add_parser("a5-integrar")
    sub.add_parser("a6-preparar")
    sub.add_parser("a6-integrar")
    sub.add_parser("a7")
    sub.add_parser("run")
    sub.add_parser("estado")
    sub.add_parser("bitacora")
    args = ap.parse_args(argv)

    out = Path(args.out)
    estado = Path(args.estado) if args.estado else (out / "estado")
    estado.mkdir(parents=True, exist_ok=True)
    # semillas por defecto
    if not (estado / "watchlist.json").exists():
        escribir_json(estado / "watchlist.json", DEFAULT_WATCHLIST)
    if not (estado / "politica_acciones.json").exists():
        escribir_json(estado / "politica_acciones.json", DEFAULT_POLITICA)

    cmd = args.cmd
    if cmd in ("a0", "coherencia"):
        coh = a0_guardavia(estado, out, marcar=not args.no_marcar)
        print(f"A0: {coh['veredicto']} · {len(coh['vencidos'])} vencidos · "
              f"{len(coh['huerfanos'])} huérfanos · {len(coh['coherentes'])} al día")
        return 0 if coh["veredicto"] == "COHERENTE" else 1
    if cmd == "a1":
        return a1(out, args.year, args.force, estado, args.pesados)
    if cmd == "a2":
        a2(out, args.year, estado)
        return 0
    if cmd == "a2-clasificar":
        a2_clasificar(estado)
        return 0
    if cmd == "a3":
        a3(out, args.year, estado)
        return 0
    if cmd == "sembrar":
        a3(out, args.year, estado, sembrar=True)
        return 0
    if cmd == "a4-preparar":
        a4_preparar(out, args.year, estado)
        return 0
    if cmd == "a4-integrar":
        a4_integrar(estado)
        return 0
    if cmd == "a5-preparar":
        a5_preparar(estado)
        return 0
    if cmd == "a5-integrar":
        a5_integrar(estado)
        return 0
    if cmd == "a6-preparar":
        a6_preparar(out, args.year, estado)
        return 0
    if cmd == "a6-integrar":
        a6_integrar(estado)
        return 0
    if cmd == "a7":
        a7(out, args.year, estado)
        return 0
    if cmd == "run":
        return run(out, args.year, estado, args.force, args.no_marcar, args.pesados)
    if cmd == "estado":
        estado_resumen(estado)
        return 0
    if cmd == "bitacora":
        p = estado / "bitacora.jsonl"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines()[-15:]:
                print(line)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
