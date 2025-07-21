.. Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. References/links
.. _sphinx-apidoc: https://www.sphinx-doc.org/en/master/man/sphinx-apidoc.html

===================
Macaron Style Guide
===================

Macaron makes use of different linters. These linters are managed using `pre-commit <https://pre-commit.com/>`_ hooks (see the `.pre-commit-config.yaml <https://github.com/oracle/macaron/blob/main/.pre-commit-config.yaml>`_ file). Most styling issues should be caught by pre-commit hooks. However, there are some additional styling rules that we follow.

--------------
Python Modules
--------------

We ban the use of ``__all__`` in ``__init__.py`` files due to known issues with the `sphinx-apidoc`_ docstring generator.

------
Naming
------

We avoid using the same name for two or more classes in all cases (including cases where the two classes are in different modules), due to known issues with the `sphinx-apidoc`_ docstring generator.


----------
Docstrings
----------

We use `sphinx-apidoc`_ to generate :doc:`API Reference </pages/developers_guide/apidoc/index>` automatically from `Python docstrings <https://www.python.org/dev/peps/pep-0257/>`_ written in the code.

We follow the `numpydoc style <https://numpydoc.readthedocs.io/en/latest/format.html>`_ for Python docstrings (see `example <https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_numpy.html>`_) with some exceptions.

''''''''''''''''''''''
Docstrings for classes
''''''''''''''''''''''

Each class should have a docstring written in a triple-quoted block describing the purpose of the class.

For variables of a class: we do not use the ``Attribute`` section as per the `numpydoc style for class docstring <https://numpydoc.readthedocs.io/en/latest/format.html#class-docstring>`_, due to some known issues with Sphinx. Instead, to document class variables, we follow the following convention:

- For simple Python classes having an ``__init__`` constructor: We document the ``__init__`` constructor like any other regular method, i.e. all parameters should be documented. We do not document `instance variables <https://docs.python.org/3/tutorial/classes.html#class-and-instance-variables>`_ and consider them to be private to the class. To expose an instance variable of a class in the documentation, we use `Python property <https://docs.python.org/3/library/functions.html#property>`_ and document the property methods (``getter``, ``setter``, and ``deleter`` methods) instead. Example:

  .. code-block:: python

    class Point2D:
        """A point in the 2D coordinate system."""

        def __init__(self, coordinate: tuple[float, float]) -> None:
            """Construct a point in the 2D coordinate system.

            Parameters
            ----------
            coordinate : tuple[float, float]
                A pair of x and y coordinates.
            """
            self._x = tuple[0]
            self._y = tuple[1]

        @property
        def x(self) -> float:
            """Get the x coordinate of the point."""
            return self._x

- For Python classes that declare instance variables in class attributes (e.g. :py:class:`typing.NamedTuple`, :py:func:`dataclasses.dataclass`, or `SQLAlchemy ORM Mapped classes <https://docs.sqlalchemy.org/en/20/orm/mapping_styles.html>`_): We document each instance variable with a comment above the variable prefixed with ``#:`` (if the comment spans more than one line, all lines must be prefixed with ``#:``). Example:

  .. code-block:: python

    from typing import NamedTuple


    class Point2D(NamedTuple):
        """A point in the 2D coordinate system."""

        #: The x coordinate of the point.
        x: float
        #: The y coordinate of the point.
        y: float


--------
Comments
--------

Comments should use typical grammar where appropriate. Ideally, they should be comprised of sentences that start with capital letters, and end with punctuation.
We use a pre-commit hook script to help enforce this.
The script is a lightweight implementation that can make mistakes in some cases.
Python script files that have been changed in the commit will be passed to the checker, if they reside in either the ``src/macaron`` or ``tests`` directories.

''''''''''''''''''''''''
Working with the script:
''''''''''''''''''''''''

- Try to avoid having Proper nouns in the middle of sentences spill over to a new line, as this will be considered as the start of a sentence instead.
- To prevent the script from changing a particular file, add the following comment after the copyright information: "# grammar: off"
- To disable the script for a particular comment, use a double pound sign, e.g. "## <The comment to ignore>"
