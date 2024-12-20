# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module processes the JSON dependency output files generated by CycloneDX Maven plugin.

It also collects the direct dependencies that should be processed by Macaron.
See https://github.com/CycloneDX/cyclonedx-maven-plugin.
"""

import logging
import os
from pathlib import Path

from cyclonedx.model.component import Component as CDXComponent
from packageurl import PackageURL

from macaron.config.global_config import global_config
from macaron.database.table_definitions import Component
from macaron.dependency_analyzer.cyclonedx import DependencyAnalyzer, DependencyInfo

logger: logging.Logger = logging.getLogger(__name__)


class CycloneDxPython(DependencyAnalyzer):
    """This class implements the CycloneDX Maven plugin analyzer."""

    def get_cmd(self) -> list:
        """Return the CLI command to run the CycloneDX Maven plugin.

        Returns
        -------
        list
            The command line arguments.
        """
        logger.info(
            (
                "The SBOM generator has started resolving the dependencies and storing them in the %s file. "
                "This might take a while..."
            ),
            self.file_name,
        )
        return [
            "cyclonedx-py",
            "environment",
            global_config.python_venv_path,
            "--output-format",
            "json",
            "--outfile",
            os.path.join(global_config.output_path, self.file_name),
        ]

    def collect_dependencies(
        self,
        dir_path: str,
        target_component: Component,
        recursive: bool = False,
    ) -> dict[str, DependencyInfo]:
        """Process the dependency JSON files and collect dependencies.

        Parameters
        ----------
        dir_path : str
            Local path to the target repo.
        target_component: Component
            The analyzed target software component.
        recursive: bool
            Whether to get all transitive dependencies, otherwise only the direct dependencies will be returned (default: False).

        Returns
        -------
        dict
            A dictionary where artifacts are grouped based on "artifactId:groupId".
        """
        return self.convert_components_to_artifacts(
            self.get_dep_components(
                target_component=target_component,
                root_bom_path=Path(global_config.output_path, self.file_name),
                recursive=recursive,
            )
        )

    def remove_sboms(self, dir_path: str) -> bool:
        """Remove all the SBOM files in the provided directory recursively.

        Parameters
        ----------
        dir_path : str
            Path to the repo.

        Returns
        -------
        bool
            Returns True if all the files are removed successfully.
        """
        return True

    def get_purl_from_cdx_component(self, component: CDXComponent) -> PackageURL:
        """Construct and return a PackageURL from a CycloneDX component.

        Parameters
        ----------
        component: CDXComponent

        Returns
        -------
        PackageURL
            The PackageURL object constructed from the CycloneDX component.
        """
        return component.purl or PackageURL(
            type="pypi",
            name=component.name,
            version=component.version or None,
        )
