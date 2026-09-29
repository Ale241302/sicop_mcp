"""Servicio de embeddings local (FASE C). Modelo multilingual-e5-base en CPU.
POST /embed {textos: [str], tipo: "query"|"passage"} -> {embeddings}.
e5-base es sensible a prefijos: query usa "query: ", doc "passage: ".
"""
from typing import List

import numpy as np
from fastapi import FastAPI, Request
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI(title="sicop-embedder")
MODEL = "intfloat/multilingual-e5-base"


class Req(BaseModel):
    textos: List[str]
    tipo: str = "passage"


_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL)
    return _model


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL}


@app.post("/embed")
def embed(req: Req):
    m = get_model()
    pref = "query: " if req.tipo == "query" else "passage: "
    textos = [pref + (t if t else " ") for t in req.textos]
    vecs = m.encode(textos, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
    return {"embeddings": [v.tolist() for v in vecs], "dim": int(vecs.shape[1])}
