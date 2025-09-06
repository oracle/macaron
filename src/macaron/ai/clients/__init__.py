# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides a mapping of AI client providers to their respective client classes."""

from macaron.ai.clients.base import AIClient
from macaron.ai.clients.openai_client import OpenAiClient

PROVIDER_MAPPING: dict[str, type[AIClient]] = {"openai": OpenAiClient}
