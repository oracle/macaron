# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""Models of supported commands, actions, etc. that may be invoked by build pipelines.

Defines how they are modelled by the dataflow analysis in terms of their effect on the abstract state.
"""

from __future__ import annotations

from enum import Enum, auto
from functools import cache

from macaron.code_analyzer.dataflow_analysis import core, evaluation, facts


class BoundParameterisedStatementSet:
    """Representation of a set of (simultaneous) write operations.

    Defined as a reference to a set of generic parameterised statements, along with a set of parameter bindings
    that instantiate the parameterised statements with concrete subexpressions.
    """

    #: Set of generic parameterised statements.
    parameterised_stmts: evaluation.StatementSet
    #: Parameter bindings for values.
    value_parameter_binds: dict[str, facts.Value]
    #: Parameter bindings for locations.
    location_parameter_binds: dict[str, facts.LocationSpecifier]
    #: Parameter bindings for scopes.
    scope_parameter_binds: dict[str, facts.Scope]
    #: Instantiated statements.
    instantiated_statements: evaluation.StatementSet

    def __init__(
        self,
        parameterised_stmts: evaluation.StatementSet,
        value_parameter_binds: dict[str, facts.Value] | None = None,
        location_parameter_binds: dict[str, facts.LocationSpecifier] | None = None,
        scope_parameter_binds: dict[str, facts.Scope] | None = None,
    ) -> None:
        """Initialize bound parameterised statement set.

        Parameters
        ----------
        parameterised_stmts: evaluation.StatementSet
            Set of generic parameterised statements.
        value_parameter_binds: dict[str, facts.Value] | None
            Parameter bindings for value.
        location_parameter_binds: dict[str, facts.LocationSpecifier] | None
            Parameter bindings for locations.
        scope_parameter_binds: dict[str, facts.Scope] | None
            Parameter bindings for scopes.
        """
        self.parameterised_stmts = parameterised_stmts
        self.value_parameter_binds = value_parameter_binds or {}
        self.location_parameter_binds = location_parameter_binds or {}
        self.scope_parameter_binds = scope_parameter_binds or {}

        transformer = evaluation.ParameterPlaceholderTransformer(
            allow_unbound_params=False,
            value_parameter_binds=self.value_parameter_binds,
            location_parameter_binds=self.location_parameter_binds,
            scope_parameter_binds=self.scope_parameter_binds,
        )
        self.instantiated_statements = transformer.transform_statement_set(parameterised_stmts)

    def get_statements(self) -> evaluation.StatementSet:
        """Return instantiated statement set."""
        return self.instantiated_statements


class BoundParameterisedModelNode(core.StatementNode):
    """Statement node that applies effects as defined in a provided model.

    Subclasses will define a statement node with a specific model.
    """

    #: Statement effects model.
    stmts: BoundParameterisedStatementSet

    def __init__(self, stmts: BoundParameterisedStatementSet) -> None:
        """Initialise model statement node."""
        super().__init__()

        self.stmts = stmts

    def apply_effects(self, before_state: core.State) -> dict[core.ExitType, core.State]:
        """Apply effects as defined in a provided model."""
        return {core.DEFAULT_EXIT: self.stmts.get_statements().apply_effects(before_state)}


class InstallPackageNode(BoundParameterisedModelNode):
    """Model for package installation.

    Stores a representation of the installed package into the abstract "installed packages" location.
    """

    @staticmethod
    @cache
    def get_model() -> evaluation.StatementSet:
        """Return the model."""
        return evaluation.StatementSet(
            {
                evaluation.WriteStatement(
                    facts.Location(
                        facts.ParameterPlaceholderScope("install_scope"),
                        facts.Installed(name=facts.ParameterPlaceholderValue("name")),
                    ),
                    facts.InstalledPackage(
                        name=facts.ParameterPlaceholderValue("name"),
                        version=facts.ParameterPlaceholderValue("version"),
                        distribution=facts.ParameterPlaceholderValue("distribution"),
                        url=facts.ParameterPlaceholderValue("url"),
                    ),
                )
            }
        )

    #: Scope into which to install.
    install_scope: facts.Scope
    #: Package name.
    name: facts.Value
    #: Package version.
    version: facts.Value
    #: Package distribution.
    distribution: facts.Value
    #: URL of package.
    url: facts.Value

    def __init__(
        self,
        install_scope: facts.Scope,
        name: facts.Value,
        version: facts.Value,
        distribution: facts.Value,
        url: facts.Value,
    ) -> None:
        """Initialize install package node.

        Parameters
        ----------
        install_scope: facts.Scope
            Scope into which to install.
        name: facts.Value
            Package name.
        version: facts.Value
            Package version.
        distribution: facts.Value
            Package distribution.
        url: facts.Value
            URL of package.
        """
        self.install_scope = install_scope
        self.name = name
        self.version = version
        self.distribution = distribution
        self.url = url

        bound_stmts = BoundParameterisedStatementSet(
            parameterised_stmts=self.get_model(),
            value_parameter_binds={"name": name, "version": version, "distribution": distribution, "url": url},
            scope_parameter_binds={"install_scope": install_scope},
        )

        super().__init__(bound_stmts)

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties tables with the model parameters."""
        return {
            "install_scope": {(None, self.install_scope.to_datalog_fact_string())},
            "name": {(None, self.name.to_datalog_fact_string())},
            "version": {(None, self.version.to_datalog_fact_string())},
            "distribution": {(None, self.distribution.to_datalog_fact_string())},
            "url": {(None, self.url.to_datalog_fact_string())},
        }


class VarAssignKind(Enum):
    """Kind of variable assignment."""

    #: Bash environment variable.
    BASH_ENV_VAR = auto()
    #: Bash function declaration.
    BASH_FUNC_DECL = auto()
    #: GitHub job variable.
    GITHUB_JOB_VAR = auto()
    #: GitHub environment variable.
    GITHUB_ENV_VAR = auto()
    #: Other uncategorized variable.
    OTHER = auto()


class VarAssignNode(BoundParameterisedModelNode):
    """Model for variable assignment.

    Stores the assigned value to the variable location.
    """

    @staticmethod
    @cache
    def get_model() -> evaluation.StatementSet:
        """Return the model."""
        return evaluation.StatementSet(
            {
                evaluation.WriteStatement(
                    facts.Location(
                        facts.ParameterPlaceholderScope("var_scope"),
                        facts.Variable(facts.ParameterPlaceholderValue("var_name")),
                    ),
                    facts.ParameterPlaceholderValue("value"),
                )
            }
        )

    #: The kind of variable.
    kind: VarAssignKind
    #: The scope in which the variable is stored.
    var_scope: facts.Scope
    #: The name of the variable.
    var_name: facts.Value
    #: The value to assign to the variable.
    value: facts.Value

    def __init__(self, kind: VarAssignKind, var_scope: facts.Scope, var_name: facts.Value, value: facts.Value) -> None:
        """Initialize variable assignment node.

        Parameters
        ----------
        kind: VarAssignKind
            The kind of variable.
        var_scope: facts.Scope
            The scope in which the variable is stored.
        var_name: facts.Value
            The name of the variable.
        value: facts.Value
            The value to assign to the variable.
        """
        self.kind = kind
        self.var_scope = var_scope
        self.var_name = var_name
        self.value = value

        bound_stmts = BoundParameterisedStatementSet(
            parameterised_stmts=self.get_model(),
            value_parameter_binds={"var_name": var_name, "value": value},
            scope_parameter_binds={"var_scope": var_scope},
        )

        super().__init__(bound_stmts)

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties tables with the model parameters."""
        return {
            "kind": {(None, self.kind.name)},
            "var_scope": {(None, self.var_scope.to_datalog_fact_string())},
            "var_name": {(None, self.var_name.to_datalog_fact_string())},
            "value": {(None, self.value.to_datalog_fact_string())},
        }


class GitHubActionsGitCheckoutModelNode(core.StatementNode):
    """Model for GitHub git checkout operation.

    Currently modelled as a no-op.
    """

    def apply_effects(self, before_state: core.State) -> dict[core.ExitType, core.State]:
        """Apply effects for git checkout (currently nothing)."""
        state = core.State()
        core.transfer_state(before_state, state)
        return {core.DEFAULT_EXIT: state}


class GitHubActionsUploadArtifactModelNode(BoundParameterisedModelNode):
    """Model for uploading artifacts to GitHub pipeline artifact storage.

    Stores the content read from a file to the artifact storage location.
    """

    @staticmethod
    @cache
    def get_model() -> evaluation.StatementSet:
        """Return the model."""
        return evaluation.StatementSet(
            {
                evaluation.WriteStatement(
                    facts.Location(
                        facts.ParameterPlaceholderScope("artifacts_scope"),
                        facts.Artifact(
                            name=facts.ParameterPlaceholderValue("artifact_name"),
                            file=facts.ParameterPlaceholderValue("artifact_file"),
                        ),
                    ),
                    facts.Read(
                        facts.Location(
                            facts.ParameterPlaceholderScope("filesystem_scope"),
                            facts.Filesystem(facts.ParameterPlaceholderValue("path")),
                        )
                    ),
                )
            }
        )

    #: Scope for pipeline artifact storage.
    artifacts_scope: facts.Scope
    #: Artifact name.
    artifact_name: facts.Value
    #: Artifact filename.
    artifact_file: facts.Value
    #: Scope for filesystem from which to read file.
    filesystem_scope: facts.Scope
    #: File path to read artifact content from.
    path: facts.Value

    def __init__(
        self,
        artifacts_scope: facts.Scope,
        artifact_name: facts.Value,
        artifact_file: facts.Value,
        filesystem_scope: facts.Scope,
        path: facts.Value,
    ) -> None:
        """Initialize upload artifacts node.

        Parameters
        ----------
        artifacts_scope: facts.Scope
            Scope for pipeline artifact storage.
        artifact_name: facts.Value
            Artifact name.
        artifact_file: facts.Value
            Artifact filename.
        filesystem_scope: facts.Scope
            Scope for filesystem from which to read file.
        path: facts.Value
            File path to read artifact content from.
        """
        self.artifacts_scope = artifacts_scope
        self.artifact_name = artifact_name
        self.artifact_file = artifact_file
        self.filesystem_scope = filesystem_scope
        self.path = path

        bound_stmts = BoundParameterisedStatementSet(
            parameterised_stmts=self.get_model(),
            value_parameter_binds={"artifact_name": artifact_name, "artifact_file": artifact_file, "path": path},
            scope_parameter_binds={"artifacts_scope": artifacts_scope, "filesystem_scope": filesystem_scope},
        )

        super().__init__(bound_stmts)

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties tables with the model parameters."""
        return {
            "artifacts_scope": {(None, self.artifacts_scope.to_datalog_fact_string())},
            "artifact_name": {(None, self.artifact_name.to_datalog_fact_string())},
            "artifact_file": {(None, self.artifact_file.to_datalog_fact_string())},
            "filesystem_scope": {(None, self.filesystem_scope.to_datalog_fact_string())},
            "path": {(None, self.path.to_datalog_fact_string())},
        }


class GitHubActionsDownloadArtifactModelNode(BoundParameterisedModelNode):
    """Model for downloading artifacts from GitHub pipeline artifact storage.

    For each file in the artifact, reads the content of that artifact and
    stores it to the filesystem under the same filename.
    """

    @staticmethod
    @cache
    def get_model() -> evaluation.StatementSet:
        """Return model."""
        return evaluation.StatementSet(
            {
                evaluation.WriteStatement(
                    facts.Location(
                        facts.ParameterPlaceholderScope("filesystem_scope"),
                        facts.Filesystem(
                            facts.Read(
                                facts.Location(
                                    facts.ParameterPlaceholderScope("artifacts_scope"),
                                    facts.ArtifactAnyFilename(facts.ParameterPlaceholderValue("artifact_name")),
                                )
                            )
                        ),
                    ),
                    facts.Read(
                        facts.Location(
                            facts.ParameterPlaceholderScope("artifacts_scope"),
                            facts.Artifact(
                                name=facts.ParameterPlaceholderValue("artifact_name"),
                                file=facts.Read(
                                    facts.Location(
                                        facts.ParameterPlaceholderScope("artifacts_scope"),
                                        facts.ArtifactAnyFilename(facts.ParameterPlaceholderValue("artifact_name")),
                                    )
                                ),
                            ),
                        )
                    ),
                )
            }
        )

    #: Scope for pipeline artifact storage.
    artifacts_scope: facts.Scope
    #: Artifact name.
    artifact_name: facts.Value
    #: Scope for filesystem to store artifacts to.
    filesystem_scope: facts.Scope

    def __init__(self, artifacts_scope: facts.Scope, artifact_name: facts.Value, filesystem_scope: facts.Scope) -> None:
        """Initialize download artifacts node.

        Parameters
        ----------
        artifacts_scope: facts.Scope
            Scope for pipeline artifact storage.
        artifact_name: facts.Value
            Artifact name.
        filesystem_scope: facts.Scope
            Scope for filesystem to store artifacts to.
        """
        self.artifacts_scope = artifacts_scope
        self.artifact_name = artifact_name
        self.filesystem_scope = filesystem_scope

        bound_stmts = BoundParameterisedStatementSet(
            parameterised_stmts=self.get_model(),
            value_parameter_binds={"artifact_name": artifact_name},
            scope_parameter_binds={"artifacts_scope": artifacts_scope, "filesystem_scope": filesystem_scope},
        )

        super().__init__(bound_stmts)

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties tables with the model parameters."""
        return {
            "artifacts_scope": {(None, self.artifacts_scope.to_datalog_fact_string())},
            "artifact_name": {(None, self.artifact_name.to_datalog_fact_string())},
            "filesystem_scope": {(None, self.filesystem_scope.to_datalog_fact_string())},
        }


class GitHubActionsReleaseModelNode(GitHubActionsUploadArtifactModelNode):
    """Model for uploading artifacts to a GitHub release.

    Modelled in the same way as artifact upload.
    """


class BashEchoNode(BoundParameterisedModelNode):
    """Model for Bash echo command, which writes the echoed value to some location."""

    @staticmethod
    @cache
    def get_model() -> evaluation.StatementSet:
        """Return model."""
        return evaluation.StatementSet(
            {
                evaluation.WriteStatement(
                    facts.Location(
                        facts.ParameterPlaceholderScope("out_loc_scope"),
                        facts.ParameterPlaceholderLocation("out_loc_spec"),
                    ),
                    facts.ParameterPlaceholderValue("value"),
                )
            }
        )

    #: Output location.
    out_loc: facts.Location
    #: Value written.
    value: facts.Value

    def __init__(self, out_loc: facts.Location, value: facts.Value) -> None:
        """Initialize echo node.

        Parameters
        ----------
        out_loc: facts.Location
            Output location.
        value: facts.Value
            Value written.
        """
        self.out_loc = out_loc
        self.value = value

        bound_stmts = BoundParameterisedStatementSet(
            parameterised_stmts=self.get_model(),
            value_parameter_binds={"value": value},
            location_parameter_binds={"out_loc_spec": out_loc.loc},
            scope_parameter_binds={"out_loc_scope": out_loc.scope},
        )

        super().__init__(bound_stmts)

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties tables with the model parameters."""
        return {
            "out_loc": {(None, self.out_loc.to_datalog_fact_string())},
            "value": {(None, self.value.to_datalog_fact_string())},
        }


class Base64EncodeNode(BoundParameterisedModelNode):
    """Model for Base64 encode operation.

    Reads a value from some location, Base64-encodes it and writes the result to another location.
    """

    @staticmethod
    @cache
    def get_model() -> evaluation.StatementSet:
        """Return model."""
        return evaluation.StatementSet(
            {
                evaluation.WriteStatement(
                    facts.Location(
                        facts.ParameterPlaceholderScope("out_loc_scope"),
                        facts.ParameterPlaceholderLocation("out_loc_spec"),
                    ),
                    facts.UnaryStringOp(
                        facts.UnaryStringOperator.BASE64_ENCODE,
                        facts.Read(
                            facts.Location(
                                facts.ParameterPlaceholderScope("in_loc_scope"),
                                facts.ParameterPlaceholderLocation("in_loc_spec"),
                            )
                        ),
                    ),
                )
            }
        )

    #: Location to read input from.
    in_loc: facts.Location
    #: Location to write encoded output to.
    out_loc: facts.Location

    def __init__(self, in_loc: facts.Location, out_loc: facts.Location) -> None:
        """Initialize Base64 encode node.

        Parameters
        ----------
        in_loc: facts.Location
            Location to read input from.
        out_loc: facts.Location
            Location to write encoded output to.
        """
        self.in_loc = in_loc
        self.out_loc = out_loc

        bound_stmts = BoundParameterisedStatementSet(
            parameterised_stmts=self.get_model(),
            location_parameter_binds={"out_loc_spec": out_loc.loc, "in_loc_spec": in_loc.loc},
            scope_parameter_binds={"out_loc_scope": out_loc.scope, "in_loc_scope": in_loc.scope},
        )

        super().__init__(bound_stmts)

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties tables with the model parameters."""
        return {
            "in_loc": {(None, self.in_loc.to_datalog_fact_string())},
            "out_loc": {(None, self.out_loc.to_datalog_fact_string())},
        }


class Base64DecodeNode(BoundParameterisedModelNode):
    """Model for Base64 decode operation.

    Reads a value from some location, Base64-decodes it and writes the result to another location.
    """

    @staticmethod
    @cache
    def get_model() -> evaluation.StatementSet:
        """Return model."""
        return evaluation.StatementSet(
            {
                evaluation.WriteStatement(
                    facts.Location(
                        facts.ParameterPlaceholderScope("out_loc_scope"),
                        facts.ParameterPlaceholderLocation("out_loc_spec"),
                    ),
                    facts.UnaryStringOp(
                        facts.UnaryStringOperator.BASE64DECODE,
                        facts.Read(
                            facts.Location(
                                facts.ParameterPlaceholderScope("in_loc_scope"),
                                facts.ParameterPlaceholderLocation("in_loc_spec"),
                            )
                        ),
                    ),
                )
            }
        )

    #: Location to read input from.
    in_loc: facts.Location
    #: Location to write decoded output to.
    out_loc: facts.Location

    def __init__(self, in_loc: facts.Location, out_loc: facts.Location) -> None:
        """Initialize Base64 decode node.

        Parameters
        ----------
        in_loc: facts.Location
            Location to read input from.
        out_loc: facts.Location
            Location to write decoded output to.
        """
        self.in_loc = in_loc
        self.out_loc = out_loc

        bound_stmts = BoundParameterisedStatementSet(
            parameterised_stmts=self.get_model(),
            location_parameter_binds={"out_loc_spec": out_loc.loc, "in_loc_spec": in_loc.loc},
            scope_parameter_binds={"out_loc_scope": out_loc.scope, "in_loc_scope": in_loc.scope},
        )

        super().__init__(bound_stmts)

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties tables with the model parameters."""
        return {
            "in_loc": {(None, self.in_loc.to_datalog_fact_string())},
            "out_loc": {(None, self.out_loc.to_datalog_fact_string())},
        }


class MavenBuildModelNode(BoundParameterisedModelNode):
    """Model for Maven build commands.

    Maven build  behaviour is approximated as writing some files under the target directory.
    """

    @staticmethod
    @cache
    def get_model() -> evaluation.StatementSet:
        """Return model."""
        return evaluation.StatementSet(
            {
                evaluation.WriteStatement(
                    facts.Location(
                        facts.ParameterPlaceholderScope("filesystem_scope"),
                        facts.FilesystemAnyUnderDir(facts.StringLiteral("./target")),
                    ),
                    facts.ArbitraryNewData("mvn"),  # TODO something better?
                )
            }
        )

    #: Scope for filesystem written to.
    filesystem_scope: facts.Scope

    def __init__(self, filesystem_scope: facts.Scope) -> None:
        """Initialize Maven build node.

        Parameters
        ----------
        filesystem_scope: facts.Scope
            Scope for filesystem written to.
        """
        self.filesystem_scope = filesystem_scope

        bound_stmts = BoundParameterisedStatementSet(
            parameterised_stmts=self.get_model(), scope_parameter_binds={"filesystem_scope": filesystem_scope}
        )

        super().__init__(bound_stmts)

    def get_printable_properties_table(self) -> dict[str, set[tuple[str | None, str]]]:
        """Return a properties tables with the model parameters."""
        return {"filesystem_scope": {(None, self.filesystem_scope.to_datalog_fact_string())}}
