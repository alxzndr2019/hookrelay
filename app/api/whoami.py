from fastapi import APIRouter

from app.api.deps import CurrentKey

router = APIRouter(tags=["auth"])


@router.get("/v1/whoami")
async def whoami(key: CurrentKey) -> dict[str, str]:
    return {"application_id": str(key.application_id), "key_prefix": key.prefix}