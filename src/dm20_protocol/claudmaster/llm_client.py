"""
LLM Client for Claudmaster multi-agent system.

Provides a unified interface for interacting with Anthropic's Claude API,
with support for multi-model configurations (different models for different agents)
and mock clients for testing.

This module implements the LLMClient protocol defined in agents/narrator.py.
"""

import logging
import os
from typing import Any, AsyncGenerator

logger = logging.getLogger("dm20-protocol")


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class LLMClientError(Exception):
    """Base exception for LLM client errors."""
    pass


class LLMConfigurationError(LLMClientError):
    """Raised when LLM client is misconfigured."""
    pass


class LLMAPIError(LLMClientError):
    """Raised when the LLM API returns an error."""
    pass


class LLMRateLimitError(LLMClientError):
    """Raised when rate limit is exceeded."""
    pass


class LLMDependencyError(LLMClientError):
    """Raised when required dependencies are missing."""
    pass


# ---------------------------------------------------------------------------
# Mock LLM Client (for testing)
# ---------------------------------------------------------------------------


class MockLLMClient:
    """Mock LLM client for testing purposes.

    Implements the same protocol as AnthropicLLMClient but returns
    configurable canned responses instead of making real API calls.

    Args:
        responses: List of responses to return in order. If empty, returns a default response.
            When exhausted, cycles back to the first response.
        default_response: Default response when responses list is empty.

    Example:
        >>> mock = MockLLMClient(responses=["First response", "Second response"])
        >>> await mock.generate("prompt")
        'First response'
        >>> await mock.generate("prompt")
        'Second response'
    """

    def __init__(
        self,
        responses: list[str] | None = None,
        default_response: str = "Mock LLM response.",
    ) -> None:
        self.responses = responses or []
        self.default_response = default_response
        self.call_count = 0
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        """Generate a mock response.

        Args:
            prompt: The prompt (recorded but not used).
            max_tokens: Maximum tokens (recorded but not used).

        Returns:
            The next canned response or default response.
        """
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        self.call_count += 1

        if not self.responses:
            return self.default_response

        # Cycle through responses
        response_index = (self.call_count - 1) % len(self.responses)
        return self.responses[response_index]

    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """Generate a mock streaming response.

        Args:
            prompt: The prompt (recorded but not used).
            max_tokens: Maximum tokens (recorded but not used).

        Yields:
            Chunks of the response.
        """
        response = await self.generate(prompt, max_tokens)
        # Split response into word-level chunks
        words = response.split()
        for word in words:
            yield word + " "

    def reset(self) -> None:
        """Reset call history."""
        self.call_count = 0
        self.calls.clear()


# ---------------------------------------------------------------------------
# Anthropic LLM Client
# ---------------------------------------------------------------------------


class AnthropicLLMClient:
    """Real Anthropic API client implementing the LLMClient protocol.

    Uses the Anthropic Python SDK to make API calls to Claude models.
    The anthropic package is imported lazily to make it an optional dependency.

    Args:
        api_key: Anthropic API key. If None, reads from ANTHROPIC_API_KEY env var.
        model: Model identifier (e.g., "claude-sonnet-4-5-20250929").
        temperature: Temperature parameter for generation (0.0-2.0).
        default_max_tokens: Default max tokens if not specified in generate().

    Raises:
        LLMDependencyError: If anthropic package is not installed.
        LLMConfigurationError: If API key is missing.

    Example:
        >>> client = AnthropicLLMClient(
        ...     api_key="sk-ant-...",
        ...     model="claude-sonnet-4-5-20250929",
        ...     temperature=0.7
        ... )
        >>> response = await client.generate("Hello, Claude!", max_tokens=100)
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-5-20250929",
        temperature: float = 0.7,
        default_max_tokens: int = 1024,
    ) -> None:
        # Lazy import anthropic to make it optional
        try:
            from anthropic import AsyncAnthropic
            self._anthropic_module = __import__("anthropic")
        except ImportError as e:
            raise LLMDependencyError(
                "The 'anthropic' package is required to use AnthropicLLMClient. "
                "Install it with: pip install anthropic"
            ) from e

        # Get API key
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise LLMConfigurationError(
                "Anthropic API key is required. Provide it via the 'api_key' parameter "
                "or set the ANTHROPIC_API_KEY environment variable."
            )

        self.model = model
        self.temperature = temperature
        self.default_max_tokens = default_max_tokens

        # Create async client
        self.client = AsyncAnthropic(api_key=self.api_key)

        logger.info(
            f"Initialized AnthropicLLMClient with model={model}, "
            f"temperature={temperature}, default_max_tokens={default_max_tokens}"
        )

    async def generate(self, prompt: str, max_tokens: int | None = None) -> str:
        """Generate text from a prompt using the Anthropic API.

        Args:
            prompt: The prompt to send to the model.
            max_tokens: Maximum tokens in the response. If None, uses default_max_tokens.

        Returns:
            The generated text.

        Raises:
            LLMAPIError: If the API returns an error.
            LLMRateLimitError: If rate limit is exceeded.
        """
        if max_tokens is None:
            max_tokens = self.default_max_tokens

        try:
            # Make API call
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=self.temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            # Extract text from response
            # The response content is a list of content blocks
            text_blocks = [
                block.text
                for block in message.content
                if hasattr(block, "text")
            ]
            response_text = "".join(text_blocks)

            logger.debug(
                f"Generated {len(response_text)} chars with model {self.model} "
                f"(tokens: {message.usage.input_tokens} in, {message.usage.output_tokens} out)"
            )

            return response_text

        except self._anthropic_module.RateLimitError as e:
            logger.error(f"Rate limit exceeded: {e}")
            raise LLMRateLimitError(f"Rate limit exceeded: {e}") from e

        except self._anthropic_module.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise LLMAPIError(f"API error: {e}") from e

        except Exception as e:
            logger.error(f"Unexpected error in generate(): {e}")
            raise LLMAPIError(f"Unexpected error: {e}") from e

    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Generate text as a stream of chunks using the Anthropic API.

        Useful for streaming responses to users in real-time.

        Args:
            prompt: The prompt to send to the model.
            max_tokens: Maximum tokens in the response. If None, uses default_max_tokens.

        Yields:
            Text chunks as they are generated.

        Raises:
            LLMAPIError: If the API returns an error.
            LLMRateLimitError: If rate limit is exceeded.
        """
        if max_tokens is None:
            max_tokens = self.default_max_tokens

        try:
            # Make streaming API call
            async with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                temperature=self.temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            ) as stream:
                async for text in stream.text_stream:
                    yield text

            # Log final message stats
            final_message = await stream.get_final_message()
            logger.debug(
                f"Streamed generation complete with model {self.model} "
                f"(tokens: {final_message.usage.input_tokens} in, "
                f"{final_message.usage.output_tokens} out)"
            )

        except self._anthropic_module.RateLimitError as e:
            logger.error(f"Rate limit exceeded: {e}")
            raise LLMRateLimitError(f"Rate limit exceeded: {e}") from e

        except self._anthropic_module.APIError as e:
            logger.error(f"Anthropic API error: {e}")
            raise LLMAPIError(f"API error: {e}") from e

        except Exception as e:
            logger.error(f"Unexpected error in generate_stream(): {e}")
            raise LLMAPIError(f"Unexpected error: {e}") from e


# ---------------------------------------------------------------------------
# Multi-Model Client
# ---------------------------------------------------------------------------


class MultiModelClient:
    """Manages multiple LLM clients for different agent roles.

    In a dual-agent architecture, different agents may use different models:
    - Narrator: Fast, creative model (e.g., Haiku)
    - Arbiter: Thorough, analytical model (e.g., Sonnet)

    Args:
        clients: Mapping of role name to LLM client instance.

    Example:
        >>> narrator_client = AnthropicLLMClient(model="claude-haiku-4-5-20251001")
        >>> arbiter_client = AnthropicLLMClient(model="claude-sonnet-4-5-20250929")
        >>> multi_client = MultiModelClient({
        ...     "narrator": narrator_client,
        ...     "arbiter": arbiter_client,
        ... })
        >>> client = multi_client.get_client("narrator")
    """

    def __init__(self, clients: dict[str, Any]) -> None:
        self.clients = clients
        logger.info(f"Initialized MultiModelClient with {len(clients)} clients: {list(clients.keys())}")

    def get_client(self, role: str) -> Any:
        """Get the LLM client for a specific role.

        Args:
            role: The agent role name (e.g., "narrator", "arbiter").

        Returns:
            The LLM client for that role.

        Raises:
            LLMConfigurationError: If the role is not configured.
        """
        if role not in self.clients:
            raise LLMConfigurationError(
                f"No LLM client configured for role '{role}'. "
                f"Available roles: {list(self.clients.keys())}"
            )
        return self.clients[role]

    def has_role(self, role: str) -> bool:
        """Check if a client exists for the given role.

        Args:
            role: The agent role name.

        Returns:
            True if a client is configured for this role.
        """
        return role in self.clients

    def list_roles(self) -> list[str]:
        """List all configured roles.

        Returns:
            List of role names with configured clients.
        """
        return list(self.clients.keys())


__all__ = [
    "LLMClientError",
    "LLMConfigurationError",
    "LLMAPIError",
    "LLMRateLimitError",
    "LLMDependencyError",
    "MockLLMClient",
    "AnthropicLLMClient",
    "MultiModelClient",
]
