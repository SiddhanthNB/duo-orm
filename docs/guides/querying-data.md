# User Guides: Querying Data

DuoORM provides a fluent, chainable API for building database queries. All queries start with the model class itself and use methods like `.where()`, `.order_by()`, and `.related()` to construct a query.

The query is not executed until you call a **terminal method** like `.first()`, `.all()`, or `.count()`.

## Starting a Query

All queries start with your model class, followed by a class method that returns a `QueryBuilder` instance.

```python
from db.models import User

# Start a query for all users
query = User.where(User.age > 18)

# You can also start with other methods
query = User.order_by("-created_at")
```

## Filtering Results with `.where()`

The `.where()` method is used to filter your results, similar to a SQL `WHERE` clause. You can pass one or more conditions. Multiple conditions are combined with `AND`.

```python
# Find active users over the age of 30
users = await User.where(
    User.age > 30,
    User.is_active == True
).all()
```

### Logical Operators

You can build complex expressions using Python's logical operators: `&` (AND), `|` (OR), and `~` (NOT).

```python
from duo_orm import not_

# Find users who are either admins or staff members
staff = await User.where(
    (User.is_admin == True) | (User.is_staff == True)
).all()

# Find users who are not named 'guest'
real_users = await User.where(not_(User.name == 'guest')).all()
```

### Common Filter Operators

DuoORM models support a wide range of operators for common filtering tasks.

| Method             | Description                          | Example                                       |
| ------------------ | ------------------------------------ | --------------------------------------------- |
| `==`               | Equals                               | `User.name == "Alice"`                        |
| `!=`               | Not equals                           | `User.status != "inactive"`                   |
| `>` , `>=` , `<`, `<=` | Greater/Less than                    | `User.age > 18`                               |
| `.in_([...])`       | Is one of the values in the list     | `User.id.in_([1, 2, 3])`                      |
| `.notin_([...])`    | Is not one of the values in the list | `User.role.notin_(['admin'])`                 |
| `.contains(s)`     | Substring match (case-sensitive)     | `User.email.contains('@example.com')`         |
| `.icontains(s)`    | Substring match (case-insensitive)   | `User.name.icontains('al')`                   |
| `.startswith(s)`   | Prefix match (case-sensitive)        | `User.username.startswith('admin_')`          |
| `.istartswith(s)`  | Prefix match (case-insensitive)      | `User.username.istartswith('admin_')`         |
| `.endswith(s)`     | Suffix match (case-sensitive)        | `User.file.endswith('.pdf')`                  |
| `.iendswith(s)`    | Suffix match (case-insensitive)      | `User.file.iendswith('.pdf')`                 |
| `.like(s)`         | SQL LIKE operator (use `%` as wildcard) | `User.name.like('A%')`                        |
| `.ilike(s)`        | SQL ILIKE operator (case-insensitive) | `User.name.ilike('a%')`                       |

## Ordering and Pagination

You can control the order and limit the number of results returned.

- `.order_by(*fields)`: Sorts the results. Prefix a field name with `-` for descending order.
- `.limit(n)`: Limits the query to `n` results.
- `.offset(n)`: Skips the first `n` results.
- `.paginate(limit, offset=0)`: A convenience method that applies both limit and offset.

```python
# Get the 10 most recently created active users
recent_users = await User.where(User.is_active == True).order_by("-created_at").limit(10).all()

# Get the second page of users (users 11-20)
paged_users = await User.order_by("id").paginate(limit=10, offset=10).all()
```

## Executing Queries (Terminal Methods)

A query is only sent to the database when you call one of these terminal methods. The same methods work in both sync and async contexts.

- `.all()`: Returns a **list** of all matching model instances.
- `.first()`: Returns the **first matching instance** or `None` if no match is found.
- `.one()`: Returns **exactly one instance**. Raises `ObjectNotFoundError` if no object is found, or `MultipleObjectsFoundError` if more than one is found.
- `.count()`: Returns the **integer count** of matching rows.
- `.exists()`: Returns `True` if at least one row matches, `False` otherwise. This is more efficient than `.count() > 0`.
- `.update_bulk(payload, with_hooks=False, batch_size=200, require_filter=True)`: Bulk update from a dict or Pydantic model. `with_hooks=True` loads rows in batches, runs `validate()` and timestamp hooks. The `require_filter` guard prevents table-wide updates unless you opt out explicitly.
- `.delete_bulk(with_hooks=False, batch_size=200, require_filter=True)`: Bulk delete with the same guard/`with_hooks` semantics as updates.
- `.iterate(batch_size=200, batch=False)`: Stream rows (or batches). When you haven’t set `order_by`, DuoORM auto-orders by primary key for deterministic paging. Use `paginate()` for classic page/offset slices; use `iterate()` for streaming or large result sets.

!!! warning "with_hooks=True trades speed for safety"
    Setting `with_hooks=True` loads every matched row into memory to run `validate()` and timestamp hooks, which can be slow and memory-heavy (N+1-ish). Use it only when you truly need per-row hooks and keep the result set small.

## CRUD helpers (model and query side)

- `Model.create(payload)` / `Model.create_bulk(payloads, return_models=False, with_hooks=False)`: High-level creates that accept Pydantic models or dicts; non-column keys are ignored. The bulk helper batches work and can run per-row hooks.
- `instance.save()` / `instance.update(payload)` / `instance.delete()`: Instance-level persistence; `update` applies partial payloads (missing/`None` fields are skipped) then calls `save()`.
- `Model.get(*pk, **pk_parts)`: Primary-key lookup; returns `None` when missing instead of raising.
- `Query.update_bulk(...)` / `Query.delete_bulk(...)`: Query-scoped bulk actions (see signatures above). They reuse the active transaction/session when one is set.
- `Query.count()` / `Query.exists()`: Cheap read-only checks; use `exists()` when you only need to know if at least one row matches.
- `Query.iterate(...)` vs. `Query.paginate(...)`: `iterate` is cursor-like streaming with batching; `paginate` is page/offset slicing.

You can call helpers directly on the model—no need to start with `where()` if you don’t need filters:

```python
# Create single + bulk
u = await User.create({"name": "Solo", "age": 30})
await User.create_bulk([{"name": "A"}, {"name": "B"}])

# Primary key lookup
maybe = await User.get(u.id)

# Bulk update with guard
await User.where(User.name.in_(["A", "B"])).update_bulk({"age": 99}, with_hooks=True)

# Stream in batches of 100
async for batch in User.order_by("id").iterate(batch=True, batch_size=100):
    ...
```

## Working with Relationships: `.related()`

A common performance problem in ORMs is the "N+1 query problem," where fetching N items requires N+1 separate database queries. DuoORM provides the `.related()` method to solve this by eagerly loading related objects in a single, efficient operation.

Let's assume a `User` has a one-to-many relationship to `Post`.

```python
# The N+1 Problem (BAD):
# This runs 1 query to get the users, then 1 query *per user* to get their posts.
users = await User.all()
for user in users:
    print(user.name, [p.title for p in user.posts]) # <-- Hidden query here!

# The Solution with .related() (GOOD):
# This runs just 2 queries total, regardless of the number of users.
users_with_posts = await User.related("posts").all()
for user in users_with_posts:
    # user.posts is already loaded, no new query is made
    print(user.name, [p.title for p in user.posts])
```

### Loading Strategies

By default, DuoORM picks the loader for you: `selectin` for collection relationships, `joined` for scalars. You can override with `loader="selectin"` or `loader="joined"` when needed.

- `loader="selectin"` (Default for collections): Runs a second `SELECT` that fetches all related objects for all parents at once. Good for one-to-many.
- `loader="joined"` (Default for scalars): Uses a SQL `JOIN` to fetch parent and related objects together. Good for one-to-one or small result sets.

!!! note "Safety guard on deep joined loads"
    DuoORM blocks `loader="joined"` on deep, multi-hop collection paths (e.g., `path(User.posts, Post.comments)`) to prevent explosive row multiplication. Use `selectin` for those cases.

```python
# Explicitly use a joined load for a user's profile (one-to-one)
user = await User.related("profile", loader="joined").first()
```

### Nested relationships with `path()`

For multi-hop eager loads, wrap the hop chain with `path(...)` and call `.related()` once per path. Chain multiple calls for siblings.

```python
from duo_orm import path

# users -> posts -> comments (selectin on collections)
users = (
    await User.related(path(User.posts, Post.comments), loader="selectin")
               .related(User.groups, loader="selectin")  # sibling path in a separate call
               .all()
)
```

### Filtering on Relationships

The `.related()` method can also be used to filter parent objects based on their relationships.

- `aggregate="exists"` (Default): Only return parents that have at least one related object matching the `where` clause.
- `aggregate="count"`: Allows you to filter or order by the *number* of related objects.
- `aggregate="all"`: A more advanced use case to find parents where *all* related objects match a condition.

```python
# Get all users who have written at least one post about "Python"
active_authors = await User.related(
    "posts",
    where=[Post.title.icontains("Python")]
).all()

# Get the top 5 most active authors, ordered by their post count
top_authors = await User.related(
    "posts",
    aggregate="count",
    order_by=["-count"]
).limit(5).all()

# Get users who have more than 10 posts
prolific_authors = await User.related(
    "posts",
    aggregate="count",
    having=[lambda count_expr: count_expr > 10]
).all()

# Users whose posts have at least 2 public comments (nested path)
engaged_authors = await User.related(
    path(User.posts, Post.comments),
    aggregate="count",
    where=[Comment.is_public.is_(True)],
    having=[lambda count_expr: count_expr >= 2],
).all()
```

!!! warning "Beware explosive joined loads"
    Joined loading on wide or multi-hop collection paths can explode row counts. DuoORM blocks `loader="joined"` on deep collection paths and defaults to `selectin` for collections. Stick to the defaults unless you have measured a benefit.

!!! warning
    Call `.related()` with exactly one relationship/path per call, and chain for siblings. Use `path()` for multi-hop eager loading. Aggregates and filters apply to the terminal hop of the path you pass in.

## Querying JSON and ARRAY columns

For structured columns, DuoORM exposes `json()` and `array()` helpers that plug into `.where(...)` just like any other expression. Use them to navigate JSON paths, cast values, or test array membership/overlap. See the dedicated guide: [JSON and ARRAY Types](json-and-array-types.md) for full examples.

## **The Escape Hatch: `.alchemize()`**

If you need to build a query that is too complex for the fluent API, you can use `.alchemize()`. This method returns the underlying SQLAlchemy `Select` object, allowing you to use the full power of SQLAlchemy Core.

```python
from duo_orm import text

# Build the base query in DuoORM
query_builder = User.where(User.age > 20)

# Eject to raw SQLAlchemy for advanced features
sa_stmt = query_builder.alchemize().where(text("name like 'A%'"))

# Execute it with a standalone session (you own commit/rollback)
async with db.standalone_session() as session:
    async with session.begin():
        results = (await session.execute(sa_stmt)).scalars().all()
```
This gives you a path to advanced query patterns without leaving the DuoORM ecosystem.

### When to reach for `.alchemize()`

- You need complex joins or window functions not covered by `.related()`, `.where()`, or `.order_by()`.
- You want to add vendor-specific SQL expressions or hints.
- You need to combine DuoORM-built clauses with hand-written SQLAlchemy Core constructs.
- You want to execute the resulting statement inside a fully manual session; see [`db.standalone_session()`](sessions-and-transactions.md#the-power-user-escape-hatch-standalone_session).

### Safety tips

- Keep the DuoORM-built base (`.alchemize()`) as your starting point so model metadata (e.g., column names, relationships) stays correct.
- Always execute the compiled statement with a DuoORM-managed or standalone session so engines/sessions remain consistent.
- Prefer `text()` only for literals you fully control; otherwise bind parameters to avoid SQL injection.
