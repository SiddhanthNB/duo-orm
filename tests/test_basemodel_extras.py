from __future__ import annotations

def test_all_returns_rows(db_session, model_registry):
    Thing = model_registry.Thing

    Thing().save()
    rows = Thing.all()
    assert len(rows) == 1


def test_first_returns_instance(db_session, model_registry):
    Thing = model_registry.Thing

    Thing().save()
    first = Thing.first()
    assert first is not None


def test_fields_includes_primary_key(db_session, model_registry):
    Thing = model_registry.Thing

    Thing().save()
    fields = Thing.fields()
    assert "id" in fields


def test_timestamp_helpers_update(db_session, model_registry):
    Thing = model_registry.Thing

    t = Thing()
    t.save()
    created = t.created
    updated = t.updated
    auto_now = t.auto_now
    auto_add = t.auto_add

    t.save()
    assert t.created == created
    assert t.updated is not None and t.updated >= updated
    assert t.auto_add == auto_add
    assert t.auto_now is not None and t.auto_now >= auto_now


def test_paginate_returns_results(db_session, db_target, model_registry):
    Thing = model_registry.Thing

    Thing().save()
    qb = Thing.paginate(10, 0)
    if db_target.dialect == "mssql":
        qb = qb.order_by("id")  # MSSQL requires ORDER BY for OFFSET/FETCH
    assert len(qb.all()) == 1
