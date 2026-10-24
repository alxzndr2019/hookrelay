from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_key, keys_match, parse_key
from app.db.models import ApiKey
from app.db.session import get_session

bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or missing API key",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApiKey:
    if credentials is None:
        raise _UNAUTHORIZED
    token = credentials.credentials

    prefix = parse_key(token)
    if prefix is None:
        raise _UNAUTHORIZED

    result = await session.execute(select(ApiKey).where(ApiKey.prefix == prefix))
    api_key = result.scalar_one_or_none()

    if api_key is None or api_key.revoked_at is not None:
        raise _UNAUTHORIZED
    if not keys_match(hash_key(token), api_key.key_hash):
        raise _UNAUTHORIZED

    return api_key


CurrentKey = Annotated[ApiKey, Depends(get_current_key)]