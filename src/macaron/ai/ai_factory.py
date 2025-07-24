# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines the AIClientFactory class for creating AI clients based on provider configuration."""

import logging

from macaron.ai.ai_client import AIClient
from macaron.ai.openai_client import OpenAiClient
from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError

logger: logging.Logger = logging.getLogger(__name__)


class AIClientFactory:
    """Factory to create AI clients based on provider configuration."""

    PROVIDER_MAPPING: dict[str, type[AIClient]] = {"openai": OpenAiClient}

    def __init__(self) -> None:
        """
        Initialize the AI client.

        The LLM configuration is read from defaults.
        """
        self.defaults = self._load_defaults()

    def _load_defaults(self) -> dict:
        section_name = "llm"
        default_values = {
            "enabled": False,
            "provider": "",
            "api_key": "",
            "api_endpoint": "",
            "model": "",
            "context_window": 10000,
        }

        if defaults.has_section(section_name):
            section = defaults[section_name]
            default_values["enabled"] = section.getboolean("enabled", default_values["enabled"])
            default_values["api_key"] = str(section.get("api_key", default_values["api_key"])).strip().lower()
            default_values["api_endpoint"] = (
                str(section.get("api_endpoint", default_values["api_endpoint"])).strip().lower()
            )
            default_values["model"] = str(section.get("model", default_values["model"])).strip().lower()
            default_values["provider"] = str(section.get("provider", default_values["provider"])).strip().lower()
            default_values["context_window"] = section.getint("context_window", 10000)

        if default_values["enabled"]:
            for key, value in default_values.items():
                if not value:
                    raise ConfigurationError(
                        f"AI client configuration '{key}' is required but not set in the defaults."
                    )

        return default_values

    def create_client(self, system_prompt: str) -> AIClient | None:
        """Create an AI client based on the configured provider."""
        client_class = self.PROVIDER_MAPPING.get(self.defaults["provider"])
        if client_class is None:
            logger.error("Provider '%s' is not supported.", self.defaults["provider"])
            return None
        return client_class(system_prompt, self.defaults)

    def list_available_providers(self) -> list[str]:
        """List all registered providers."""
        return list(self.PROVIDER_MAPPING.keys())
