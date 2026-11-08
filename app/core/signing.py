import base64
import hashlib
import hmac
import time
from collections.abc import Sequence

TOLERANCE_SECONDS = 300


def _digest(secret: str, msg_id: str, timestamp: int, body: bytes) -> str:
    signed = f"{msg_id}.{timestamp}.".encode() + body
    mac = hmac.new(secret.encode(), signed, hashlib.sha256).digest()
    return base64.b64encode(mac).decode()


def sign(secrets: Sequence[str], msg_id: str, timestamp: int, body: bytes) -> str:
    return " ".join(f"v1,{_digest(s, msg_id, timestamp, body)}" for s in secrets)


def verify(
    secret: str,
    msg_id: str,
    timestamp_header: str,
    signature_header: str,
    body: bytes,
    *,
    now: float | None = None,
    tolerance: int = TOLERANCE_SECONDS,
) -> bool:
    try:
        timestamp = int(timestamp_header)
    except (TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    if abs(current - timestamp) > tolerance:
        return False
    expected = _digest(secret, msg_id, timestamp, body).encode()
    for part in signature_header.split():
        version, _, sig = part.partition(",")
        if version == "v1" and hmac.compare_digest(sig.encode(), expected):
            return True
    return False