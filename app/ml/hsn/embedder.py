"""
Sentence-transformers wrapper for HSN embeddings.
"""


import numpy as np
from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None


def get_embedder() -> SentenceTransformer:
    """Lazy-load the sentence-transformers model."""
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embed(texts: list[str]) -> np.ndarray:
    """
    Generate embeddings for a list of texts.

    Args:
        texts: List of text strings to embed

    Returns:
        numpy array of shape (len(texts), 384)
    """
    model = get_embedder()
    return model.encode(texts, convert_to_numpy=True)


def embed_single(text: str) -> np.ndarray:
    """
    Generate embedding for a single text.

    Args:
        text: Text string to embed

    Returns:
        numpy array of shape (384,)
    """
    model = get_embedder()
    return model.encode(text, convert_to_numpy=True)
