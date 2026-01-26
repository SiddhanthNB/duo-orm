from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import DateTime, Integer, Identity

from duo_orm import Mapped, mapped_column


def test_basemodel_helpers_and_timestamps(db, db_target):
    class Thing(db.Model):
        __tablename__ = "things_extra"
        id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
        created: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), info={"set_on": "create"}, nullable=True
        )
        updated: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), info={"set_on": {"create", "update"}}, nullable=True
        )
        auto_now: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), info={"auto_now": True}, nullable=True
        )
        auto_add: Mapped[datetime | None] = mapped_column(
            DateTime(timezone=True), info={"auto_now_add": True}, nullable=True
        )

    db.metadata.create_all(db.sync_engine)
    try:
        t = Thing()
        t.save()

        assert Thing.all()
        assert Thing.first() is not None
        assert Thing.fields()

        # Update path triggers update timestamp hooks
        t.save()

        # Paginate should still work
        qb = Thing.paginate(10, 0)
        if db_target.dialect == "mssql":
            qb = qb.order_by("id")  # MSSQL requires ORDER BY for OFFSET/FETCH
        assert qb.all()
    finally:
        db.metadata.drop_all(db.sync_engine)
