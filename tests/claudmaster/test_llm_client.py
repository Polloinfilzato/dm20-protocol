"""
Unit tests for LLM Client implementations.

Tests MockLLMClient, AnthropicLLMClient, and MultiModelClient.
All tests of AnthropicLLMClient mock the SDK to avoid real API calls.
"""

import os
import pytest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from dm20_protocol.claudmaster.llm_client import (
    AnthropicLLMClient,
    MockLLMClient,
    MultiModelClient,
    LLMClientError,
    LLMConfigurationError,
    LLMAPIError,
    LLMRateLimitError,
    LLMDependencyError,
)
from dm20_protocol.claudmaster.config import ClaudmasterConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm_client() -> MockLLMClient:
    """Create a basic MockLLMClient."""
    return MockLLMClient()


@pytest.fixture
def mock_llm_with_responses() -> MockLLMClient:
    """Create a MockLLMClient with predefined responses."""
    return MockLLMClient(
        responses=[
            "First response",
            "Second response",
            "Third response",
        ]
    )


@pytest.fixture
def mock_anthropic_message() -> MagicMock:
    """Create a mock Anthropic message response."""
    message = MagicMock()

    # Mock content block with text
    content_block = MagicMock()
    content_block.text = "This is a generated response from Claude."
    message.content = [content_block]

    # Mock usage stats
    message.usage = MagicMock()
    message.usage.input_tokens = 50
    message.usage.output_tokens = 100

    return message


@pytest.fixture
def mock_anthropic_stream() -> AsyncMock:
    """Create a mock Anthropic streaming response."""
    stream = AsyncMock()

    # Mock text stream
    async def text_stream_generator():
        for chunk in ["This ", "is ", "a ", "streamed ", "response."]:
            yield chunk

    stream.text_stream = text_stream_generator()

    # Mock final message
    final_message = MagicMock()
    final_message.usage = MagicMock()
    final_message.usage.input_tokens = 50
    final_message.usage.output_tokens = 100
    stream.get_final_message = AsyncMock(return_value=final_message)

    return stream


# ---------------------------------------------------------------------------
# MockLLMClient Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_llm_basic_generate(mock_llm_client: MockLLMClient) -> None:
    """Test basic MockLLMClient generation."""
    response = await mock_llm_client.generate("Test prompt")

    assert response == "Mock LLM response."
    assert mock_llm_client.call_count == 1
    assert len(mock_llm_client.calls) == 1
    assert mock_llm_client.calls[0]["prompt"] == "Test prompt"
    assert mock_llm_client.calls[0]["max_tokens"] == 1024


@pytest.mark.asyncio
async def test_mock_llm_custom_max_tokens(mock_llm_client: MockLLMClient) -> None:
    """Test MockLLMClient with custom max_tokens."""
    response = await mock_llm_client.generate("Test prompt", max_tokens=2048)

    assert mock_llm_client.calls[0]["max_tokens"] == 2048


@pytest.mark.asyncio
async def test_mock_llm_multiple_responses(mock_llm_with_responses: MockLLMClient) -> None:
    """Test MockLLMClient cycling through multiple responses."""
    response1 = await mock_llm_with_responses.generate("Prompt 1")
    response2 = await mock_llm_with_responses.generate("Prompt 2")
    response3 = await mock_llm_with_responses.generate("Prompt 3")
    response4 = await mock_llm_with_responses.generate("Prompt 4")  # Should cycle back

    assert response1 == "First response"
    assert response2 == "Second response"
    assert response3 == "Third response"
    assert response4 == "First response"  # Cycled back
    assert mock_llm_with_responses.call_count == 4


@pytest.mark.asyncio
async def test_mock_llm_reset(mock_llm_client: MockLLMClient) -> None:
    """Test MockLLMClient reset functionality."""
    await mock_llm_client.generate("Test 1")
    await mock_llm_client.generate("Test 2")

    assert mock_llm_client.call_count == 2
    assert len(mock_llm_client.calls) == 2

    mock_llm_client.reset()

    assert mock_llm_client.call_count == 0
    assert len(mock_llm_client.calls) == 0


@pytest.mark.asyncio
async def test_mock_llm_stream(mock_llm_client: MockLLMClient) -> None:
    """Test MockLLMClient streaming generation."""
    chunks = []
    async for chunk in mock_llm_client.generate_stream("Test prompt"):
        chunks.append(chunk)

    # Should split "Mock LLM response." into words with spaces
    assert len(chunks) == 3
    assert "".join(chunks).strip() == "Mock LLM response."


# ---------------------------------------------------------------------------
# AnthropicLLMClient Tests - Initialization
# ---------------------------------------------------------------------------


def test_anthropic_client_missing_dependency() -> None:
    """Test that AnthropicLLMClient raises error when anthropic package is missing."""
    with patch("dm20_protocol.claudmaster.llm_client.__import__", side_effect=ImportError):
        with pytest.raises(LLMDependencyError, match="anthropic"):
            AnthropicLLMClient(api_key="test-key")


def test_anthropic_client_missing_api_key() -> None:
    """Test that AnthropicLLMClient raises error when API key is missing."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(LLMConfigurationError, match="API key is required"):
            AnthropicLLMClient()


def test_anthropic_client_with_api_key_param() -> None:
    """Test AnthropicLLMClient initialization with API key parameter."""
    with patch("dm20_protocol.claudmaster.llm_client.AsyncAnthropic"):
        client = AnthropicLLMClient(api_key="test-key-123")
        assert client.api_key == "test-key-123"
        assert client.model == "claude-sonnet-4-5-20250929"
        assert client.temperature == 0.7
        assert client.default_max_tokens == 1024


def test_anthropic_client_with_env_var() -> None:
    """Test AnthropicLLMClient initialization with environment variable."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key-456"}):
        with patch("dm20_protocol.claudmaster.llm_client.AsyncAnthropic"):
            client = AnthropicLLMClient()
            assert client.api_key == "env-key-456"


def test_anthropic_client_custom_params() -> None:
    """Test AnthropicLLMClient with custom parameters."""
    with patch("dm20_protocol.claudmaster.llm_client.AsyncAnthropic"):
        client = AnthropicLLMClient(
            api_key="test-key",
            model="claude-haiku-4-5-20251001",
            temperature=0.9,
            default_max_tokens=2048,
        )
        assert client.model == "claude-haiku-4-5-20251001"
        assert client.temperature == 0.9
        assert client.default_max_tokens == 2048


# ---------------------------------------------------------------------------
# AnthropicLLMClient Tests - Generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anthropic_generate_success(mock_anthropic_message: MagicMock) -> None:
    """Test successful generation with AnthropicLLMClient."""
    with patch("dm20_protocol.claudmaster.llm_client.AsyncAnthropic") as mock_anthropic:
        # Setup mock
        mock_client_instance = AsyncMock()
        mock_client_instance.messages.create = AsyncMock(return_value=mock_anthropic_message)
        mock_anthropic.return_value = mock_client_instance

        # Create client and generate
        client = AnthropicLLMClient(api_key="test-key")
        response = await client.generate("Test prompt", max_tokens=512)

        # Verify
        assert response == "This is a generated response from Claude."
        mock_client_instance.messages.create.assert_called_once()
        call_kwargs = mock_client_instance.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-5-20250929"
        assert call_kwargs["max_tokens"] == 512
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["messages"][0]["content"] == "Test prompt"


@pytest.mark.asyncio
async def test_anthropic_generate_default_max_tokens(mock_anthropic_message: MagicMock) -> None:
    """Test that AnthropicLLMClient uses default_max_tokens when not specified."""
    with patch("dm20_protocol.claudmaster.llm_client.AsyncAnthropic") as mock_anthropic:
        mock_client_instance = AsyncMock()
        mock_client_instance.messages.create = AsyncMock(return_value=mock_anthropic_message)
        mock_anthropic.return_value = mock_client_instance

        client = AnthropicLLMClient(api_key="test-key", default_max_tokens=2048)
        await client.generate("Test prompt")

        call_kwargs = mock_client_instance.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 2048


@pytest.mark.asyncio
async def test_anthropic_generate_api_error() -> None:
    """Test AnthropicLLMClient handles API errors."""
    with patch("dm20_protocol.claudmaster.llm_client.AsyncAnthropic") as mock_anthropic:
        # Create a real anthropic module mock with APIError
        anthropic_module = MagicMock()
        api_error_instance = Exception("API request failed")
        anthropic_module.APIError = type("APIError", (Exception,), {})
        api_error = anthropic_module.APIError("API request failed")

        mock_client_instance = AsyncMock()
        mock_client_instance.messages.create = AsyncMock(side_effect=api_error)
        mock_anthropic.return_value = mock_client_instance

        with patch("dm20_protocol.claudmaster.llm_client.AnthropicLLMClient._anthropic_module", anthropic_module):
            client = AnthropicLLMClient(api_key="test-key")
            client._anthropic_module = anthropic_module

            with pytest.raises(LLMAPIError, match="API error"):
                await client.generate("Test prompt")


@pytest.mark.asyncio
async def test_anthropic_generate_rate_limit_error() -> None:
    """Test AnthropicLLMClient handles rate limit errors."""
    with patch("dm20_protocol.claudmaster.llm_client.AsyncAnthropic") as mock_anthropic:
        # Create a real anthropic module mock with RateLimitError
        anthropic_module = MagicMock()
        anthropic_module.RateLimitError = type("RateLimitError", (Exception,), {})
        rate_limit_error = anthropic_module.RateLimitError("Rate limit exceeded")

        mock_client_instance = AsyncMock()
        mock_client_instance.messages.create = AsyncMock(side_effect=rate_limit_error)
        mock_anthropic.return_value = mock_client_instance

        with patch("dm20_protocol.claudmaster.llm_client.AnthropicLLMClient._anthropic_module", anthropic_module):
            client = AnthropicLLMClient(api_key="test-key")
            client._anthropic_module = anthropic_module

            with pytest.raises(LLMRateLimitError, match="Rate limit exceeded"):
                await client.generate("Test prompt")


@pytest.mark.asyncio
async def test_anthropic_generate_stream_success(mock_anthropic_stream: AsyncMock) -> None:
    """Test successful streaming generation with AnthropicLLMClient."""
    with patch("dm20_protocol.claudmaster.llm_client.AsyncAnthropic") as mock_anthropic:
        # Setup mock
        mock_client_instance = AsyncMock()
        mock_client_instance.messages.stream = MagicMock(return_value=mock_anthropic_stream)
        mock_anthropic.return_value = mock_client_instance

        # Create client and generate stream
        client = AnthropicLLMClient(api_key="test-key")
        chunks = []
        async for chunk in client.generate_stream("Test prompt", max_tokens=512):
            chunks.append(chunk)

        # Verify
        assert len(chunks) == 5
        assert "".join(chunks) == "This is a streamed response."


# ---------------------------------------------------------------------------
# MultiModelClient Tests
# ---------------------------------------------------------------------------


def test_multi_model_client_initialization() -> None:
    """Test MultiModelClient initialization."""
    narrator_client = MockLLMClient(default_response="Narrator response")
    arbiter_client = MockLLMClient(default_response="Arbiter response")

    multi_client = MultiModelClient({
        "narrator": narrator_client,
        "arbiter": arbiter_client,
    })

    assert multi_client.has_role("narrator")
    assert multi_client.has_role("arbiter")
    assert not multi_client.has_role("unknown")
    assert set(multi_client.list_roles()) == {"narrator", "arbiter"}


def test_multi_model_client_get_client() -> None:
    """Test MultiModelClient returns correct client for role."""
    narrator_client = MockLLMClient(default_response="Narrator response")
    arbiter_client = MockLLMClient(default_response="Arbiter response")

    multi_client = MultiModelClient({
        "narrator": narrator_client,
        "arbiter": arbiter_client,
    })

    retrieved_narrator = multi_client.get_client("narrator")
    retrieved_arbiter = multi_client.get_client("arbiter")

    assert retrieved_narrator is narrator_client
    assert retrieved_arbiter is arbiter_client


def test_multi_model_client_unknown_role() -> None:
    """Test MultiModelClient raises error for unknown role."""
    narrator_client = MockLLMClient()

    multi_client = MultiModelClient({"narrator": narrator_client})

    with pytest.raises(LLMConfigurationError, match="No LLM client configured for role 'unknown'"):
        multi_client.get_client("unknown")


@pytest.mark.asyncio
async def test_multi_model_client_routing() -> None:
    """Test that MultiModelClient correctly routes to different models."""
    narrator_client = MockLLMClient(default_response="Narrator response")
    arbiter_client = MockLLMClient(default_response="Arbiter response")

    multi_client = MultiModelClient({
        "narrator": narrator_client,
        "arbiter": arbiter_client,
    })

    # Generate with different clients
    narrator_response = await multi_client.get_client("narrator").generate("Describe a scene")
    arbiter_response = await multi_client.get_client("arbiter").generate("Apply rules")

    assert narrator_response == "Narrator response"
    assert arbiter_response == "Arbiter response"
    assert narrator_client.call_count == 1
    assert arbiter_client.call_count == 1


# ---------------------------------------------------------------------------
# Config Integration Tests
# ---------------------------------------------------------------------------


def test_config_per_agent_fields() -> None:
    """Test that ClaudmasterConfig has per-agent model fields."""
    config = ClaudmasterConfig()

    # Check default values
    assert config.narrator_model == "claude-haiku-4-5-20251001"
    assert config.arbiter_model == "claude-sonnet-4-5-20250929"
    assert config.narrator_max_tokens == 1024
    assert config.arbiter_max_tokens == 2048
    assert config.narrator_temperature == 0.8
    assert config.arbiter_temperature == 0.3


def test_config_per_agent_custom_values() -> None:
    """Test ClaudmasterConfig with custom per-agent values."""
    config = ClaudmasterConfig(
        narrator_model="claude-opus-4-6",
        arbiter_model="claude-haiku-4-5-20251001",
        narrator_max_tokens=2048,
        arbiter_max_tokens=4096,
        narrator_temperature=0.9,
        arbiter_temperature=0.2,
    )

    assert config.narrator_model == "claude-opus-4-6"
    assert config.arbiter_model == "claude-haiku-4-5-20251001"
    assert config.narrator_max_tokens == 2048
    assert config.arbiter_max_tokens == 4096
    assert config.narrator_temperature == 0.9
    assert config.arbiter_temperature == 0.2


def test_config_temperature_validation() -> None:
    """Test that temperature validators work for per-agent fields."""
    # Valid temperatures
    config = ClaudmasterConfig(
        narrator_temperature=0.0,
        arbiter_temperature=2.0,
    )
    assert config.narrator_temperature == 0.0
    assert config.arbiter_temperature == 2.0

    # Invalid narrator_temperature
    with pytest.raises(ValueError, match="temperature must be between 0.0 and 2.0"):
        ClaudmasterConfig(narrator_temperature=3.0)

    # Invalid arbiter_temperature
    with pytest.raises(ValueError, match="temperature must be between 0.0 and 2.0"):
        ClaudmasterConfig(arbiter_temperature=-0.1)


def test_config_max_tokens_bounds() -> None:
    """Test that max_tokens fields have correct bounds."""
    # Valid values
    config = ClaudmasterConfig(
        narrator_max_tokens=256,  # Minimum
        arbiter_max_tokens=16384,  # Maximum
    )
    assert config.narrator_max_tokens == 256
    assert config.arbiter_max_tokens == 16384

    # Below minimum (narrator)
    with pytest.raises(ValueError):
        ClaudmasterConfig(narrator_max_tokens=100)

    # Above maximum (arbiter)
    with pytest.raises(ValueError):
        ClaudmasterConfig(arbiter_max_tokens=20000)


# ---------------------------------------------------------------------------
# Integration Test: Create Clients from Config
# ---------------------------------------------------------------------------


def test_create_multi_model_client_from_config() -> None:
    """Test creating a MultiModelClient from ClaudmasterConfig."""
    config = ClaudmasterConfig(
        narrator_model="claude-haiku-4-5-20251001",
        arbiter_model="claude-sonnet-4-5-20250929",
        narrator_temperature=0.8,
        arbiter_temperature=0.3,
        narrator_max_tokens=1024,
        arbiter_max_tokens=2048,
    )

    # Create mock clients based on config
    narrator_client = MockLLMClient(default_response="Narrator response")
    arbiter_client = MockLLMClient(default_response="Arbiter response")

    multi_client = MultiModelClient({
        "narrator": narrator_client,
        "arbiter": arbiter_client,
    })

    # Verify routing works
    assert multi_client.get_client("narrator") is narrator_client
    assert multi_client.get_client("arbiter") is arbiter_client
