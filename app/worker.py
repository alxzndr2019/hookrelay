import asyncio
import contextlib
import logging
import signal
from datetime import timedelta

import httpx
from sqlalchemy import func, or_, select, update

from app.core.config import get_settings
from app.db.models import Delivery, DeliveryAttempt, Endpoint, Event
from app.db.session import SessionLocal, engine
from app.delivery import Job, Result, send

log = logging.getLogger("hookrelay.worker")


async def claim(limit: int, lease_seconds: int) -> list[Job]:
    async with SessionLocal() as session, session.begin():
        rows = (
            await session.execute(
                select(Delivery, Event, Endpoint)
                .join(Event, Event.id == Delivery.event_id)
                .join(Endpoint, Endpoint.id == Delivery.endpoint_id)
                .where(
                    Delivery.status == "pending",
                    Delivery.next_attempt_at <= func.now(),
                    or_(Delivery.locked_until.is_(None), Delivery.locked_until < func.now()),
                    Endpoint.status == "active",
                )
                .order_by(Delivery.next_attempt_at)
                .limit(limit)
                .with_for_update(skip_locked=True, of=Delivery)
            )
        ).all()
        if not rows:
            return []

        await session.execute(
            update(Delivery)
            .where(Delivery.id.in_([d.id for d, _, _ in rows]))
            .values(locked_until=func.now() + timedelta(seconds=lease_seconds))
        )
        return [
            Job(
                delivery_id=d.id,
                url=ep.url,
                event_id=ev.id,
                event_type=ev.event_type,
                payload=ev.payload,
                event_created_at=ev.created_at,
            )
            for d, ev, ep in rows
        ]


async def record(job: Job, result: Result) -> None:
    async with SessionLocal() as session, session.begin():
        session.add(
            DeliveryAttempt(
                delivery_id=job.delivery_id,
                status_code=result.status_code,
                response_body=result.response_body,
                error=result.error,
                duration_ms=result.duration_ms,
            )
        )
        await session.execute(
            update(Delivery)
            .where(Delivery.id == job.delivery_id)
            .values(
                status="succeeded" if result.ok else "dead",
                attempt_count=Delivery.attempt_count + 1,
                last_attempt_at=func.now(),
                locked_until=None,
            )
        )


async def process(client: httpx.AsyncClient, job: Job) -> None:
    settings = get_settings()
    try:
        result = await send(
            client,
            job,
            timeout=settings.delivery_timeout_seconds,
            body_limit=settings.response_body_limit,
        )
    except Exception as exc:
        log.exception("unexpected error delivering %s", job.delivery_id)
        result = Result(False, None, None, f"internal error: {exc!r}"[:500], 0)

    try:
        await record(job, result)
    except Exception:
        log.exception("failed to record attempt for %s; lease will expire", job.delivery_id)
        return
    log.info("delivery %s ok=%s status=%s %sms", job.delivery_id, result.ok,
             result.status_code, result.duration_ms)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    in_flight: set[asyncio.Task] = set()
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
    timeout = httpx.Timeout(settings.delivery_timeout_seconds, connect=5.0)

    async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=False) as client:
        log.info("worker started, concurrency=%s", settings.worker_concurrency)
        while not stop.is_set():
            free = settings.worker_concurrency - len(in_flight)
            if free <= 0:
                await asyncio.wait(set(in_flight), return_when=asyncio.FIRST_COMPLETED)
                continue
            try:
                jobs = await claim(free, settings.lease_seconds)
            except Exception:
                log.exception("claim failed")
                jobs = []
                await asyncio.sleep(settings.worker_poll_seconds)

            for job in jobs:
                task = asyncio.create_task(process(client, job))
                in_flight.add(task)
                task.add_done_callback(in_flight.discard)

            if not jobs:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)

        log.info("shutting down, waiting for %s in-flight deliveries", len(in_flight))
        if in_flight:
            await asyncio.gather(*in_flight, return_exceptions=True)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())