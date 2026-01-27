# Quickstart

This guide walks through setup and the two core usage modes: standalone (default) and transactions for related graphs.

## Setup

### Install

```bash
pip install duo-orm
```

Use **driverless URLs** (e.g., `postgresql://...`, `sqlite:///...`); the ORM injects the right drivers.

### Scaffold the project

Create the recommended layout (database entrypoint, models package, migrations).

```bash
duo-orm init
```

Result:

```
.
├── db/
│   ├── database.py
│   ├── models/
│   │   └── __init__.py
│   └── migrations/
│       ├── alembic.ini
│       ├── env.py
│       └── ...
└── pyproject.toml
```

Need a different location? Run:

```bash
duo-orm init --dir path/to/db
```

This creates or updates `pyproject.toml` so future migration commands find your db stack:

```toml title="pyproject.toml"
[tool.duo-orm]
duo_orm_dir = "path/to/db"
```

### Configure the database

Edit `db/database.py` to set your connection.

```python title="db/database.py"
from duo_orm import Database

db = Database("sqlite:///./test.db")  # driverless URL; drivers managed for you
```

### Define models

Create `db/models/user.py` and `db/models/post.py`.

```python title="db/models/user.py"
from __future__ import annotations
from typing import List
from duo_orm import Mapped, mapped_column, relationship
from ..database import db

class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    age: Mapped[int]

    posts: Mapped[List["Post"]] = relationship(back_populates="author")
```

```python title="db/models/post.py"
from __future__ import annotations
from duo_orm import Mapped, mapped_column, relationship, ForeignKey
from ..database import db
from .user import User

class Post(db.Model):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    author: Mapped["User"] = relationship(back_populates="posts")
```

Expose them in `db/models/__init__.py`:

```python title="db/models/__init__.py"
from .user import User
from .post import Post
```

### Create and apply migrations

Generate and apply a migration to create the tables.

```bash
duo-orm migration create "add user and post models"
duo-orm migration upgrade
```

## Usage

### Standalone calls (default)

Most work uses single-statement calls with short-lived sessions. This is ideal for simple CRUD and scripts.

```python title="main.py"
import asyncio
from db.database import db
from db.models import User

async def main():
    await User(name="Ada", age=30).save()  # one-shot write
    ada = await User.where(User.name == "Ada").first()  # one-shot read
    print(ada.to_dict())

if __name__ == "__main__":
    asyncio.run(main())
```

Run:

```bash
python main.py
```

### Controlled transactions

Need more control over how work commits or rolls back? Use a transaction block. It becomes important when you work with related graphs, cascades, or multi-step flows that must stay consistent. In frameworks, a common pattern is to wrap each request in a dependency (e.g., FastAPI) that opens a transaction so handlers avoid dirty or partial state.

```python title="main.py"
import asyncio
from db.database import db
from db.models import User, Post

async def main():
    async with db.transaction():  # shared session for the block
        alice = User(name="Alice", age=30)
        await alice.save()

        await Post(title="DuoORM Quickstart", author=alice).save()
        await Post(title="Advanced Queries", author=alice).save()

        user_with_posts = await User.related("posts").where(User.name == "Alice").first()
        print([p.title for p in user_with_posts.posts])

if __name__ == "__main__":
    asyncio.run(main())
```

### Synchronous?

Drop `await` and use the same API; the ORM chooses sync or async automatically based on context.

```python title="sync_main.py"
from db.database import db
from db.models import User

def main():
    User(name="Syncy", age=45).save()  # standalone
    with db.transaction():             # shared session for the block
        User(name="Another", age=50).save()

if __name__ == "__main__":
    main()
```
