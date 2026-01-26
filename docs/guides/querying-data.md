# User Guides: Querying Data

Duo ORM provides a fluent, chainable API for building database queries. All queries start with the model class itself and use methods like `.where()`, `.order_by()`, and `.related()` to construct a query.

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

Duo ORM models support a wide range of operators for common filtering tasks.

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
- `.update(**values)`: Performs a bulk update on all matching rows. Does not return the records.
- `.delete()`: Performs a bulk delete on all matching rows.

## Working with Relationships: `.related()`

A common performance problem in ORMs is the "N+1 query problem," where fetching N items requires N+1 separate database queries. Duo ORM provides the `.related()` method to solve this by eagerly loading related objects in a single, efficient operation.

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

By default, `.related()` uses a `selectinload` strategy, which is efficient for most cases. You can also choose a `joinedload` strategy.

- `loader="selectin"` (Default): Runs a second `SELECT` statement that fetches all related objects for all parent objects at once. Works well for one-to-many relationships.
- `loader="joined"`: Uses a SQL `JOIN` to fetch parent and related objects in a single, potentially large query. This is often better for one-to-one relationships.

```python
# Explicitly use a joined load for a user's profile (one-to-one)
user = await User.related("profile", loader="joined").first()
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
```

!!! warning
    The `.related()` method is very powerful but is intentionally limited to a single relationship hop at a time to keep the API simple and predictable. For more complex, multi-level joins, you can use the `.alchemize()` escape hatch.

## The Escape Hatch: `.alchemize()`

If you need to build a query that is too complex for the fluent API, you can use `.alchemize()`. This method returns the underlying SQLAlchemy `Select` object, allowing you to use the full power of SQLAlchemy Core.

```python
from duo_orm import text

# Build the base query in Duo ORM
query_builder = User.where(User.age > 20)

# Eject to raw SQLAlchemy for advanced features
sa_stmt = query_builder.alchemize().where(text("name like 'A%'"))

# Execute it with a standalone session
async with db.standalone_session() as session:
    results = (await session.execute(sa_stmt)).scalars().all()
```
This gives you a path to advanced query patterns without leaving the Duo ORM ecosystem.
