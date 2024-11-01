# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the JSON template for repo finder/commit finder standalone reports."""
import json


def create_report(purl: str, commit: str, repo: str) -> str:
    """Use schema to generate report for standalone uses of the repo / commit finder.

    Parameters
    ----------
    purl: str
        The PackageURL of the target artifact, as a string.
    commit: str
        The commit hash to report.
    repo: str
        The repository to report.

    Returns
    -------
    str
        The schema
    """
    data = {"purl": purl, "commit": commit, "repo": repo, "repo_validated": False, "commit_validated": False, "url": ""}
    if "github.com" in repo:
        data["url"] = f"{repo}/commit/{commit}"
    return json.dumps(data, indent=4)
