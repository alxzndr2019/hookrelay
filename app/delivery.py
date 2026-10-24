import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime

import httpx


@dataclass(frozen=True)
class Job:
    delivery_id: uuid.UUID
    url: str
    event_id: uuid.UUID
    event_type: str
    payload: dict
    event_created_at: datetime


@dataclass(frozen=True)
class Result:
    ok: bool
    status_code: int | None
    response_body: str | None
    error: str | None
    duration_ms: int


def build_body(job: Job) -> bytes:
    envelope = {
        "id": str(job.event_id),
        "type": job.event_type,
        "created_at": job.event_created_at.isoformat(),
        "data": job.payload,
    }
    return json.dumps(envelope, separators=(",", ":")).encode()


async def send(client: httpx.AsyncClient, job: Job, *, timeout: float, body_limit: int) -> Result:
    body = build_body(job)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "HookRelay/0.1",
        "Webhook-Id": str(job.event_id),
    }
    started = time.monotonic()
    status_code: int | None = None
    text: str | None = None
    error: str | None = None

    try:
        async with asyncio.timeout(timeout):
            async with client.stream("POST", job.url, content=body, headers=headers) as resp:
                status_code = resp.status_code
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= body_limit:
                        break
                raw = b"".join(chunks)[:body_limit]
                text = raw.decode("utf-8", errors="replace").replace("\x00", "")
    except TimeoutError:
        error = f"timeout after {timeout}s"
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        error = f"{type(exc).__name__}: {exc}"[:500]

    duration_ms = int((time.monotonic() - started) * 1000)
    ok = error is None and status_code is not None and 200 <= status_code < 300
    return Result(ok, status_code, text, error, duration_ms)