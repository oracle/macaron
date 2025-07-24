# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines the abstract AIClient class for implementing AI clients."""

import logging
from abc import ABC, abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

logger: logging.Logger = logging.getLogger(__name__)


class AIClient(ABC):
    """This abstract class is used to implement ai clients."""

    def __init__(self, system_prompt: str, defaults: dict) -> None:
        """
        Initialize the AI client.

        The LLM configuration is read from defaults.
        """
        self.system_prompt = system_prompt
        self.defaults = defaults

    @abstractmethod
    def invoke(
        self,
        user_prompt: str,
        temperature: float = 0.2,
        structured_output: type[T] | None = None,
    ) -> Any:
        """
        Invoke the LLM and optionally validate its response.

        Parameters
        ----------
        user_prompt: str
            The user prompt to send to the LLM.
        temperature: float
            The temperature for the LLM response.
        structured_output: Optional[Type[T]]
            The Pydantic model to validate the response against. If provided, the response will be parsed and validated.

        Returns
        -------
        Optional[T | str]
            The validated Pydantic model instance if `structured_output` is provided,
            or the raw string response if not.
        """
