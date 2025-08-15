# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module defines the AIClientFactory class for creating AI clients based on provider configuration."""

import logging

from macaron.ai.clients import PROVIDER_MAPPING
from macaron.ai.clients.base import AIClient
from macaron.config.defaults import defaults
from macaron.errors import ConfigurationError

logger: logging.Logger = logging.getLogger(__name__)


class AIClientFactory:
    """Factory to create AI clients based on provider configuration."""

    def __init__(self) -> None:
        """
        Initialize the AI client.

        The LLM configuration is read from defaults.
        """
        self.params = self._load_defaults()

    def _load_defaults(self) -> dict | None:
        section_name = "llm"
        default_values = {
            "enabled": False,
            "provider": "",
            "api_key": "",
            "api_endpoint": "",
            "model": "",
        }

        if defaults.has_section(section_name):
            section = defaults[section_name]
            default_values["enabled"] = section.getboolean("enabled", default_values["enabled"])
            for key, default_value in default_values.items():
                if isinstance(default_value, str):
                    default_values[key] = str(section.get(key, default_value)).strip().lower()

        if default_values["enabled"]:
            for key, value in default_values.items():
                if not value:
                    raise ConfigurationError(
                        f"AI client configuration '{key}' is required but not set in the defaults."
                    )

        return default_values

    def create_client(self, system_prompt: str) -> AIClient | None:
        """Create an AI client based on the configured provider."""
        if not self.params or not self.params["enabled"]:
            return None

        client_class = PROVIDER_MAPPING.get(self.params["provider"])
        if client_class is None:
            logger.error("Provider '%s' is not supported.", self.params["provider"])
            return None
        return client_class(system_prompt, self.params)
