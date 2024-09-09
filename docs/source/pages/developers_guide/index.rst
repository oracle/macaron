.. Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
.. Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

.. _macaron-developer-guide:

=========================
Macaron Developer's Guide
=========================

To get started with contributing to Macaron, see the `CONTRIBUTING <https://github.com/oracle/macaron/blob/main/CONTRIBUTING.md>`_ page.

To follow the project's code style, see the :doc:`Macaron Style Guide </pages/developers_guide/style_guide>` page.

For API reference, see the :doc:`API Reference </pages/developers_guide/apidoc/index>` page.

-------------------
Writing a New Check
-------------------

Contributors to Macaron are very likely to need to write a new check or modify an existing one at some point. In this
section, we will explain how Macaron checks work. We will also show how to develop a new check.

+++++++++++++++++
High-level Design
+++++++++++++++++

Before jumping into coding, it is useful to understand how Macaron as a framework works. Macaron is an extensible
framework designed to make writing new supply chain security analyses easy. It provides an interface
that you can leverage to access existing models and abstractions instead of implementing everything from scratch. For
instance, many security checks require traversing through the code in GitHub Actions configurations. Normally,
you would need to find the right repository and commit, clone it, find the workflows, and parse them. With Macaron,
you don't need to do any of that and can simply write your security check by using the parsed shell scripts that are
triggered in the CI.

Another important aspect of our design is that all the check results are automatically mapped and stored in a local database.
By performing this mapping, we make it possible to enforce use case-specific policies on the results of the checks. While storing
the check results in the database happens automatically in Macaron's backend, the developer needs to add a brief specification
to make that possible as we will see later.

Once you get familiar with writing a basic check, you can explore the check dependency feature in Macaron. The checks
in our framework can be customized to only run if another check has run and returned a specific
:class:`result type <macaron.slsa_analyzer.checks.check_result.CheckResultType>`. This feature can be used when checks
have an ordering and a parent-child relationship, i.e., one check implements a weaker or stronger version of a
security property in a parent check. Therefore, it might make sense to skip running the check and report a
:class:`result type <macaron.slsa_analyzer.checks.check_result.CheckResultType>` based on the result of the parent check.

+++++++++++++++++++
The Check Interface
+++++++++++++++++++

Each check needs to be implemented as a Python class in a Python module under ``src/macaron/slsa_analyzer/checks``.
A check class should subclass the :class:`BaseCheck <macaron.slsa_analyzer.checks.base_check.BaseCheck>` class. The name of the source file containing the check should end with ``_check.py``.

The main logic of a check should be implemented in the :func:`run_check <macaron.slsa_analyzer.checks.base_check.BaseCheck.run_check>` abstract method. It is important to understand the input
parameters and output objects computed by this method.

.. code-block: python
    def run_check(self, ctx: AnalyzeContext) -> CheckResultData:

''''''''''''''''
Input Parameters
''''''''''''''''

The :func:`run_check <macaron.slsa_analyzer.checks.base_check.BaseCheck.run_check>` method is a callback called by our checker framework. The framework pre-computes a context object,
:class:`ctx: AnalyzeContext <macaron.slsa_analyzer.analyze_context.AnalyzeContext>` and makes it available as the input
parameter to the function. The ``ctx`` object contains various intermediate representations and models as the input parameter.
Most likely, you will need to use the following properties:

* :attr:`component <macaron.slsa_analyzer.analyze_context.AnalyzeContext.component>`
* :attr:`dynamic_data <macaron.slsa_analyzer.analyze_context.AnalyzeContext.dynamic_data>`

The :attr:`component <macaron.slsa_analyzer.analyze_context.AnalyzeContext.component>`
object acts as a representation of a software component and contains data, such as it's
corresponding :class:`Repository <macaron.database.table_definitions.Repository>` and
:data:`dependencies <macaron.database.table_definitions.components_association_table>`.
Note that :attr:`component <macaron.slsa_analyzer.analyze_context.AnalyzeContext.component>` will also be stored
in the database and its attributes, such as :attr:`repository <macaron.database.table_definitions.Component.repository>`
are established as database relationships. You can see the existing tables and their relationships
in our :mod:`data model <macaron.database.table_definitions>`.

The :attr:`dynamic_data <macaron.slsa_analyzer.analyze_context.AnalyzeContext.dynamic_data>` property would be particularly useful as it contains
data about the CI service, artifact registry, and build tool used for building the software component.
Note that this object is a shared state among checks. If a check runs before another check, it can
make changes to this object, which will be accessible to the checks run subsequently.

''''''
Output
''''''

The :func:`run_check <macaron.slsa_analyzer.checks.base_check.BaseCheck.run_check>` method returns a :class:`CheckResultData <macaron.slsa_analyzer.checks.check_result.CheckResultData>` object.
This object consists of :attr:`result_tables <macaron.slsa_analyzer.checks.check_result.CheckResultData.result_tables>` and
:attr:`result_type <macaron.slsa_analyzer.checks.check_result.CheckResultData.result_type>`.
The :attr:`result_tables <macaron.slsa_analyzer.checks.check_result.CheckResultData.result_tables>` object is the list of facts generated from the check. The :attr:`result_type <macaron.slsa_analyzer.checks.check_result.CheckResultData.result_type>`
value shows the final result type of the check.

+++++++
Example
+++++++

In this example, we show how to add a check to determine if a software component has a source-code repository.
Note that this is a simple example to just demonstrate how to add a check from scratch.
Feel free to explore other existing checks under ``src/macaron/slsa_analyzer/checks`` for more examples.

As discussed earlier, each check needs to be implemented as a Python class in a Python module under ``src/macaron/slsa_analyzer/checks``.
A check class should subclass the :class:`BaseCheck <macaron.slsa_analyzer.checks.base_check.BaseCheck>` class.

'''''''''''''''
Create a module
'''''''''''''''
First create a module called ``repo_check.py`` under ``src/macaron/slsa_analyzer/checks``.


''''''''''''''''''''''''''''
Add a class for the database
''''''''''''''''''''''''''''

* Add a class that subclasses :class:`CheckFacts <macaron.database.table_definitions.CheckFacts>` to map your outputs to a table in the database. The class name should follow the ``<MyCheck>Facts`` pattern.
* Specify the table name in the ``__tablename__`` class variable. Note that the table name should start with ``_`` and it should not have been used by other checks.
* Add the ``id`` column as the primary key where the foreign key is ``_check_facts.id``.
* Add columns for the check outputs that you would like to store in the database. If a column needs to appear as a justification in the HTML/JSON report, pass ``info={"justification": JustificationType.<TEXT or HREF>}`` to the column mapper.
* Add ``__mapper_args__`` class variable and set ``"polymorphic_identity"`` key to the table name.

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
           "polymorphic_identity": "_repo_check",
       }

'''''''''''''''''''
Add the check class
'''''''''''''''''''

Add a class for your check that subclasses :class:`BaseCheck <macaron.slsa_analyzer.checks.base_check.BaseCheck>`,
provide the check details in the initializer method, and implement the logic of the check in
:func:`run_check <macaron.slsa_analyzer.checks.base_check.BaseCheck.run_check>`.

A ``check_id`` should match the ``^mcn_([a-z]+_)+([0-9]+)$`` regular expression, which means it should meet the following requirements:

    - The general format: ``mcn_<name>_<digits>``.
    - Use lowercase alphabetical letters in ``name``. If ``name`` contains multiple words, they must be separated by underscores.

You can set the ``depends_on`` attribute in the initializer method to declare such dependencies. In this example, we leave this list empty.

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

As you can see, the result of the check is returned via the :class:`CheckResultData <macaron.slsa_analyzer.checks.check_result.CheckResultData>` object.
You should specify a :class:`Confidence <macaron.slsa_analyzer.checks.check_result.Confidence>`
score choosing one of the :class:`Confidence <macaron.slsa_analyzer.checks.check_result.Confidence>` enum values,
e.g., :class:`Confidence.HIGH <macaron.slsa_analyzer.checks.check_result.Confidence.HIGH>` and pass it via keyword
argument :attr:`confidence <macaron.database.table_definitions.CheckFacts.confidence>`. You should choose a suitable
confidence score based on the accuracy of your check analysis.

'''''''''''''''''''
Register your check
'''''''''''''''''''

Finally, you need to register your check by adding it to the :mod:`registry module <macaron.slsa_analyzer.registry>` at the end of your check module:

.. code-block:: python

   registry.register(RepoCheck())


'''''''''''''''
Test your check
'''''''''''''''

Finally, you can add tests for you check. We utilize two types of tests: unit tests, and integration tests.

For unit tests, you can add a ``tests/slsa_analyzer/checks/test_repo_check.py`` module. Macaron
uses `pytest <https://docs.pytest.org>`_ and `hypothesis <https://hypothesis.readthedocs.io>`_ for unit testing. Take a look
at other tests for inspiration!

For integration tests, please refer to the README file under ``tests/integration`` for
further instructions and have a look at our existing integration test cases if you need
some examples.

.. toctree::
   :maxdepth: 1

   style_guide
   apidoc/index
