# User Guides: JSON and ARRAY Types

For databases that support them (most notably PostgreSQL), Duo ORM provides expressive, Pythonic helpers for querying complex `JSON` and `ARRAY` data types. These helpers, `json()` and `array()`, allow you to write readable filters without needing to remember dialect-specific SQL operators.

!!! tip
    While many databases can store JSON as text, the rich operator support described here is primarily available on PostgreSQL. The helpers will raise a `TypeError` if used on an unsupported database dialect.

## JSON Helpers

To work with a `JSON` or `JSONB` column, first define it on your model using the standard SQLAlchemy types.

```python
from duo_orm import Mapped, mapped_column, JSON
from ..database import db

class Device(db.Model):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # A JSONB column to store arbitrary metadata
    metadata: Mapped[dict] = mapped_column(JSON, nullable=False)
```

### Querying with `json()`

To filter on the contents of the `metadata` column, import the `json` helper from `duo_orm` and use it inside a `.where()` clause. The helper uses standard Python dictionary access (`[]`) to navigate the JSON structure.

```python
from duo_orm import json

# Find devices where the 'status' key is 'active'
active_devices = await Device.where(
    json(Device.metadata)["status"] == "active"
).all()

# Find devices where a nested flag is true
beta_devices = await Device.where(
    json(Device.metadata)["flags"]["is_beta"].is_true()
).all()
```

### Casting Values

JSON values are stored as strings internally. To perform typed comparisons, you can use casting helpers.

- `.as_integer()`
- `.as_float()`
- `.as_boolean()`
- `.as_text()` (Default)

```python
# Find devices where the 'retries' count is greater than 5
high_retry_devices = await Device.where(
    json(Device.metadata)["telemetry"]["retries"].as_integer() > 5
).all()
```

### Available Operators

| Method                      | Description                                       | Example                                                  |
| --------------------------- | ------------------------------------------------- | -------------------------------------------------------- |
| `json(col)[key]`            | Navigate a path                                   | `json(Device.metadata)["status"]`                        |
| `==` or `.equals(val)`      | Equality check (auto-casts for scalars)           | `json(Device.metadata)["status"] == "active"`            |
| `!=` or `.not_equals(val)`  | Inequality check                                  | `json(Device.metadata)["status"] != "archived"`          |
| `.is_null()` / `.is_not_null()` | Check if a path exists and is (or is not) null.   | `json(Device.metadata)["archived_at"].is_null()`         |
| `.is_true()` / `.is_false()`  | Boolean checks (requires a boolean value in JSON) | `json(Device.metadata)["flags"]["is_beta"].is_true()`    |
| `.contains(fragment)`       | Check if the JSON contains a given sub-document.  | `json(Device.metadata).contains({"flags": {"is_beta": True}})` |
| `.has_key(key)`             | Check if a JSON object has a specific top-level key. | `json(Device.metadata)["flags"].has_key("is_beta")`      |

All these helpers generate standard SQLAlchemy expressions, so they can be combined with `&`, `|`, and other model filters.

## ARRAY Helpers

Similarly, you can query `ARRAY` columns using the `array()` helper.

First, define a model with an array column. Note that you must import the specific array type from the dialect you are using (e.g., PostgreSQL).

```python
from duo_orm import Mapped, mapped_column, String, PG_ARRAY
from ..database import db

class Article(db.Model):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    
    # An array of string tags
    tags: Mapped[list[str]] = mapped_column(PG_ARRAY(String), nullable=False)
```

### Querying with `array()`

Import the `array` helper to build expressive membership and overlap queries.

```python
from duo_orm import array

# Find all articles tagged with 'python'
python_articles = await Article.where(
    array(Article.tags).includes("python")
).all()

# Find all articles tagged with BOTH 'python' and 'async'
py_async_articles = await Article.where(
    array(Article.tags).includes_all(["python", "async"])
).all()

# Find all articles tagged with EITHER 'guide' OR 'tutorial'
guide_articles = await Article.where(
    array(Article.tags).includes_any(["guide", "tutorial"])
).all()
```

### Available Operators

| Method                | Description                                       | Example                                                |
| --------------------- | ------------------------------------------------- | ------------------------------------------------------ |
| `.includes(value)`    | True if the array contains the single value.      | `array(Article.tags).includes("orm")`                  |
| `.includes_all(vals)` | True if the array contains *all* provided values. | `array(Article.tags).includes_all(["python", "orm"])`  |
| `.includes_any(vals)` | True if the array contains *any* provided value.  | `array(Article.tags).includes_any(["go", "rust"])`     |
| `.length()`           | Returns the number of elements in the array.      | `array(Article.tags).length() > 3`                     |
| `.equals(vals)`       | Exact equality match of the entire array.         | `array(Article.tags).equals(["news"])`                 |
| `.not_equals(vals)`   | Inequality match of the entire array.             | `array(Article.tags).not_equals(["obsolete"])`         |

These helpers provide a clean, readable syntax for common array operations, making it easier to leverage the full power of your database.
