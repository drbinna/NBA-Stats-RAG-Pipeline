"""Text embeddings with nomic-embed-text-v1.5.

The model expects a task prefix: documents are embedded as "search_document: ..."
and questions as "search_query: ...". Both providers return unit-length vectors,
so cosine distance in pgvector ranks them correctly.
"""
import math
import time

import requests

from backend.config import EMBED_MODEL, EMBED_PROVIDER, FIREWORKS_API_KEY

FIREWORKS_URL = "https://api.fireworks.ai/inference/v1/embeddings"
_local = None


def _normalize(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _fireworks(texts, retries=6):
    if not FIREWORKS_API_KEY:
        raise RuntimeError("FIREWORKS_API_KEY is not set")
    for attempt in range(retries):
        try:
            r = requests.post(FIREWORKS_URL, timeout=60,
                              headers={"Authorization": f"Bearer {FIREWORKS_API_KEY}"},
                              json={"model": EMBED_MODEL, "input": texts})
        except (requests.ConnectionError, requests.Timeout):
            # Dropped connections and timeouts are retried like server errors.
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (429, 500, 502, 503) and attempt < retries - 1:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        body = r.json()
        data = sorted(body["data"], key=lambda d: d["index"])
        tokens = (body.get("usage") or {}).get("prompt_tokens", 0)
        return [_normalize(d["embedding"]) for d in data], tokens
    raise RuntimeError("embedding request failed")


def _fastembed(texts):
    global _local
    if _local is None:
        from fastembed import TextEmbedding  # optional dependency, see requirements-ingest.txt
        import os
        _local = TextEmbedding("nomic-ai/nomic-embed-text-v1.5-Q", threads=os.cpu_count())
    return [_normalize(list(map(float, v))) for v in _local.embed(texts, batch_size=32)], 0


def embed(texts, kind="document"):
    """Embed a list of texts. Returns (vectors, tokens_billed)."""
    prefix = "search_document: " if kind == "document" else "search_query: "
    texts = [prefix + t for t in texts]
    return _fastembed(texts) if EMBED_PROVIDER == "local" else _fireworks(texts)


def embed_query(text):
    vecs, tokens = embed([text], kind="query")
    return vecs[0], tokens


def to_pgvector(v):
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"
