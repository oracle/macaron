# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module tests the provenance finder."""
from packageurl import PackageURL

from macaron.repo_finder.provenance_finder import ProvenanceFinder


def test_callable_interface() -> None:
    """Test the callable parameter behaviour of the provenance finder using mock values."""
    provenance_finder = ProvenanceFinder()
    purl = PackageURL.from_string("pkg:npm/test@1.0.0")
    provenance = provenance_finder.find_provenance(purl, [lambda x, y, z: [x + y + z]], [[1, 2, 3]])
    assert provenance
    validated = provenance_finder.verify_provenance(purl, [], lambda a, b: False)
    assert not validated
