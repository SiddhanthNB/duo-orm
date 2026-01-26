from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import DateTime, LargeBinary, String, Text, Integer, Identity

from duo_orm import Mapped, mapped_column


@pytest.fixture
def datatype_model(db, db_target):
    if db_target.is_async:
        pytest.skip("Data-type roundtrips run on sync engines.")

    # Prefer the generic UUID type; fall back to dialect-specific if available.
    uuid_type = None
    try:
        from sqlalchemy import Uuid as _UUID

        uuid_type = _UUID
    except Exception:
        try:
            from sqlalchemy.dialects.postgresql import UUID as _PGUUID  # type: ignore

            uuid_type = _PGUUID
        except Exception:
            uuid_type = None

    if uuid_type is None:
        pytest.skip("SQLAlchemy UUID type not available in this environment.")

    class Artifact(db.Model):
        __tablename__ = "artifacts"
        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        artifact_id: Mapped[uuid.UUID] = mapped_column(uuid_type(as_uuid=True), nullable=False)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
        payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
        notes: Mapped[str] = mapped_column(Text, nullable=False)
        tag: Mapped[str] = mapped_column(String(255), nullable=False)

    db.metadata.drop_all(db.sync_engine)
    db.metadata.create_all(db.sync_engine)
    try:
        yield Artifact, db
    finally:
        db.metadata.drop_all(db.sync_engine)


def test_datatype_roundtrip(datatype_model):
    Artifact, db = datatype_model

    artifact_id = uuid.uuid4()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = b"\x00\x01binary-payload\xff"
    notes = "unicode text payload"

    saved = Artifact(
        artifact_id=artifact_id,
        created_at=now,
        payload=payload,
        notes=notes,
        tag="sample",
    )
    saved.save()

    fetched = Artifact.where(Artifact.tag == "sample").first()
    assert fetched is not None
    assert fetched.artifact_id == artifact_id
    # Some dialects drop tzinfo; normalize to UTC before comparison.
    assert fetched.created_at.replace(tzinfo=timezone.utc) == now
    assert bytes(fetched.payload) == payload
    assert fetched.notes == notes
