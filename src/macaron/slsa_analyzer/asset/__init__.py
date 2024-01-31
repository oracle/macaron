# Copyright (c) 2023 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines classes and interfaces related to assets.

Assets are files published from some build.
"""

from typing import NamedTuple, Protocol


class AssetLocator(Protocol):
    """Interface of an asset locator."""

    @property
    def name(self) -> str:
        """Get the name (file name) of the asset."""

    @property
    def url(self) -> str:
        """Get the url to the asset."""

    @property
    def size_in_bytes(self) -> int:
        """Get the size of the asset in bytes."""

    def download(self, dest: str) -> bool:
        """Download the asset.

        Parameters
        ----------
        dest : str
            The local destination where the asset is downloaded to.
            Note that this must include the file name.

        Returns
        -------
        bool
            ``True`` if the asset is downloaded successfully; ``False`` if not.
        """


class VirtualReleaseAsset(NamedTuple):
    """A dummy asset used when an asset doesn't actually exist."""

    #: The asset name.
    name: str
    #: The URL to the asset.
    url: str
    #: The size of the asset, in bytes.
    size_in_bytes: int

    def download(self, dest: str) -> bool:  # pylint: disable=unused-argument
        """Download the asset.

        Parameters
        ----------
        dest : str
            The local destination where the asset is downloaded to.
            Note that this must include the file name.

        Returns
        -------
        bool
            ``True`` if the asset is downloaded successfully; ``False`` if not.
        """
        return False
