# Reference: The `Database` Object

The `Database` class is the main entry point for DuoORM. An instance of this class manages database connections, sessions, and serves as a factory for your `db.Model` base class.

## `db.Model` base class

Each `Database` instance manufactures its own declarative base. Inherit all of your models from `db.Model` to keep metadata, engines, and helper methods scoped to that database.

::: duo_orm.db.Database
    options:
      show_root_heading: true
      show_source: false
      members:
        - url
        - sync_url
        - async_url
        - metadata
        - transaction
        - connect
        - disconnect
        - standalone_session
        - sync_standalone_session
