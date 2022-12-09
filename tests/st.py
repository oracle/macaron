# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides useful hypothesis search strategies."""

from string import printable

from hypothesis import strategies as st

PRIMITIVES = st.none() | st.booleans() | st.floats() | st.text(printable) | st.integers()

# https://hypothesis.readthedocs.io/en/latest/data.html#recursive-data
# Suitable for representing JSON data.
RECURSIVE_ST = st.recursive(
    PRIMITIVES,
    lambda children: st.lists(children, max_size=3) | st.dictionaries(st.text(printable), children, max_size=3),
    max_leaves=1,
)

# Represent a flat dictionary.
UN_NESTED_DICT_ST = st.dictionaries(PRIMITIVES, PRIMITIVES, max_size=4)

# Represent nested dictionaries. The keys and values in these dictionaries can be of primitive types.
RECURSIVE_DICT_ST = st.dictionaries(PRIMITIVES, RECURSIVE_ST, max_size=4)

# Represent a context dictionary passed to the Jinja Environment.
# This dictionary MUST have keys as strings, but the values can be nested dictionaries.
JINJA_CONTEXT_DICT = st.dictionaries(st.text(printable), RECURSIVE_DICT_ST, max_size=4)
