# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements SQLAlchemy type for converting date format to RFC3339 string representation."""

import datetime
from typing import Any, Optional

from sqlalchemy import String, TypeDecorator


class RFC3339DateTime(TypeDecorator):  # pylint: disable=W0223
    """
    SQLAlchemy column type to serialise datetime objects for SQLite in consistent format matching in-toto.

    https://docs.sqlalchemy.org/en/20/core/custom_types.html#store-timezone-aware-timestamps-as-timezone-naive-utc
    """

    # It is stored in the database as a string
    impl = String

    # To prevent Sphinx from rendering the docstrings for `cache_ok`, make this docstring private.
    #: :meta private:
    cache_ok = True

    def process_bind_param(self, value: Optional[Any], dialect: Any) -> None | str:
        """Process when storing.

        value: None | datetime.datetime
            The value being stored
        """
        result = None
        if value is not None:
            if not value.tzinfo:
                raise TypeError("tzinfo is required")
            value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            result = value.isoformat(sep="T", timespec="seconds") + "Z"
        return result

    def process_result_value(self, value: Optional[Any], dialect: Any) -> None | datetime.datetime:
        """Process when loading.

        value: None | str
            The value being loaded
        """
        result = None
        if value is not None:
            result = datetime.datetime.fromisoformat(value)
            result = result.astimezone(datetime.timezone.utc)
        return result
