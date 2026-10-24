import hashlib
import hmac
import secrets

KEY_MARKER = "hr_live_"


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, key_hash). The full key is shown once, then discarded."""
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    full_key = f"{KEY_MARKER}{prefix}_{secret}"
    return full_key, prefix, hash_key(full_key)


def hash_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


def parse_key(token: str) -> str | None:
    """Extract the prefix from a presented token, or None if it is malformed."""
    if not token.startswith(KEY_MARKER):
        return None
    rest = token[len(KEY_MARKER):]
    prefix, sep, secret = rest.partition("_")
    if not sep or len(prefix) != 8 or not secret:
        return None
    return prefix


def keys_match(presented_hash: str, stored_hash: str) -> bool:
    return hmac.compare_digest(presented_hash, stored_hash)