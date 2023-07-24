# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements SQLAlchemy type for converting date format to RFC3339 string representation."""

import datetime
from typing import Any

from sqlalchemy import String, TypeDecorator


class RFC3339DateTime(TypeDecorator):  # pylint: disable=W0223
    """
    SQLAlchemy column type to serialise datetime objects for SQLite in consistent format matching in-toto.

    https://docs.sqlalchemy.org/en/20/core/custom_types.html#store-timezone-aware-timestamps-as-timezone-naive-utc
    https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#sqlalchemy.dialects.sqlite.DATETIME
    """

    # It is stored in the database as a string
    impl = String
    cache_ok = True

    def process_bind_param(self, value: None | Any, dialect: Any) -> None | str:
        """Process when storing a ``datetime`` object to the SQLite db.

        If the timezone of the serialized ``datetime`` object is provided, this function preserves it. Otherwise,
        if the provided ``datetime`` is a naive ``datetime`` object then UTC is added.

        value: None | datetime.datetime
            The value being stored
        """
        if value is None:
            return None
        if not isinstance(value, datetime.datetime):
            raise TypeError("RFC3339DateTime type expects a datetime object")
        if not value.tzinfo:
            value = value.astimezone(datetime.timezone.utc)  # Consider coercing to host timezone.
        return value.isoformat(timespec="seconds")

    def process_result_value(self, value: None | str, dialect: Any) -> None | datetime.datetime:
        """Process when loading a ``datetime`` object from the SQLite db.

        If the deserialized ``datetime`` has a timezone then return it, otherwise add UTC as its timezone.

        value: None | str
            The value being loaded
        """
        if value is None:
            return None
        result = datetime.datetime.fromisoformat(value)
        if result.tzinfo:
            return result
        return result.astimezone(datetime.timezone.utc)  # Consider coercing to host timezone.
