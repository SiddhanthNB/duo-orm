# Reference: The Model Class

All models in your application inherit from `db.Model`. This base class provides the Active Record-style API for querying and persistence.

The methods documented here are available on all your model classes (e.g., `User.where(...)`) and their instances (e.g., `my_user.save()`).

::: duo_orm.basemodel._YourOrmMethods
    options:
      show_root_heading: true
      show_source: false
      members:
        # Class-level methods
        - where
        - all
        - first
        - related
        - order_by
        - paginate
        - bulk_create
        # Instance-level methods
        - save
        - delete
        # Helper methods
        - validate
        - fields
        - to_dict
