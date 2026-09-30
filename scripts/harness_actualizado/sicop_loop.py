#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sicop_loop.py (v2) — Extracción completa de contratación pública SICOP (Costa Rica).

Por mes: descargar -> verificar hash -> extraer 15 CSV -> validar -> deduplicar -> registrar.
Al final, una sola vez: cruce de competencia (Ofertas x LineasOfertadas) sobre el acumulado.

Fuente (datos abiertos oficiales, actualización diaria 08:00, historial desde 2010):
  https://dlsaobservatorioprod.blob.core.windows.net/fs-synapse-observatorio-produccion/Zip/{AAAAMM}.zip

Sólo biblioteca estándar. Sin scraping, sin claves de API.

Uso:
  python3 scripts/sicop_loop.py --year 2026 --out ./salida
  python3 scripts/sicop_loop.py --year 2026 --months 01,02,03 --out ./salida
  python3 scripts/sicop_loop.py --year 2026 --out ./salida --solo adjudicaciones,ofertas
  python3 scripts/sicop_loop.py --year 2026 --out ./salida --pesados
  python3 scripts/sicop_loop.py --year 2026 --out ./salida --force

Salidas en --out: un CSV por conjunto ({conjunto}_{año}.csv), competencia_por_linea.csv,
manifiesto.json (v2), REPORTE.md y _cache/ con los zips originales.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

# Windows: consolas cp1252 no saben imprimir ₡ (U+20A1). Fuerza UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BASE_URL = (
    "https://dlsaobservatorioprod.blob.core.windows.net/"
    "fs-synapse-observatorio-produccion/Zip/{AAAAMM}.zip"
)
MIN_ZIP_BYTES = 1_000_000
RETRIES = 3
BACKOFF = (5, 15, 45)
UA = "Mozilla/5.0 (sicop-extraccion; stdlib)"
TRACE = ("ARCHIVO_ORIGEN", "MES_ZIP", "MES_PUBLICACION")

# ---------------------------------------------------------------------------
# Configuración de los 15 conjuntos (más los 2 "pesados" opcionales)
# ---------------------------------------------------------------------------

CONJUNTOS = {
    "carteles": {
        "archivo": "DetalleCarteles.csv",
        "clave": ("NRO_SICOP",),
        "obligatorios": ("NRO_SICOP",),
        "columnas": ["NRO_SICOP", "CEDULA_INSTITUCION", "FECHA_PUBLICACION",
                     "NRO_PROCEDIMIENTO", "TIPO_PROCEDIMIENTO", "MODALIDAD_PROCEDIMIENTO",
                     "CARTEL_STAT", "CARTEL_NM", "FECHAH_APERTURA", "CODIGO_BPIP",
                     "CLAS_OBJ", "COD_EXCEPCION", "DES_EXCEPCION", "MONTO_EST",
                     "FECHA_MOD"],
    },
    "lineas_cartel": {
        "archivo": "DetalleLineaCartel.csv",
        "clave": ("NRO_SICOP", "NUMERO_LINEA"),
        "obligatorios": ("NRO_SICOP", "NUMERO_LINEA"),
        "columnas": ["NRO_SICOP", "NUMERO_LINEA", "NUMERO_PARTIDA",
                     "CANTIDAD_SOLICITADA", "PRECIO_UNITARIO_ESTIMADO", "TIPO_MONEDA",
                     "TIPO_CAMBIO_CRC", "TIPO_CAMBIO_DOLAR", "CODIGO_IDENTIFICACION",
                     "MONTO_RESERVADO", "DESC_LINEA"],
    },
    "ofertas": {
        "archivo": "Ofertas.csv",
        "clave": ("NRO_SICOP", "NRO_OFERTA"),
        "obligatorios": ("NRO_SICOP", "NRO_OFERTA"),
        "columnas": ["NRO_SICOP", "NRO_OFERTA", "CEDULA_PROVEEDOR",
                     "FECHA_PRESENTA_OFERTA", "TIPO_OFERTA", "ID_CONSORCIO"],
    },
    "lineas_ofertadas": {
        "archivo": "LineasOfertadas.csv",
        "clave": ("NRO_SICOP", "NRO_OFERTA", "NRO_LINEA"),
        "obligatorios": ("NRO_SICOP", "NRO_OFERTA", "NRO_LINEA"),
        "columnas": ["NRO_SICOP", "NRO_OFERTA", "NRO_LINEA", "CODIGO_PRODUCTO",
                     "CANTIDAD_OFERTADA", "PRECIO_UNITARIO_OFERTADO", "TIPO_MONEDA",
                     "DESCUENTO", "IVA", "OTROS_IMPUESTOS", "ACARREOS",
                     "TIPO_CAMBIO_CRC", "TIPO_CAMBIO_DOLAR", "CODIGO_PRODUCTO_CL"],
    },
    "adjudicaciones": {
        "archivo": "ProcedimientoAdjudicacion.csv",
        "clave": ("NRO_SICOP", "LINEA", "CEDULA_PROVEEDOR"),
        "obligatorios": ("NRO_SICOP", "LINEA", "CEDULA_PROVEEDOR"),
        "columnas": ["CEDULA", "INSTITUCION", "ANO", "NUMERO_PROCEDIMIENTO",
                     "DESCR_PROCEDIMIENTO", "LINEA", "PROD_ID", "DESCR_BIEN_SERVICIO",
                     "CANTIDAD", "UNIDAD_MEDIDA", "MONTO_UNITARIO", "MONEDA_PRECIO_EST",
                     "MONEDA_ADJUDICADA", "MONTO_ADJU_LINEA", "MONTO_ADJU_LINEA_CRC",
                     "MONTO_ADJU_LINEA_USD", "FECHA_ADJUD_FIRME", "FECHA_SOL_CONTRA",
                     "CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR", "PERFIL_PROV",
                     "CEDULA_REPRESENTANTE", "REPRESENTANTE", "OBJETO_GASTO",
                     "NRO_SICOP", "TIPO_PROCEDIMIENTO", "MODALIDAD_PROCEDIMIENTO",
                     "fecha_rev", "FECHA_SOL_CONTRA_CL", "PROD_ID_CL"],
    },
    "adjudicaciones_firme": {
        "archivo": "AdjudicacionesFirme.csv",
        "clave": ("NRO_SICOP", "NRO_ACTO"),
        "obligatorios": ("NRO_SICOP", "NRO_ACTO"),
        "columnas": ["NRO_SICOP", "NRO_ACTO", "FECHA_ADJ_FIRME", "PERMITE_RECURSOS",
                     "DESIERTO", "FECHA_REV"],
    },
    "lineas_adjudicadas": {
        "archivo": "LineasAdjudicadas.csv",
        "clave": ("NRO_SICOP", "NRO_OFERTA", "NRO_LINEA", "CEDULA_PROVEEDOR"),
        "obligatorios": ("NRO_SICOP", "NRO_OFERTA", "NRO_LINEA"),
        "columnas": ["NRO_SICOP", "NRO_OFERTA", "CODIGO_PRODUCTO", "NRO_LINEA",
                     "NRO_ACTO", "CEDULA_PROVEEDOR", "CANTIDAD_ADJUDICADA",
                     "PRECIO_UNITARIO_ADJUDICADO", "TIPO_MONEDA", "DESCUENTO", "IVA",
                     "OTROS_IMPUESTOS", "ACARREOS", "TIPO_CAMBIO_CRC",
                     "TIPO_CAMBIO_DOLAR"],
    },
    "contratos": {
        "archivo": "Contratos.csv",
        "clave": ("NRO_CONTRATO", "SECUENCIA"),
        "obligatorios": ("NRO_CONTRATO", "SECUENCIA"),
        "columnas": ["NRO_CONTRATO", "SECUENCIA", "NUMERO_PROCEDIMIENTO",
                     "CEDULA_PROVEEDOR", "NRO_SICOP", "CEDULA_INSTITUCION",
                     "TIPO_CONTRATO", "TIPO_MODIFICACION", "FECHA_NOTIFICACION",
                     "FECHA_ELABORACION", "TIPO_AUTORIZACION", "TIPO_DISMINUCION",
                     "VIGENCIA", "MONEDA", "FECHA_INI_SUSP", "FECHA_REINI_CONT",
                     "PLAZO_SUSP", "FECHA_MODIFICACION", "FECHA_INI_PRORR",
                     "FECHA_FIN_PRORR", "NRO_CONTRATO_WEB"],
    },
    "lineas_contratadas": {
        "archivo": "LineasContratadas.csv",
        "clave": ("NRO_SICOP", "NRO_LINEA_CONTRATO", "NRO_CONTRATO", "SECUENCIA"),
        "obligatorios": ("NRO_SICOP", "NRO_LINEA_CONTRATO", "NRO_CONTRATO"),
        "columnas": ["NRO_SICOP", "NRO_LINEA_CONTRATO", "NRO_LINEA_CARTEL",
                     "NRO_CONTRATO", "SECUENCIA", "CEDULA_PROVEEDOR",
                     "CODIGO_PRODUCTO", "CANTIDAD_CONTRATADA", "PRECIO_UNITARIO",
                     "TIPO_MONEDA", "DESCUENTO", "IVA", "OTROS_IMPUESTOS", "ACARREOS",
                     "TIPO_CAMBIO_CRC", "TIPO_CAMBIO_DOLAR", "NRO_ACTO",
                     "DESC_PRODUCTO", "cantidad_aumentada", "cantidad_disminuida",
                     "monto_aumentado", "monto_disminuido"],
    },
    "lineas_recibidas": {
        "archivo": "LineasRecibidas.csv",
        "clave": ("NRO_SICOP", "NRO_LINEA", "NRO_RECEP_PROVISIONAL", "ENTREGA",
                  "SECUENCIA"),
        "obligatorios": ("NRO_SICOP", "NRO_LINEA"),
        "columnas": ["NRO_SICOP", "NRO_CONTRATO", "SECUENCIA", "NRO_RECEP_PROVISIONAL",
                     "ESTADO_RECEP_PROVISIONAL", "NRO_RECEP_DEFINITIVA",
                     "ESTADO_RECEP_DEFINITIVA", "NRO_LINEA", "ENTREGA",
                     "CODIGO_PRODUCTO", "CANTIDAD_REAL_RECIBIDA", "desc_producto",
                     "precio", "dias_adelanto_atraso", "fecha_recepcion_Definitiva"],
    },
    "garantias": {
        "archivo": "Garantias.csv",
        "clave": ("NRO_SICOP", "nro_garantia", "ced_garante", "gara_seq"),
        "obligatorios": ("NRO_SICOP",),
        "columnas": ["NRO_SICOP", "NUMERO_PROCEDIMIENTO", "DESCRIPCION_PROCEDIMIENTO",
                     "TIPO_PROCEDIMIENTO", "NOMBRE_INSTITUCION", "CEDULA_INSTITUCION",
                     "NOMBRE_PROVEEDOR", "CEDULA_PROVEEDOR", "TIPO_GARANTIA", "MONTO",
                     "ESTADO", "VIGENCIA", "fecha_registro", "nro_garantia",
                     "ced_garante", "gara_seq", "garantia_NM"],
    },
    "etapas": {
        "archivo": "FechaPorEtapas.csv",
        "clave": ("NRO_SICOP", "CARTEL_SEQ", "PARTIDA", "LINEA"),
        "obligatorios": ("NRO_SICOP", "LINEA"),
        "columnas": ["NRO_SICOP", "NUMERO_PROCEDIMIENTO", "CARTEL_SEQ", "PARTIDA",
                     "LINEA", "PUBLICACION", "FECHA_APERTURA",
                     "SOLICITUD_ESTUDIOS_TECNICOS", "COMUNICACION",
                     "SOLICITUD_PAGO_ESP_FISCALES", "RESPUESTA_ESTUDIOS_TECNICOS",
                     "SOLICITUD_RECOM_ADJUD", "RESPUESTA_RECOM_ADJUD",
                     "SOLICITUD_ADJUD", "RESPUESTA_ADJUD", "ADJUDICACION_FIRME",
                     "FECHA_RESUL_PAGO_ESP_FISCALES", "FECHA_ELABORACION_CONTRATO",
                     "SOLICITUD_APROBACION_CONTRATO", "RESPUESTA_APROBACION_CONTRATO",
                     "FECHA_NOTIFICACION", "FECHA_1RA_SOL_RECEPCION",
                     "FECHA_1RA_SOL_RECEP_PROVI", "FECHA_ULT_SOL_RECEP_DEFI",
                     "FECHA_1RA_SOL_PAGO", "FECHA_ULT_SOL_PAGO", "FECHA_RESUL_PAGO"],
    },
    "inhibiciones": {
        "archivo": "FuncionariosInhibicion.csv",
        "clave": ("CED_INSTITUCION", "CED_FUNCIONARIO", "FECHA_INICIO", "FECHA_FIN"),
        "obligatorios": ("CED_FUNCIONARIO",),
        "columnas": ["CED_INSTITUCION", "CED_FUNCIONARIO", "NOM_FUNCIONARIO",
                     "FECHA_INICIO", "FECHA_FIN", "ESTADO", "fecha_registro"],
    },
    "instituciones": {
        "archivo": "InstitucionesRegistradas.csv",
        "clave": ("CEDULA",),
        "obligatorios": ("CEDULA",),
        "columnas": ["CEDULA", "NOMBRE_INSTITUCION", "ZONA_GEO_INST", "FECHA_INGRESO",
                     "FECHA_MOD"],
    },
    "procedimientos_adm": {
        "archivo": "ProcedimientoADM.csv",
        "clave": ("NRO_SICOP", "NUMERO_PA"),
        "obligatorios": ("NRO_SICOP",),
        "columnas": ["NRO_SICOP", "NUMERO_PROCEDIMIENTO", "NOMBRE_PROVEEDOR",
                     "NUMERO_PA", "NOMBRE_INSTITUCION", "CEDULA_INSTITUCION",
                     "CEDULA_PROVEEDOR", "FECHA_NOTIFICACION", "INHAB_APERC",
                     "MULTA_CAUSULA"],
    },
    # --- descubiertos el 2026-08-23: el zip trae 25 archivos, no 17 ---
    "recursos": {
        "archivo": "RecursosObjecion.csv",
        "clave": ("NRO_RECURSO",),
        "obligatorios": ("NRO_RECURSO", "NRO_SICOP"),
        "columnas": ["NRO_RECURSO", "CEDULA_PROVEEDOR", "NRO_SICOP", "NRO_ACTO",
                     "LINEA_OBJETADA", "TIPO_RECURSO", "RESULTADO",
                     "CAUSA_RESULTADO", "FECHA_PRESENTACION_RECURSO",
                     "nro_procedimiento", "desc_procedimiento", "reqer_nm",
                     "recurso_stat"],
    },
    "proveedores": {
        "archivo": "Proveedores.csv",
        "clave": ("CEDULA_PROVEEDOR",),
        "obligatorios": ("CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR"),
        "columnas": ["CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR", "TIPO_PROVEEDOR",
                     "TAMAÑO_PROVEEDOR", "FECHA_CONSTITUCION", "FECHA_EXPIRACION",
                     "zona_geo_prov", "fecha_registro", "fecha_mod"],
    },
    "evaluacion_ofertas": {
        "archivo": "SistemaEvaluacionOfertas.csv",
        "clave": ("NRO_SICOP", "EVAL_ITEM_SEQNO"),
        "obligatorios": ("NRO_SICOP",),
        "columnas": ["NRO_SICOP", "EVAL_ITEM_SEQNO", "FACTOR_EVAL", "PORC_EVAL",
                     "fecha_registro"],
    },
    "sanciones_registro": {
        "archivo": "SancionProveedores.csv",   # delimitador ',' — el sniff lo detecta
        "clave": ("NO_RESOLUCION", "CEDULA_PROVEEDOR"),
        "obligatorios": ("CEDULA_PROVEEDOR",),
        "columnas": ["NOMBRE_INSTITUCION", "CEDULA_INSTITUCION", "CODIGO_PRODUCTO",
                     "DESCRIP_PRODUCTO", "CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR",
                     "TIPO_SANCION", "DESCR_SANCION", "INICIO_SANCION",
                     "FINAL_SANCION", "ESTADO", "NO_RESOLUCION", "fecha_registro"],
    },
    "remates": {
        "archivo": "Remates.csv",
        "clave": ("NRO_SICOP", "CED_PROVEEDOR", "MONTO_PUJA"),
        "obligatorios": ("NRO_SICOP",),
        "columnas": ["NRO_SICOP", "NUMERO_PROCEDIMIENTO", "FECHA_INVITACION",
                     "CED_PROVEEDOR", "MONTO_PUJA", "MONEDA_PUJA",
                     "MONTO_EST_LINEA", "CANT_EST", "MONEDA_ADJ", "MONTO_ADJ",
                     "CANT_ADJ", "TIPO_CAMBIO_MONEDA", "fecha_mod"],
    },
    "recepciones": {
        "archivo": "Recepciones.csv",
        "clave": ("NRO_RECEP_DEFINITIVA",),
        "obligatorios": ("NRO_SICOP", "NRO_CONTRATO"),
        "columnas": ["NRO_SICOP", "NRO_CONTRATO", "NRO_RECEP_DEFINITIVA",
                     "FECHA_RECEP_DEFINITIVA", "nro_procedimiento",
                     "cedula_proveedor", "cedula_institucion", "moneda",
                     "nombre_proveedor", "fecha_ent_ini"],
    },
    "reajustes": {
        "archivo": "ReajustePrecios.csv",
        "clave": ("NRO_CONTRATO", "NRO_LINEA_CONTRATO", "NUMERO_REAJUSTE"),
        "obligatorios": ("NRO_CONTRATO",),
        "columnas": ["NRO_SICOP", "NUMERO_PROCEDIMIENTO", "NOMBRE_INSTITUCION",
                     "CEDULA_INSTITUCION", "CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR",
                     "FECHA_ELABORACION", "CODIGO_PRODUCTO", "DES_PRODUCTO",
                     "NRO_CONTRATO", "NRO_LINEA_CONTRATO", "CANTIDAD_CONTRATADA",
                     "PRECIO_UNITARIO", "NUMERO_REAJUSTE", "PRECIO_ANT_ULT_RJ",
                     "MONTO_REAJUSTE", "NUEVO_PRECIO", "PORC_INCR_ULT_RJ",
                     "FECHA_INICIO", "FECHA_FIN"],
    },
    "lineas_sistema": {
        "archivo": "Sistemas.csv",
        "clave": ("NRO_SICOP", "NUMERO_LINEA", "NUMERO_PARTIDA"),
        "obligatorios": ("NRO_SICOP",),
        "columnas": ["NRO_SICOP", "NUMERO_LINEA", "NUMERO_PARTIDA", "DESC_LINEA",
                     "CEDULA_INSTITUCION", "NRO_PROCEDIMIENTO",
                     "TIPO_PROCEDIMIENTO", "FECHA_PUBLICACION"],
    },
}

# Columnas de monto por conjunto (para métricas de validación en el manifiesto).
MONTO_COLS = {
    "carteles": ("MONTO_EST",),
    "lineas_cartel": ("PRECIO_UNITARIO_ESTIMADO", "MONTO_RESERVADO"),
    "lineas_ofertadas": ("PRECIO_UNITARIO_OFERTADO",),
    "adjudicaciones": ("MONTO_UNITARIO", "MONTO_ADJU_LINEA",
                       "MONTO_ADJU_LINEA_CRC", "MONTO_ADJU_LINEA_USD"),
    "lineas_adjudicadas": ("PRECIO_UNITARIO_ADJUDICADO",),
    "lineas_contratadas": ("PRECIO_UNITARIO", "monto_aumentado", "monto_disminuido"),
    "lineas_recibidas": ("precio",),
    "garantias": ("MONTO",),
    "remates": ("MONTO_PUJA", "MONTO_EST_LINEA", "MONTO_ADJ"),
    "reajustes": ("PRECIO_UNITARIO", "PRECIO_ANT_ULT_RJ", "MONTO_REAJUSTE",
                  "NUEVO_PRECIO"),
}

# Columnas de texto libre por conjunto (donde la fuente deja ';' sin escapar).
# Se usan para reconstruir filas con más campos que columnas: el excedente
# pertenece a la descripción y se re-une ahí, restaurando la alineación de las
# columnas posteriores. Conjuntos sin columna de descripción ponen la fila en
# cuarentena en vez de guardarla corrida.
DESC_COLS = {
    "lineas_recibidas": ("desc_producto",),
    "lineas_contratadas": ("DESC_PRODUCTO",),
    "lineas_cartel": ("DESC_LINEA",),
    "adjudicaciones": ("DESCR_PROCEDIMIENTO", "DESCR_BIEN_SERVICIO"),
    "garantias": ("DESCRIPCION_PROCEDIMIENTO",),
    "carteles": ("DES_EXCEPCION",),
    "sanciones_registro": ("DESCR_SANCION", "DESCRIP_PRODUCTO"),
    "reajustes": ("DES_PRODUCTO",),
}

PESADOS = {
    "invitaciones": {
        "archivo": "InvitacionProcedimiento.csv",
        "clave": ("NRO_SICOP", "CEDULA_PROVEEDOR", "FECHA_INVITACION"),
        "obligatorios": ("NRO_SICOP",),
        "columnas": ["SECUENCIA", "CED_INSTITUCION", "INSTITUCION", "NRO_SICOP",
                     "CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR", "NUMERO_PROCEDIMIENTO",
                     "FECHA_INVITACION"],
    },
    "ordenes_pedido": {
        "archivo": "OrdenPedido.csv",
        # Trampas verificadas (orden 2026-08-24 + v2 2026-08-25):
        # a) TOTAL_ORDEN es el total de la orden completa replicado en cada línea;
        #    SECUENCIA es un ENUM (98% en '00'), NO identifica línea.
        # b) La clave de línea es LINEA_ORD_PEDIDO. (NRO_ORDEN, LINEA_ORD_PEDIDO)
        #    distingue 545.896 pares vs 545.272 órdenes: deduplicar solo por
        #    NRO_ORDEN borra 1 línea en 624 órdenes (0,1%). Verificado por el
        #    obrero (2026-08-25). Sumar TOTAL_ORDEN en crudo sigue inflando ~3×:
        #    el monto de una orden = TOTAL_ORDEN una sola vez por NRO_ORDEN.
        "clave": ("NRO_ORDEN", "LINEA_ORD_PEDIDO"),
        "obligatorios": ("NRO_ORDEN",),
        "columnas": ["NRO_SICOP", "NUMERO_PROCEDIMIENTO", "NRO_CONTRATO",
                     "CONTRACT_NO", "SECUENCIA_CONTRATO", "TOTAL_ORDEN",
                     "TOTALESTIMADO", "USD_MONT", "MONEDA_ORDEN", "NRO_ORDEN",
                     "SECUENCIA", "LINEA_ORD_PEDIDO", "ESTADO_ORDEN",
                     "DESC_PROCEDIMIENTO", "FECHA_ELABORACION_ORDEN",
                     "FECHA_NOTIFICACION_ORDEN", "FECHA_PROVEEDOR_RECIBE_ORDEN",
                     "FECHA_PROV_RECIBE_ORDEN", "FECHA_REC_PEDIDO", "FECHAREGISTRO",
                     "CEDULAPROVEEDOR", "NOMBRE_PROVEEDOR"],
    },
}

# Control de la corrida de referencia (23/08/2026): filas únicas por conjunto.
REFERENCIA_CONJUNTOS = {
    "ofertas": 155_375, "etapas": 129_036, "lineas_cartel": 128_501,
    "inhibiciones": 65_801, "lineas_recibidas": 43_340,
    "adjudicaciones_firme": 43_132, "adjudicaciones": 12_994,
    "lineas_ofertadas": 39_442, "contratos": 32_027, "garantias": 19_492,
    "carteles": 19_098, "lineas_adjudicadas": 14_531,
    "lineas_contratadas": 12_892, "instituciones": 681,
}
REFERENCIA_TOTAL = 715_350          # total declarado en la skill
REFERENCIA_ADJ_MES = {              # líneas de adjudicaciones por mes
    "202601": 0, "202602": 610, "202603": 839, "202604": 879,
    "202605": 2_009, "202606": 4_541, "202607": 2_467, "202608": 1_649,
}
REFERENCIA_ADJ_CRC = 89_131_237_957
REFERENCIA_CRUCE = {"filas_competencia": 24_710, "lineas_con_oferente": 9_585,
                    "cobertura": 0.626}


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def parse_number(s):
    """Monto textual -> float (None si no es numérico). Acepta miles, decimales
    estilo CR/US y notación científica ('2.9999999999999999E-2').

    VERIFICADO contra lineas_ofertadas_2026.csv (2026-08-23): la fuente usa
    punto decimal sin separador de miles (39.327 precios, 0 con coma, 0 con
    2+ puntos; '1.000' = 1.0, '507.66000000000003' = 507.66; 0 valores donde
    este parser difiere de float()). La rama de miles estilo CR (con coma)
    queda dormida con esta fuente y sólo actuaría si apareciera '1.234,56'."""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    for ch in ("₡", "$", "€", " ", "\u00a0", "\t"):
        s = s.replace(ch, "")
    if "e" in s.lower():
        s2 = s
        if "," in s2 and "." not in s2:
            s2 = s2.replace(",", ".")
        try:
            return float(s2)
        except ValueError:
            return None
    if not re.fullmatch(r"[+-]?[\d.,]+", s):
        return None
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        left, _, right = s.partition(",")
        if len(right) == 3 and "," not in left and "." not in left:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def fmt_colon(v) -> str:
    if v is None:
        return "—"
    return f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def head_remoto(url: str) -> dict:
    """ETag / Last-Modified / Content-Length del zip remoto, sin bajarlo.

    Es la mitad barata de la detección de reescritura: si la fuente reescribió
    un mes que ya está en OK, el ETag cambia y no hay que descargar 180 MB para
    enterarse.

    Tres retornos distintos, y la diferencia importa:
      {"etag": …}        → el servidor contestó
      {"not_found": True} → 404, la fuente retiró el mes
      {"error": True}     → no se pudo preguntar (red, throttling)

    El tercero se agregó el 2026-08-25 porque medimos el problema: en un barrido
    secuencial de 84 HEAD, **16 meses que SÍ existen** devolvieron error — el
    blob storage tira la conexión bajo ráfaga. Antes eso devolvía {} y el
    llamador lo interpretaba como «sin validadores» → re-descarga de 180 MB por
    un hipo de red. Ahora reintenta con backoff y, si igual falla, dice que
    falló en vez de mentir.
    """
    for intento in range(3):
        try:
            req = urllib.request.Request(url, method="HEAD",
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return {
                    "etag": (r.headers.get("ETag") or "").strip('"') or None,
                    "last_modified": r.headers.get("Last-Modified"),
                    "content_length": r.headers.get("Content-Length"),
                }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"not_found": True}
            if e.code not in (429, 500, 502, 503, 504):
                return {"error": True}
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.5 * (intento + 1))
    return {"error": True}


def download(url: str, dest: Path) -> str:
    """'ok' | 'not_found' (404). Otros fallos reintentan y lanzan RuntimeError.

    Descarga ATÓMICA: escribe a <dest>.tmp y renombra al final. Sin esto, un
    corte de red deja un zip parcial en el caché que luce sano — el tamaño pasa
    MIN_ZIP_BYTES y el mes se procesa incompleto sin que nadie se entere.
    """
    last_err = None
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, length=1024 * 1024)
            if tmp.stat().st_size < MIN_ZIP_BYTES:
                tmp.unlink(missing_ok=True)
                last_err = f"descarga demasiado pequeña ({tmp.stat().st_size} bytes)"
            else:
                os.replace(tmp, dest)      # atómico en el mismo volumen
                return "ok"
        except urllib.error.HTTPError as e:
            tmp.unlink(missing_ok=True)
            if e.code == 404:
                if dest.exists():
                    dest.unlink()
                return "not_found"
            last_err = f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            tmp.unlink(missing_ok=True)
            last_err = f"{type(e).__name__}: {e}"
        if attempt < RETRIES:
            log(f"  descarga falló ({last_err}); reintento {attempt + 1}/{RETRIES} "
                f"en {BACKOFF[attempt - 1]}s")
            time.sleep(BACKOFF[attempt - 1])
    tmp.unlink(missing_ok=True)
    raise RuntimeError(f"descarga falló tras {RETRIES} intentos: {last_err}")


def detect_encoding(raw: bytes) -> str:
    """Codificación validando el archivo completo (un corte a mitad de una
    secuencia UTF-8 multibyte falsearía la detección con un prefijo corto).

    utf-16 SOLO con BOM: sin esa guarda, bytes latin-1 de longitud par se
    decodifican como utf-16 y devuelven basura sin lanzar excepción (bug
    encontrado por la implementación de referencia al probar su propia
    corrección — v0.4 del orquestador)."""
    for cand in ("utf-8-sig", "utf-8"):
        try:
            raw.decode(cand)
            return cand
        except UnicodeDecodeError:
            continue
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            raw.decode("utf-16")
            return "utf-16"
        except UnicodeDecodeError:
            pass
    return "latin-1"


def sniff_delim(raw: bytes, enc: str) -> str:
    sample = raw.decode(enc, errors="replace")
    line = sample.splitlines()[0] if sample else ""
    counts = {d: 0 for d in ",;\t|"}
    in_q = False
    for ch in line:
        if ch == '"':
            in_q = not in_q
        elif ch in counts and not in_q:
            counts[ch] += 1
    return max(counts, key=counts.get) if any(counts.values()) else ";"


def leer_miembro(zip_path: Path, basename: str):
    """Devuelve (raw_bytes, nombre_miembro) o (None, None) si no está."""
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if Path(name).name.lower() == basename.lower():
                return z.read(name), name
    return None, None


def registrar_inventario(out_dir: Path, month: str, archivos: list) -> None:
    """Guarda el inventario COMPLETO y ordenado del zip mensual en
    inventario_zip.json (append-only por mes). A2 lo compara contra el
    inventario conocido: si aparece o desaparece un archivo → BLOQUEADO."""
    p = out_dir / "inventario_zip.json"
    inv = {}
    if p.exists():
        try:
            inv = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            inv = {}
    inv[month] = {"archivos": sorted(archivos), "n": len(archivos),
                  "actualizado": datetime.now().isoformat(timespec="seconds")}
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(inv, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


# ---------------------------------------------------------------------------
# Procesamiento de un mes
# ---------------------------------------------------------------------------

def procesar_conjunto(conf: dict, nombre: str, raw: bytes, mes: str, writer,
                      vistos: set, salida: dict, qwriter=None, cartel_pub=None):
    """Lee un CSV de un conjunto, valida, deduplica y escribe al writer del
    conjunto. salida acumula métricas del mes.

    Dedupe por **clave natural** (conf['clave']): la fuente repite filas dentro
    y entre meses, y los snapshots mensuales evolucionan campos de estado (p.
    ej. recepciones que ganan número definitivo); una fila por clave natural es
    la unidad de observación. La clave de cada conjunto está calibrada contra
    la corrida de referencia (13 de 15 conjuntos calzan exacto)."""
    enc = detect_encoding(raw)
    delim = sniff_delim(raw, enc)
    text = raw.decode(enc, errors="replace")
    if not text.strip():
        salida["filas"] = 0
        return
    rdr = csv.reader(text.splitlines(), delimiter=delim)
    try:
        header = [h.strip() for h in next(rdr)]
    except StopIteration:
        salida["filas"] = 0
        return
    idx = {h: i for i, h in enumerate(header)}

    # validación de esquema
    ausentes = [c for c in conf["columnas"] if c not in idx]
    if ausentes:
        salida.setdefault("columnas_ausentes", []).extend(ausentes)
    cols_salida = conf["columnas"] + list(TRACE)

    n = 0
    dups = 0
    oblig_vacios = 0
    extras = 0
    cuarentena = 0
    monto_no_num = 0
    monto_neg = 0
    monto_cols = MONTO_COLS.get(nombre, ())
    desc_cols = DESC_COLS.get(nombre, ())
    for row in rdr:
        if len(row) > len(header):
            extras += 1
            exceso = len(row) - len(header)
            di = next((idx[c] for c in desc_cols if idx.get(c) is not None), None)
            if di is not None and exceso <= 4:
                # Separador ';' sin escapar dentro de la columna de descripción:
                # el excedente pertenece a esa columna. Se re-une ahí y se
                # restaura la alineación de las columnas posteriores (montos,
                # fechas, días) — antes se truncaba y los datos quedaban corridos.
                row = (list(row[:di])
                       + [";".join(row[di:di + exceso + 1])]
                       + list(row[di + exceso + 1:]))
            else:
                # Sin columna de descripción o exceso extraño (fuente con dos
                # registros pegados): no se puede reconstruir de forma confiable.
                # La fila va a CUARENTENA (se archiva cruda, no se pierde) y no
                # entra al conjunto limpio.
                cuarentena += 1
                if qwriter is not None:
                    qwriter.writerow({
                        "CONJUNTO": nombre, "MES_PUBLICACION": mes,
                        "MOTIVO": f"exceso de {exceso} campos (registros pegados o "
                                  f"separador sin escapar sin columna de descripción)",
                        "N_CAMPOS": len(row),
                        "CAMPOS_CRUDOS": json.dumps(list(row), ensure_ascii=False),
                    })
                continue
        elif len(row) < len(header):
            row = list(row) + [""] * (len(header) - len(row))
        rec = {h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(header)}
        if any(not rec.get(k) for k in conf["obligatorios"]):
            oblig_vacios += 1
        for mc in monto_cols:
            v = rec.get(mc, "")
            if not v:
                continue
            p = parse_number(v)
            if p is None:
                monto_no_num += 1
            elif p < 0:
                monto_neg += 1
        key = tuple(rec.get(k, "") for k in conf["clave"])
        if key in vistos:
            dups += 1
            continue
        vistos.add(key)
        rec["ARCHIVO_ORIGEN"] = conf["archivo"]
        # MES_ZIP: mes del zip donde se vio por PRIMERA vez (dedup first-seen).
        # MES_PUBLICACION: mes REAL del procedimiento (cartel FECHA_PUBLICACION);
        # fallback al mes del zip si el cartel no se conoce aun.
        rec["MES_ZIP"] = mes
        rec["MES_PUBLICACION"] = (cartel_pub or {}).get(rec.get("NRO_SICOP") or "", mes)
        writer.writerow({c: rec.get(c, "") for c in cols_salida})
        n += 1
    salida["filas"] = n
    salida["duplicados"] = salida.get("duplicados", 0) + dups
    salida["obligatorios_vacios"] = salida.get("obligatorios_vacios", 0) + oblig_vacios
    salida["extras"] = salida.get("extras", 0) + extras
    salida["cuarentena"] = salida.get("cuarentena", 0) + cuarentena
    salida["montos_no_numericos"] = salida.get("montos_no_numericos", 0) + monto_no_num
    salida["montos_negativos"] = salida.get("montos_negativos", 0) + monto_neg


def build_cartel_pub(out_dir: Path, year: int) -> dict:
    """Mapa NRO_SICOP -> mes real de publicacion (YYYYMM), desde FECHA_PUBLICACION
    del cartel acumulado del anio (corrida previa). Sella MES_PUBLICACION real en
    vez del mes del primer zip. Complementa por mes al procesar DetalleCarteles."""
    pub = {}
    p = out_dir / f"carteles_{year}.csv"
    if not p.exists():
        return pub
    with open(p, encoding="utf-8-sig", newline="") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            nro = (r.get("NRO_SICOP") or "").strip()
            fec = (r.get("FECHA_PUBLICACION") or "").strip()
            if nro and len(fec) >= 7:
                m = fec[:7].replace("-", "")
                if m.isdigit() and len(m) == 6:
                    pub.setdefault(nro, m)
    log(f"cartel_pub: {len(pub)} procedimientos con mes real de publicacion")
    return pub


def _drop_months(path: Path, cols: list, col: str, meses: set) -> int:
    """Reescribe `path` quitando las filas cuyo valor de `col` esté en `meses`.

    Atómico (tmp + os.replace), preserva cabecera y orden. Devuelve cuántas
    filas quitó. Lo usa --replace para reconstruir un año reemplazando SOLO los
    meses reescritos por la fuente, sin reprocesar los otros 11.
    """
    if not path.exists():
        return 0
    tmp = path.with_suffix(path.suffix + ".tmp")
    n = 0
    with open(path, encoding="utf-8-sig", newline="") as fin, \
            open(tmp, "w", encoding="utf-8-sig", newline="") as fout:
        rdr = csv.DictReader(fin)
        wtr = csv.DictWriter(fout, fieldnames=cols, lineterminator="\n",
                             extrasaction="ignore")
        wtr.writeheader()
        for r in rdr:
            if (r.get(col) or "").strip() in meses:
                n += 1
                continue
            wtr.writerow({c: r.get(c, "") for c in cols})
    os.replace(tmp, path)
    return n


def procesar_mes(mes: str, zip_path: Path, confs: dict, writers: dict,
                 vistos: dict, qwriters: dict = None, cartel_pub=None) -> dict:
    """Procesa un zip mensual. Devuelve el dict que se registra en el manifiesto."""
    m = {"estado": "ERROR", "archivo": f"{mes}.zip", "sha256": None,
         "tamano_bytes": zip_path.stat().st_size if zip_path.exists() else 0,
         "conjuntos": {}, "hallazgos": []}
    if m["tamano_bytes"] < MIN_ZIP_BYTES:
        m["hallazgos"].append({"nivel": "ERROR", "tipo": "zip_demasiado_pequeno",
                               "n": 1, "detalle": f"tamaño {m['tamano_bytes']}"})
        return m
    try:
        m["sha256"] = sha256_file(zip_path)
    except OSError as e:
        m["hallazgos"].append({"nivel": "ERROR", "tipo": "no_legible",
                               "n": 1, "detalle": str(e)})
        return m
    try:
        zf = zipfile.ZipFile(zip_path)
        # inventario COMPLETO del zip (nunca truncado) — lo consume A2 para la
        # regresión de inventario: si aparece o desaparece un archivo, bloquea.
        # El error de "17 archivos" ocurrió justamente por un listado truncado.
        registrar_inventario(zip_path.parent.parent, mes, sorted(zf.namelist()))
        zf.close()
    except zipfile.BadZipFile as e:
        m["hallazgos"].append({"nivel": "ERROR", "tipo": "zip_corrupto",
                               "n": 1, "detalle": str(e)})
        return m

    for nombre, conf in confs.items():
        salida = {"filas": 0, "duplicados": 0, "obligatorios_vacios": 0,
                  "extras": 0, "cuarentena": 0, "columnas_ausentes": []}
        raw, miembro = leer_miembro(zip_path, conf["archivo"])
        if raw is None:
            salida["columnas_ausentes"] = ["<miembro ausente del zip>"]
            m["conjuntos"][nombre] = salida
            continue
        try:
            procesar_conjunto(conf, nombre, raw, mes, writers[nombre], vistos[nombre],
                              salida, (qwriters or {}).get(nombre), cartel_pub)
        except Exception as e:  # noqa: BLE001
            salida["filas"] = -1
            m["hallazgos"].append({"nivel": "ERROR", "tipo": "error_lectura",
                                   "n": 1, "detalle": f"{nombre}: {e}"})
        m["conjuntos"][nombre] = salida

    # trampa: enero sin adjudicaciones (y afines) pero con movimiento en firme/contratos
    vacios = [c for c in ("adjudicaciones", "lineas_adjudicadas", "lineas_ofertadas")
              if c in confs and m["conjuntos"][c]["filas"] == 0]
    con_datos = [c for c in ("adjudicaciones_firme", "contratos")
                 if c in confs and m["conjuntos"][c]["filas"] > 0]
    if vacios and con_datos:
        m["hallazgos"].append({
            "nivel": "INFO", "tipo": "mes_sin_filas_en_origen",
            "n": 1,
            "detalle": (f"{', '.join(vacios)} vacíos en el archivo de origen, pero "
                        f"{', '.join(con_datos)} sí traen movimiento — no concluir "
                        "ausencia de actividad")})
    # si algún conjunto falló, el mes no queda OK (se reintentará)
    if any(h["nivel"] == "ERROR" for h in m["hallazgos"]):
        m["estado"] = "ERROR"
    else:
        m["estado"] = "OK"
    return m


# ---------------------------------------------------------------------------
# Cruce de competencia (una vez, sobre el acumulado)
# ---------------------------------------------------------------------------

def cruce_competencia(out_dir: Path, year: int, confs: dict) -> dict:
    """Une Ofertas x LineasOfertadas por (NRO_SICOP, NRO_OFERTA) y marca quién
    resultó adjudicatario. Devuelve métricas para el manifiesto/reporte."""
    if "ofertas" not in confs or "lineas_ofertadas" not in confs:
        return {}
    log("Cruce de competencia sobre el acumulado…")
    f_ofertas = out_dir / f"ofertas_{year}.csv"
    f_lineas = out_dir / f"lineas_ofertadas_{year}.csv"
    f_adj = out_dir / f"adjudicaciones_{year}.csv"
    f_salida = out_dir / "competencia_por_linea.csv"

    ofertas = {}
    with open(f_ofertas, "r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            k = (r.get("NRO_SICOP", ""), r.get("NRO_OFERTA", ""))
            ofertas[k] = r
    adjudicados = set()
    ganadas_linea = set()
    if f_adj.exists():
        with open(f_adj, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                adjudicados.add((r.get("NRO_SICOP", ""), r.get("LINEA", ""),
                                 r.get("CEDULA_PROVEEDOR", "")))
                ganadas_linea.add((r.get("NRO_SICOP", ""), r.get("LINEA", "")))
    # catálogo de nombres: Proveedores.csv primero, adjudicaciones como respaldo
    nombres = {}
    f_prov = out_dir / f"proveedores_{year}.csv"
    if f_prov.exists():
        with open(f_prov, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                c = (r.get("CEDULA_PROVEEDOR") or "").strip()
                n = (r.get("NOMBRE_PROVEEDOR") or "").strip()
                if c and n and c not in nombres:
                    nombres[c] = n
    if f_adj.exists():
        with open(f_adj, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                c = (r.get("CEDULA_PROVEEDOR") or "").strip()
                n = (r.get("NOMBRE_PROVEEDOR") or "").strip()
                if c and n and c not in nombres:
                    nombres[c] = n

    cols = ["NRO_SICOP", "NRO_OFERTA", "NRO_LINEA", "CODIGO_PRODUCTO",
            "CODIGO_PRODUCTO_CL", "CL_ORIGEN", "CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR",
            "FECHA_PRESENTA_OFERTA", "TIPO_OFERTA", "ID_CONSORCIO",
            "CANTIDAD_OFERTADA", "PRECIO_UNITARIO_OFERTADO", "TIPO_MONEDA",
            "TIPO_CAMBIO_CRC", "PRECIO_UNITARIO_CRC", "PRECIO_SOSPECHOSO",
            "ES_ADJUDICATARIO", "MES_PUBLICACION"]
    lineas_total = set()
    lineas_cruzadas = set()
    sin_oferta = 0
    sin_conversion = 0
    n = 0
    n_adj = 0
    n_sosp = 0
    tmp = f_salida.with_suffix(".csv.tmp")
    with open(f_lineas, "r", encoding="utf-8-sig", newline="") as f, \
         open(tmp, "w", encoding="utf-8-sig", newline="") as g:
        w = csv.DictWriter(g, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in csv.DictReader(f):
            linea = (r.get("NRO_SICOP", ""), r.get("NRO_LINEA", ""))
            lineas_total.add(linea)
            k = (r.get("NRO_SICOP", ""), r.get("NRO_OFERTA", ""))
            of = ofertas.get(k)
            if of is None:
                sin_oferta += 1
                continue
            lineas_cruzadas.add(linea)
            precio = parse_number(r.get("PRECIO_UNITARIO_OFERTADO"))
            mon = (r.get("TIPO_MONEDA") or "").strip() or "CRC"
            tc = parse_number(r.get("TIPO_CAMBIO_CRC"))
            precio_crc = ""
            pval = None
            if precio is not None:
                if mon == "CRC":
                    precio_crc = f"{precio:.6f}"
                    pval = precio
                elif tc:
                    pval = precio * tc
                    precio_crc = f"{pval:.6f}"
                else:
                    sin_conversion += 1
            # precio simbólico o por definir: >0 y ≤ 1 colón → S
            sosp = "S" if (pval is not None and 0 < pval <= 1.0) else ""
            if sosp == "S":
                n_sosp += 1
            # convención S/N/"" : S si este oferente ganó la línea, N si la ganó
            # otro (la línea está adjudicada), "" si no hay adjudicación registrada
            prov_ced = of.get("CEDULA_PROVEEDOR", "")
            if (r.get("NRO_SICOP", ""), r.get("NRO_LINEA", ""), prov_ced) in adjudicados:
                es_adj = "S"
            elif (r.get("NRO_SICOP", ""), r.get("NRO_LINEA", "")) in ganadas_linea:
                es_adj = "N"
            else:
                es_adj = ""
            if es_adj == "S":
                n_adj += 1
            # ── imputación CL (2026-08-25) ────────────────────────────────
            # El campo CODIGO_PRODUCTO_CL viene vacío en el 65,7% de 2023 y en
            # tramos de 2020-21: es hueco DE CAMPO, no de dato. Verificado
            # sobre 106.585 filas: 100,00% derivable como CODIGO_PRODUCTO[:16]
            # (anidamiento confirmado al 96,9% donde ambos existen).
            # Se imputa y se marca la procedencia — nunca se pisa el original.
            _cl_raw = (r.get("CODIGO_PRODUCTO_CL") or "").strip()
            _cod24 = (r.get("CODIGO_PRODUCTO") or "").strip()
            if _cl_raw:
                _cl, _cl_org = _cl_raw, "FUENTE"
            elif len(_cod24) >= 16:
                _cl, _cl_org = _cod24[:16], "DERIVADO"
            else:
                _cl, _cl_org = "", "AUSENTE"
            w.writerow({
                "NRO_SICOP": r.get("NRO_SICOP", ""), "NRO_OFERTA": r.get("NRO_OFERTA", ""),
                "NRO_LINEA": r.get("NRO_LINEA", ""), "CODIGO_PRODUCTO": _cod24,
                "CODIGO_PRODUCTO_CL": _cl, "CL_ORIGEN": _cl_org,
                "CEDULA_PROVEEDOR": prov_ced,
                "NOMBRE_PROVEEDOR": nombres.get(prov_ced, ""),
                "FECHA_PRESENTA_OFERTA": of.get("FECHA_PRESENTA_OFERTA", ""),
                "TIPO_OFERTA": of.get("TIPO_OFERTA", ""), "ID_CONSORCIO": of.get("ID_CONSORCIO", ""),
                "CANTIDAD_OFERTADA": r.get("CANTIDAD_OFERTADA", ""),
                "PRECIO_UNITARIO_OFERTADO": r.get("PRECIO_UNITARIO_OFERTADO", ""),
                "TIPO_MONEDA": mon, "TIPO_CAMBIO_CRC": r.get("TIPO_CAMBIO_CRC", ""),
                "PRECIO_UNITARIO_CRC": precio_crc, "PRECIO_SOSPECHOSO": sosp,
                "ES_ADJUDICATARIO": es_adj,
                "MES_PUBLICACION": r.get("MES_PUBLICACION", ""),
            })
            n += 1
    tmp.replace(f_salida)
    cobertura = n / (n + sin_oferta) if (n + sin_oferta) else 0.0
    res = {
        "filas_lineas_ofertadas": n + sin_oferta,
        "lineas_ofertadas_distintas": len(lineas_total),
        "filas_competencia": n,
        "lineas_con_oferente": len(lineas_cruzadas),
        "cobertura": round(cobertura, 4),
        "lineas_sin_oferente": len(lineas_total) - len(lineas_cruzadas),
        "filas_sin_oferta_en_ofertas": sin_oferta,
        "filas_sin_conversion_crc": sin_conversion,
        "filas_adjudicatario": n_adj,
        "precios_sospechosos": n_sosp,
    }
    log(f"Cruce: {n:,} filas · {len(lineas_cruzadas):,} líneas con oferente "
        f"({cobertura * 100:.1f}% de cobertura sobre filas) · {n_adj:,} adjudicatarias · "
        f"{n_sosp} precios sospechosos")
    return res


# ---------------------------------------------------------------------------
# Tablas derivadas (una vez, sobre el acumulado)
# ---------------------------------------------------------------------------

def _leer(out_dir: Path, nombre: str, year: int):
    path = out_dir / f"{nombre}_{year}.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _dias(a: str, b: str):
    """Días entre dos fechas ISO (parte de fecha). '' si falta alguna."""
    def f(s):
        s = (s or "").strip()
        if len(s) >= 10:
            try:
                return datetime.strptime(s[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
        return None
    da, db = f(a), f(b)
    if da is None or db is None:
        return ""
    return (db - da).days


def derivadas(out_dir: Path, year: int, confs: dict) -> dict:
    """Produce las tablas derivadas sobre el acumulado y devuelve métricas
    para el manifiesto y el REPORTE."""
    log("Tablas derivadas sobre el acumulado…")
    res = {}

    # ---------------------------------------------------------------- traza
    tramos = {
        "cartel": "carteles", "ofertas": "ofertas",
        "acto_firme": "adjudicaciones_firme", "adjudicado": "adjudicaciones",
        "contrato": "contratos", "garantia": "garantias",
        "recibido": "lineas_recibidas",
    }
    procs = {}
    info = {}
    for tramo, conjunto in tramos.items():
        for r in _leer(out_dir, conjunto, year):
            p = (r.get("NRO_SICOP") or "").strip()
            if not p:
                continue
            procs.setdefault(p, set()).add(tramo)
            if p not in info:
                info[p] = {"num": (r.get("NUMERO_PROCEDIMIENTO")
                                   or r.get("NRO_PROCEDIMIENTO") or "").strip(),
                           "ced": (r.get("CEDULA_INSTITUCION")
                                   or r.get("CEDULA") or "").strip()}
    # etapas: procedimientos que sólo tienen línea de tiempo (15 en 2026)
    for r in _leer(out_dir, "etapas", year):
        p = (r.get("NRO_SICOP") or "").strip()
        if p:
            procs.setdefault(p, set())
            if p not in info:
                info[p] = {"num": (r.get("NUMERO_PROCEDIMIENTO") or "").strip(),
                           "ced": ""}
    cols_t = ["NRO_SICOP", "NUMERO_PROCEDIMIENTO", "CEDULA_INSTITUCION",
              "T_CARTEL", "T_OFERTAS", "T_ACTO_FIRME", "T_ADJUDICADO",
              "T_CONTRATO", "T_GARANTIA", "T_RECIBIDO", "NUM_TRAMOS"]
    with open(out_dir / "expediente_trazabilidad.csv", "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols_t, lineterminator="\n")
        w.writeheader()
        for p in sorted(procs):
            s = procs[p]
            w.writerow({"NRO_SICOP": p, "NUMERO_PROCEDIMIENTO": info[p]["num"],
                        "CEDULA_INSTITUCION": info[p]["ced"],
                        "T_CARTEL": "S" if "cartel" in s else "",
                        "T_OFERTAS": "S" if "ofertas" in s else "",
                        "T_ACTO_FIRME": "S" if "acto_firme" in s else "",
                        "T_ADJUDICADO": "S" if "adjudicado" in s else "",
                        "T_CONTRATO": "S" if "contrato" in s else "",
                        "T_GARANTIA": "S" if "garantia" in s else "",
                        "T_RECIBIDO": "S" if "recibido" in s else "",
                        "NUM_TRAMOS": len(s)})
    res["trazabilidad"] = {
        "total_procedimientos": len(procs),
        "con_5_mas_tramos": sum(1 for s in procs.values() if len(s) >= 5),
        "por_tramo": {t: sum(1 for s in procs.values() if t in s) for t in tramos},
    }
    log(f"Trazabilidad: {len(procs):,} procedimientos · "
        f"{res['trazabilidad']['con_5_mas_tramos']:,} con ≥5 tramos")

    # -------------------------------------------------------- carteles objetados
    inst_nombres = {}
    for r in _leer(out_dir, "instituciones", year):
        c = (r.get("CEDULA") or "").strip()
        if c and c not in inst_nombres:
            inst_nombres[c] = (r.get("NOMBRE_INSTITUCION") or "").strip()
    adj_set = {r["NRO_SICOP"] for r in _leer(out_dir, "adjudicaciones", year)}
    firme_set = {r["NRO_SICOP"] for r in _leer(out_dir, "adjudicaciones_firme", year)}
    fechas_firme = {}
    for r in _leer(out_dir, "adjudicaciones_firme", year):
        p = r["NRO_SICOP"]
        fa = (r.get("FECHA_ADJ_FIRME") or "").strip()
        if fa and p not in fechas_firme:
            fechas_firme[p] = fa
    objetados = [r for r in _leer(out_dir, "carteles", year)
                 if (r.get("CARTEL_STAT") or "").strip() == "Objetado"]
    monto_obj = 0.0
    for r in objetados:
        monto_obj += parse_number(r.get("MONTO_EST")) or 0.0
    cols_o = ["NRO_SICOP", "NUMERO_PROCEDIMIENTO", "CEDULA_INSTITUCION",
              "NOMBRE_INSTITUCION", "TIPO_PROCEDIMIENTO", "MODALIDAD_PROCEDIMIENTO",
              "MONTO_EST", "FECHA_PUBLICACION", "FECHAH_APERTURA",
              "SE_ADJUDICO", "FECHA_ADJUDICACION", "MES_PUBLICACION"]
    with open(out_dir / "carteles_objetados.csv", "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols_o, lineterminator="\n")
        w.writeheader()
        for r in sorted(objetados, key=lambda x: -(parse_number(x.get("MONTO_EST")) or 0.0)):
            p = r["NRO_SICOP"]
            w.writerow({"NRO_SICOP": p,
                        "NUMERO_PROCEDIMIENTO": r.get("NRO_PROCEDIMIENTO", ""),
                        "CEDULA_INSTITUCION": r.get("CEDULA_INSTITUCION", ""),
                        "NOMBRE_INSTITUCION": inst_nombres.get(
                            r.get("CEDULA_INSTITUCION", ""), ""),
                        "TIPO_PROCEDIMIENTO": r.get("TIPO_PROCEDIMIENTO", ""),
                        "MODALIDAD_PROCEDIMIENTO": r.get("MODALIDAD_PROCEDIMIENTO", ""),
                        "MONTO_EST": r.get("MONTO_EST", ""),
                        "FECHA_PUBLICACION": r.get("FECHA_PUBLICACION", ""),
                        "FECHAH_APERTURA": r.get("FECHAH_APERTURA", ""),
                        "SE_ADJUDICO": "S" if (p in adj_set or p in firme_set) else "",
                        "FECHA_ADJUDICACION": fechas_firme.get(p, ""),
                        "MES_PUBLICACION": r.get("MES_PUBLICACION", "")})
    res["carteles_objetados"] = {"n": len(objetados),
                                 "monto_est_crc": round(monto_obj, 2)}
    log(f"Carteles objetados: {len(objetados)} · ₡{fmt_colon(monto_obj)}")

    # ------------------------------------------------- excepciones por adjudicatario
    cart_causal = {}
    for r in _leer(out_dir, "carteles", year):
        des = (r.get("DES_EXCEPCION") or "").strip()
        if des:
            cart_causal[r["NRO_SICOP"]] = ((r.get("COD_EXCEPCION") or "").strip(), des)
    pares = {}
    for r in _leer(out_dir, "adjudicaciones", year):
        c = cart_causal.get(r["NRO_SICOP"])
        if not c:
            continue
        prov = (r.get("CEDULA_PROVEEDOR") or "").strip()
        key = (prov, c[1])
        d = pares.setdefault(key, {"monto": 0.0, "lineas": 0, "procs": set(),
                                   "insts": set(), "nombre": "",
                                   "cod": c[0], "meses": set()})
        d["monto"] += parse_number(r.get("MONTO_ADJU_LINEA_CRC")) or 0.0
        d["lineas"] += 1
        d["procs"].add(r["NRO_SICOP"])
        d["insts"].add(r.get("CEDULA") or "")
        d["meses"].add(r.get("MES_PUBLICACION") or "")
        if not d["nombre"]:
            d["nombre"] = (r.get("NOMBRE_PROVEEDOR") or "").strip()
    cols_e = ["CEDULA_PROVEEDOR", "NOMBRE_PROVEEDOR", "CAUSAL_EXCEPCION",
              "COD_EXCEPCION", "PROCEDIMIENTOS", "LINEAS_ADJUDICADAS",
              "INSTITUCIONES", "MONTO_CRC", "MESES"]
    with open(out_dir / "excepciones_por_adjudicatario.csv", "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols_e, lineterminator="\n")
        w.writeheader()
        for (prov, causal), d in sorted(pares.items(),
                                        key=lambda kv: -kv[1]["monto"]):
            w.writerow({"CEDULA_PROVEEDOR": prov, "NOMBRE_PROVEEDOR": d["nombre"],
                        "CAUSAL_EXCEPCION": causal, "COD_EXCEPCION": d["cod"],
                        "PROCEDIMIENTOS": len(d["procs"]),
                        "LINEAS_ADJUDICADAS": d["lineas"],
                        "INSTITUCIONES": len(d["insts"]),
                        "MONTO_CRC": f"{d['monto']:.2f}",
                        "MESES": ",".join(sorted(d["meses"]))})
    por_causal = {}
    for (prov, causal), d in pares.items():
        pc = por_causal.setdefault(causal, {"monto": 0.0, "provs": set()})
        pc["monto"] += d["monto"]
        pc["provs"].add(prov)
    res["excepciones"] = {
        "procedimientos_con_causal": len(cart_causal),
        "pares": len(pares),
        "por_causal": {c: {"monto": round(pc["monto"], 2), "proveedores": len(pc["provs"])}
                       for c, pc in sorted(por_causal.items(),
                                           key=lambda kv: -kv[1]["monto"])},
    }
    log(f"Excepciones: {len(cart_causal):,} procedimientos con causal · "
        f"{len(pares)} pares proveedor×causal")

    # ------------------------------------------------------------ sanciones
    adm = _leer(out_dir, "procedimientos_adm", year)
    by_proc = {}
    for r in adm:
        by_proc.setdefault(r["NRO_SICOP"], []).append(r)
    cols_s = ["NRO_SICOP", "NUMERO_PROCEDIMIENTO", "CEDULA_INSTITUCION",
              "NOMBRE_INSTITUCION", "CEDULAS_PROVEEDOR", "NOMBRES_PROVEEDOR",
              "FECHA_NOTIFICACION", "INHAB_APERC", "MULTA_CAUSULA",
              "N_NOTIFICACIONES"]
    provs_sanc = set()
    with open(out_dir / "sanciones_proveedores.csv", "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols_s, lineterminator="\n")
        w.writeheader()
        for p in sorted(by_proc):
            rows = by_proc[p]
            ceds = sorted({r.get("CEDULA_PROVEEDOR", "") for r in rows})
            provs_sanc.update(ceds)
            nombres = "; ".join(sorted({r.get("NOMBRE_PROVEEDOR", "") for r in rows}))
            w.writerow({"NRO_SICOP": p,
                        "NUMERO_PROCEDIMIENTO": rows[0].get("NUMERO_PROCEDIMIENTO", ""),
                        "CEDULA_INSTITUCION": rows[0].get("CEDULA_INSTITUCION", ""),
                        "NOMBRE_INSTITUCION": rows[0].get("NOMBRE_INSTITUCION", ""),
                        "CEDULAS_PROVEEDOR": ";".join(ceds),
                        "NOMBRES_PROVEEDOR": nombres,
                        "FECHA_NOTIFICACION": min(r.get("FECHA_NOTIFICACION", "")
                                                  for r in rows),
                        "INHAB_APERC": rows[0].get("INHAB_APERC", ""),
                        "MULTA_CAUSULA": rows[0].get("MULTA_CAUSULA", ""),
                        "N_NOTIFICACIONES": len(rows)})
    res["sanciones"] = {
        "n": len(by_proc),
        "cedulas_proveedor": len(provs_sanc),
        "empresas": len({c for c in provs_sanc if c.startswith("3")}),
    }
    log(f"Sanciones: {len(by_proc)} procedimientos administrativos · "
        f"{len(provs_sanc)} cédulas de proveedor")

    # ------------------------------------------------------ tiempos por etapa
    etapas_first = {}
    for r in _leer(out_dir, "etapas", year):
        p = r["NRO_SICOP"]
        if p not in etapas_first:
            etapas_first[p] = r
    recep = {}
    for r in _leer(out_dir, "lineas_recibidas", year):
        p = r["NRO_SICOP"]
        fr = (r.get("fecha_recepcion_Definitiva") or "").strip()
        if fr and (p not in recep or fr < recep[p]):
            recep[p] = fr
    ced_cartel = {}
    for r in _leer(out_dir, "carteles", year):
        p = r["NRO_SICOP"]
        if p not in ced_cartel:
            ced_cartel[p] = (r.get("CEDULA_INSTITUCION") or "").strip()
    cols_tp = ["NRO_SICOP", "CEDULA_INSTITUCION", "FECHA_PUBLICACION",
               "FECHA_APERTURA", "FECHA_ADJUDICACION_FIRME", "FECHA_CONTRATO",
               "FECHA_RECEPCION", "DIAS_PUBLICACION_APERTURA",
               "DIAS_APERTURA_ADJUDICACION", "DIAS_ADJUDICACION_CONTRATO",
               "DIAS_CONTRATO_RECEPCION"]
    with open(out_dir / "tiempos_por_etapa.csv", "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols_tp, lineterminator="\n")
        w.writeheader()
        for p, r in sorted(etapas_first.items()):
            pub = r.get("PUBLICACION", "")
            aper = r.get("FECHA_APERTURA", "")
            adj = r.get("ADJUDICACION_FIRME", "")
            con = r.get("FECHA_ELABORACION_CONTRATO", "")
            rec = recep.get(p, "")
            w.writerow({"NRO_SICOP": p, "CEDULA_INSTITUCION": ced_cartel.get(p, ""),
                        "FECHA_PUBLICACION": pub, "FECHA_APERTURA": aper,
                        "FECHA_ADJUDICACION_FIRME": adj, "FECHA_CONTRATO": con,
                        "FECHA_RECEPCION": rec,
                        "DIAS_PUBLICACION_APERTURA": _dias(pub, aper),
                        "DIAS_APERTURA_ADJUDICACION": _dias(aper, adj),
                        "DIAS_ADJUDICACION_CONTRATO": _dias(adj, con),
                        "DIAS_CONTRATO_RECEPCION": _dias(con, rec)})
    res["tiempos_por_etapa"] = {"procedimientos": len(etapas_first)}
    log(f"Tiempos por etapa: {len(etapas_first):,} procedimientos")

    # ------------------------------------------------- recursos de objeción
    # Descubrimiento del 2026-08-23: RecursosObjecion.csv SÍ está en los zips y
    # trae RESULTADO/CAUSA_RESULTADO — la skill decía que no estaba en la fuente.
    recursos = _leer(out_dir, "recursos", year)
    if recursos and "recursos" in confs:
        cart_cab = {r["NRO_SICOP"]: r for r in _leer(out_dir, "carteles", year)}
        prov_cat = {}
        for r in _leer(out_dir, "proveedores", year):
            c = (r.get("CEDULA_PROVEEDOR") or "").strip()
            if c and c not in prov_cat:
                prov_cat[c] = r
        rec_rows = []
        for r in recursos:
            ced = r.get("CEDULA_PROVEEDOR", "")
            c = cart_cab.get(r["NRO_SICOP"], {})
            ci = c.get("CEDULA_INSTITUCION", "")
            p = prov_cat.get(ced, {})
            resu = (r.get("RESULTADO") or "").strip().lower()
            if not resu:
                prospero = ""    # sin desenlace registrado: no aplica (convención S/N/"")
            elif "con lugar" in resu and "sin lugar" not in resu:
                prospero = "S"
            else:
                prospero = "N"   # resuelto y no prosperó (sin lugar, rechaza de plano, etc.)
            rec_rows.append({
                "NRO_RECURSO": r.get("NRO_RECURSO", ""),
                "NRO_SICOP": r.get("NRO_SICOP", ""),
                "NRO_PROCEDIMIENTO": (r.get("nro_procedimiento")
                                      or c.get("NRO_PROCEDIMIENTO", "")),
                "LINEA_OBJETADA": r.get("LINEA_OBJETADA", ""),
                "TIPO_RECURSO": r.get("TIPO_RECURSO", ""),
                "RESULTADO": r.get("RESULTADO", ""),
                "CAUSA_RESULTADO": r.get("CAUSA_RESULTADO", ""),
                "ESTADO": r.get("recurso_stat", ""),
                "FECHA_PRESENTACION": r.get("FECHA_PRESENTACION_RECURSO", ""),
                "CEDULA_RECURRENTE": ced,
                "NOMBRE_RECURRENTE": (p.get("NOMBRE_PROVEEDOR", "")
                                      or r.get("reqer_nm", "")),
                "TAMANO_RECURRENTE": p.get("TAMAÑO_PROVEEDOR", ""),
                "CEDULA_INSTITUCION": ci,
                "INSTITUCION": inst_nombres.get(ci, ""),
                "TIPO_PROCEDIMIENTO": c.get("TIPO_PROCEDIMIENTO", ""),
                "PROSPERO": prospero,
                "MES_PUBLICACION": r.get("MES_PUBLICACION", ""),
            })
        cols_r = ["NRO_RECURSO", "NRO_SICOP", "NRO_PROCEDIMIENTO",
                  "LINEA_OBJETADA", "TIPO_RECURSO", "RESULTADO",
                  "CAUSA_RESULTADO", "ESTADO", "FECHA_PRESENTACION",
                  "CEDULA_RECURRENTE", "NOMBRE_RECURRENTE", "TAMANO_RECURRENTE",
                  "CEDULA_INSTITUCION", "INSTITUCION", "TIPO_PROCEDIMIENTO",
                  "PROSPERO", "MES_PUBLICACION"]
        with open(out_dir / "recursos_desenlace.csv", "w",
                  encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols_r, lineterminator="\n")
            w.writeheader()
            for row in rec_rows:
                w.writerow({c: row.get(c, "") for c in cols_r})
        from collections import Counter as _C
        prosperaron = sum(1 for x in rec_rows if x["PROSPERO"] == "S")
        con_resultado = sum(1 for x in rec_rows
                            if (x.get("RESULTADO") or "").strip())
        res["recursos"] = {
            "recursos": len(rec_rows),
            "procedimientos_recurridos": len({x["NRO_SICOP"] for x in rec_rows}),
            "recurrentes_distintos": len({x["CEDULA_RECURRENTE"] for x in rec_rows
                                          if x["CEDULA_RECURRENTE"]}),
            "prosperaron": prosperaron,
            "resultado_vacio": len(rec_rows) - con_resultado,
            "tasa_exito_pct": round(prosperaron * 100 / len(rec_rows), 1)
                              if rec_rows else 0,      # sobre todos
            "tasa_exito_desenlace_pct": round(prosperaron * 100 / con_resultado, 1)
                                        if con_resultado else 0,  # sobre con resultado
            "por_tipo": dict(_C(x["TIPO_RECURSO"] or "(vacío)"
                                for x in rec_rows).most_common(10)),
            "por_resultado": dict(_C(x["RESULTADO"] or "(vacío)"
                                     for x in rec_rows).most_common(10)),
            "por_causa": dict(_C(x["CAUSA_RESULTADO"] or "(vacío)"
                                 for x in rec_rows).most_common(10)),
        }
        log(f"Recursos de objeción: {len(rec_rows):,} · "
            f"{prosperaron} prosperaron "
            f"({res['recursos']['tasa_exito_pct']}% sobre todos, "
            f"{res['recursos']['tasa_exito_desenlace_pct']}% con resultado)")

    # ── catálogo de productos — el universo completo, transversal a los años ──
    # Marca/modelo viven en las tablas de EJECUCIÓN (skill §8):
    #   lineas_contratadas.DESC_PRODUCTO · lineas_recibidas.desc_producto
    #   con el patrón «Marca X Modelo Y». CODIGO_PRODUCTO (24) = UNSPSC(8) +
    #   ID_CATALOGO(8) + correlativo(8); CODIGO_PRODUCTO_CL (16) = UNSPSC+ID.
    # La atribución (quién lo provee, quién lo compra) sale de adjudicaciones
    # por PROD_ID (16). La Fecha de Registro del catálogo NO está en los zips:
    # vive en el catálogo web (gateado, ver skill §1/§8).
    import glob as _glob
    from collections import Counter as _Cnt, defaultdict as _dd

    # Regex case-sensitive a propósito (v. Claude 2026-08-24): en las tablas de
    # ejecución el patrón viene capitalizado («Marca X Modelo Y»); con re.I,
    # «BOTA SIN MARCA NI MODELO DECLARADO» se parsea como Marca=NI. Verificado
    # sobre 2.059 líneas reales de 461816: misma cobertura (99,6%) sin el ruido.
    RX_MARCA = re.compile(r"\bMarca\s+(.+?)\s+Modelo\s+(.*)$")

    # Lista de descarte explícita y versionada (v1, 2026-08-24, por revisión de
    # Claude): tokens que el patrón captura pero NO son marca — tipo de bien,
    # atributo de origen, norma técnica, fórmulas de pliego. Con esto
    # MARCA_PLAUSIBLE separa «el patrón matcheó» de «el resultado es marca».
    DESCARTE_MARCAS = {
        "LIBRO", "NACIONAL", "SEGÚN OFERTA", "SEGUN OFERTA", "INTECO",
        "SIN REGISTRO", "NINGUNA", "VARIOS", "GENERICO", "TOTAL", "NO APLICA",
        "NA", "SN", "N/A", "-", "—", ".", "*", "SEGUN MUESTRA", "SEGÚN MUESTRA",
        "A DEFINIR", "POR DEFINIR", "NO INDICA", "NO DECLARADO",
    }

    def _plausible(t):
        t = (t or "").strip()
        if not t or len(t) < 3 or t.isdigit():
            return False
        if t.upper() in DESCARTE_MARCAS:
            return False
        return True

    prod = {}  # cl -> {lineas, procs:set, patron:int, marcas:Counter, desc:Counter}
    for nombre, campo in (("lineas_contratadas", "DESC_PRODUCTO"),
                          ("lineas_recibidas", "desc_producto")):
        for p in sorted(_glob.glob(str(out_dir / f"{nombre}_20*.csv"))):
            with open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    cod = (r.get("CODIGO_PRODUCTO") or "").strip()
                    if len(cod) < 16:
                        continue
                    cl = cod[:16]
                    desc = (r.get(campo) or "").strip()
                    if not desc:
                        continue
                    d = prod.setdefault(cl, {"lineas": 0, "procs": set(),
                                             "patron": 0, "marcas": _Cnt(),
                                             "desc": _Cnt()})
                    d["lineas"] += 1
                    d["procs"].add((r.get("NRO_SICOP") or "").strip())
                    if desc:
                        d["desc"][desc] += 1
                    m = RX_MARCA.search(desc)
                    if m:
                        d["patron"] += 1
                        ma, mo = m.group(1).strip(), m.group(2).strip()
                        if _plausible(ma):
                            d["marcas"][(ma.upper(), mo.upper())] += 1

    # catálogo de proveedores para el nombre (todos los años)
    prov_nom = {}
    for p in sorted(_glob.glob(str(out_dir / "proveedores_20*.csv"))):
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                ced = (r.get("CEDULA_PROVEEDOR") or "").strip()
                if ced:
                    prov_nom.setdefault(ced, (r.get("NOMBRE_PROVEEDOR") or ced).strip())

    adj_prod = {}  # prod_id -> {prov:Counter, inst:set, anios:set}
    for p in sorted(_glob.glob(str(out_dir / "adjudicaciones_20*.csv"))):
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                pid = (r.get("PROD_ID") or "").strip()
                if len(pid) != 16:
                    continue
                d = adj_prod.setdefault(pid, {"prov": _Cnt(), "inst": set(),
                                              "anios": set()})
                ced = (r.get("CEDULA_PROVEEDOR") or "").strip()
                if ced:
                    d["prov"][ced] += 1
                if r.get("INSTITUCION"):
                    d["inst"].add(r.get("INSTITUCION"))
                d["anios"].add((r.get("MES_PUBLICACION") or "")[:4])

    cols_p = ["CODIGO_PRODUCTO_CL", "FAMILIA_UNSPSC", "DESCRIPCION", "MARCA",
              "MODELO", "PATRON_MATCH", "MARCA_PLAUSIBLE", "LINEAS_EJECUCION",
              "PROCEDIMIENTOS", "PROVEEDORES_ADJUDICADOS", "PROVEEDOR_TOP",
              "INSTITUCIONES", "ANIOS_ADJUDICACION"]
    patron_n = plausible_n = 0
    with open(out_dir / "catalogo_productos.csv", "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols_p, lineterminator="\n")
        w.writeheader()
        for cl in sorted(prod):
            d = prod[cl]
            (ma, mo), n_mar = d["marcas"].most_common(1)[0] if d["marcas"] else (("", ""), 0)
            ad = adj_prod.get(cl, {})
            prov_top = ad["prov"].most_common(1)[0] if ad.get("prov") else (None, 0)
            w.writerow({
                "CODIGO_PRODUCTO_CL": cl,
                "FAMILIA_UNSPSC": cl[:8],
                "DESCRIPCION": d["desc"].most_common(1)[0][0][:160] if d["desc"] else "",
                "MARCA": ma, "MODELO": mo,
                "PATRON_MATCH": "S" if d["patron"] else "N",
                "MARCA_PLAUSIBLE": "S" if ma else "N",
                "LINEAS_EJECUCION": d["lineas"],
                "PROCEDIMIENTOS": len(d["procs"]),
                "PROVEEDORES_ADJUDICADOS": len(ad.get("prov", {})),
                "PROVEEDOR_TOP": prov_nom.get(prov_top[0], prov_top[0] or "")
                                 if prov_top[0] else "",
                "INSTITUCIONES": len(ad.get("inst", set())),
                "ANIOS_ADJUDICACION": ",".join(sorted(ad.get("anios", set()))),
            })
            if d["patron"]:
                patron_n += 1
            if ma:
                plausible_n += 1
    total_p = len(prod)
    por_fam = {}
    for cl in prod:
        fam = cl[:8]
        e = por_fam.setdefault(fam, {"productos": 0, "marca_plausible": 0})
        e["productos"] += 1
        if prod[cl]["marcas"]:
            e["marca_plausible"] += 1
    top_fam = {f: {"productos": e["productos"],
                   "marca_plausible_pct": round(e["marca_plausible"] * 100
                                                / e["productos"], 1)}
               for f, e in sorted(por_fam.items(),
                                  key=lambda kv: -kv[1]["productos"])[:8]}
    res["productos"] = {
        "productos": total_p,
        "patron_match": patron_n,
        "patron_match_pct": round(patron_n * 100 / total_p, 1) if total_p else 0,
        "marca_plausible": plausible_n,
        "marca_plausible_pct": round(plausible_n * 100 / total_p, 1)
                               if total_p else 0,
        "top_familias": top_fam,
        "descarte_v1": sorted(DESCARTE_MARCAS),
    }
    log(f"Catálogo de productos: {total_p:,} · patrón {patron_n:,} "
        f"({res['productos']['patron_match_pct']}%) · marca plausible "
        f"{plausible_n:,} ({res['productos']['marca_plausible_pct']}%) · "
        f"cobertura por familia en manifiesto")

    # ── invitados vs ofertantes — el lado que falta de la competencia ──
    # Requiere --pesados (InvitacionProcedimiento). Por procedimiento:
    # a quién se invitó, quién ofertó, quién entró sin ser llamado, si el
    # adjudicatario fue invitado, y la ventana real para ofertar.
    inv_files = sorted(_glob.glob(str(out_dir / "invitaciones_20*.csv")))
    if not inv_files:
        res["invitaciones"] = {"estado": "SIN_DATOS_PESADOS",
                               "nota": "correr con --pesados para producir "
                                       "invitados_vs_ofertantes.csv"}
    else:
        inv = _dd(lambda: {"invitados": set(), "fechas": [],
                                   "num_proc": "", "ced_inst": "", "inst": ""})
        for p in inv_files:
            with open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    ns = (r.get("NRO_SICOP") or "").strip()
                    if not ns:
                        continue
                    d = inv[ns]
                    ced = (r.get("CEDULA_PROVEEDOR") or "").strip()
                    if ced:
                        d["invitados"].add(ced)
                    fec = (r.get("FECHA_INVITACION") or "").strip()
                    if fec:
                        d["fechas"].append(fec[:10])
                    if not d["num_proc"]:
                        d["num_proc"] = (r.get("NUMERO_PROCEDIMIENTO") or "").strip()
                        d["ced_inst"] = (r.get("CED_INSTITUCION") or "").strip()
                        d["inst"] = (r.get("INSTITUCION") or "").strip()

        ofertaron = _dd(set)
        for p in sorted(_glob.glob(str(out_dir / "ofertas_20*.csv"))):
            with open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    ns = (r.get("NRO_SICOP") or "").strip()
                    ced = (r.get("CEDULA_PROVEEDOR") or "").strip()
                    if ns and ced:
                        ofertaron[ns].add(ced)

        adj_ganador = {}
        for p in sorted(_glob.glob(str(out_dir / "adjudicaciones_20*.csv"))):
            with open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    ns = (r.get("NRO_SICOP") or "").strip()
                    ced = (r.get("CEDULA_PROVEEDOR") or "").strip()
                    if ns and ced:
                        adj_ganador.setdefault(ns, set()).add(ced)

        apertura = {}
        for p in sorted(_glob.glob(str(out_dir / "carteles_20*.csv"))):
            with open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    ns = (r.get("NRO_SICOP") or "").strip()
                    if ns and "FECHAH_APERTURA" in r:
                        apertura[ns] = (r.get("FECHAH_APERTURA") or "")[:10]

        cols_i = ["NRO_SICOP", "NUMERO_PROCEDIMIENTO", "CEDULA_INSTITUCION",
                  "INSTITUCION", "N_INVITADOS", "N_OFERTARON",
                  "N_INVITADOS_QUE_NO_OFERTARON", "N_OFERTARON_SIN_INVITACION",
                  "TASA_RESPUESTA_PCT", "ADJUDICATARIO_FUE_INVITADO",
                  "ADJUDICATARIO_OFERTO", "FECHA_INVITACION_MIN",
                  "FECHA_INVITACION_MAX", "FECHA_APERTURA"]
        n_proc = n_con_respuesta = 0
        with open(out_dir / "invitados_vs_ofertantes.csv", "w",
                  encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols_i, lineterminator="\n")
            w.writeheader()
            for ns in sorted(inv):
                d = inv[ns]
                ofe = ofertaron.get(ns, set())
                inv_set = d["invitados"]
                ofe_sin = ofe - inv_set
                inv_no_ofe = inv_set - ofe
                tasa = 0.0
                if inv_set:
                    tasa = round(len(inv_set & ofe) * 100 / len(inv_set), 1)
                if ofe:
                    n_con_respuesta += 1
                gan = adj_ganador.get(ns, set())
                g_invitado = ("S" if (gan & inv_set) else
                              ("N" if gan else ""))
                g_oferto = ("S" if (gan & ofe) else ("N" if gan else ""))
                fechas = sorted(d["fechas"])
                n_proc += 1
                w.writerow({
                    "NRO_SICOP": ns,
                    "NUMERO_PROCEDIMIENTO": d["num_proc"],
                    "CEDULA_INSTITUCION": d["ced_inst"],
                    "INSTITUCION": d["inst"],
                    "N_INVITADOS": len(inv_set),
                    "N_OFERTARON": len(ofe),
                    "N_INVITADOS_QUE_NO_OFERTARON": len(inv_no_ofe),
                    "N_OFERTARON_SIN_INVITACION": len(ofe_sin),
                    "TASA_RESPUESTA_PCT": tasa,
                    "ADJUDICATARIO_FUE_INVITADO": g_invitado,
                    "ADJUDICATARIO_OFERTO": g_oferto,
                    "FECHA_INVITACION_MIN": fechas[0] if fechas else "",
                    "FECHA_INVITACION_MAX": fechas[-1] if fechas else "",
                    "FECHA_APERTURA": apertura.get(ns, ""),
                })

        # concentración de invitaciones por institución (top-3)
        inst_inv = _dd(lambda: {"rows": _Cnt(), "procs": set(),
                                        "inst": ""})
        for p in inv_files:
            with open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    ci = (r.get("CED_INSTITUCION") or "").strip()
                    ced = (r.get("CEDULA_PROVEEDOR") or "").strip()
                    if ci and ced:
                        e = inst_inv[ci]
                        e["rows"][ced] += 1
                        e["procs"].add((r.get("NRO_SICOP") or "").strip())
                        e["inst"] = e["inst"] or (r.get("INSTITUCION") or "").strip()
        cols_c = ["CEDULA_INSTITUCION", "INSTITUCION", "PROCEDIMIENTOS",
                  "INVITACIONES", "INVITADOS_DISTINTOS", "TOP1", "TOP2", "TOP3",
                  "PARTICIPACION_TOP3_PCT"]
        with open(out_dir / "invitaciones_concentracion.csv", "w",
                  encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols_c, lineterminator="\n")
            w.writeheader()
            for ci in sorted(inst_inv):
                e = inst_inv[ci]
                tot = sum(e["rows"].values())
                top = e["rows"].most_common(3)
                top3 = sum(n for _, n in top)
                w.writerow({
                    "CEDULA_INSTITUCION": ci, "INSTITUCION": e["inst"],
                    "PROCEDIMIENTOS": len(e["procs"]),
                    "INVITACIONES": tot,
                    "INVITADOS_DISTINTOS": len(e["rows"]),
                    "TOP1": top[0][0] if top else "",
                    "TOP2": top[1][0] if len(top) > 1 else "",
                    "TOP3": top[2][0] if len(top) > 2 else "",
                    "PARTICIPACION_TOP3_PCT": round(top3 * 100 / tot, 1) if tot else 0,
                })
        res["invitaciones"] = {
            "procedimientos_con_invitaciones": n_proc,
            "con_al_menos_un_ofertante": n_con_respuesta,
            "instituciones": len(inst_inv),
            "nota": "el cruce invitados→ofertantes responde direccionamiento en "
                    "contratación directa: quién fue invitado y no ofertó, quién "
                    "entró sin invitación, si el adjudicatario fue invitado",
        }
        log(f"Invitados vs ofertantes: {n_proc:,} procedimientos · "
            f"{n_con_respuesta:,} con ≥1 ofertante")

    # ── derivadas 10-15 (derivadas_extra.py — orden de trabajo 2026-08-24) ──
    # Independientes de --pesados. Cada una imprime su cobertura; las métricas
    # quedan en el manifiesto y una línea en el REPORTE.
    try:
        import derivadas_extra as _dx
        _dx.BASE = str(out_dir)
        res["extra"] = {
            "cartera_proveedor": _dx.d16(),
            "desempeno_proveedor": _dx.d10(),
            "atributos_producto": _dx.d14(),
            "precio_por_institucion": _dx.d11(),
            "barato_y_prorrogado": _dx.d15(),
            "representante_compartido": _dx.d12(),
            "precios_identicos": _dx.d13(),
        }
    except Exception as e:  # noqa: BLE001 — las derivadas extra no bloquean la corrida
        log(f"derivadas extra: {e}")
        res["extra"] = {"error": str(e)}
    return res


# ---------------------------------------------------------------------------
# Manifiesto / reporte
# ---------------------------------------------------------------------------

def load_manifest(path: Path):
    if path.exists():
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
            if m.get("version") == 2:
                return m
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 2, "meses": {}}


def write_manifest(path: Path, manifest: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def pct(a, b):
    if b in (None, 0):
        return None
    return (a - b) / b * 100.0


def build_reporte(manifest: dict, out_dir: Path, year: int) -> None:
    meses = manifest.get("meses", {})
    orden = sorted(meses)
    fecha = manifest.get("fecha_ultima_corrida", "")
    cruce = manifest.get("cruce", {})
    L = []
    L.append(f"# REPORTE — SICOP {year} (núcleo de {len(CONJUNTOS)} conjuntos; "
             "+2 pesados con `--pesados`)")
    L.append("")
    L.append(f"- **Período cubierto:** enero–diciembre {year} (12 meses intentados)")
    L.append(f"- **Fecha de extracción:** {fecha}")
    L.append(f"- **Fuente:** `{BASE_URL.format(AAAAMM='{AAAAMM}')}` (datos abiertos oficiales)")
    L.append(f"- **Archivos de origen por mes:** los {len(CONJUNTOS)} CSV del núcleo de "
             "cada zip (15 originales de la skill + 8 descubiertos el 2026-08-23: "
             "RecursosObjecion, Proveedores, SistemaEvaluacionOfertas, "
             "SancionProveedores, Remates, Recepciones, ReajustePrecios, Sistemas)")
    L.append(f"- **Caché:** `_cache/` ({sum(1 for m in meses.values() if m.get('estado') == 'OK')} "
             "zips procesados)")
    L.append("")
    L.append("### Alcance (léelo antes de interpretar)")
    L.append("")
    L.append("- **Período:** enero–23 de agosto de 2026 — **agosto es parcial** (hasta la "
             "última actualización disponible); sep–dic `SIN_DATOS` (aún no publicados).")
    L.append("- **Año 2026 = actividad observada en snapshots de publicación 2026**, no "
             "procedimientos nacidos en 2026 (el archivo corta por publicación). % de "
             "`NRO_SICOP` que inicia en 2026, por conjunto:")
    alc = manifest.get("alcance", {}).get("nro_sicop_inician_en_anio_pct", {})
    if alc:
        L.append("  " + " · ".join(f"{k}: {v}%" for k, v in alc.items()))
    L.append(f"- **No es la extracción de los 25 archivos del zip:** quedan fuera por "
             "tamaño `InvitacionProcedimiento.csv` (9.096.790 filas snapshot / 7.951.544 "
             "claves únicas, medido 2026-08-23) y `OrdenPedido.csv` (404.472 filas / "
             "129.154 claves únicas). Se incluyen con `--pesados`.")
    L.append("")

    # --- estado por mes ---
    L.append("## Estado por mes")
    L.append("")
    L.append("| Mes | Estado | Filas (todos los conjuntos) |")
    L.append("|---|---|---|")
    for mo in orden:
        m = meses[mo]
        if m["estado"] == "SIN_DATOS":
            L.append(f"| {mo} | SIN_DATOS (404) | — |")
        elif m["estado"] == "ERROR":
            det = m["hallazgos"][0]["detalle"] if m.get("hallazgos") else ""
            L.append(f"| {mo} | **ERROR** ({det}) | — |")
        else:
            tot = sum(c.get("filas", 0) for c in m.get("conjuntos", {}).values())
            L.append(f"| {mo} | OK | {tot:,} |")
    L.append("")

    # --- filas por conjunto (acumulado, único) ---
    L.append("## Filas únicas por conjunto (acumulado)")
    L.append("")
    L.append("| Conjunto | Filas | Referencia 23/08/2026 | Δ |")
    L.append("|---|---|---|---|")
    total = 0
    for nombre in sorted(CONJUNTOS):
        path = out_dir / f"{nombre}_{year}.csv"
        n = sum(1 for _ in open(path, encoding="utf-8-sig")) - 1 if path.exists() else 0
        total += n
        ref = REFERENCIA_CONJUNTOS.get(nombre)
        if ref is None:
            L.append(f"| {nombre} | {n:,} | — | — |")
        else:
            d = pct(n, ref)
            flag = "" if d is None or abs(d) <= 2 else " ⚠"
            L.append(f"| {nombre} | {n:,} | {ref:,} | "
                     f"{('—' if d is None else f'{d:+.1f}%')}{flag} |")
    L.append("")
    L.append(f"**Total:** {total:,} filas únicas en {len(CONJUNTOS)} conjuntos "
             "(referencia declarada: 715.350; la suma de la tabla de la skill da "
             "716.342, sin `procedimientos_adm`).")
    L.append("")
    L.append("> **Política de dedupe:** una fila por **clave natural** por conjunto "
             "(claves en el manifiesto). Los snapshots mensuales evolucionan campos de "
             "estado (recepciones que ganan número definitivo, días de atraso, "
             "descripciones), por eso la clave natural — no la igualdad de fila — es la "
             "unidad de observación. 13 de 15 conjuntos calzan exacto con la referencia; "
             "las diferencias en `lineas_recibidas` (−198), `garantias` (+2) e "
             "`inhibiciones` (+86) dependen de la clave exacta de dedupe, que la skill no "
             "especifica.")

    # --- adjudicaciones por mes (control) ---
    L.append("")
    L.append("## Adjudicaciones por mes (control)")
    L.append("")
    L.append("| Mes | Líneas | Referencia | Δ |")
    L.append("|---|---|---|---|")
    f_adj = out_dir / f"adjudicaciones_{year}.csv"
    por_mes = {}
    if f_adj.exists():
        with open(f_adj, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                por_mes[r["MES_PUBLICACION"]] = por_mes.get(r["MES_PUBLICACION"], 0) + 1
    adj_tot = 0
    crc_tot = 0.0
    for mo in sorted(por_mes):
        n = por_mes[mo]
        adj_tot += n
        ref = REFERENCIA_ADJ_MES.get(mo)
        d = pct(n, ref) if ref is not None else None
        flag = "" if d is None or abs(d) <= 2 else " ⚠"
        L.append(f"| {mo} | {n:,} | {ref if ref is not None else '—'} | "
                 f"{('—' if d is None else f'{d:+.1f}%')}{flag} |")
    if f_adj.exists():
        with open(f_adj, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                crc_tot += parse_number(r.get("MONTO_ADJU_LINEA_CRC")) or 0.0
    d_tot = pct(adj_tot, sum(REFERENCIA_ADJ_MES.values()))
    L.append(f"| **Total** | **{adj_tot:,}** | **{sum(REFERENCIA_ADJ_MES.values()):,}** | "
             f"{d_tot:+.1f}% |")
    L.append("")
    L.append(f"Monto total adjudicado: **₡{fmt_colon(crc_tot)}** "
             f"(referencia: ₡{fmt_colon(REFERENCIA_ADJ_CRC)})")
    L.append("")

    # --- cruce de competencia ---
    if cruce:
        L.append("## Cruce de competencia (Ofertas × LineasOfertadas)")
        L.append("")
        L.append("> `LineasOfertadas.csv` trae el precio pero no la cédula del oferente; "
                 "el cruce con `Ofertas.csv` es por `NRO_SICOP + NRO_OFERTA` y sólo "
                 "funciona sobre el acumulado (el archivo mensual corta por publicación, "
                 "no por procedimiento). **Una estadística de competencia sobre cobertura "
                 "baja no es representativa.**")
        L.append("")
        L.append(f"- Filas de lineas_ofertadas: **{cruce.get('filas_lineas_ofertadas', 0):,}** "
                 f"({cruce.get('lineas_ofertadas_distintas', 0):,} líneas distintas)")
        L.append(f"- Cobertura del cruce: **{cruce.get('cobertura', 0) * 100:.1f}%** "
                 f"(filas de competencia / filas de lineas_ofertadas; referencia: "
                 f"{REFERENCIA_CRUCE['cobertura'] * 100:.1f}%)")
        L.append(f"- Líneas con oferente identificado: **{cruce.get('lineas_con_oferente', 0):,}** "
                 f"({cruce.get('lineas_sin_oferente', 0):,} sin oferente identificado; "
                 f"referencia: {REFERENCIA_CRUCE['lineas_con_oferente']:,})")
        L.append(f"- Filas de competencia (oferente × línea): **{cruce.get('filas_competencia', 0):,}** "
                 f"(referencia: {REFERENCIA_CRUCE['filas_competencia']:,})")
        L.append(f"- Precios sospechosos (0 < precio CRC ≤ 1, `PRECIO_SOSPECHOSO=S`): "
                 f"**{cruce.get('precios_sospechosos', 0):,}** (referencia: 298)")
        L.append(f"- Filas que no encontraron oferta en `Ofertas.csv`: "
                 f"{cruce.get('filas_sin_oferta_en_ofertas', 0):,} · sin conversión a CRC: "
                 f"{cruce.get('filas_sin_conversion_crc', 0):,}")
        L.append(f"- Filas donde el oferente resultó adjudicatario: "
                 f"{cruce.get('filas_adjudicatario', 0):,}")
        L.append("")
        L.append("Producto: `competencia_por_linea.csv` — una fila por oferente y línea, con "
                 "precio unitario ofertado, precio normalizado a colones, bandera "
                 "`PRECIO_SOSPECHOSO` (precio simbólico o por definir) y si resultó "
                 "adjudicatario.")
        L.append("")

    # --- tablas derivadas ---
    deriv = manifest.get("derivadas", {})
    if deriv:
        L.append("## Tablas derivadas (control)")
        L.append("")
        L.append("> Producidas una sola vez, al final, sobre el acumulado de los 23 "
                 "conjuntos. La cobertura entre tramos es muy desigual — es cómo viene "
                 "poblada la fuente, no se arregla con más meses. **Un expediente completo "
                 "es la excepción, no la regla.**")
        L.append("")
        L.append(f"- **Catálogo de productos** (transversal 2020–{year}): "
                 f"**{deriv.get('productos', {}).get('productos', 0):,}** productos · "
                 f"{deriv.get('productos', {}).get('patron_match_pct', 0)}% con patrón "
                 f"«Marca X Modelo Y» · "
                 f"{deriv.get('productos', {}).get('marca_plausible_pct', 0)}% con marca "
                 f"plausible (ver `catalogo_productos.csv`, cobertura por familia en el "
                 f"manifiesto; la Fecha de Registro del catálogo web queda fuera del zip "
                 f"— gate legal pendiente).")
        L.append("")
        x = deriv.get("extra", {})
        if x and "error" not in x:
            car = x.get("cartera_proveedor", {})
            d10, d14, d11, d15, d12, d13 = (x.get(k, {}) for k in (
                "desempeno_proveedor", "atributos_producto", "precio_por_institucion",
                "barato_y_prorrogado", "representante_compartido", "precios_identicos"))
            L.append(f"- **Derivadas extra** (`derivadas_extra.py`, NIVEL DE MEDICION "
                     f"declarado en cada salida):")
            L.append(f"  - **Cartera del proveedor (EJECUCIÓN — órdenes de pedido)**: "
                     f"**{car.get('pares', 0):,}** proveedor×año · ver `cartera_proveedor.csv` "
                     f"(`MONTO_EJECUTADO_CRC` vs `MONTO_ADJUDICADO_CRC` = el ratio que nadie "
                     f"publica) y `cartera_resumen.csv`. ⚠ los montos >₡100.000M de la "
                     f"fuente se reportan como sospechosos, no se suman.")
            L.append(f"  - desempeño de proveedor **{d10.get('proveedores', 0):,}** · "
                     f"atributos de producto **{d14.get('atributos', 0):,}** "
                     f"({d14.get('firmas', 0):,} firmas de SKU) · "
                     f"precio por institución **{d11.get('grupos', 0):,}** grupos "
                     f"marca+firma+año · barato_y_prorrogado **{d15.get('procedimientos', 0):,}** "
                     f"procedimientos · representante compartido **{d12.get('lineas', 0):,}** "
                     f"líneas · precios idénticos **{d13.get('lineas', 0):,}** líneas "
                     f"({d13.get('pares', 0):,} pares). Cobertura de cada una: "
                     f"ver `derivadas_extra.py <N>` o el manifiesto.")
            L.append("")
        L.append("> **NIVEL DE MEDICION (regla permanente):** toda salida que hable del "
                 "negocio de un proveedor declara qué nivel mide — captación "
                 "(adjudicaciones) · ejecución (órdenes de pedido) · entrega "
                 "(recepciones). Sin ese rótulo, un lector asume que «₡15,5M en 2026» "
                 "es el negocio del proveedor, cuando puede ser el 1,5% de lo que "
                 "facturó (caso SONDEL 2026, v2: ₡15,5M adjudicados vs ₡993,7M "
                 "ejecutados en 308 órdenes CRC = 64×; solo colones, dedupe por "
                 "NRO_ORDEN).")
        L.append("")
        t = deriv.get("trazabilidad", {})
        L.append("### Trazabilidad del expediente")
        L.append("")
        L.append(f"- Procedimientos en el universo (7 tramos + etapas): "
                 f"**{t.get('total_procedimientos', 0):,}** (referencia: 37,447)")
        L.append(f"- Con **5 tramos o más**: **{t.get('con_5_mas_tramos', 0):,}** "
                 f"(referencia: 5,193)")
        L.append("")
        L.append("| Tramo | Procedimientos | Referencia |")
        L.append("|---|---|---|")
        for tramo in ("contrato", "cartel", "ofertas", "acto_firme", "garantia",
                      "recibido", "adjudicado"):
            n = t.get("por_tramo", {}).get(tramo, 0)
            L.append(f"| {tramo} | {n:,} | — |")
        L.append("")
        L.append("Producto: `expediente_trazabilidad.csv` (banderas por procedimiento).")
        L.append("")

        co = deriv.get("carteles_objetados", {})
        L.append("### Carteles objetados")
        L.append("")
        L.append(f"- **{co.get('n', 0):,}** carteles con `CARTEL_STAT = Objetado` "
                 f"(referencia: 665) · monto estimado ₡{fmt_colon(co.get('monto_est_crc', 0))} "
                 f"(referencia: ₡273.618 millones)")
        L.append("- `CARTEL_STAT` es el rastro de la objeción; el **resultado** del recurso "
                 "sí está en la fuente: ver `recursos_desenlace.csv` (RecursosObjecion.csv). "
                 "El texto del recurso y las apelaciones ante la Contraloría quedan fuera.")
        L.append("")
        L.append("Producto: `carteles_objetados.csv` (cola de revisión, con si llegó a "
                 "adjudicarse).")
        L.append("")

        rc = deriv.get("recursos", {})
        if rc:
            L.append("### Recursos de objeción (desenlace)")
            L.append("")
            L.append(f"- **{rc.get('recursos', 0):,}** recursos en `RecursosObjecion.csv` · "
                     f"{rc.get('procedimientos_recurridos', 0):,} procedimientos recurridos "
                     f"· {rc.get('recurrentes_distintos', 0):,} recurrentes distintos")
            L.append(f"- **Prosperaron: {rc.get('prosperaron', 0):,}** — "
                     f"{rc.get('tasa_exito_pct', 0)}% sobre todos los recursos "
                     f"({rc.get('recursos', 0):,}) · "
                     f"**{rc.get('tasa_exito_desenlace_pct', 0)}%** sobre los recursos con "
                     f"resultado ({rc.get('recursos', 0) - rc.get('resultado_vacio', 0):,}; "
                     f"{rc.get('resultado_vacio', 0)} sin resultado)")
            L.append("")
            L.append("| Resultado | n |")
            L.append("|---|---|")
            for k, v in list(rc.get("por_resultado", {}).items())[:6]:
                L.append(f"| {k} | {v} |")
            L.append("")
            L.append("> Descubrimiento del 2026-08-23: la skill afirmaba que los recursos "
                     "de objeción no estaban en los datos abiertos; `RecursosObjecion.csv` "
                     "sí los trae con `RESULTADO` y `CAUSA_RESULTADO`. Lo que sigue fuera: "
                     "el texto del recurso y las apelaciones ante la Contraloría.")
            L.append("")
            L.append("Producto: `recursos_desenlace.csv`.")
            L.append("")

        ex = deriv.get("excepciones", {})
        L.append("### Excepciones por adjudicatario")
        L.append("")
        L.append(f"- **{ex.get('procedimientos_con_causal', 0):,}** procedimientos con "
                 f"causal de excepción (`DES_EXCEPCION` no vacía; referencia: 4,278) · "
                 f"**{ex.get('pares', 0):,}** pares proveedor × causal (referencia: 238)")
        top = list(ex.get("por_causal", {}).items())[:3]
        if top:
            L.append("")
            L.append("| Causal | Monto CRC | Proveedores |")
            L.append("|---|---|---|")
            for causal, d in top:
                L.append(f"| {causal} | ₡{fmt_colon(d['monto'])} | {d['proveedores']} |")
        L.append("")
        L.append("Producto: `excepciones_por_adjudicatario.csv`.")
        L.append("")

        sn = deriv.get("sanciones", {})
        L.append("### Sanciones a proveedores")
        L.append("")
        L.append(f"- **{sn.get('n', 0):,}** procedimientos administrativos con sanción "
                 f"(referencia: 8) · {sn.get('cedulas_proveedor', 0)} cédulas distintas "
                 f"({sn.get('empresas', 0)} personas jurídicas; referencia: 4 proveedores)")
        L.append("- Origen: `ProcedimientoADM.csv` (inhabilitaciones y multas). El registro "
                 "completo de sancionados de la Contraloría (SIRSA) no está en esta fuente.")
        L.append("")
        L.append("Producto: `sanciones_proveedores.csv`.")
        L.append("")

        tp = deriv.get("tiempos_por_etapa", {})
        L.append("### Tiempos por etapa")
        L.append("")
        L.append(f"- {tp.get('procedimientos', 0):,} procedimientos con fechas de etapas "
                 "(`FechaPorEtapas.csv`); días entre publicación, apertura, adjudicación, "
                 "contrato y recepción (recepción desde `LineasRecibidas.csv`).")
        L.append("")
        L.append("Producto: `tiempos_por_etapa.csv`.")
        L.append("")

    # --- hallazgos ---
    rev, inf, err = [], [], []
    for mo in orden:
        for h in meses[mo].get("hallazgos", []):
            (rev if h["nivel"] == "REVISION" else inf if h["nivel"] == "INFO"
             else err).append((mo, h))
    # hallazgos a nivel conjunto (obligatorios vacíos, columnas ausentes)
    for mo in orden:
        for cname, cs in meses[mo].get("conjuntos", {}).items():
            if cs.get("obligatorios_vacios"):
                rev.append((mo, {"nivel": "REVISION", "tipo": f"obligatorios_vacios[{cname}]",
                                 "n": cs["obligatorios_vacios"], "detalle": ""}))
            if cs.get("extras"):
                rev.append((mo, {"nivel": "INFO", "tipo": f"campos_extra[{cname}]",
                                 "n": cs["extras"],
                                 "detalle": "descripciones con ';' sin escapar (reconstruidas "
                                            "re-uniendo el excedente en la columna de "
                                            "descripción)"}))
            if cs.get("cuarentena"):
                rev.append((mo, {"nivel": "REVISION", "tipo": f"filas_cuarentena[{cname}]",
                                 "n": cs["cuarentena"],
                                 "detalle": "filas no reconstruibles (sin columna de "
                                            "descripción o exceso raro) — se descartaron "
                                            "en vez de guardarlas corridas"}))
            if cs.get("columnas_ausentes"):
                rev.append((mo, {"nivel": "REVISION",
                                 "tipo": f"columnas_ausentes[{cname}]",
                                 "n": len(cs["columnas_ausentes"]),
                                 "detalle": ", ".join(cs["columnas_ausentes"][:8])}))
    if err:
        L.append("## Errores de mes")
        L.append("")
        for mo, h in err:
            L.append(f"- **{mo}** — {h['tipo']}: {h['detalle']}")
        L.append("")
    L.append("## Hallazgos que requieren revisión humana")
    if not rev:
        L.append("")
        L.append("_Ninguno._")
    else:
        L.append("")
        L.append("| Mes | Tipo | n | Detalle |")
        L.append("|---|---|---|---|")
        for mo, h in rev:
            L.append(f"| {mo} | {h['tipo']} | {h['n']} | {h['detalle']} |")
    L.append("")
    L.append("## Notas informativas")
    if not inf:
        L.append("")
        L.append("_Ninguna._")
    else:
        L.append("")
        L.append("| Mes | Tipo | n | Detalle |")
        L.append("|---|---|---|---|")
        for mo, h in inf:
            L.append(f"| {mo} | {h['tipo']} | {h['n']} | {h['detalle']} |")
    L.append("")

    # --- límites ---
    L.append("---")
    L.append("")
    L.append("**Límites que hay que decir siempre:**")
    L.append("")
    L.append("- **No hay marca ni modelo del bien ofertado** en los datos abiertos: el "
             "producto se identifica por `CODIGO_PRODUCTO`/`CODIGO_PRODUCTO_CL` del "
             "catálogo. Comparar precios del mismo código es válido; inferir la marca "
             "desde la descripción no lo es.")
    L.append("- **Plazos de recurso:** desde el 2026-04-06 rige la circular "
             "MH-DCoP-CIR-0010-2026 de Hacienda (hora límite de recursos 23:59, excepto "
             "Grupo ICE; conversión de moneda extranjera a colones en contratos; renombra "
             "dos campos de monto). El corpus cruza esa fecha. Esta extracción marca "
             "fechas, no computa plazos: si la fuente renombra campos de monto o agrega "
             "columnas de conversión, el chequeo de esquema de A2 lo bloqueará y una "
             "persona decide (no se adapta el parser a ciegas).")
    L.append("- Esta extracción produce **datos y preguntas, no conclusiones**. Una "
             "concentración alta puede tener explicaciones legítimas. **La lectura "
             "jurídica la hace una persona.**")
    L.append("- Los datos son públicos pero contienen datos personales (cédulas de "
             "personas físicas, representantes y **funcionarios con inhibición**). No "
             "publicar los consolidados crudos sin decisión expresa (Ley 8968, principio "
             "de finalidad). El conjunto `inhibiciones` es el más sensible.")
    (out_dir / "REPORTE.md").write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Extracción completa SICOP (15 conjuntos)")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--months", default=None, help="01,02,03 (por defecto: los 12)")
    ap.add_argument("--out", default="salida")
    ap.add_argument("--base", default=None,
                    help="directorio canonico (Salidas). Antes de escribir, si el CSV "
                         "anual de --out falta o es mas chico, se siembra desde aqui "
                         "(merge incremental: no depende de un sembrado externo).")
    ap.add_argument("--solo", default=None,
                    help="sólo estos conjuntos, p. ej. adjudicaciones,ofertas")
    ap.add_argument("--pesados", action="store_true",
                    help="incluye InvitacionProcedimiento y OrdenPedido")
    ap.add_argument("--force", action="store_true", help="reprocesa todo")
    ap.add_argument("--replace", action="store_true",
                    help="con --months: reemplaza SOLO esos meses en los CSV del "
                         "año (quita sus filas por MES_ZIP), re-descarga sus zips "
                         "y los reprocesa. No toca los demás meses. "
                         "Excluyente con --force.")
    ap.add_argument("--no-vigilancia", action="store_true",
                    help="no verificar si la fuente reescribió meses ya en OK "
                         "(más rápido; solo para corridas de desarrollo)")
    ap.add_argument("--vigilar-n", type=int, default=2,
                    help="meses históricos rotativos a verificar por corrida "
                         "además del actual y los 2 más recientes (default 2: "
                         "barrido completo de 84 meses en ~40 días)")
    ap.add_argument("--bronze", default=None,
                    help="directorio de bronze inmutable. Con --force escribe "
                         "una copia sin deduplicar, con hash de fila y origen, "
                         "para reconstruir observado_desde")
    args = ap.parse_args(argv)

    if args.bronze:
        # 2026-08-25: la bandera existe para fijar el contrato, pero la ruta de
        # escritura de bronze NO está implementada. Fallar fuerte es preferible
        # a que alguien crea que corrió y no escribió nada.
        # Reconstrucción de bronze hoy = este mismo script con --force contra un
        # directorio nuevo (~4-6 h). Ver SPEC_BRONZE_REBUILD.md.
        print("ERROR: --bronze aún no está implementado. Para reconstruir "
              "bronze: sicop_loop.py --force --out <dir_nuevo> (4-6 h). "
              "Ver SPEC_BRONZE_REBUILD.md §2.", file=sys.stderr)
        return 2

    if args.replace and not args.months:
        print("ERROR: --replace requiere --months (p. ej. --months 09)",
              file=sys.stderr)
        return 2
    if args.replace and args.force:
        print("ERROR: --replace y --force son excluyentes", file=sys.stderr)
        return 2

    year = args.year
    out_dir = Path(args.out)
    base_dir = Path(args.base) if args.base else None
    cache_dir = out_dir / "_cache"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    confs = dict(CONJUNTOS)
    if args.pesados:
        confs.update(PESADOS)
    if args.solo:
        solo = {s.strip() for s in args.solo.split(",") if s.strip()}
        confs = {k: v for k, v in confs.items() if k in solo}
    if not confs:
        print("No quedan conjuntos por procesar (revisar --solo)", file=sys.stderr)
        return 2

    meses = ([f"{year}{m}" for m in args.months.split(",") if m.strip()]
             if args.months else [f"{year}{m:02d}" for m in range(1, 13)])

    man_path = out_dir / "manifiesto.json"
    manifest = load_manifest(man_path)
    manifest.setdefault("ano", year)
    manifest.setdefault("meses", {})
    meses_reg = manifest["meses"]

    # MES_PUBLICACION real: leer el cartel acumulado ANTES de que --force lo trunque.
    cartel_pub = build_cartel_pub(out_dir, year)
    # --replace: reemplaza SOLO los meses pedidos. Se validan los esquemas ANTES
    # de tocar nada (si falta MES_ZIP no se puede reemplazar sin perder meses).
    meses_rep = set(meses) if args.replace else set()
    if args.replace:
        for nombre, conf in confs.items():
            path = out_dir / f"{nombre}_{year}.csv"
            if not path.exists():
                continue
            cols = conf["columnas"] + list(TRACE)
            try:
                with open(path, encoding="utf-8-sig", newline="") as f:
                    actual = csv.DictReader(f).fieldnames or []
            except (OSError, csv.Error):
                actual = []
            if actual != cols or "MES_ZIP" not in actual:
                print(f"ERROR: {path.name} no tiene el esquema canónico con "
                      f"MES_ZIP. Correr una vez sin --replace para migrarlo.",
                      file=sys.stderr)
                return 3

    # --- abrir writers de salida (truncar en force) y cargar claves vistas ---
    writers = {}
    fhs = {}
    vistos = {}
    for nombre, conf in confs.items():
        path = out_dir / f"{nombre}_{year}.csv"
        cols = conf["columnas"] + list(TRACE)
        # MERGE (2026-09-29): sembrar el CSV anual desde el directorio canonico
        # (--base) para no operar sobre una copia parcial. Sin esto, con --replace
        # los meses ausentes del archivo de --out se pierden; el guard de recarga
        # (<50%) rechaza el resultado y el mes reprocesado nunca llega a las tablas.
        if base_dir and not args.force:
            src = base_dir / f"{nombre}_{year}.csv"
            try:
                if (src.exists() and src.resolve() != path.resolve()
                        and (not path.exists()
                             or path.stat().st_size < src.stat().st_size)):
                    out_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(src, path)
                    log(f"{nombre}: base sembrada desde {base_dir.name} "
                        f"({path.stat().st_size} B)")
            except OSError as e:  # noqa: BLE001
                log(f"{nombre}: no pude sembrar la base ({e})")
        if args.force:
            path.unlink(missing_ok=True)
        elif args.replace:
            quitadas = _drop_months(path, cols, "MES_ZIP", meses_rep)
            if quitadas:
                log(f"{nombre}: {quitadas} filas de {sorted(meses_rep)} "
                    f"quitadas (reemplazo por mes)")
        elif path.exists():
            # migración de esquema: si la cabecera existente no coincide con la
            # esperada, se reconstruye el archivo (p. ej. paso de v1 a v2)
            try:
                with open(path, encoding="utf-8-sig", newline="") as f:
                    actual = csv.DictReader(f).fieldnames or []
                if actual != cols:
                    log(f"{nombre}: esquema de salida cambió — se reconstruye")
                    path.unlink(missing_ok=True)
            except (OSError, csv.Error):
                path.unlink(missing_ok=True)
        if not path.exists():
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                csv.DictWriter(f, fieldnames=cols, lineterminator="\n").writeheader()
        fh = open(path, "a", encoding="utf-8-sig", newline="")
        writers[nombre] = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        fhs[nombre] = fh
        vistos[nombre] = set()
        # claves ya presentes en el archivo acumulado (clave natural)
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                vistos[nombre].add(tuple(r.get(k, "") for k in conf["clave"]))

    # --- cuarentena: filas malformadas de la fuente se archivan crudas ---
    qcols = ["CONJUNTO", "MES_PUBLICACION", "MOTIVO", "N_CAMPOS", "CAMPOS_CRUDOS"]
    qdir = out_dir / "_cuarentena"
    qdir.mkdir(parents=True, exist_ok=True)
    qwriters = {}
    qfhs = {}
    for nombre in confs:
        qpath = qdir / f"{nombre}_{year}.csv"
        if args.force:
            qpath.unlink(missing_ok=True)
        elif args.replace:
            # en cuarentena, MES_PUBLICACION guarda el mes del zip de origen
            _drop_months(qpath, qcols, "MES_PUBLICACION", meses_rep)
        if not qpath.exists():
            with open(qpath, "w", encoding="utf-8-sig", newline="") as f:
                csv.DictWriter(f, fieldnames=qcols, lineterminator="\n").writeheader()
        qf = open(qpath, "a", encoding="utf-8-sig", newline="")
        qwriters[nombre] = csv.DictWriter(qf, fieldnames=qcols,
                                          lineterminator="\n",
                                          extrasaction="ignore")
        qfhs[nombre] = qf

    log(f"Año {year} · {len(meses)} mes(es) · {len(confs)} conjunto(s) · "
        f"salida en {out_dir.resolve()}"
        + (" · FORCE" if args.force else "")
        + (f" · REPLACE {sorted(meses_rep)}" if args.replace else ""))

    # --- VIGILANCIA DE REESCRITURA DE LA FUENTE (2026-08-25) -----------------
    # No alcanza con verificar el mes en curso: la fuente puede reescribir un
    # mes cerrado y hoy eso es invisible. Verificar los 84 todos los días es
    # caro; verificar solo el actual deja huecos de meses.
    #
    # Regla: mes en curso SIEMPRE + los 2 cerrados más recientes (los que más
    # se mueven) + N rotativos del histórico por día del mes. Con --vigilar-n 2
    # el barrido completo cierra en ~40 días.
    meses_reprocesados = []
    meses_vigilar = set()
    if not args.no_vigilancia:
        hoy = time.localtime()
        actual = f"{hoy.tm_year}{hoy.tm_mon:02d}"
        meses_vigilar.add(actual)
        cerrados = sorted(m for m in meses
                          if meses_reg.get(m, {}).get("estado") == "OK"
                          and m < actual)
        meses_vigilar.update(cerrados[-2:])          # los 2 más recientes
        if cerrados and args.vigilar_n > 0:
            # rotación determinista por día del mes: sin azar, reproducible
            resto = [m for m in cerrados[:-2]] or cerrados
            base = (hoy.tm_mday - 1) * args.vigilar_n
            for i in range(args.vigilar_n):
                meses_vigilar.add(resto[(base + i) % len(resto)])
        log(f"vigilancia de reescritura: {sorted(meses_vigilar)}")

    t0 = time.time()


    for mo in meses:
        prev = meses_reg.get(mo, {})
        sets_hechos = set(prev.get("conjuntos", {}).keys())
        if (not args.force and not args.replace and prev.get("estado") == "OK"
                and set(confs).issubset(sets_hechos)):
            # ANTES de saltar hay que descartar que la FUENTE reescribió el mes.
            # El bug corregido el 2026-08-25: este `continue` estaba antes de
            # cualquier hash, y el hash vive dentro de procesar_mes() — así que
            # un mes en OK jamás se volvía a verificar y la reescritura de la
            # fuente era indetectable salvo con --force.
            #
            # Dos niveles, del más barato al más caro:
            #   1. HEAD remoto: si ETag/Last-Modified/Content-Length coinciden
            #      con lo registrado, la fuente no tocó el mes. Cuesta un
            #      round-trip, no 180 MB.
            #   2. Si no hay validadores o difieren: re-descargar y comparar
            #      sha256 contra el manifiesto.
            reproc = None
            if args.no_vigilancia:
                pass
            elif mo in meses_vigilar:
                url = BASE_URL.format(AAAAMM=mo)
                h = head_remoto(url)
                val_prev = prev.get("validadores") or {}
                if h.get("not_found"):
                    log(f"{mo}: 404 en vigilancia — la fuente retiró el mes")
                elif h.get("error"):
                    # No se pudo preguntar. NO es motivo para bajar 180 MB:
                    # se salta la vigilancia de este mes y se reintenta mañana.
                    log(f"{mo}: HEAD falló tras 3 intentos — vigilancia diferida")
                elif h and val_prev:
                    # Escalera de disparo, corregida por el censo del 2026-08-25.
                    # Medición: 35 de 67 meses tienen Last-Modified >60 días tras
                    # su cierre, en TRES tandas (2022-12-07, 2024-09-20,
                    # 2025-05-06) con el tamaño remoto idéntico al local. Eso es
                    # migración de almacenamiento, no reescritura de contenido.
                    # Disparar por Last-Modified reprocesaría 5 años de historia
                    # por nada. Ver CENSO_REESCRITURA_2026-08-25.md §3.
                    _cl_r, _cl_p = h.get("content_length"), val_prev.get("content_length")
                    _et_r, _et_p = h.get("etag"), val_prev.get("etag")
                    if _cl_r and _cl_p and _cl_r != _cl_p:
                        reproc = f"tamaño remoto difiere ({_cl_p} → {_cl_r})"
                    elif _et_r and _et_p and _et_r != _et_p:
                        # ETag distinto con tamaño igual: puede ser reescritura
                        # real o re-empaquetado. Cuesta una descarga saberlo.
                        zp = cache_dir / f"{mo}.zip"
                        try:
                            if download(url, zp) == "ok":
                                nuevo = sha256_file(zp)
                                if prev.get("sha256") and nuevo != prev["sha256"]:
                                    reproc = "sha256 difiere (ETag cambió)"
                                else:
                                    prev["validadores"] = {k: v for k, v in h.items() if v}
                                    meses_reg[mo] = prev
                                    log(f"{mo}: ETag cambió, contenido idéntico "
                                        f"— validadores actualizados")
                        except RuntimeError as e:
                            log(f"{mo}: vigilancia no pudo descargar — {e}")
                    elif h != val_prev:
                        # Solo Last-Modified. Migración: se anota, no se reprocesa.
                        prev["validadores"] = {k: v for k, v in h.items() if v}
                        meses_reg[mo] = prev
                        log(f"{mo}: MIGRACION — solo cambió Last-Modified "
                            f"({val_prev.get('last_modified')} → "
                            f"{h.get('last_modified')}); sin reproceso")
                elif h and not val_prev:
                    # primera vez: sembrar validadores sin reprocesar
                    prev["validadores"] = {k: v for k, v in h.items() if v}
                    meses_reg[mo] = prev
                    log(f"{mo}: validadores sembrados ({h.get('etag') or 'sin ETag'})")
                elif not h:
                    # sin validadores utilizables: re-descargar y comparar hash
                    zp = cache_dir / f"{mo}.zip"
                    try:
                        if download(url, zp) == "ok":
                            nuevo = sha256_file(zp)
                            if prev.get("sha256") and nuevo != prev["sha256"]:
                                reproc = "sha256 difiere del manifiesto"
                    except RuntimeError as e:
                        log(f"{mo}: vigilancia no pudo descargar — {e}")

            # El caché también puede haber sido alterado localmente.
            if reproc is None:
                zp = cache_dir / f"{mo}.zip"
                if zp.exists() and prev.get("sha256"):
                    if sha256_file(zp) != prev["sha256"]:
                        reproc = "el zip en caché no coincide con el manifiesto"

            if reproc is None:
                log(f"{mo}: OK según manifiesto — se salta")
                continue
            log(f"{mo}: REPROCESO — {reproc}")
            meses_reprocesados.append((mo, reproc))
        t1 = time.time()
        zip_path = cache_dir / f"{mo}.zip"
        if zip_path.exists() and not args.replace:
            log(f"{mo}: zip en caché ({zip_path.stat().st_size / 1e6:.1f} MB)")
        else:
            if args.replace and zip_path.exists():
                log(f"{mo}: --replace: re-descargando para capturar la reescritura")
            url = BASE_URL.format(AAAAMM=mo)
            log(f"{mo}: descargando {url}")
            try:
                res = download(url, zip_path)
            except RuntimeError as e:
                log(f"{mo}: ERROR descarga — {e}")
                meses_reg[mo] = {"estado": "ERROR", "archivo": f"{mo}.zip",
                                 "sha256": None, "tamano_bytes": 0,
                                 "conjuntos": {}, "hallazgos": [
                                     {"nivel": "ERROR", "tipo": "descarga",
                                      "n": 1, "detalle": str(e)}]}
                continue
            if res == "not_found":
                log(f"{mo}: 404 — SIN_DATOS (mes aún no publicado)")
                meses_reg[mo] = {"estado": "SIN_DATOS", "archivo": f"{mo}.zip",
                                 "sha256": None, "tamano_bytes": 0,
                                 "conjuntos": {}, "hallazgos": []}
                continue
            log(f"{mo}: descargado ({zip_path.stat().st_size / 1e6:.1f} MB)")

        m = procesar_mes(mo, zip_path, confs, writers, vistos, qwriters, cartel_pub)
        m["archivo"] = f"{mo}.zip"
        # Sembrar los validadores HTTP para que la próxima corrida pueda
        # detectar reescritura de la fuente con un HEAD en vez de 180 MB.
        if not args.no_vigilancia:
            _h = head_remoto(BASE_URL.format(AAAAMM=mo))
            if _h and not _h.get("not_found") and not _h.get("error"):
                m["validadores"] = {k: v for k, v in _h.items() if v}
        meses_reg[mo] = m
        tot = sum(c.get("filas", 0) for c in m.get("conjuntos", {}).values())
        log(f"{mo}: {m['estado']} · {tot:,} filas · {time.time() - t1:.0f}s")
        for nombre, cs in m.get("conjuntos", {}).items():
            if cs.get("duplicados"):
                log(f"   {nombre}: {cs['duplicados']} filas idénticas descartadas")

    # --- cerrar writers ---
    for fh in fhs.values():
        fh.close()
    for qf in qfhs.values():
        qf.close()

    # --- cruce de competencia y tablas derivadas sobre el acumulado ---
    # Con --solo NO se recalculan (modo quirúrgico: solo re-extraer el conjunto
    # pedido; las derivadas completas corren en la corrida normal o con todo).
    if args.solo:
        log(f"--solo: se omite el recálculo de cruce y derivadas")
    else:
        cruce = cruce_competencia(out_dir, year, confs)
        if cruce:
            manifest["cruce"] = cruce
        deriv = derivadas(out_dir, year, confs)
        if deriv:
            manifest["derivadas"] = deriv

    # --- manifiesto y reporte ---
    # reproducibilidad: esquemas (claves naturales) y hashes de cada salida.
    # Con --solo NO se tocan: son artefactos de la corrida completa (escribirlos
    # con un solo conjunto pisa el esquema/hashes/alcance del corpus entero).
    if not args.solo:
        manifest["esquemas"] = {
            nombre: {"archivo": conf["archivo"], "clave": list(conf["clave"]),
                     "obligatorios": list(conf["obligatorios"]),
                     "columnas": conf["columnas"]}
            for nombre, conf in confs.items()
        }
        salidas = {}
        for p in sorted(out_dir.glob(f"*_{year}.csv")):
            salidas[p.name] = sha256_file(p)
        for nombre in ("competencia_por_linea", "expediente_trazabilidad",
                       "carteles_objetados", "excepciones_por_adjudicatario",
                       "sanciones_proveedores", "tiempos_por_etapa",
                       "recursos_desenlace"):
            p = out_dir / f"{nombre}.csv"
            if p.exists():
                salidas[p.name] = sha256_file(p)
        manifest["salidas"] = salidas

        # alcance temporal: % de NRO_SICOP que inicia en el año pedido (el archivo
        # corta por publicación, no por fecha del procedimiento)
        alcance = {}
        for cn in ("adjudicaciones", "contratos", "lineas_recibidas", "ofertas",
                   "lineas_ofertadas"):
            path = out_dir / f"{cn}_{year}.csv"
            n = tot = 0
            if path.exists():
                with open(path, encoding="utf-8-sig", newline="") as f:
                    for r in csv.DictReader(f):
                        p = (r.get("NRO_SICOP") or "").strip()
                        if p:
                            tot += 1
                            if p.startswith(str(year)):
                                n += 1
            alcance[cn] = round(n * 100 / tot, 1) if tot else None
        manifest["alcance"] = {"nro_sicop_inician_en_anio_pct": alcance}
        manifest["fecha_ultima_corrida"] = datetime.now().isoformat(timespec="seconds")
        write_manifest(man_path, manifest)
        build_reporte(manifest, out_dir, year)
    else:
        # igual se registra la corrida de los meses procesados
        write_manifest(man_path, manifest)

    log(f"Listo en {time.time() - t0:.0f}s → {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
