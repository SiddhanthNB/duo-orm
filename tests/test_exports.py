from duo_orm import (
    Integer,
    BigInteger,
    SmallInteger,
    String,
    Text,
    Boolean,
    DateTime,
    Date,
    Time,
    Float,
    Numeric,
    UUID,
    JSON,
    LargeBinary,
    PG_ARRAY,
)
from sqlalchemy import (
    Integer as SAInteger,
    BigInteger as SABigInteger,
    SmallInteger as SASmallInteger,
    String as SAString,
    Text as SAText,
    Boolean as SABoolean,
    DateTime as SADateTime,
    Date as SADate,
    Time as SATime,
    Float as SAFloat,
    Numeric as SANumeric,
    UUID as SAUUID,
    JSON as SAJSON,
    LargeBinary as SALargeBinary,
)
from sqlalchemy.dialects.postgresql import ARRAY as SAPG_ARRAY


def test_type_exports_match_sqlalchemy():
    assert Integer is SAInteger
    assert BigInteger is SABigInteger
    assert SmallInteger is SASmallInteger
    assert String is SAString
    assert Text is SAText
    assert Boolean is SABoolean
    assert DateTime is SADateTime
    assert Date is SADate
    assert Time is SATime
    assert Float is SAFloat
    assert Numeric is SANumeric
    assert UUID is SAUUID
    assert JSON is SAJSON
    assert LargeBinary is SALargeBinary


def test_pg_array_export_matches_sqlalchemy():
    assert PG_ARRAY is SAPG_ARRAY
