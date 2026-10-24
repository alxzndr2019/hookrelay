import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentKey
from app.api.schemas import EndpointCreate, EndpointCreated, EndpointOut, EndpointUpdate
from app.core.security import generate_signing_secret
from app.db.models import Endpoint, EndpointSecret
from app.db.session import get_session

router = APIRouter(prefix="/v1/endpoints", tags=["endpoints"])

Session = Annotated[AsyncSession, Depends(get_session)]


async def _get_owned(session: AsyncSession, key: CurrentKey, endpoint_id: uuid.UUID) -> Endpoint:
    result = await session.execute(
        select(Endpoint).where(
            Endpoint.id == endpoint_id, Endpoint.application_id == key.application_id
        )
    )
    endpoint = result.scalar_one_or_none()
    if endpoint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Endpoint not found")
    return endpoint


@router.post("", response_model=EndpointCreated, status_code=status.HTTP_201_CREATED)
async def create_endpoint(body: EndpointCreate, key: CurrentKey, session: Session):
    endpoint = Endpoint(
        application_id=key.application_id,
        url=body.url,
        description=body.description,
        event_types=body.event_types,
    )
    session.add(endpoint)
    await session.flush()

    secret = generate_signing_secret()
    session.add(EndpointSecret(endpoint_id=endpoint.id, secret=secret))
    await session.commit()
    await session.refresh(endpoint)

    out = EndpointOut.model_validate(endpoint)
    return EndpointCreated(**out.model_dump(), secret=secret)


@router.get("", response_model=list[EndpointOut])
async def list_endpoints(key: CurrentKey, session: Session, limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 100))
    result = await session.execute(
        select(Endpoint)
        .where(Endpoint.application_id == key.application_id)
        .order_by(Endpoint.created_at.desc(), Endpoint.id)
        .limit(limit)
        .offset(max(0, offset))
    )
    return result.scalars().all()


@router.get("/{endpoint_id}", response_model=EndpointOut)
async def get_endpoint(endpoint_id: uuid.UUID, key: CurrentKey, session: Session):
    return await _get_owned(session, key, endpoint_id)


@router.patch("/{endpoint_id}", response_model=EndpointOut)
async def update_endpoint(
    endpoint_id: uuid.UUID, body: EndpointUpdate, key: CurrentKey, session: Session
):
    endpoint = await _get_owned(session, key, endpoint_id)
    changes = body.model_dump(exclude_unset=True)

    if changes.get("status") == "active" and endpoint.status == "disabled":
        endpoint.consecutive_failures = 0
        endpoint.disabled_reason = None
    for field, value in changes.items():
        if value is None and field != "description":
            continue
        setattr(endpoint, field, value)

    await session.commit()
    await session.refresh(endpoint)
    return endpoint


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(endpoint_id: uuid.UUID, key: CurrentKey, session: Session):
    endpoint = await _get_owned(session, key, endpoint_id)
    await session.delete(endpoint)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)