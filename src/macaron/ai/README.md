# Macaron AI Module

This module provides the foundation for interacting with Large Language Models (LLMs) in a provider-agnostic way. It includes an abstract client definition, provider-specific client implementations, a client factory, and utility functions for processing responses.

## Module Components

- **ai_client.py**
  Defines the abstract [`AIClient`](./ai_client.py) class. This class handles the initialization of LLM configuration from the defaults and serves as the base for all specific AI client implementations.

- **openai_client.py**
  Implements the [`OpenAiClient`](./openai_client.py) class, a concrete subclass of [`AIClient`](./ai_client.py). This client interacts with OpenAI-like APIs by sending requests using HTTP and processing the responses. It also validates and structures responses using the tools provided.

- **ai_factory.py**
  Contains the [`AIClientFactory`](./ai_factory.py) class, which is responsible for reading provider configuration from the defaults and creating the correct AI client instance.

- **ai_tools.py**
  Offers utility functions such as `structure_response` to assist with parsing and validating the JSON response returned by an LLM. These functions ensure that responses conform to a given Pydantic model for easier downstream processing.

## Usage

1. **Configuration:**
   The module reads the LLM configuration from the application defaults (using the `defaults` module). Make sure that the `llm` section in your configuration includes valid settings such as `enabled`, `api_key`, `api_endpoint`, `model`, and `context_window`.

2. **Creating a Client:**
   Use the [`AIClientFactory`](./ai_factory.py) to create an AI client instance. The factory checks the configured provider and returns a client (e.g., an instance of [`OpenAiClient`](./openai_client.py)) that can be used to invoke the LLM.

   Example:
   ```py
   from macaron.ai.ai_factory import AIClientFactory

   factory = AIClientFactory()
   client = factory.create_client(system_prompt="You are a helpful assistant.")
   response = client.invoke("Hello, how can you assist me?")
   print(response)
   ```

3. **Response Processing:**
   When a structured response is required, pass a Pydantic model class to the `invoke` method. The [`ai_tools.py`](./ai_tools.py) module takes care of parsing and validating the response to ensure it meets the expected structure.

## Logging and Error Handling

- The module uses Python's logging framework to report important events, such as token usage and warnings when prompts exceed the allowed context window.
- Configuration errors (e.g., missing API key or endpoint) are handled by raising descriptive exceptions, such as those defined in the [`ConfigurationError`](../errors.py).

## Extensibility

The design of the AI module is provider-agnostic. To add support for additional LLM providers:
- Implement a new client by subclassing [`AIClient`](./ai_client.py).
- Add the new client to the [`PROVIDER_MAPPING`](./ai_factory.py).
- Update the configuration defaults accordingly.
