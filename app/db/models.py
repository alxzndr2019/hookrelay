import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def created_at_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    created_at: Mapped[datetime] = created_at_col()


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("account_id", "name", name="uq_applications_account_name"),)

    id: Mapped[uuid.UUID] = pk()
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = created_at_col()

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    prefix: Mapped[str] = mapped_column(String(16), unique=True)
    key_hash: Mapped[str] = mapped_column(String(64))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()

class Endpoint(Base):
    __tablename__ = "endpoints"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused', 'disabled')", name="ck_endpoints_status"),
        Index("ix_endpoints_event_types", "event_types", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    event_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]")
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    disabled_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EndpointSecret(Base):
    __tablename__ = "endpoint_secrets"

    id: Mapped[uuid.UUID] = pk()
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("endpoints.id", ondelete="CASCADE"), index=True
    )
    secret: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = created_at_col()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("application_id", "idempotency_key", name="uq_events_app_idempotency"),
        Index("ix_events_app_created", "application_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = pk()
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE")
    )
    event_type: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict] = mapped_column(JSONB)
    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = created_at_col()

class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("event_id", "endpoint_id", name="uq_deliveries_event_endpoint"),
        CheckConstraint("status IN ('pending', 'succeeded', 'dead')", name="ck_deliveries_status"),
        Index("ix_deliveries_due", "next_attempt_at", postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[uuid.UUID] = pk()
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("endpoints.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_col()


class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    __table_args__ = (Index("ix_attempts_delivery_time", "delivery_id", "attempted_at"),)

    id: Mapped[uuid.UUID] = pk()
    delivery_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deliveries.id", ondelete="CASCADE"))
    attempted_at: Mapped[datetime] = created_at_col()
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)