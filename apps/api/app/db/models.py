from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    language: Mapped[str] = mapped_column(String(8), default="en")  # "en" | "hi" | "mixed"
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|completed|abandoned
    # Captured up-front in the splash form, before the chat begins. Both nullable
    # because rows created before the splash existed (or by a future API client
    # that bypasses it) won't have them.
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all,delete"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_messages_session_seq"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant|system
    content: Mapped[str] = mapped_column(Text)
    widget: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped[Session] = relationship(back_populates="messages")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("session_id", "doc_type", name="uq_documents_session_doctype"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    doc_type: Mapped[str] = mapped_column(String(16))  # "aadhaar" | "pan"
    file_path: Mapped[str] = mapped_column(String(512))
    photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    extracted_json: Mapped[dict] = mapped_column(JSONB)
    confirmed_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ocr_confidence: Mapped[str] = mapped_column(String(8), default="medium")  # low|medium|high
    engine: Mapped[str] = mapped_column(String(16), default="ollama_vision")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ValidationResult(Base):
    __tablename__ = "validation_results"
    __table_args__ = (UniqueConstraint("session_id", name="uq_validation_session"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    overall_score: Mapped[float] = mapped_column(Float)  # 0..100
    checks: Mapped[list] = mapped_column(JSONB)  # [{name, status, score, detail}]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Selfie(Base):
    __tablename__ = "selfies"
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    file_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FaceCheck(Base):
    __tablename__ = "face_checks"
    __table_args__ = (
        UniqueConstraint("session_id", "selfie_id", name="uq_face_check_session_selfie"),
    )
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    selfie_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("selfies.id"))
    verified: Mapped[bool] = mapped_column(Boolean)
    distance: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)  # 0..100
    predicted_gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    aadhaar_gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    gender_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    model: Mapped[str] = mapped_column(String(32), default="VGG-Face")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IPCheck(Base):
    __tablename__ = "ip_checks"
    __table_args__ = (UniqueConstraint("session_id", name="uq_ip_check_session"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    ip: Mapped[str] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    aadhaar_city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    aadhaar_state: Mapped[str | None] = mapped_column(String(128), nullable=True)
    city_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    state_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    country_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ComplianceQna(Base):
    __tablename__ = "compliance_qna"
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSONB)  # [{source, chunk_id, score}]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class KYCRecord(Base):
    __tablename__ = "kyc_records"
    __table_args__ = (UniqueConstraint("session_id", name="uq_kyc_records_session"),)
    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(16))  # approved|flagged|rejected
    decision_reason: Mapped[str] = mapped_column(Text)
    flags: Mapped[list] = mapped_column(JSONB, default=list)
    recommendations: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
