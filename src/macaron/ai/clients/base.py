# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines the abstract AIClient class for implementing AI clients."""

from abc import ABC, abstractmethod


class AIClient(ABC):
    """This abstract class is used to implement ai clients."""

    def __init__(self, system_prompt: str, params: dict) -> None:
        """
        Initialize the AI client.

        The LLM configuration is read from defaults.
        """
        self.system_prompt = system_prompt
        self.params = params

    @abstractmethod
    def invoke(
        self,
        user_prompt: str,
        temperature: float = 0.2,
        response_format: dict | None = None,
    ) -> dict:
        """
        Invoke the LLM and optionally validate its response.

        Parameters
        ----------
        user_prompt: str
            The user prompt to send to the LLM.
        temperature: float
            The temperature for the LLM response.
        response_format: dict | None
            The json schema to validate the response against.

        Returns
        -------
        dict
            The validated schema if `response_format` is provided,
            or the raw string response if not.
        """
