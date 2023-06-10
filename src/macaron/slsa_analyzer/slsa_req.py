# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the base classes for defining SLSA requirements."""

import logging
from enum import Enum

from macaron.slsa_analyzer.levels import SLSALevels

logger: logging.Logger = logging.getLogger(__name__)


class ReqName(Enum):
    """Store the name of each requirement."""

    # Source requirements
    VCS = "Version controlled"
    VERIFIED_HISTORY = "Verified history"
    RETAINED_INDEFINITELY = "Retained indefinitely"
    TWO_PERSON_REVIEWED = "Two-person reviewed"

    # Build requirements
    SCRIPTED_BUILD = "Scripted Build"
    BUILD_SERVICE = "Build service"
    BUILD_AS_CODE = "Build as code"
    EPHEMERAL_ENVIRONMENT = "Ephemeral environment"
    ISOLATED = "Isolated"
    PARAMETERLESS = "Parameterless"
    HERMETIC = "Hermetic"
    REPRODUCIBLE = "Reproducible"

    # Provenance requirements
    PROV_AVAILABLE = "Provenance - Available"
    PROV_AUTH = "Provenance - Authenticated"
    PROV_SERVICE_GEN = "Provenance - Service generated"
    PROV_NON_FALSIFIABLE = "Provenance - Non falsifiable"
    PROV_DEPENDENCIES_COMPLETE = "Provenance - Dependencies complete"

    # Provenance content requirements
    PROV_CONT_ARTI = "Provenance content - Identifies artifacts"
    PROV_CONT_BUILDER = "Provenance content - Identifies builder"
    PROV_CONT_BUILD_INS = "Provenance content - Identifies build instructions"
    PROV_CONT_SOURCE = "Provenance content - Identifies source code"
    PROV_CONT_ENTRY = "Provenance content - Identifies entry point"
    PROV_CONT_BUILD_PARAMS = "Provenance content - Includes all build parameters"
    PROV_CONT_TRANSITIVE_DEPS = "Provenance content - Includes all transitive dependencies"
    PROV_CONT_REPRODUCIBLE_INFO = "Provenance content - Includes reproducible info"
    PROV_CONT_META_DATA = "Provenance content - Includes metadata"

    # Common requirements
    SECURITY = "Security"
    ACCESS = "Access"
    SUPERUSERS = "Superusers"
    EXPECTATION = "Provenance conforms with expectations"


class Category(Enum):
    """The category each requirement belongs to."""

    BUILD = "Build"
    """Related to the build process."""
    SOURCE = "Source"
    """Related to the source control."""
    PROVENANCE = "Provenance"
    """Related to how the provenance is generated and consumed."""
    PROVENANCE_CONTENT = "Provenance content"
    """Related to the content of provenance."""
    COMMON = "Common requirements"
    """Related to common requirements for every trusted system involved in the supply chain."""


# Contains the description, category and level each requirement correspond to.
BUILD_REQ_DESC = {
    ReqName.VCS: [
        """
        Every change to the source is tracked in a version control
        """,
        Category.SOURCE,
        SLSALevels.LEVEL2,
    ],
    ReqName.VERIFIED_HISTORY: [
        """
        Every change in the revision's history has at least one strongly authenticated actor identity
        (author, uploader, reviewer, etc.) and timestamp.
        """,
        Category.SOURCE,
        SLSALevels.LEVEL3,
    ],
    ReqName.RETAINED_INDEFINITELY: [
        """
        The revision and its change history are preserved indefinitely and cannot be deleted,
        except when subject to an established and transparent expectation for obliteration,
        such as a legal or expectation requirement.
        """,
        Category.SOURCE,
        SLSALevels.LEVEL3,
    ],
    ReqName.TWO_PERSON_REVIEWED: [
        """
        Every change in the revision's history was agreed to by two trusted persons prior to submission,
        and both of these trusted persons were strongly authenticated.
        """,
        Category.SOURCE,
        SLSALevels.LEVEL4,
    ],
    ReqName.SCRIPTED_BUILD: [
        """
        All build steps were fully defined in some sort of "build script".
        The only manual command, if any, was to invoke the build script.
        Examples:
        - Build script is Makefile, invoked via make all.
        - Build script is .github/workflows/build.yaml, invoked by GitHub Actions.
        """,
        Category.BUILD,
        SLSALevels.LEVEL1,
    ],
    ReqName.BUILD_SERVICE: [
        """
        All build steps ran using some build service, not on a developer's workstation.
        Examples: GitHub Actions, Google Cloud Build, Travis CI.
        """,
        Category.BUILD,
        SLSALevels.LEVEL2,
    ],
    ReqName.BUILD_AS_CODE: [
        """
        The build definition and configuration is defined in source control and is executed by the build service.
        """,
        Category.BUILD,
        SLSALevels.LEVEL3,
    ],
    ReqName.EPHEMERAL_ENVIRONMENT: [
        """
        The build service ensured that the build steps ran in an ephemeral environment, such as a container or VM,
        provisioned solely for this build, and not reused from a prior build.
        """,
        Category.BUILD,
        SLSALevels.LEVEL3,
    ],
    ReqName.ISOLATED: [
        """
        The build service ensured that the build steps ran in an isolated environment free of influence
        from other build instances, whether prior or concurrent.
        """,
        Category.BUILD,
        SLSALevels.LEVEL3,
    ],
    ReqName.PARAMETERLESS: [
        """
        The build output cannot be affected by user parameters other than the build entry point
        and the top-level source location. In other words, the build is fully defined through the build script
        and nothing else.
        """,
        Category.BUILD,
        SLSALevels.LEVEL4,
    ],
    ReqName.HERMETIC: [
        """
        All transitive build steps, sources, and dependencies were fully declared up front with immutable references,
        and the build steps ran with no network access.
        """,
        Category.BUILD,
        SLSALevels.LEVEL4,
    ],
    ReqName.REPRODUCIBLE: [
        """
        Re-running the build steps with identical input artifacts results in bit-for-bit identical output.
        Builds that cannot meet this MUST provide a justification why the build cannot be made reproducible.
        """,
        Category.BUILD,
        SLSALevels.LEVEL4,
    ],
    ReqName.PROV_AVAILABLE: [
        """
        The provenance is available to the consumer in a format that the consumer accepts.
        The format SHOULD be in-toto SLSA Provenance, but another format MAY be used if both
        producer and consumer agree and it meets all the other requirements.
        """,
        Category.PROVENANCE,
        SLSALevels.LEVEL1,
    ],
    ReqName.PROV_AUTH: [
        """
        The provenance's authenticity and integrity can be verified by the consumer. This SHOULD be through
        a digital signature from a private key accessible only to the service generating the provenance.
        """,
        Category.PROVENANCE,
        SLSALevels.LEVEL2,
    ],
    ReqName.PROV_SERVICE_GEN: [
        """
        The data in the provenance MUST be obtained from the build service (either because
        the generator is the build service or because the provenance generator reads
        the data directly from the build service).
        Regular users of the service MUST NOT be able to inject or alter the contents.
        """,
        Category.PROVENANCE,
        SLSALevels.LEVEL2,
    ],
    ReqName.PROV_NON_FALSIFIABLE: [
        """
        Provenance cannot be falsified by the build service's users.
        """,
        Category.PROVENANCE,
        SLSALevels.LEVEL3,
    ],
    ReqName.PROV_DEPENDENCIES_COMPLETE: [
        """
        Provenance records all build dependencies that were available while running the build steps.
        """,
        Category.PROVENANCE,
        SLSALevels.LEVEL4,
    ],
    ReqName.PROV_CONT_ARTI: [
        """
        The provenance MUST identify the output artifact via at least one cryptographic hash.
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL1,
    ],
    ReqName.PROV_CONT_BUILDER: [
        """
        The provenance identifies the entity that performed the build and generated the provenance.
        This represents the entity that the consumer must trust.
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL1,
    ],
    ReqName.PROV_CONT_BUILD_INS: [
        """
        The provenance identifies the top-level instructions used to execute the build.
        The identified instructions SHOULD be at the highest level available to the build.
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL1,
    ],
    ReqName.PROV_CONT_SOURCE: [
        """
        The provenance identifies the repository origin(s) for the source code used in the build.
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL2,
    ],
    ReqName.PROV_CONT_ENTRY: [
        """
        The provenance identifies the “entry point” of the build definition (see build-as-code)
        used to drive the build including what source repo the configuration was read from.
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL3,
    ],
    ReqName.PROV_CONT_BUILD_PARAMS: [
        """
        The provenance includes all build parameters under a user's control.
        See Parameterless for details. (At L3, the parameters must be listed; at L4, they must be empty.)
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL3,
    ],
    ReqName.PROV_CONT_TRANSITIVE_DEPS: [
        """
        The provenance includes all transitive dependencies listed in Provenance: Dependencies Complete requirement.
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL4,
    ],
    ReqName.PROV_CONT_REPRODUCIBLE_INFO: [
        """
        The provenance includes a boolean indicating whether build is intended to be reproducible and, if so,
        all information necessary to reproduce the build. See Reproducible for more details.
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL4,
    ],
    ReqName.PROV_CONT_META_DATA: [
        """
        The provenance includes metadata to aid debugging and investigations.
        This SHOULD at least include start and end timestamps and a permalink to debug logs.
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL1,
    ],
    ReqName.SECURITY: [
        """
        The system meets some baseline security standard to prevent compromise.
        (Patching, vulnerability scanning, user isolation, transport security, secure boot, machine identity, etc.)
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL4,
    ],
    ReqName.ACCESS: [
        """
        All physical and remote access must be rare, logged, and gated behind multi-party approval.
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL4,
    ],
    ReqName.SUPERUSERS: [
        """
        Only a small number of platform admins may override the guarantees listed here.
        Doing so MUST require approval of a second platform admin.
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL4,
    ],
    ReqName.EXPECTATION: [
        """
        Check whether the SLSA provenance for the produced artifact conforms to the expectation.
        """,
        Category.PROVENANCE_CONTENT,
        SLSALevels.LEVEL3,
    ],
}


class SLSAReq:
    """This class represents a SLSA requirement (e.g Version Controlled)."""

    def __init__(self, name: str, desc: str, category: Category, req_level: SLSALevels):
        """Initialize instance.

        Parameters
        ----------
        name : str
            The name of the SLSA requirement.
        desc : str
            The description of the SLSA requirement.
        category : Category
            The category of the SLSA requirement.
        req_level : SLSALevels
            The SLSA level that this requirement belongs to.
        """
        self.name = name
        self.desc = desc
        self.category = category
        self.is_addressed = False
        self.is_pass = False
        self.feedback = ""
        self.min_level_required = req_level

    def get_status(self) -> tuple:
        """Return the current feedback of a requirement.

        Returns
        -------
        is_addressed : bool
            Whether this SLSA req has been addressed from the analysis.
        is_pass : bool
            True if the repository pass this requirement else False.
        feedback : bool
            The feedback from the analyzer for this requirement.
        """
        if self.is_addressed:
            logger.debug("Return the status for requirement %s", self.name)
        else:
            logger.debug("Trying to return a feedback of unaddressed requirement %s", self.name)

        return self.is_addressed, self.is_pass, self.feedback

    def set_status(self, status: bool, fb_content: str) -> None:
        """Update the feedback accordingly of this requirement.

        Parameters
        ----------
        status : bool
            The status of the requirement to update.
        fb_content : str
            The content of the feedback.
        """
        self.is_pass = status
        self.feedback = fb_content
        self.is_addressed = True

    def __str__(self) -> str:  # pragma: no cover
        """Return the status of a requirement in printable format."""
        return f"{self.name} - {self.min_level_required.value}"

    def get_dict(self) -> dict:
        """Get a dictionary representation for this SLSAReq instance.

        Returns
        -------
        dict
        """
        return {
            "Name": str(self.name),
            "Description": " ".join((str(self.desc).replace("\n", "").strip()).split()),
            "Category": str(self.category.value),
            "Required from level": str(self.min_level_required.value),
            "Is passing": str(self.is_pass),
            "Justification": self.feedback,
        }


def get_requirements_dict() -> dict:
    """Get a dictionary that stores the name of each requirement and its details."""
    result = {}
    for req_name, req_details in BUILD_REQ_DESC.items():
        desc = req_details[0]
        category = req_details[1]
        min_level = req_details[2]
        result[req_name] = SLSAReq(req_name.value, desc, category, min_level)  # type: ignore [arg-type]

    return result
