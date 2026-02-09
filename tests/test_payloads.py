from __future__ import annotations

import pytest
from pydantic import BaseModel

from duo_orm._payloads import coerce_payload
from duo_orm.exceptions import ValidationError


def test_coerce_payload_none_returns_empty_dict(model_registry):
    User = model_registry.User
    assert coerce_payload(None, partial=False, model_cls=User) == {}


def test_coerce_payload_rejects_invalid_type(model_registry):
    User = model_registry.User
    with pytest.raises(ValidationError, match="Expected a dict"):
        coerce_payload(["bad"], partial=False, model_cls=User)


def test_coerce_payload_wraps_pydantic_validation_error(model_registry):
    class Payload(BaseModel):
        model_config = {"revalidate_instances": "always"}
        age: int

    bad = Payload.model_construct(age="nope")
    with pytest.raises(ValidationError):
        coerce_payload(bad, partial=False, model_cls=model_registry.User)
