"""FASE C: embebe los docs de 08_kb en emb_doc (coleccion KB), chunked."""
import os
import sys

sys.path.insert(0, "/app")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

import requests
from django.db import connection

EMBEDDER_URL = os.environ.get("EMBEDDER_URL", "http://sicop_mcp-embedder-1:8500")
KB_DIR = "/app/08_kb"


def chunk_text(texto, max_chars=1800):
    """Divide un doc en chunks por parrafos, respetando max_chars."""
    parrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    chunks = []
    actual = ""
    for p in parrafos:
        if len(actual) + len(p) > max_chars and actual:
            chunks.append(actual)
            actual = p
        else:
            actual = (actual + "\n\n" + p).strip() if actual else p
    if actual:
        chunks.append(actual)
    return chunks or [texto[:max_chars]]


def run():
    docs = sorted(os.listdir(KB_DIR))
    total_rows = 0
    for fn in docs:
        if not fn.endswith(".md"):
            continue
        with open(os.path.join(KB_DIR, fn), encoding="utf-8", errors="replace") as f:
            texto = f.read()
        chunks = chunk_text(texto)
        textos = [f"[SICOP KB: {fn}]\n{c}" for c in chunks]
        resp = requests.post(f"{EMBEDDER_URL}/embed", json={"textos": textos}, timeout=180)
        resp.raise_for_status()
        vecs = resp.json()["embeddings"]
        with connection.cursor() as cur:
            for i, (ch, v) in enumerate(zip(chunks, vecs)):
                ref = f"{fn}#{i+1}"
                vec = "[" + ",".join(f"{x:.6f}" for x in v) + "]"
                cur.execute(
                    """
                    INSERT INTO emb_doc (coleccion, ref_id, texto, embedding, actualizado)
                    VALUES ('KB', %s, %s, %s::vector, now())
                    ON CONFLICT (coleccion, ref_id)
                    DO UPDATE SET texto=EXCLUDED.texto, embedding=EXCLUDED.embedding, actualizado=now()
                    """,
                    [ref, ch, vec],
                )
        total_rows += len(chunks)
        print(f"  {fn}: {len(chunks)} chunks", flush=True)
    print(f"DONE {total_rows} chunks KB", flush=True)


run()
