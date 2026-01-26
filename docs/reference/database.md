# Reference: The `Database` Object

The `Database` class is the main entry point for Duo ORM. An instance of this class manages database connections, sessions, and serves as a factory for your `db.Model` base class.

::: duo_orm.db.Database
    options:
      show_root_heading: true
      show_source: false
      members:
        - Model
        - url
        - sync_url
        - async_url
        - metadata
        - transaction
        - connect
        - disconnect
        - standalone_session
        - sync_standalone_session
