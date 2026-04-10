"""Semantic embedding engine with optional sentence-transformers backend.

When sentence-transformers is installed, uses all-MiniLM-L6-v2 (384-dim) for
true semantic search.  When absent, all methods return None and hybrid_search
falls through to FTS5-only -- zero runtime cost.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_model = None
_model_load_attempted = False


def _load_model():
    """Lazy-load the sentence-transformers model on first use."""
    global _model, _model_load_attempted
    if _model_load_attempted:
        return _model
    _model_load_attempted = True
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-MiniLM-L6-v2")
    except (ImportError, Exception):
        _model = None
    return _model


def is_available() -> bool:
    """Return True if the embedding backend is loaded and ready."""
    return _load_model() is not None


def embed(text: str) -> list[float] | None:
    """Embed a single text string.  Returns None if backend unavailable."""
    model = _load_model()
    if model is None:
        return None
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def embed_batch(texts: list[str]) -> list[list[float]] | None:
    """Embed multiple texts at once.  Returns None if backend unavailable."""
    model = _load_model()
    if model is None:
        return None
    vecs = model.encode(texts, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two normalised vectors.

    Since all-MiniLM-L6-v2 outputs are L2-normalised, this reduces to dot product.
    Kept general for safety if embeddings come from another source.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
