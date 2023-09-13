# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the InferArtifactPipelineCheck class to check if an artifact is published from a pipeline automatically."""

import logging

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql.sqltypes import String

from macaron.config.defaults import defaults
from macaron.database.table_definitions import CheckFacts
from macaron.errors import InvalidHTTPResponseError
from macaron.slsa_analyzer.analyze_context import AnalyzeContext
from macaron.slsa_analyzer.build_tool.gradle import Gradle
from macaron.slsa_analyzer.build_tool.maven import Maven
from macaron.slsa_analyzer.checks.base_check import BaseCheck
from macaron.slsa_analyzer.checks.check_result import CheckResult, CheckResultType
from macaron.slsa_analyzer.ci_service.base_ci_service import NoneCIService
from macaron.slsa_analyzer.package_registry.maven_central_registry import MavenCentralRegistry
from macaron.slsa_analyzer.provenance.intoto import InTotoV01Payload
from macaron.slsa_analyzer.registry import registry
from macaron.slsa_analyzer.slsa_req import ReqName
from macaron.slsa_analyzer.specs.package_registry_spec import PackageRegistryInfo

logger: logging.Logger = logging.getLogger(__name__)


class InferArtifactPipelineFacts(CheckFacts):
    """The ORM mapping for justifications of the infer_artifact_pipeline check."""

    __tablename__ = "_infer_artifact_pipeline_check"

    #: The primary key.
    id: Mapped[int] = mapped_column(ForeignKey("_check_facts.id"), primary_key=True)  # noqa: A003

    #: The workflow job that triggered deploy.
    deploy_job: Mapped[str] = mapped_column(String, nullable=False)

    #: The workflow step that triggered deploy.
    deploy_step: Mapped[str] = mapped_column(String, nullable=False)

    #: The workflow run URL.
    run_url: Mapped[str] = mapped_column(String, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": "_infer_artifact_pipeline_check",
    }


class InferArtifactPipelineCheck(BaseCheck):
    """This check detects a potential pipeline from which an artifact is published.

    When a verifiable provenance is found for an artifact, the result of this check can be discarded.
    Otherwise, we check whether a CI workflow run has automatically published the artifact.

    We use several heuristics in this check:

      * The workflow run should have started before the artifact is published.
      * The workflow step that calls a deploy command should have run successfully.
      * The workflow step that calls a deploy command should have started before the artifact is published.

    Note: due to a limitation, we cannot specify the provenance checks as parents of this
    check because a check cannot have more than one parent in the current design. It would
    be good to skip this with a success result if the relevant provenance checks pass in the future.
    """

    def __init__(self) -> None:
        """Initialize the InferArtifactPipeline instance."""
        check_id = "mcn_infer_artifact_pipeline_1"
        description = "Detects potential pipelines from which an artifact is published."
        depends_on = [("mcn_build_as_code_1", CheckResultType.PASSED)]
        eval_reqs = [ReqName.BUILD_AS_CODE]
        super().__init__(
            check_id=check_id,
            description=description,
            depends_on=depends_on,
            eval_reqs=eval_reqs,
            result_on_skip=CheckResultType.FAILED,
        )

    def run_check(self, ctx: AnalyzeContext, check_result: CheckResult) -> CheckResultType:
        """Implement the check in this method.

        Parameters
        ----------
        ctx : AnalyzeContext
            The object containing processed data for the target repo.
        check_result : CheckResult
            The object containing result data of a check.

        Returns
        -------
        CheckResultType
            The result type of the check (e.g. PASSED).
        """
        # This check requires the build_as_code check to pass and a repository to be available.
        if not ctx.component.repository:
            check_result["justification"] = [
                "Unable to find a potential workflow run for the artifact because no repository is available."
            ]
            return CheckResultType.FAILED

        # Look for the artifact in the corresponding registry and find the publish timestamp.
        artifact_published_date = None
        package_registry_info_entries = ctx.dynamic_data["package_registries"]
        for package_registry_info_entry in package_registry_info_entries:
            match package_registry_info_entry:
                # TODO: add package registries for other ecosystems.
                case PackageRegistryInfo(
                    build_tool=Gradle() | Maven(),
                    package_registry=MavenCentralRegistry() as mvn_central_registry,
                ):
                    group_id = ctx.component.namespace
                    artifact_id = ctx.component.name
                    version = ctx.component.version
                    try:
                        artifact_published_date = mvn_central_registry.find_publish_timestamp(
                            group_id, artifact_id, version
                        )
                    except InvalidHTTPResponseError as error:
                        logger.debug(error)

        # This check requires the artifact publish artifact to proceed. If the timestamp is not
        # found, we return with a fail result.
        if not artifact_published_date:
            check_result["justification"] = ["Unable to find a publishing timestamp for the artifact."]
            return CheckResultType.FAILED

        # Obtain the metadata inferred by the build_as_code check, which is stored in the `provenances`
        # attribute of the corresponding CI service.
        ci_services = ctx.dynamic_data["ci_services"]
        for ci_info in ci_services:
            ci_service = ci_info["service"]
            # Checking if a CI service is discovered for this repo.
            if isinstance(ci_service, NoneCIService):
                continue

            if ctx.dynamic_data["is_inferred_prov"] and ci_info["provenances"]:
                for inferred_prov in ci_info["provenances"]:
                    # Skip processing the inferred provenance if it does not conform with the in-toto v0.1 specification.
                    if not isinstance(inferred_prov, InTotoV01Payload):
                        continue

                    # This check requires the job and step calling the deploy command.
                    # Validate the content of inferred_prov.
                    predicate = inferred_prov.statement["predicate"]
                    if (
                        not predicate
                        or not isinstance(predicate["invocation"], dict)
                        or "configSource" not in predicate["invocation"]
                        or not isinstance(predicate["invocation"]["configSource"], dict)
                        or "entryPoint" not in predicate["invocation"]["configSource"]
                        or not isinstance(predicate["invocation"]["configSource"]["entryPoint"], str)
                    ):
                        continue
                    if (
                        not isinstance(predicate["buildConfig"], dict)
                        or "jobID" not in predicate["buildConfig"]
                        or not isinstance(predicate["buildConfig"]["jobID"], str)
                        or "stepID" not in predicate["buildConfig"]
                        or not isinstance(predicate["buildConfig"]["stepID"], str)
                    ):
                        continue
                    try:
                        publish_time_range = defaults.getint("package_registries", "publish_time_range", fallback=3600)
                    except ValueError as error:
                        logger.error(
                            "Configuration error: publish_time_range in section of package_registries is not a valid integer %s.",
                            error,
                        )
                        check_result["justification"] = [
                            "Unable to find a potential workflow run for the artifact due to configuration issues."
                        ]
                        return CheckResultType.FAILED

                    # Find the potential workflow runs.
                    if html_urls := ci_service.workflow_run_in_date_time_range(
                        repo_full_name=ctx.component.repository.full_name,
                        workflow=predicate["invocation"]["configSource"]["entryPoint"],
                        date_time=artifact_published_date,
                        step_name=predicate["buildConfig"]["stepID"],
                        time_range=publish_time_range,
                    ):
                        for html_url in html_urls:
                            justification: list[str | dict[str, str]] = [
                                {
                                    f"The artifact is potentially published by workflow"
                                    f" job '{predicate['buildConfig']['jobID']}' at"
                                    f" step '{predicate['buildConfig']['stepID']}' "
                                    "triggered by": html_url,
                                },
                            ]
                            check_result["justification"].extend(justification)
                            check_result["result_tables"].append(
                                InferArtifactPipelineFacts(
                                    deploy_job=predicate["buildConfig"]["jobID"],
                                    deploy_step=predicate["buildConfig"]["stepID"],
                                    run_url=html_url,
                                )
                            )
                        return CheckResultType.PASSED

        check_result["justification"] = ["Unable to find a potential workflow run for the artifact."]
        return CheckResultType.FAILED


registry.register(InferArtifactPipelineCheck())
