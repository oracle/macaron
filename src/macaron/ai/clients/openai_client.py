# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides a client for interacting with a Large Language Model (LLM) that is Openai like."""

import logging
from typing import Any, TypeVar

from pydantic import BaseModel

from macaron.ai.ai_tools import extract_json
from macaron.ai.clients.base import AIClient
from macaron.errors import ConfigurationError, HeuristicAnalyzerValueError
from macaron.util import send_post_http_raw

logger: logging.Logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OpenAiClient(AIClient):
    """A client for interacting with a Large Language Model that is OpenAI API like."""

    def invoke(
        self,
        user_prompt: str,
        temperature: float = 0.2,
        response_format: dict | None = None,
        max_tokens: int = 4000,
        seed: int = 42,
        timeout: int = 30,
    ) -> Any:
        """
        Invoke the LLM and optionally validate its response.

        Parameters
        ----------
        user_prompt: str
            The user prompt to send to the LLM.
        temperature: float
            The temperature for the LLM response.
        response_format: dict
            The json schema to validate the response against. If provided, the response will be parsed and validated.
        max_tokens: int
            The maximum number of tokens for the LLM response.
        timeout: int
            The timeout for the HTTP request in seconds.

        Returns
        -------
        Optional[T | str]
            The validated Pydantic model instance if `structured_output` is provided,
            or the raw string response if not.

        Raises
        ------
        HeuristicAnalyzerValueError
            If there is an error in parsing or validating the response.
        """
        if not self.params["enabled"]:
            raise ConfigurationError("AI client is not enabled. Please check your configuration.")

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.params['api_key']}"}
        payload = {
            "model": self.params["model"],
            "messages": [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user_prompt}],
            "response_format": response_format,
            "temperature": temperature,
            "seed": seed,
            "max_tokens": max_tokens,
        }

        try:
            response = send_post_http_raw(
                url=self.params["api_endpoint"], json_data=payload, headers=headers, timeout=timeout
            )
            if not response:
                raise HeuristicAnalyzerValueError("No response received from the LLM.")
            response_json = response.json()
            usage = response_json.get("usage", {})

            if usage:
                usage_str = ", ".join(f"{key} = {value}" for key, value in usage.items())
                logger.info("LLM call token usage: %s", usage_str)

            message_content = response_json["choices"][0]["message"]["content"]
            return extract_json(message_content)

        except Exception as e:
            logger.error("Error during LLM invocation: %s", e)
            raise HeuristicAnalyzerValueError(f"Failed to get or validate LLM response: {e}") from e
