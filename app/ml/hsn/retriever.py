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


async def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = sum(a * a for a in vec1) ** 0.5
    mag2 = sum(b * b for b in vec2) ** 0.5
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


async def retrieve_hsn(
    text_query: str,
    db: AsyncSession,
    top_k: int = 5,
) -> list[HSNMatch]:
    """
    Retrieve top-k similar HSN codes using pgvector cosine similarity search.
    """
    query_embedding = embed_single(text_query)
    embedding_list = query_embedding.tolist()
    embedding_str = "[" + ",".join(map(str, embedding_list)) + "]"

    sql = text(f"""
        SELECT code, description, gst_rate,
               (embedding <=> CAST(:embedding AS vector)) as distance
        FROM hsn_codes
        WHERE embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT :top_k
    """)

    result = await db.execute(sql, {"embedding": embedding_str, "top_k": top_k})
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
