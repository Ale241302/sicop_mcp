"""Vigilancia de reescritura de la fuente (plan FASE 2.4.2).

HEAD a los meses objetivo (mes en curso + 3 cerrados + 2 rotativos del historico),
compara ETag / Content-Length contra lo registrado (ctl_mes_fuente) y anota el
resultado. Un cambio de contenido -> senal con precedencia.
"""
import hashlib
import logging
import urllib.error
import urllib.request
from datetime import datetime

from django.utils import timezone

from .models import VigilanciaCheck, CtlMesFuente

logger = logging.getLogger(__name__)

BASE_URL = ("https://dlsaobservatorioprod.blob.core.windows.net/"
            "fs-synapse-observatorio-produccion/Zip/{AAAAMM}.zip")
RETRIES = 3
BACKOFF = (5, 15, 45)
UA = "Mozilla/5.0 (sicop-vigilancia; stdlib)"


def _head(aaaamm):
    url = BASE_URL.format(AAAAMM=aaaamm)
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return {
                    "etag": r.headers.get("ETag"),
                    "last_modified": r.headers.get("Last-Modified"),
                    "content_length": int(r.headers.get("Content-Length", 0) or 0),
                    "status": r.status,
                }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"status": 404, "error": "SIN_DATOS"}
        except Exception:  # noqa: BLE001
            import time

            if attempt < RETRIES - 1:
                time.sleep(BACKOFF[attempt])
    return {"error": True}


def _meses_objetivo():
    """Mes en curso + 3 cerrados + 2 rotativos del historico."""
    hoy = datetime.now()
    actual = int(f"{hoy.year:04d}{hoy.month:02d}")
    meses = [actual - 1, actual - 2, actual - 3, actual - 4]  # en curso y 3 cerrados
    # 2 rotativos: barridos por el historial (2020..), deterministas por dia
    rot = []
    hist = [v for v in range(202001, actual - 4) if 1 <= v % 100 <= 12]
    if hist:
        dia = hoy.toordinal()
        for i in range(2):
            rot.append(hist[(dia + i * 7) % len(hist)])
    return list(dict.fromkeys(meses + rot))[:7]


def revisar_reescritura(corrida=None, aaaamm=None):
    """HEAD a los meses objetivo; registra el resultado en vigilancia_check."""
    if not aaaamm:
        aaaamm = _meses_objetivo()
    elif isinstance(aaaamm, int):
        aaaamm = [aaaamm]
    now = timezone.now()
    cambios = []
    for mes in aaaamm:
        mes_s = str(mes)
        h = _head(mes_s)
        if h.get("error") or h.get("status") == 404:
            VigilanciaCheck.objects.create(
                aaaamm=mes_s, etag=None, content_length=None, sha256=None,
                resultado="ERROR" if h.get("error") else "SIN_DATOS",
                detalle="no pude preguntar" if h.get("error") else "404",
                fecha=now, corrida=corrida)
            continue
        prev = CtlMesFuente.objects.filter(AAAAMM=mes_s).first()
        prev_etag = prev.HASH_ZIP if prev else None
        etag = (h.get("etag") or "").strip('"')
        if prev_etag and prev_etag != etag:
            resultado = "CAMBIO"
            cambios.append(mes_s)
        elif prev_etag and prev_etag == etag:
            resultado = "OK"
        else:
            resultado = "OK_PRIMERA"
        VigilanciaCheck.objects.create(
            aaaamm=mes_s, etag=etag, content_length=h.get("content_length"),
            sha256=prev_etag, resultado=resultado,
            detalle=f"CL={h.get('content_length')} LM={h.get('last_modified')}",
            fecha=now, corrida=corrida)
        print(f"  vigilancia {mes_s}: {resultado}", flush=True)
    return cambios
