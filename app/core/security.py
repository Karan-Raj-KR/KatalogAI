import secrets

import bcrypt


_PREFIX = "kat_live_"
_RANDOM_BYTES = 24  # 24 bytes → 32-char URL-safe base64


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key.

    Returns (raw_key, key_prefix) where:
    - raw_key is the full key shown once to the user  e.g. ``kat_live_abc123…``
    - key_prefix is the first 8 chars used for fast DB lookup  e.g. ``kat_live``
    """
    random_part = secrets.token_urlsafe(_RANDOM_BYTES)  # 32 URL-safe chars
    raw_key = f"{_PREFIX}{random_part}"
    key_prefix = raw_key[:8]  # "kat_live"
    return raw_key, key_prefix


def hash_api_key(raw_key: str) -> str:
    """Return a bcrypt hash of *raw_key*."""
    return bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    """Return True if *raw_key* matches the stored *key_hash*."""
    return bcrypt.checkpw(raw_key.encode(), key_hash.encode())
