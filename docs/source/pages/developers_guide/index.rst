.. Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

=========================
Macaron Developer's Guide
=========================

To get started with contributing to Macaron, see the `CONTRIBUTING <https://github.com/oracle/macaron/blob/main/CONTRIBUTING.md>`_ page.

To follow the project's code style, see the :doc:`Macaron Style Guide </pages/developers_guide/style_guide>` page.

For API reference, see the :doc:`API Reference </pages/developers_guide/apidoc/index>` page.

-------------------
Writing a New Check
-------------------

As a contributor to Macaron, it is very likely to need to write a new check or modify an existing one at some point. In this
section, we will understand how Macaron checks work and what we need to do to develop one.

+++++++++++++++++
High-level Design
+++++++++++++++++

Before jumping into coding, it is useful to understand how Macaron as a framework works. Macaron is an extensible
framework designed to make writing new supply chain security analyses easy. It provides an interface
that you can leverage to access existing models and abstractions instead of implementing everything from scratch. For
instance, many security checks require to traverse through the code in GitHub Actions configurations. Normally,
you would need to find the right repository and commit, clone it, find the workflows, and parse them. With Macaron,
you don't need to do any of that and can simply write your security check by using the parsed shell scripts that are
triggered in the CI.

Another important aspect of our design is that all the check results are automatically mapped and stored in a local database.
By performing this mapping, we make it possible to enforce flexible policies on the results of the checks. While storing
the check results to the database happens automatically by Macaron's backend, the developer needs to add a brief specification
to make that possible as we will see later.

+++++++++++++++++++
The Check Interface
+++++++++++++++++++

Each check needs to be implemented as a Python class in a Python module under ``src/macaron/slsa_analyzer/checks``.
A check class should subclass the ``BaseCheck`` class in :ref:`base_check module <pages/developers_guide/apidoc/macaron\.slsa_analyzer\.checks:macaron.slsa\\_analyzer.checks.base\\_check module>`.

You need to set the name, description, and other details of your new check in the ``__init__`` method. After implementing
the initializer, you need to implement the ``run_check`` abstract method. This method provides the context object
:ref:`AnalyzeContext <pages/developers_guide/apidoc/macaron\.slsa_analyzer:macaron.slsa\\_analyzer.analyze\\_context module>`, which contains various
intermediate representations and models. The ``dynamic_data`` property would be particularly useful as it contains
data about the CI service, artifact registry, and build tool used for building the software component.

``component`` is another useful attribute in the :ref:`AnalyzeContext <pages/developers_guide/apidoc/macaron\.slsa_analyzer:macaron.slsa\\_analyzer.analyze\\_context module>` object
that you should know about. This attribute contains the information about a software component, such
as it's corresponding ``repository`` and ``dependencies``. Note that ``component`` will also be stored into the database and its attributes
such as ``repository`` are established as database relationships. You can see the existing tables and their
relationships in our :ref:`data model <pages/developers_guide/apidoc/macaron.database:macaron.database.table\\_definitions module>`.

Once you implement the logic of your check in the ``run_check`` method, you need to add a class to help
Macaron handle your check's output:

   * Add a class that subclasses ``CheckFacts`` to map your outputs to a table in the database. The class name should follow the ``<MyCheck>Facts`` pattern.
   * Specify the table name in the ``__tablename__ = "_my_check"`` class variable. Note that the table name should start with ``_`` and it should not have been used by other checks.
   * Add the ``id`` column as the primary key where the foreign key is ``_check_facts.id``.
   * Add columns for the check outputs that you would like to store into the database. If a column needs to appear as a justification in the HTML/JSON report, pass ``info={"justification": JustificationType.<TEXT or HREF>}`` to the column mapper.
   * Add ``__mapper_args__`` class variable and set ``"polymorphic_identity"`` key to the table name.

Next, you need to create a ``result_tables`` list and append check facts as part of the ``run_check`` implementation.
You should also specify a :ref:`Confidence <pages/developers_guide/apidoc/macaron\.slsa_analyzer\.checks:macaron.slsa\\_analyzer.checks.check\\_result module>`
score choosing one of  the ``Confidence`` enum values, e.g., ``Confidence.HIGH`` and pass it via keyword
argument ``confidence``. You should choose a suitable confidence score based on the accuracy
of your check analysis.

.. code-block:: python

   result_tables.append(MyCheckFacts(col_foo=foo, col_bar=bar, confidence=Confidence.HIGH))

This list as well as the check result status should be stored in a :ref:`CheckResultData <pages/developers_guide/apidoc/macaron\.slsa_analyzer\.checks:macaron.slsa\\_analyzer.checks.check\\_result module>`
object and returned by ``run_check``.

Finally, you need to register your check by adding it to the :ref:`registry module <pages/developers_guide/apidoc/macaron\.slsa_analyzer:macaron.slsa\\_analyzer.registry module>`:

.. code-block:: python

   registry.register(MyCheck())

And of course, make sure to add tests for you check by adding a module under ``tests/slsa_analyzer/checks/``.

+++++++
Example
+++++++

In this example, we show how to add a check determine if a software component has a source-code repository.
Feel free to explore other existing checks under ``src/macaron/slsa_analyzer/checks`` for more examples.

1. First create a module called ``repo_check.py`` under ``src/macaron/slsa_analyzer/checks``.

2. Add a class and specify the columns that you want to store for the check outputs to the database.

.. code-block:: python

   # Add this line at the top of the file to create the logger object if you plan to use it.
   logger: logging.Logger = logging.getLogger(__name__)


   class RepoCheckFacts(CheckFacts):
       """The ORM mapping for justifications in the check repository check."""

       __tablename__ = "_repo_check"

       #: The primary key.
       id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)

       #: The Git repository path.
       git_repo: Mapped[str] = mapped_column(String, nullable=True, info={"justification": JustificationType.HREF})

       __mapper_args__ = {
           "polymorphic_identity": "__repo_check",
       }

3. Add a class for your check, provide the check details in the initializer method, and implement the logic of the check in ``run_check``.

.. code-block:: python

   class RepoCheck(BaseCheck):
       """This Check checks whether the target software component has a source-code repository."""

       def __init__(self) -> None:
           """Initialize instance."""
           check_id = "mcn_repo_exists_1"
           description = "Check whether the target software component has a source-code repository."
           depends_on: list[tuple[str, CheckResultType]] = []  # This check doesn't depend on any other checks.
           eval_reqs = [
               ReqName.VCS
           ]  # Choose a SLSA requirement that roughly matches this check from the ReqName enum class.
           super().__init__(check_id=check_id, description=description, depends_on=depends_on, eval_reqs=eval_reqs)

       def run_check(self, ctx: AnalyzeContext) -> CheckResultData:
           """Implement the check in this method.

           Parameters
           ----------
           ctx : AnalyzeContext
                 The object containing processed data for the target software component.

           Returns
           -------
           CheckResultData
                 The result of the check.
           """
           if not ctx.component.repository:
               logger.info("Unable to find a Git repository for %s", ctx.component.purl)
               # We do not store any results in the database if a check fails. So, just leave result_tables empty.
               return CheckResultData(result_tables=[], result_type=CheckResultType.FAILED)

           return CheckResultData(
               result_tables=[RepoCheckFacts(git_repo=ctx.component.repository.remote_path, confidence=Confidence.HIGH)],
               result_type=CheckResultType.PASSED,
           )

4. Register your check.

.. code-block:: python

   registry.register(RepoCheck())


Finally, you can add tests for you check by adding ``tests/slsa_analyzer/checks/test_repo_check.py`` module. Macaron
uses `pytest <https://docs.pytest.org>`_ and `hypothesis <https://hypothesis.readthedocs.io>`_ for testing. Take a look
at other tests for inspiration!

.. toctree::
   :maxdepth: 1

   style_guide
   apidoc/index
