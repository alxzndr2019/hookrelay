import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentKey
from app.api.schemas import EventAccepted, EventCreate
from app.db.models import Delivery, Endpoint, Event
from app.db.session import get_session

router = APIRouter(prefix="/v1/events", tags=["events"])

Session = Annotated[AsyncSession, Depends(get_session)]
IdempotencyKey = Annotated[str | None, Header(min_length=1, max_length=255)]

MAX_PAYLOAD_BYTES = 256 * 1024


@router.post("", response_model=EventAccepted, status_code=status.HTTP_202_ACCEPTED)
async def publish_event(
    body: EventCreate,
    key: CurrentKey,
    session: Session,
    response: Response,
    idempotency_key: IdempotencyKey = None,
):
    size = len(json.dumps(body.payload, separators=(",", ":")).encode())
    if size > MAX_PAYLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Payload too large")

    insert_stmt = (
        pg_insert(Event)
        .values(
            id=uuid.uuid4(),
            application_id=key.application_id,
            event_type=body.event_type,
            payload=body.payload,
            idempotency_key=idempotency_key,
        )
        .on_conflict_do_nothing(constraint="uq_events_app_idempotency")
        .returning(Event.id, Event.created_at)
    )
    row = (await session.execute(insert_stmt)).first()

    if row is None:
        return await _replay(session, key, body, idempotency_key, response)

    event_id, created_at = row
    endpoint_ids = (
        await session.execute(
            select(Endpoint.id).where(
                Endpoint.application_id == key.application_id,
                Endpoint.status == "active",
                or_(
                    Endpoint.event_types.contains([body.event_type]),
                    Endpoint.event_types.contains(["*"]),
                ),
            )
        )
    ).scalars().all()

    session.add_all([Delivery(event_id=event_id, endpoint_id=eid) for eid in endpoint_ids])
    await session.commit()

    return EventAccepted(
        id=event_id,
        event_type=body.event_type,
        created_at=created_at,
        deliveries_created=len(endpoint_ids),
    )


async def _replay(
    session: AsyncSession,
    key: CurrentKey,
    body: EventCreate,
    idempotency_key: str | None,
    response: Response,
) -> EventAccepted:
    existing = (
        await session.execute(
            select(Event).where(
                Event.application_id == key.application_id,
                Event.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one()

    if existing.event_type != body.event_type or existing.payload != body.payload:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Idempotency-Key was already used with a different request",
        )

    count = (
        await session.execute(
            select(func.count()).select_from(Delivery).where(Delivery.event_id == existing.id)
        )
    ).scalar_one()

    response.headers["Idempotent-Replayed"] = "true"
    return EventAccepted(
        id=existing.id,
        event_type=existing.event_type,
        created_at=existing.created_at,
        deliveries_created=count,
    )