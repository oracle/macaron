# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module contains the parser for POM files."""
import logging
from xml.etree.ElementTree import Element  # nosec B405

import defusedxml.ElementTree
from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

logger: logging.Logger = logging.getLogger(__name__)


def parse_pom_string(pom_string: str) -> Element | None:
    """
    Parse the passed POM string using defusedxml.

    Parameters
    ----------
    pom_string : str
        The contents of a POM file as a string.

    Returns
    -------
    Element | None
        The parsed element representing the POM's XML hierarchy.
    """
    try:
        # Stored here first to help with type checking.
        pom: Element = fromstring(pom_string)
        return pom
    except (DefusedXmlException, defusedxml.ElementTree.ParseError) as error:
        logger.debug("Failed to parse XML: %s", error)
        return None
