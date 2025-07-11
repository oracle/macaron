# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides a client for interacting with a Large Language Model (LLM)."""

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError, HeuristicAnalyzerValueError
from macaron.util import send_post_http_raw

logger: logging.Logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AIClient:
    """A client for interacting with a Large Language Model."""

    def __init__(self, system_prompt: str):
        """
        Initialize the AI client.

        The LLM configuration (enabled, API key, endpoint, model) is read from defaults.
        """
        self.enabled, self.api_endpoint, self.api_key, self.model, self.context_window = self._load_defaults()
        self.system_prompt = system_prompt.strip() or "You are a helpful AI assistant."
        logger.info("AI client is %s.", "enabled" if self.enabled else "disabled")

    def _load_defaults(self) -> tuple[bool, str, str, str, int]:
        """Load the LLM configuration from the defaults."""
        section_name = "llm"
        enabled, api_key, api_endpoint, model, context_window = False, "", "", "", 10000

        if defaults.has_section(section_name):
            section = defaults[section_name]
            enabled = section.get("enabled", "False").strip().lower() == "true"
            api_key = section.get("api_key", "").strip()
            api_endpoint = section.get("api_endpoint", "").strip()
            model = section.get("model", "").strip()
            context_window = section.getint("context_window", 10000)

        if enabled:
            if not api_key:
                raise ConfigurationError("API key for the AI client is not configured.")
            if not api_endpoint:
                raise ConfigurationError("API endpoint for the AI client is not configured.")
            if not model:
                raise ConfigurationError("Model for the AI client is not configured.")

        return enabled, api_endpoint, api_key, model, context_window

    def _validate_response(self, response_text: str, response_model: type[T]) -> T:
        """
        Validate and parse the response from the LLM.

        If raw JSON parsing fails, attempts to extract a JSON object from text.

        Parameters
        ----------
        response_text: str
            The response text from the LLM.
        response_model: Type[T]
            The Pydantic model to validate the response against.

        Returns
        -------
        bool
            The validated Pydantic model instance.

        Raises
        ------
        HeuristicAnalyzerValueError
            If there is an error in parsing or validating the response.
        """
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            logger.debug("Full JSON parse failed; trying to extract JSON from text.")
            # If the response is not a valid JSON, try to extract a JSON object from the text.
            match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if not match:
                raise HeuristicAnalyzerValueError("No JSON object found in the LLM response.") from match
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError as e:
                logger.error("Failed to parse extracted JSON: %s", e)
                raise HeuristicAnalyzerValueError("Invalid JSON extracted from response.") from e

        try:
            return response_model.model_validate(data)
        except ValidationError as e:
            logger.error("Validation failed against response model: %s", e)
            raise HeuristicAnalyzerValueError("Response JSON validation failed.") from e

    def invoke(
        self,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4000,
        structured_output: type[T] | None = None,
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
        max_tokens: int
            The maximum number of tokens for the LLM response.
        structured_output: Optional[Type[T]]
            The Pydantic model to validate the response against. If provided, the response will be parsed and validated.
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
        if not self.enabled:
            raise ConfigurationError("AI client is not enabled. Please check your configuration.")

        if len(user_prompt.split()) > self.context_window:
            logger.warning(
                "User prompt exceeds context window (%s words). "
                "Truncating the prompt to fit within the context window.",
                self.context_window,
            )
            user_prompt = " ".join(user_prompt.split()[: self.context_window])

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user_prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            response = send_post_http_raw(url=self.api_endpoint, json_data=payload, headers=headers, timeout=timeout)
            if not response:
                raise HeuristicAnalyzerValueError("No response received from the LLM.")
            response_json = response.json()
            usage = response_json.get("usage", {})

            if usage:
                usage_str = ", ".join(f"{key} = {value}" for key, value in usage.items())
                logger.info("LLM call token usage: %s", usage_str)

            message_content = response_json["choices"][0]["message"]["content"]

            if not structured_output:
                logger.debug("Returning raw message content (no structured output requested).")
                return message_content
            return self._validate_response(message_content, structured_output)

        except Exception as e:
            logger.error("Error during LLM invocation: %s", e)
            raise HeuristicAnalyzerValueError(f"Failed to get or validate LLM response: {e}") from e
