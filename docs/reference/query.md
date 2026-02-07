# Reference: The QueryBuilder

A `QueryBuilder` instance is created whenever you start a query (e.g., by calling `User.where(...)`). It provides a chainable, fluent interface for constructing a database query. The query is not executed until a terminal method like `.all()` or `.first()` is called.

## Quick examples

```python
# Count active users
await User.where(User.is_active.is_(True)).count()

# Bulk update with guard + hooks
await User.where(User.signup_source == "beta").update_bulk(
    {"plan": "pro"},
    with_hooks=True,         # run validate() + timestamp hooks per row
    require_filter=True,     # keep the safety guard on (default)
)

# Stream in batches of 500 without loading everything into memory
async for batch in User.order_by("id").iterate(batch=True, batch_size=500):
    ...
```

## Query Construction Methods

These methods are used to build the query and are chainable.

::: duo_orm.query.QueryBuilder
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3
      members:
        - where
        - order_by
        - limit
        - offset
        - paginate
        - related
        - alchemize
        - iterate

## Terminal (Execution) Methods

These methods execute the constructed query against the database.

::: duo_orm.query.QueryBuilder
    options:
      show_root_heading: false
      show_source: false
      heading_level: 3
      members:
        - all
        - first
        - one
        - count
        - exists
        - update_bulk
        - delete_bulk

## JSON and ARRAY Helpers

These helper functions are used inside a `.where()` clause to build expressions for querying `JSON` and `ARRAY` column types.

### `json()` Helper

::: duo_orm.query.json

### `array()` Helper

::: duo_orm.query.array
