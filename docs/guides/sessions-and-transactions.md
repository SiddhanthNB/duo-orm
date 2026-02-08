# User Guides: Sessions and Transactions

A key design principle of DuoORM is making the "Unit of Work" explicit. The library operates in two distinct modes: the default **statement-driven** mode and an opt-in **transaction-driven** mode. Understanding the difference is key to using the ORM effectively.

## Statement-Driven Mode (Default)

By default, every single ORM operation is its own isolated "micro-transaction".

- **Action**: You call `await user.save()` or `await User.first()`.
- **Behind the Scenes**: DuoORM creates a new, temporary session, executes exactly one statement, commits the result (for writes), and immediately closes the session.

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
- **Behind the Scenes**: DuoORM creates a single, shared session that is kept open for the entire duration of the `with` block. All ORM calls made inside the block will use this same session.

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
- `db.disconnect()` disposes any initialized engines (sync and async) and clears cached factories. It does not affect sessions opened through `db.transaction()`, `standalone_session()`, or `sync_standalone_session()` because those context managers already clean up after themselves. Use `disconnect()` when a script or CLI is finished and you want to release pools explicitly.

## **The Power User Escape Hatch: `standalone_session`**

What if you need complete, manual control over the session, perhaps for a very complex query or to use an advanced SQLAlchemy feature? For this, DuoORM provides `db.standalone_session()`.

This context manager gives you a raw, unmanaged SQLAlchemy `Session` or `AsyncSession`. You are responsible for all operations, including flushing, committing, and rolling back.

```python
from duo_orm import text
from db.database import db

# This session is NOT managed by DuoORM's contextvars.
# It is for your use only.
async with db.standalone_session() as session:
    # You can use raw SQLAlchemy Core expressions
    stmt = text("SELECT * FROM users WHERE age > :age")
    result = await session.execute(stmt, {"age": 30})
    users = result.scalars().all()

    # You must commit changes manually
    # await session.commit()
```
This is an advanced feature and should only be used when the standard DuoORM patterns do not fit your needs.

### When to use it
- You need full SQLAlchemy Core/ORM control (bulk ops, vendor-specific pragmas, advanced query plans).
- You’re mixing DuoORM with another abstraction that manages its own units of work.
- You need to stream results or use server-side cursors outside DuoORM’s managed context.

### Safety tips
- You own commits/rollbacks; always wrap writes in try/except and commit/rollback explicitly.
- Don’t mix a standalone session with `db.transaction()`-managed work in the same call stack unless you know the boundaries.
- Ensure you close the session (the context manager does this); leaking sessions can exhaust pools.

## transaction() vs standalone_session(): who owns the boundary?

- **Lifecycle & scope**

  - `db.transaction()` opens a session/transaction for the block and closes it on exit.
  - `db.standalone_session()` hands you a session; you choose when to `session.begin()`, `commit()`, or `rollback()`, and you can run multiple transactions on that one session.

- **Safety defaults**

  - `transaction()` is “safe by default”: atomicity and rollback-on-exception are handled.
  - `standalone_session()` is “powerful by default”: you must manage transactions; forgetting to commit/rollback can hold locks.

- **Typical use**

  - Use `transaction()` for routine reads/writes and most app code.
  - Use `standalone_session()` when you need multiple sequential or nested transactions on a single session, or when integrating with code that already manages transaction boundaries.

- **Concurrency impact**

  - `transaction()` keeps locks for the life of the block (short-lived by design).
  - `standalone_session()` can stay open longer—only do this when you need fine-grained control.


Parallel examples (same ORM calls; only ownership differs):

```python
# Managed
with db.transaction():
    user = User.create({"name": "Ada", "age": 30})
    User.where(User.id == user.id).update_bulk({"age": 31})
    posts = Post.where(Post.author == user).all()
    # commit/rollback handled by the context manager

# Unmanaged
with db.standalone_session() as session:
    with session.begin():  # you own the transaction
        user = User.create({"name": "Ada", "age": 30})
        User.where(User.id == user.id).update_bulk({"age": 31})
        posts = Post.where(Post.author == user).all()
    with session.begin():
        User.where(User.id == user.id).delete_bulk(require_filter=False)
    # you must ensure commits/rollbacks; the session stays open
```

## Visual cheat sheet

```text
Single call (default)
  User.where(...).first()
    -> DuoORM opens a session
    -> executes one statement
    -> commits (if write) / closes

Transaction block
  async with db.transaction():
      ...multiple ORM calls...
    -> one shared session for the block
    -> commit on exit / rollback on error

Standalone session (escape hatch)
  async with db.standalone_session() as session:
      session.execute(raw_stmt)
    -> you own commit/rollback
    -> full SQLAlchemy control
```

## Summary

| Context                        | Session Lifetime     | Commit Model                       | Typical Use Case                     |
| ------------------------------ | -------------------- | ---------------------------------- | ------------------------------------ |
| **Default Call** (e.g., `.save()`) | Short-lived, per-call | Auto-commit on write              | Simple reads/writes, scripts         |
| **`db.transaction()`** block     | Shared for the block | Commit on exit, rollback on error | Web requests, multi-step workflows   |
| **`db.standalone_session()`**  | Manual control       | You must call `.commit()`          | Advanced SQLAlchemy Core integration |
