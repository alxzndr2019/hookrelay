import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import get_settings
from app.core.urls import validate_endpoint_url

EventType = Field(min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9_.\-*]+$")


def _check_url(value: str) -> str:
    try:
        return validate_endpoint_url(
            value, allow_http=get_settings().allow_insecure_endpoints
        )
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


class EndpointCreate(BaseModel):
    url: str
    description: str | None = Field(default=None, max_length=255)
    event_types: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        return _check_url(v)


class EndpointUpdate(BaseModel):
    url: str | None = None
    description: str | None = Field(default=None, max_length=255)
    event_types: list[str] | None = Field(default=None, max_length=50)
    status: Literal["active", "paused"] | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        return None if v is None else _check_url(v)


class EndpointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    description: str | None
    status: str
    event_types: list[str]
    consecutive_failures: int
    disabled_reason: str | None
    created_at: datetime


class EndpointCreated(EndpointOut):
    secret: str


class EventCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=255, pattern=r"^[a-zA-Z0-9_.\-]+$")
    payload: dict


class EventAccepted(BaseModel):
    id: uuid.UUID
    event_type: str
    created_at: datetime
    deliveries_created: int