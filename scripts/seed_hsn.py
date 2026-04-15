#!/usr/bin/env python3
"""
HSN code seeding script.

Loads CSV → inserts into hsn_codes table → computes embeddings → stores in pgvector.
Idempotent: safe to run multiple times.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import csv

from sqlalchemy import select

from app.db.base import Base
from app.db.session import async_session_maker, engine
from app.ml.hsn.embedder import embed
from app.models.hsn_code import HSNCode


async def seed_hsn(db) -> None:
    """Load CSV and seed HSN codes with embeddings."""
    csv_path = Path(__file__).parent / "app" / "ml" / "hsn" / "reference_data.csv"

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} HSN codes from CSV")

    result = await db.execute(select(HSNCode))
    existing = result.scalars().all()
    existing_codes = {h.code for h in existing}

    to_insert = []
    to_update = []

    for row in rows:
        code = row["code"]
        description = row["description"]
        gst_rate = float(row["gst_rate"]) if row.get("gst_rate") else None
        aliases = row.get("common_aliases", "")

        if code in existing_codes:
            to_update.append(
                {
                    "code": code,
                    "description": description,
                    "gst_rate": gst_rate,
                    "common_aliases": aliases,
                }
            )
        else:
            to_insert.append(
                {
                    "code": code,
                    "description": description,
                    "gst_rate": gst_rate,
                    "common_aliases": aliases,
                }
            )

    if to_update:
        print(f"Updating {len(to_update)} existing codes")

    if to_insert:
        print(f"Inserting {len(to_insert)} new codes")

    descriptions = [r["description"] for r in rows]
    aliases_list = [r.get("common_aliases", "") for r in rows]

    search_texts = [
        f"{desc} {aliases}" if aliases else desc
        for desc, aliases in zip(descriptions, aliases_list)
    ]

    print("Computing embeddings...")
    embeddings = embed(search_texts)
    print(f"Generated {len(embeddings)} embeddings, dim={embeddings.shape[1]}")

    for i, row in enumerate(rows):
        hsn = HSNCode(
            code=row["code"],
            description=row["description"],
            gst_rate=float(row["gst_rate"]) if row.get("gst_rate") else None,
            common_aliases=row.get("common_aliases", ""),
            embedding=embeddings[i].tolist(),
        )
        db.add(hsn)

    await db.commit()

    print(f"Seeded {len(rows)} HSN codes with embeddings")


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        await seed_hsn(session)

    print("HSN seeding completed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
