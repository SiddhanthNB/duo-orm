# User Guides: Defining Models

Models are the heart of your application's data layer. In DuoORM, a model is a Python class that inherits from the `db.Model` base class provided by your `Database` instance. Each model maps to a table in your database.

## Basic Model Definition

To define a model, create a class that inherits from `db.Model` and include a `__tablename__` attribute. Columns are defined using type annotations with `Mapped` and `mapped_column` from `duo_orm` (which re-exports them from SQLAlchemy).

```python
from duo_orm import Mapped, mapped_column
from ..database import db

class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    age: Mapped[int]
```

DuoORM uses modern SQLAlchemy 2.0 syntax, which relies on `Mapped` to indicate which attributes are part of the database mapping.

!!! tip
    All your models should inherit from the **same** `db.Model` object. This is how DuoORM associates your models with the correct database connection and metadata.

## Column Configuration

You can configure columns by passing arguments to `mapped_column`. This is where you set primary keys, default values, constraints, and more.

```python
from datetime import datetime
from duo_orm import Mapped, mapped_column, String, DateTime, func
from ..database import db

class Product(db.Model):
    __tablename__ = "products"

    # A primary key that auto-increments
    id: Mapped[int] = mapped_column(primary_key=True)

    # A string column with a max length
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # A column with a server-side default value
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # A nullable column
    description: Mapped[str | None]
```

DuoORM re-exports all of SQLAlchemy's standard types and constraints, so you can import them directly from `duo_orm`.

## Automatic Timestamps

DuoORM provides a declarative, Django-style way to automatically manage creation and update timestamps. You can add `info` flags to a `mapped_column` to control this behavior.

- `info={"set_on": "create"}`: The field will be set to the current UTC timestamp only when the record is first inserted.
- `info={"set_on": {"create", "update"}}`: The field will be set on insert and also every time the record is updated via `.save()`.

```python
from datetime import datetime
from duo_orm import Mapped, mapped_column, DateTime
from ..database import db

class Order(db.Model):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)

    # Set once on creation
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        info={"set_on": "create"}
    )

    # Set on creation AND on every update
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        info={"set_on": {"create", "update"}}
    )

# --- Usage ---
# order = Order()
# await order.save()
#
# # order.created_at is now set
# # order.updated_at is now set
#
# # ... later ...
# await order.save()
#
# # order.created_at remains the same
# # order.updated_at is updated to the new current time
```

!!! warning
    These timestamp hooks are executed in Python code right before the `INSERT` or `UPDATE` statement is sent to the database. For this reason, they are not compatible with `server_default`. Use one or the other.

!!! tip
    Pydantic is optional. You can pass dicts to all CRUD helpers. If you want schema validation/serialization, see the [Pydantic Integration](pydantic-integration.md) guide.

## Model Validation

You can enforce custom business logic by overriding the `.validate()` method on your model. This method is automatically called before any `.save()` or `.create_bulk()` operation.

If validation fails, raise a `ValidationError` from `duo_orm.exceptions`.

```python
from duo_orm import Mapped, mapped_column, ValidationError
from ..database import db

class User(db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    age: Mapped[int]

    def validate(self):
        """Custom validation logic."""
        if self.age < 18:
            raise ValidationError(
                "Users must be at least 18 years old.",
                field="age"
            )

# --- Usage ---
#
# # This will succeed
# user_ok = User(name="Alice", age=30)
# await user_ok.save()
#
# # This will fail
# user_invalid = User(name="Bob", age=15)
# try:
#     await user_invalid.save()
# except ValidationError as e:
#     print(f"Validation failed for field '{e.field}': {e}")

```

## Defining Relationships

You can define relationships between your models using `relationship` from `duo_orm`. This allows you to navigate between related objects in your code.

### Many-to-One

A `Post` belongs to a `User`. This requires a foreign key column on the "many" side.

```python title="models/post.py"
from duo_orm import Mapped, mapped_column, relationship, ForeignKey
from .user import User
from ..database import db

class Post(db.Model):
    __tablename__ = "posts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]

    # Foreign key to the users table
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Relationship to the User object
    author: Mapped["User"] = relationship(back_populates="posts")
```

### One-to-Many

A `User` can have many `Post`s. The `back_populates` argument is crucial because it links the two sides of the relationship together.

```python title="models/user.py"
from typing import List
from duo_orm import Mapped, mapped_column, relationship
from .post import Post
from ..database import db

class User(db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

    # Relationship to the list of Post objects
    posts: Mapped[List["Post"]] = relationship(back_populates="author")
```

With this setup, you can access `user.posts` to get a list of post objects, and `post.author` to get the user object. To learn how to efficiently query and load these relationships, see the [Querying Data](querying-data.md) guide.
