from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Optional

from duo_orm import (
    ARRAY,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    JSON as SAJSON,
    LargeBinary,
    Mapped,
    PG_ARRAY,
    String,
    Text,
    UUID,
    mapped_column,
    relationship,
)
from duo_orm.exceptions import ValidationError

_CACHE_KEY = "_test_model_registry"


def _int_pk_factory(db):
    use_identity = db.sync_engine.dialect.name == "oracle"

    def _int_pk():
        if use_identity:
            return mapped_column(Integer, Identity(), primary_key=True)
        return mapped_column(Integer, primary_key=True)

    return _int_pk


def _supports_uuid(db) -> bool:
    # Limit UUID usage to dialects known to accept it in DDL.
    return db.sync_engine.dialect.name in {"postgresql", "mysql", "mssql", "sqlite"}


@dataclass(frozen=True)
class ModelRegistry:
    User: type
    Post: type
    Thing: type
    Compound: type
    Audit: type
    GroupQH: type
    CommentNest: type
    CommentRel: type
    CommentRelated: type
    DepthA: type
    DepthB: type
    DepthC: type
    UserDepth: type
    Number: type
    JsonDoc: type
    BagInt: type
    ArrayItem: Optional[type]
    Artifact: Optional[type]


def registry(db) -> ModelRegistry:
    cached = getattr(db, _CACHE_KEY, None)
    if cached is not None:
        return cached
    int_pk = _int_pk_factory(db)

    class User(db.Model):
        __tablename__ = "duo_users"

        id: Mapped[int] = int_pk()
        name: Mapped[str] = mapped_column(String(255), nullable=False)
        age: Mapped[int] = mapped_column(nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), info={"set_on": "create"}, nullable=True
        )
        updated_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), info={"set_on": {"create", "update"}}, nullable=True
        )
        posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")
        groups_qh = relationship("GroupQH", back_populates="user")

        def validate(self):
            if self.age < 0:
                raise ValidationError("age must be non-negative", field="age")

    class Post(db.Model):
        __tablename__ = "duo_posts"

        id: Mapped[int] = int_pk()
        title: Mapped[str] = mapped_column(String(255), nullable=False)
        author_id: Mapped[int] = mapped_column(ForeignKey("duo_users.id"), nullable=False)
        author = relationship("User", back_populates="posts")

    class Thing(db.Model):
        __tablename__ = "things_extra"

        id: Mapped[int] = int_pk()
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

    class Compound(db.Model):
        __tablename__ = "compound_get"

        org_id: Mapped[int] = mapped_column(Integer, primary_key=True)
        code: Mapped[str] = mapped_column(String(20), primary_key=True)
        name: Mapped[str] = mapped_column(String(50))

    class Audit(db.Model):
        __tablename__ = "audit_logs"

        id: Mapped[int] = int_pk()
        user_id: Mapped[int] = mapped_column(nullable=False)
        ts: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
        action: Mapped[str] = mapped_column(String(255), nullable=False)

    class GroupQH(db.Model):
        __tablename__ = "groups_qh"

        id: Mapped[int] = int_pk()
        user_id: Mapped[int] = mapped_column(ForeignKey("duo_users.id"), nullable=False)
        name: Mapped[str] = mapped_column(String(50), nullable=False)
        user = relationship("User", back_populates="groups_qh")

    class CommentNest(db.Model):
        __tablename__ = "comments_nest"

        id: Mapped[int] = int_pk()
        post_id: Mapped[int] = mapped_column(ForeignKey("duo_posts.id"), nullable=False)
        body: Mapped[str] = mapped_column(String(255), nullable=False)
        post = relationship("Post", backref="comments_nest")

    class CommentRel(db.Model):
        __tablename__ = "comments_rel"

        id: Mapped[int] = int_pk()
        post_id: Mapped[int] = mapped_column(ForeignKey("duo_posts.id"), nullable=False)
        body: Mapped[str] = mapped_column(String(255), nullable=False)
        post = relationship("Post", backref="comments_rel_test")

    class CommentRelated(db.Model):
        __tablename__ = "comments_related"

        id: Mapped[int] = int_pk()
        post_id: Mapped[int] = mapped_column(ForeignKey("duo_posts.id"), nullable=False)
        body: Mapped[str] = mapped_column(String(100), nullable=False)
        post = relationship("Post", backref="comments_related")

    class DepthA(db.Model):
        __tablename__ = "a_depth"

        id: Mapped[int] = int_pk()
        users = relationship("UserDepth", back_populates="a")

    class DepthB(db.Model):
        __tablename__ = "b_depth"

        id: Mapped[int] = int_pk()
        a_id: Mapped[int] = mapped_column(ForeignKey("a_depth.id"))
        a = relationship("DepthA", back_populates="bs")

    class DepthC(db.Model):
        __tablename__ = "c_depth"

        id: Mapped[int] = int_pk()
        b_id: Mapped[int] = mapped_column(ForeignKey("b_depth.id"))
        b = relationship("DepthB", back_populates="cs")

    class UserDepth(db.Model):
        __tablename__ = "user_depth"

        id: Mapped[int] = int_pk()
        a_id: Mapped[int] = mapped_column(ForeignKey("a_depth.id"))
        a = relationship("DepthA", back_populates="users")

    DepthA.bs = relationship("DepthB", back_populates="a")  # type: ignore[attr-defined]
    DepthB.cs = relationship("DepthC", back_populates="b")  # type: ignore[attr-defined]

    class Number(db.Model):
        __tablename__ = "nums_patch"

        id: Mapped[int] = int_pk()
        value: Mapped[int] = mapped_column(nullable=False)

    class JsonDoc(db.Model):
        __tablename__ = "docs"

        id: Mapped[int] = int_pk()
        profile: Mapped[dict] = mapped_column(SAJSON, nullable=False)
        label: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    class BagInt(db.Model):
        __tablename__ = "bags_qh"

        id: Mapped[int] = int_pk()
        tags: Mapped[list[int]] = mapped_column(ARRAY(Integer))

    class ArrayItem(db.Model):
        __tablename__ = "items"

        id: Mapped[int] = int_pk()
        tags: Mapped[list[str]] = mapped_column(PG_ARRAY(String), nullable=False)

    Artifact = None
    if _supports_uuid(db):
        class Artifact(db.Model):
            __tablename__ = "artifacts"

            id: Mapped[int] = int_pk()
            artifact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
            created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
            payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
            notes: Mapped[str] = mapped_column(Text, nullable=False)
            tag: Mapped[str] = mapped_column(String(255), nullable=False)

    reg = ModelRegistry(
        User=User,
        Post=Post,
        Thing=Thing,
        Compound=Compound,
        Audit=Audit,
        GroupQH=GroupQH,
        CommentNest=CommentNest,
        CommentRel=CommentRel,
        CommentRelated=CommentRelated,
        DepthA=DepthA,
        DepthB=DepthB,
        DepthC=DepthC,
        UserDepth=UserDepth,
        Number=Number,
        JsonDoc=JsonDoc,
        BagInt=BagInt,
        ArrayItem=ArrayItem,
        Artifact=Artifact,
    )

    setattr(db, _CACHE_KEY, reg)
    return reg


def schema_tables(db, db_target, reg: ModelRegistry):
    include = {
        reg.User.__table__,
        reg.Post.__table__,
        reg.Thing.__table__,
        reg.Compound.__table__,
        reg.Audit.__table__,
        reg.GroupQH.__table__,
        reg.CommentNest.__table__,
        reg.CommentRel.__table__,
        reg.CommentRelated.__table__,
        reg.Number.__table__,
    }
    if db_target.supports_json:
        include.add(reg.JsonDoc.__table__)
    if reg.Artifact is not None:
        include.add(reg.Artifact.__table__)
    if db_target.supports_array:
        include.add(reg.BagInt.__table__)
        if reg.ArrayItem is not None:
            include.add(reg.ArrayItem.__table__)

    return [table for table in db.metadata.sorted_tables if table in include]
