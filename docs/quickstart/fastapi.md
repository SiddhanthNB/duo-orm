# Quickstart: Framework Integration (FastAPI example)

This page shows a complete integration using FastAPI. The same pattern (per-request transaction dependency + model hooks) works with other ASGI frameworks like Starlette or Starlite. Pydantic is a core dependency, but all helpers also accept plain dictionaries.

## Layout

```
app/
├── main.py
├── deps.py
├── db/
│   ├── database.py
│   ├── models/
│   │   └── user.py
│   └── schemas/
│       └── user.py
└── routers/
    └── users.py
```

## Database

```python title="db/database.py"
from duo_orm import Database

# driverless URL; async engine is built by default (derive_async=True)
db = Database("sqlite:///./app.db")
```

!!! note
    If you set `derive_async=False`, only the sync engine is available; async calls will raise. For Starlette/other ASGI, keep async enabled.

## Schemas (optional layer)

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

## Model with validation

```python title="db/models/user.py"
from duo_orm import Mapped, mapped_column, String
from duo_orm.exceptions import ValidationError
from ..database import db

class User(db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    def validate(self):
        if not self.email:
            raise ValidationError("email required", field="email")
```

## Dependency: one transaction per request

```python title="deps.py"
from db.database import db

async def unit_of_work():
    async with db.transaction():
        yield
```

## Router

```python title="routers/users.py"
from fastapi import APIRouter, Depends, HTTPException
from db.models import User
from db.schemas import User as UserSchema
from deps import unit_of_work

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/", response_model=UserSchema.Read, dependencies=[Depends(unit_of_work)])
async def create_user(payload: UserSchema.Create):
    return await User.create(payload)  # runs validate() + timestamp hooks

@router.get("/", response_model=list[UserSchema.Read], dependencies=[Depends(unit_of_work)])
async def list_users():
    users = await User.order_by("id").all()
    return [u.to_schema(UserSchema.Read) for u in users]

@router.patch("/{user_id}", response_model=UserSchema.Read, dependencies=[Depends(unit_of_work)])
async def update_user(user_id: int, payload: UserSchema.Update):
    user = await User.get(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    await user.update(payload)
    return user

@router.post("/bulk-bump", response_model=int, dependencies=[Depends(unit_of_work)])
async def bump_all():
    # with_hooks=True loads rows in batches, runs validate() + timestamp hooks
    await User.where(User.id > 0).update_bulk({"name": User.name + "!"}, with_hooks=True)
    return await User.count()
```

## App entrypoint

```python title="main.py"
from fastapi import FastAPI
from routers.users import router as users_router

app = FastAPI()
app.include_router(users_router)
```

How it fits together:
- FastAPI validates request bodies via Pydantic schemas (or you can pass dicts).
- `unit_of_work` wraps each request in `db.transaction()`, so all ORM calls share one async session and commit/rollback together.
- Model hooks (`validate`, timestamp fields) run on `save`/`create`/`update` and on bulk operations when `with_hooks=True`.
- Responses use `to_schema` to serialize safely; set `from_attributes=True` on read schemas.

Other frameworks:
- **Starlette/Starlite**: use the same dependency pattern; call `async with db.transaction():` inside middleware or dependency.
- **Sync-only apps**: set `derive_async=False` in `Database(...)` and expose sync endpoints; keep the transaction dependency as `with db.transaction():`.
