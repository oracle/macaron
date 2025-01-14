# Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module implements SQLAlchemy type for converting date format to RFC3339 string representation."""

import datetime
from typing import Any

from sqlalchemy import JSON, String, TypeDecorator

from macaron.slsa_analyzer.provenance.intoto import InTotoPayload, validate_intoto_payload


class RFC3339DateTime(TypeDecorator):  # pylint: disable=W0223
    """
    SQLAlchemy column type to serialise datetime objects for SQLite in consistent format matching in-toto.

    https://docs.sqlalchemy.org/en/20/core/custom_types.html#store-timezone-aware-timestamps-as-timezone-naive-utc
    https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#sqlalchemy.dialects.sqlite.DATETIME
    """

    # It is stored in the database as a string
    impl = String

    # To prevent Sphinx from rendering the docstrings for `cache_ok`, make this docstring private.
    #: :meta private:
    cache_ok = True

    # Unfortunately there appears to be no efficient way to detect a host's timezone:
    # https://discuss.python.org/t/get-local-time-zone/4169
    # https://blog.ganssle.io/articles/2018/03/pytz-fastest-footgun.html
    _host_tzinfo = datetime.datetime.now().astimezone().tzinfo

    def process_bind_param(self, value: None | Any, dialect: Any) -> None | str:
        """Process when storing a ``datetime`` object to the SQLite db.

        If the timezone of the serialized ``datetime`` object is provided, this function preserves it. Otherwise,
        if the provided ``datetime`` is a naive ``datetime`` object then UTC is added.

        value: None | datetime.datetime
            The value being stored.
        """
        if value is None:
            return None
        if not isinstance(value, datetime.datetime):
            raise TypeError("RFC3339DateTime type expects a datetime object")
        if not value.tzinfo:
            value = value.astimezone(RFC3339DateTime._host_tzinfo)
        return value.isoformat(timespec="seconds")

    def process_result_value(self, value: None | str, dialect: Any) -> None | datetime.datetime:
        """Process when loading a ``datetime`` object from the SQLite db.

        If the deserialized ``datetime`` has a timezone then return it, otherwise add UTC as its timezone.

        value: None | str
            The value being loaded.
        """
        if value is None:
            return None
        result = datetime.datetime.fromisoformat(value)
        if result.tzinfo:
            return result
        return result.astimezone(RFC3339DateTime._host_tzinfo)


class DBJsonDict(TypeDecorator):  # pylint: disable=W0223
    """SQLAlchemy column type to serialize dictionaries."""

    # It is stored in the database as a json value.
    impl = JSON

    # To prevent Sphinx from rendering the docstrings for `cache_ok`, make this docstring private.
    #: :meta private:
    cache_ok = True

    def process_bind_param(self, value: None | dict, dialect: Any) -> None | dict:
        """Process when storing a dict object to the SQLite db.

        value: None | dict
            The value being stored.
        """
        if not isinstance(value, dict):
            raise TypeError("DBJsonDict type expects a dict.")

        return value

    def process_result_value(self, value: None | dict, dialect: Any) -> None | dict:
        """Process when loading a dict object from the SQLite db.

        value: None | dict
            The value being loaded.
        """
        if not isinstance(value, dict):
            raise TypeError("DBJsonDict type expects a dict.")
        return value


class ProvenancePayload(TypeDecorator):  # pylint: disable=W0223
    """SQLAlchemy column type to serialize InTotoProvenance."""

    # It is stored in the database as a json value.
    impl = JSON

    # To prevent Sphinx from rendering the docstrings for `cache_ok`, make this docstring private.
    #: :meta private:
    cache_ok = True

    def process_bind_param(self, value: None | InTotoPayload, dialect: Any) -> None | dict:
        """Process when storing an InTotoPayload object to the SQLite db.

        value: None | InTotoPayload
            The value being stored.
        """
        if value is None:
            return None

        if not isinstance(value, InTotoPayload):
            raise TypeError("ProvenancePayload type expects an InTotoPayload.")

        return value.statement.get("predicate")

    def process_result_value(self, value: None | dict, dialect: Any) -> None | InTotoPayload:
        """Process when loading an InTotoPayload object from the SQLite db.

        value: None | dict
            The value being loaded.
        """
        if value is None:
            return None

        if not isinstance(value, dict):
            raise TypeError("ProvenancePayload type expects a dict.")

        return validate_intoto_payload(value)
