# User Guides: Cookbook (Advanced Patterns)

Use these end-to-end recipes to combine DuoORM features in real workflows.

## Soft deletes

Keep rows but hide them by default.

```python
# db/models/base.py
from duo_orm import Mapped, mapped_column, Boolean

class SoftDeleteMixin:
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def delete(self):
        # logical delete
        return self.update({"is_deleted": True})
```

```python
# db/models/user.py
from db.models.base import SoftDeleteMixin
from db.database import db

class User(SoftDeleteMixin, db.Model):
    __tablename__ = "users"
    # ...
```

```python
# Query helper: hide soft-deleted by default
@classmethod
def alive(cls):
    return cls.where(cls.is_deleted.is_(False))

active_users = await User.alive().order_by("id").all()
```

Notes:
- Use `require_filter=True` defaults when bulk-updating/deleting to avoid wiping all rows.
- Physical deletes are still available via `Query.delete_bulk(require_filter=False)` if you truly want to purge.

## Dynamic search API (optional filters + relationships + JSON)

```python
from duo_orm import and_, json
from db.models import User, Post

def build_search_query(filters: dict):
    qb = User.where(User.is_deleted.is_(False))

    if name := filters.get("name"):
        qb = qb.where(User.name.icontains(name))
    if min_age := filters.get("min_age"):
        qb = qb.where(User.age >= min_age)
    if tag := filters.get("tag"):
        qb = qb.related(
            User.posts,
            where=[Post.tags.contains(tag)]  # PG ARRAY or JSON tags column
        )
    if profile_flag := filters.get("profile_flag"):
        qb = qb.where(json(User.profile)["flags"][profile_flag].is_true())

    return qb

# Usage
query = build_search_query({"name": "ada", "profile_flag": "beta"})
rows = await query.order_by("-created_at").paginate(limit=50).all()
```

Notes:
- `related(..., where=[...])` pushes the filter into the related table while keeping eager loading.
- Use `json()` helper for JSON columns; see the JSON/ARRAY guide for more path/casting examples.

## Window functions with `.alchemize()`

Add windowed ranking without abandoning DuoORM setup.

```python
from duo_orm import func
from db.database import db
from db.models import Order

base = Order.where(Order.status == "completed").order_by("-created_at")
stmt = base.alchemize()

ranked = stmt.add_columns(
    func.row_number().over(partition_by=Order.customer_id, order_by=Order.created_at.desc()).label("rnk")
)

async with db.standalone_session() as session:
    async with session.begin():
        result = await session.execute(ranked)
        for order, rnk in result.all():
            ...
```

Notes:
- Start with DuoORM for filters/ordering, then extend the SQLAlchemy `Select`.
- Use `standalone_session` (or `sync_standalone_session`) when you want full control; use `db.transaction()` to stay managed.
