#!/usr/bin/env python3
"""
CLI script to generate and insert a named API key.

Usage:
    python -m scripts.generate_api_key --name "My API Key" --description "Description"
"""

import argparse
import asyncio

from app.core.security import generate_api_key, hash_api_key
from app.db.session import async_session_maker
from app.models.api_key import APIKey


async def create_api_key(name: str) -> None:
    raw_key, key_prefix = generate_api_key()
    key_hash = hash_api_key(raw_key)

    api_key = APIKey(
        key_prefix=key_prefix,
        key_hash=key_hash,
        name=name,
    )

    async with async_session_maker() as session:
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

    print(f"\n{'=' * 60}")
    print(f"API KEY CREATED: {name}")
    print(f"{'=' * 60}")
    print(f"Key: {raw_key}")
    print(f"Prefix: {key_prefix}")
    print(f"ID: {api_key.id}")
    print(f"{'=' * 60}")
    print("IMPORTANT: Save this key - it cannot be retrieved!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a new API key")
    parser.add_argument("--name", required=True, help="Name for the API key")
    args = parser.parse_args()

    asyncio.run(create_api_key(args.name))


if __name__ == "__main__":
    main()
