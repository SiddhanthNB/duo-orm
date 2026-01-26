# User Guides: Sessions and Transactions

A key design principle of Duo ORM is making the "Unit of Work" explicit. The library operates in two distinct modes: the default **statement-driven** mode and an opt-in **transaction-driven** mode. Understanding the difference is key to using the ORM effectively.

## Statement-Driven Mode (Default)

By default, every single ORM operation is its own isolated "micro-transaction".

- **Action**: You call `await user.save()` or `await User.first()`.
- **Behind the Scenes**: Duo ORM creates a new, temporary session, executes exactly one statement, commits the result (for writes), and immediately closes the session.

```python
# Statement-Driven Example
from db.models import User

# Operation 1: A new session is created and closed for this .save() call.
user = User(name="Standalone", age=50)
await user.save()

# Operation 2: A *different*, new session is created and closed for this .first() call.
fetched_user = await User.where(User.name == "Standalone").first()
```

### Characteristics

- **Simple & Stateless**: Each operation is independent. There is no shared state or identity map between calls.
- **Predictable**: You know that each line of code corresponds to a single, atomic database interaction.
- **Safe**: There is no risk of unintended changes being flushed to the database, as the session does not persist.

### Limitations

This mode is not suitable for workflows that involve multiple steps or related objects.

```python
# This will NOT work as expected in statement-driven mode
user = await User.where(User.id == 1).first()

# At this point, the session used to fetch the user is GONE.
# The `user` object is "detached".

post = Post(title="My Post", author=user)

# This .save() will fail because its new, temporary session
# does not know about the `user` object.
await post.save()
# Raises IntegrityError: The new session doesn't know the state of `user`
# and can't link it to `post.author_id`.
```

For these related workflows, you need a transaction.

## Transaction-Driven Mode

When you need to perform multiple operations as a single, atomic unit of work, you must "opt-in" to a transaction using the `db.transaction()` context manager.

- **Action**: You wrap your code in `async with db.transaction():` or `with db.transaction():`.
- **Behind the Scenes**: Duo ORM creates a single, shared session that is kept open for the entire duration of the `with` block. All ORM calls made inside the block will use this same session.

```python
from db.models import User, Post

async with db.transaction():
    # All operations within this block share ONE session.
    user = await User.where(User.id == 1).first()

    # The session knows about `user`, so it can correctly
    # link it to the new post.
    post = Post(title="My Post", author=user)
    await post.save()

# The transaction is automatically committed here when the block exits.
# If any exception had occurred, it would have been rolled back.
```

### Characteristics

- **Atomic**: All operations within the block either succeed together (commit) or fail together (rollback).
- **Stateful**: The session maintains an "identity map." If you fetch the same object multiple times within the block, you will get the exact same Python object back.
- **Efficient**: It uses a single connection from the pool for the entire block, reducing the overhead of connecting and disconnecting for each statement.

### Framework Integration

The `db.transaction()` block is the ideal tool for integrating with web frameworks like FastAPI. You can create a dependency that wraps each incoming request in a transaction.

```python
from fastapi import Depends, FastAPI
from db.database import db

app = FastAPI()

async def get_db_session():
    """This dependency wraps the request in a transaction."""
    async with db.transaction():
        yield

@app.post("/users/")
async def create_user(user_data: dict, _ = Depends(get_db_session)):
    # All code in this request handler now shares a single session.
    user = User(**user_data)
    await user.save()
    # ... do other related work ...
    return user
```

This pattern ensures that each API request is handled as an atomic transaction.

## Connecting and disconnecting engines

- `db.connect()` eagerly initializes sync/async engines so misconfiguration surfaces early. It is optional; engines are still created lazily on first use.
- `db.disconnect()` disposes any initialized engines (sync and async) and clears cached factories. It does not affect sessions opened through `db.transaction()`, `standalone_session()`, or `sync_standalone_session()`—those context managers already clean up after themselves. Use `disconnect()` when a script or CLI is finished and you want to release pools explicitly.

## The Power User Escape Hatch: `standalone_session`

What if you need complete, manual control over the session, perhaps for a very complex query or to use an advanced SQLAlchemy feature? For this, Duo ORM provides `db.standalone_session()`.

This context manager gives you a raw, unmanaged SQLAlchemy `Session` or `AsyncSession`. You are responsible for all operations, including flushing, committing, and rolling back.

```python
from duo_orm import text
from db.database import db

# This session is NOT managed by Duo ORM's contextvars.
# It is for your use only.
async with db.standalone_session() as session:
    # You can use raw SQLAlchemy Core expressions
    stmt = text("SELECT * FROM users WHERE age > :age")
    result = await session.execute(stmt, {"age": 30})
    users = result.scalars().all()

    # You must commit changes manually
    # await session.commit()
```
This is an advanced feature and should only be used when the standard Duo ORM patterns do not fit your needs.

## Summary

| Context                        | Session Lifetime     | Commit Model                       | Typical Use Case                     |
| ------------------------------ | -------------------- | ---------------------------------- | ------------------------------------ |
| **Default Call** (e.g., `.save()`) | Short-lived, per-call | Auto-commit on write              | Simple reads/writes, scripts         |
| **`db.transaction()`** block     | Shared for the block | Commit on exit, rollback on error | Web requests, multi-step workflows   |
| **`db.standalone_session()`**  | Manual control       | You must call `.commit()`          | Advanced SQLAlchemy Core integration |
