from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


@pytest.fixture
def artifact_model(db_session, model_registry):
    if model_registry.Artifact is None:
        pytest.skip("SQLAlchemy UUID type not available in this environment.")
    return model_registry.Artifact, db_session


def test_datatype_roundtrip(artifact_model):
    Artifact, _ = artifact_model

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
