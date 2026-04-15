"""
HSN retriever using pgvector cosine similarity search.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.hsn.embedder import embed_single

SIMILARITY_THRESHOLD = 0.65


@dataclass
class HSNMatch:
    """Result from HSN retrieval."""

    code: str
    description: str
    gst_rate: float | None
    score: float


def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = sum(a * a for a in v1) ** 0.5
    norm2 = sum(b * b for b in v2) ** 0.5
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


async def retrieve_hsn(
    text_query: str,
    db: AsyncSession,
    top_k: int = 5,
) -> list[HSNMatch]:
    """
    Retrieve top-k similar HSN codes using pgvector cosine similarity.

    Args:
        text_query: Product description or name
        db: Database session
        top_k: Number of results to return

    Returns:
        List of HSNMatch tuples (code, description, score)
    """
    query_embedding = embed_single(text_query)

    embedding_list = query_embedding.tolist()

    sql = text("""
        SELECT code, description, gst_rate,
               (embedding <=> :embedding::vector) as distance
        FROM hsn_codes
        WHERE embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT :top_k
    """)

    result = await db.execute(sql, {"embedding": embedding_list, "top_k": top_k})
    rows = result.fetchall()

    matches = []
    for row in rows:
        code = row[0]
        description = row[1]
        gst_rate = float(row[2]) if row[2] else None
        distance = row[3]
        score = 1.0 - distance

        if score >= SIMILARITY_THRESHOLD:
            matches.append(
                HSNMatch(
                    code=code,
                    description=description,
                    gst_rate=gst_rate,
                    score=round(score, 4),
                )
            )

    return matches
