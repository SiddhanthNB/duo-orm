from __future__ import annotations

from typing import Any, Dict, Type

from sqlalchemy import inspect as sa_inspect

from .exceptions import ValidationError

from pydantic import BaseModel, ValidationError as PydanticValidationError


def coerce_payload(obj: Any, *, partial: bool, model_cls: Type) -> Dict[str, Any]:
    """Normalize incoming data (dict or Pydantic model) to a plain dict of column keys.

    Args:
        obj: dict or pydantic BaseModel (or None treated as empty dict).
        partial: if True, drop unset/None fields (for updates); if False, include all.
        model_cls: model class used to filter to mapped columns.

    Returns:
        dict of column-key -> value suitable for constructing or updating the model.
    """
    if obj is None:
        data: Dict[str, Any] = {}
    elif isinstance(obj, BaseModel):
        try:
            validated = type(obj).model_validate(obj)
            data = validated.model_dump(exclude_none=partial, exclude_unset=partial)
        except PydanticValidationError as exc:
            raise ValidationError(str(exc)) from exc
    elif isinstance(obj, dict):
        data = dict(obj)
    else:
        raise ValidationError("Expected a dict or Pydantic BaseModel as payload.")

    mapper = sa_inspect(model_cls)
    column_keys = {col.key for col in mapper.columns}
    guarded_fields = set(getattr(model_cls, "__guarded__", ()))
    pk_keys = {col.key for col in mapper.primary_key}
    guarded_fields.update(pk_keys)

    # Allow PKs on create (partial=False) so required keys can be provided,
    # but still block __guarded__ fields always.
    effective_guarded = guarded_fields if partial else (guarded_fields - pk_keys)

    return {k: v for k, v in data.items() if k in column_keys and k not in effective_guarded}
