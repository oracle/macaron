# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides utility functions for Large Language Model (LLM)."""
import json
import logging
import re
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)


def extract_json(response_text: str) -> Any:
    """
    Parse the response from the LLM.

    If raw JSON parsing fails, attempts to extract a JSON object from text.

    Parameters
    ----------
    response_text: str
        The response text from the LLM.

    Returns
    -------
    dict[str, Any] | None
        The structured JSON object.
    """
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        logger.debug("Full JSON parse failed; trying to extract JSON from text.")
        # If the response is not a valid JSON, try to extract a JSON object from the text.
        match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            logger.debug("Failed to parse extracted JSON: %s", e)
            return None

    return data
