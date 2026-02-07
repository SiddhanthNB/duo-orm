# User Guides: Pydantic Integration

Pydantic is a **core dependency** of DuoORM—no extra install flags are needed. It is an *optional layer* on top of the core CRUD API (`save`, `create`, `create_bulk`, `update`, `update_bulk`, `delete`, `delete_bulk`, `iterate`, etc.). Every helper accepts plain `dict` payloads; passing Pydantic models is a convenience that adds validation and field filtering.

For a full framework example, see [Quickstart: Framework Integration](../quickstart/fastapi.md).

## Pydantic-specific helpers

- **`Model.from_schema(payload)`** → Build an **unsaved** instance from a Pydantic model (or dict).
- **`instance.apply_schema(payload)`** → Apply a Pydantic payload **in memory only** (partial; missing/`None` skipped).
- **`instance.to_schema(SchemaClass)`** → Serialize to a Pydantic schema. Requires `model_config.from_attributes = True`; otherwise raises `duo_orm.exceptions.ValidationError`.

Core CRUD helpers (`create`, `create_bulk`, `update`, `update_bulk`, `delete`, `delete_bulk`, `iterate`, `get`, etc.) live in the [CRUD API](crud-api.md) guide. They accept dicts or Pydantic models; Pydantic just adds validation/field filtering.

## Common pitfalls

- **Missing `from_attributes` on Read schema**  
  ```python
  class Read(BaseModel):
      id: int
      # forgot: model_config = ConfigDict(from_attributes=True)
  user.to_schema(Read)  # raises duo_orm.exceptions.ValidationError
  ```
  Fix: set `model_config = ConfigDict(from_attributes=True)` (or `Config.from_attributes = True`).

- **Non-column keys are ignored** — relationships/nested fields aren’t written by schema payloads; create related rows manually.

- **Explicit `None` in dict payloads** — dicts keep `None`; Pydantic payloads drop unset/`None` fields on partial updates.

## See also
- Core CRUD methods: [CRUD API](crud-api.md)
- Query chaining and eager loading: [Querying Data](querying-data.md)
- Framework wiring: [Quickstart: Framework Integration](../quickstart/fastapi.md)

## Input rules and limits

- Payloads can be **Pydantic models or dicts**. Anything that isn’t a mapped column is silently ignored (relationships/nested fields are skipped).
- Partial updates (`apply_schema`, `update_bulk` with schemas, `instance.update(schema)`) drop missing/`None` fields for Pydantic payloads (`exclude_unset` + `exclude_none`). When you pass a plain `dict`, any explicit `None` values are kept.
- Pydantic validation runs before DuoORM writes. Serialization via `to_schema` raises a DuoORM `ValidationError` if the target schema lacks `from_attributes=True`.
- No automatic nested writes yet; manage relationships manually (create/attach related rows yourself).

## Example schemas (recommended layout)

`duo-orm init` now creates `db/schemas/__init__.py` alongside `db/models/`. Keep Pydantic schemas there to mirror your models.

```python title="db/schemas/user.py"
from pydantic import BaseModel, ConfigDict

class User:
    class Create(BaseModel):
        email: str
        name: str

    class Update(BaseModel):
        email: str | None = None
        name: str | None = None
        model_config = ConfigDict(extra="forbid")

    class Read(BaseModel):
        model_config = ConfigDict(from_attributes=True)
        id: int
        email: str
        name: str
```

## Creating and updating with schemas

```python title="async create & update"
from db.models import User
from db.schemas import User as UserSchema

# Create + save in one call from a Pydantic payload
new_user = await User.create(UserSchema.Create(email="ada@example.com", name="Ada"))

# Partial update in-place; missing fields are skipped
await new_user.update(UserSchema.Update(name="Ada Lovelace"))
```

```python title="sync create & update"
from db.models import User
from db.schemas import User as UserSchema

user = User.create(UserSchema.Create(email="sync@example.com", name="Syncy"))
user.update(UserSchema.Update(name="Syncer"))
```

## Bulk create/update with schemas

```python
from db.models import User
from db.schemas import User as UserSchema

# Bulk create from schemas; returns models when requested
created = User.create_bulk(
    [
        UserSchema.Create(email="u1@example.com", name="U1"),
        UserSchema.Create(email="u2@example.com", name="U2"),
    ],
    return_models=True,
)

# Bulk update with validation hooks, guarded by WHERE
User.where(User.email.like("u%")).update_bulk(
    UserSchema.Update(name="Updated"),
    with_hooks=True,
)
```

## Serializing to a schema

```python
from db.models import User
from db.schemas import User as UserSchema

user = await User.where(User.email == "ada@example.com").one()
dto = user.to_schema(UserSchema.Read)  # Pydantic validation happens here
```

## FastAPI example with nested schemas

Small snippet; for a complete app layout see [Quickstart: Framework Integration](../quickstart/fastapi.md).

```python title="routes.py"
from fastapi import FastAPI, Depends, HTTPException
from db.database import db
from db.models import User
from db.schemas import User as UserSchema

app = FastAPI()

async def db_session():
    async with db.transaction():
        yield

@app.post("/users/", response_model=UserSchema.Read)
async def create_user(payload: UserSchema.Create, _=Depends(db_session)):
    return await User.create(payload)

@app.patch("/users/{user_id}", response_model=UserSchema.Read)
async def update_user(user_id: int, payload: UserSchema.Update, _=Depends(db_session)):
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await user.update(payload)  # partial apply + save
    return user
```

## Quick reference (Pydantic-only helpers)

| Task | Helper | Usage |
| --- | --- | --- |
| Build unsaved instance from schema | `Model.from_schema(schema)` | `user = User.from_schema(payload)` |
| Apply schema in-memory (no save) | `instance.apply_schema(schema)` | `user.apply_schema(payload)` |
| Serialize instance to schema | `instance.to_schema(SchemaClass)` | `dto = user.to_schema(UserSchema.Read)` |

For CRUD helpers and bulk operations, see the [CRUD API guide](crud-api.md); they accept dicts or Pydantic models interchangeably.
