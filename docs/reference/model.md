# Reference: The Model Class

All models in your application inherit from `db.Model`. This base class provides the Active Record-style API for querying and persistence.

The methods documented here are available on all your model classes (e.g., `User.where(...)`) and their instances (e.g., `my_user.save()`).

::: duo_orm.basemodel._DuoOrmMethods
    options:
      show_root_heading: true
      show_source: false
      members:
        # Class-level methods
        - where
        - all
        - first
        - count
        - related
        - order_by
        - paginate
        - iterate
        - get
        - from_schema
        - create
        - create_bulk
        - update_bulk
        - delete_bulk
        # Instance-level methods
        - save
        - update
        - delete
        - apply_schema
        - to_schema
        # Helper methods
        - validate
        - fields
        - to_dict

!!! warning "Bulk safety guard"
    `update_bulk` and `delete_bulk` default to `require_filter=True` to prevent accidental full-table writes. Set it to `False` only when you explicitly intend to touch every row.
