"""PostgreSQL transaction models for the server foundation.

These models are intentionally separate from the legacy SQLite adapter. They
define the durable identity and run/telemetry records used by later workers.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    stations: Mapped[list[Station]] = relationship(back_populates="tenant")


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(160))
    province: Mapped[str] = mapped_column(String(32), default="")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    tenant: Mapped[Tenant] = relationship(back_populates="stations")

    __table_args__ = (Index("ix_stations_tenant_name", "tenant_id", "name", unique=True),)


class TelemetryPoint(Base):
    __tablename__ = "telemetry_points"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    station_id: Mapped[UUID] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"))
    device_id: Mapped[str] = mapped_column(String(120))
    point_id: Mapped[str] = mapped_column(String(120))
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingest_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    quality_code: Mapped[str] = mapped_column(String(32), default="good")
    source_protocol: Mapped[str] = mapped_column(String(32))
    raw_message_id: Mapped[str] = mapped_column(String(160), unique=True)

    __table_args__ = (
        Index("ix_telemetry_station_event", "station_id", "event_time"),
        Index("ix_telemetry_station_point_event", "station_id", "point_id", "event_time"),
    )


class RunRecord(Base):
    __tablename__ = "run_records"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    result_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_runs_tenant_created", "tenant_id", "created_at"),)
