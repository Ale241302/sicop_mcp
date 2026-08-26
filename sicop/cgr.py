"""Buscador CGR (plan §13): PDFs de resoluciones de texto nativo.

https://cgrbuscador.cgr.go.cr/BuscadorWebCGR/queryGET?searchText={término}&page=N
Uso dirigido (un NRO_SICOP a la vez), NUNCA barrido. Gate legal pendiente: los
terminos de uso de la CGR no estan leidos (bloqueante para extraccion masiva).
"""
import logging
import re
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

BASE = "https://cgrbuscador.cgr.go.cr/BuscadorWebCGR/queryGET"
UA = "Mozilla/5.0 (sicop-cgr; stdlib)"


def _fetch(termino, page=1):
    url = f"{BASE}?searchText={urllib.parse.quote(termino)}&page={page}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _parse(html):
    """Extrae resultados: titulo + link al PDF + snippet."""
    out = []
    # enlaces a documentos publicos de la CGR
    for m in re.finditer(r'<a[^>]+href="([^"]*(?:cgrfiles\.cgr\.go\.cr|publico|Documento|archivo)[^"]*)"[^>]*>(.*?)</a>', html, re.I | re.S):
        href, txt = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if href and (txt or True):
            out.append({"titulo": txt[:160] or href[-80:], "url": href})
    # fallback: cualquier href con .pdf o /publico/
    if not out:
        for m in re.finditer(r'href="([^"]+)"', html):
            h = m.group(1)
            if ".pdf" in h.lower() or "publico" in h.lower() or "descarga" in h.lower():
                out.append({"titulo": h[-80:], "url": h})
    # dedupe conservando orden
    seen, res = set(), []
    for o in out:
        if o["url"] not in seen:
            seen.add(o["url"])
            res.append(o)
    return res


def buscar(termino, page=1, limit=15):
    """Busqueda dirigida en el buscador CGR. Advertencia legal en el sobre."""
    try:
        html = _fetch(termino, page)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    docs = _parse(html)[:limit]
    return {
        "termino": termino,
        "documentos": docs,
        "total_mostrados": len(docs),
        "sobre": {
            "nivel_medicion": "fuente externa (CGR)",
            "aviso_legal": "USO DIRIGIDO, no barrido. Los terminos de uso de cgr.go.cr NO estan leidos: cualquier extraccion masiva queda bloqueada hasta dictamen legal (gate B1/F5).",
            "privacidad": "los PDFs pueden contener datos personales: no republicar sin decision expresa.",
        },
    }
