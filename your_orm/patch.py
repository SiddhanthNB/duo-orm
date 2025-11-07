# your_orm/patch.py

from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql import functions
from sqlalchemy.dialects import postgresql


def not_in_(self, values):
    return self.notin_(values)

def like_(self, pattern):
    return self.like(pattern)

def ilike_(self, pattern):
    return self.ilike(pattern)

def startswith_(self, prefix):
    return self.startswith(prefix)

def endswith_(self, suffix):
    return self.endswith(suffix)

def contains_(self, substr):
    if hasattr(self, "type") and isinstance(self.type, (postgresql.JSON, postgresql.JSONB, postgresql.ARRAY)):
        return self.contains(substr)
    return self.like(f"%{substr}%")

def overlap_(self, values):
    return self.op("&&")(values)

def contained_in_(self, values):
    return self.op("<@")(values)

def has_key_(self, key):
    return self.has_key(key)

def exists_(self, path):
    return self.op("?")(path)

def any_(self, expr=None):
    return self.any(expr)

def all_(self, expr):
    return self.all(expr)

def count_(self):
    return functions.count(self)

def is_null_(self):
    return self.is_(None)

def is_not_null_(self):
    return self.is_not(None)

def between_(self, a, b):
    return self.between(a, b)

InstrumentedAttribute.not_in_ = not_in_
InstrumentedAttribute.like_ = like_
InstrumentedAttribute.ilike_ = ilike_
InstrumentedAttribute.startswith_ = startswith_
InstrumentedAttribute.endswith_ = endswith_
InstrumentedAttribute.contains_ = contains_
InstrumentedAttribute.overlap_ = overlap_
InstrumentedAttribute.contained_in_ = contained_in_
InstrumentedAttribute.has_key_ = has_key_
InstrumentedAttribute.exists_ = exists_
InstrumentedAttribute.any_ = any_
InstrumentedAttribute.all_ = all_
InstrumentedAttribute.count_ = count_
InstrumentedAttribute.is_null_ = is_null_
InstrumentedAttribute.is_not_null_ = is_not_null_
InstrumentedAttribute.between_ = between_
