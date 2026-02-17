"""Tests for D&D Beyond character fetcher."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
import json
from pathlib import Path

from dm20_protocol.importers.dndbeyond.fetcher import (
    extract_character_id,
    fetch_character,
    read_character_file,
)
from dm20_protocol.importers.base import ImportError


class TestExtractCharacterId:
    """Test character ID extraction from various URL formats."""

    def test_extract_character_id_from_full_url(self):
        """Extract ID from full DDB character URL."""
        url = "https://www.dndbeyond.com/characters/12345678"
        assert extract_character_id(url) == 12345678

    def test_extract_character_id_from_builder_url(self):
        """Extract ID from DDB character builder URL."""
        url = "https://www.dndbeyond.com/characters/12345678/builder"
        assert extract_character_id(url) == 12345678

    def test_extract_character_id_bare_number(self):
        """Extract ID from bare numeric string."""
        assert extract_character_id("12345678") == 12345678

    def test_extract_character_id_www_url(self):
        """Extract ID from www URL variant."""
        url = "https://www.dndbeyond.com/characters/99999"
        assert extract_character_id(url) == 99999

    def test_extract_character_id_without_protocol(self):
        """Extract ID from URL without protocol."""
        url = "dndbeyond.com/characters/87654321"
        assert extract_character_id(url) == 87654321

    def test_extract_character_id_invalid(self):
        """Reject invalid input that's not a URL or number."""
        with pytest.raises(ImportError) as exc_info:
            extract_character_id("not-a-url")
        assert "Invalid D&D Beyond character URL or ID" in str(exc_info.value)


class TestFetchCharacter:
    """Test fetching character data from DDB API."""

    @pytest.mark.asyncio
    async def test_fetch_character_success(self):
        """Successfully fetch a character from the API."""
        mock_response_data = {
            "data": {
                "name": "Test Character",
                "stats": [
                    {"id": 1, "value": 10},
                    {"id": 2, "value": 12},
                    {"id": 3, "value": 14},
                    {"id": 4, "value": 13},
                    {"id": 5, "value": 15},
                    {"id": 6, "value": 8}
                ],
                "classes": [
                    {"level": 5, "definition": {"name": "Fighter"}}
                ]
            }
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            # Create mock response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_response_data

            # Configure mock client
            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # Test
            result = await fetch_character("12345678")

            # Verify unwrapped data is returned
            assert result["name"] == "Test Character"
            assert "stats" in result
            assert "classes" in result
            assert "data" not in result  # Envelope should be unwrapped

    @pytest.mark.asyncio
    async def test_fetch_character_not_found(self):
        """Handle 404 error with user-friendly message."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 404

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(ImportError) as exc_info:
                await fetch_character("99999999")

            assert "not found" in str(exc_info.value).lower()
            assert "99999999" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_character_private(self):
        """Handle 403 error for private characters."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 403

            mock_client = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(ImportError) as exc_info:
                await fetch_character("12345678")

            assert "private" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_fetch_character_timeout(self):
        """Handle timeout with user-friendly message."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            with pytest.raises(ImportError) as exc_info:
                await fetch_character("12345678")

            assert "not responding" in str(exc_info.value).lower()


class TestReadCharacterFile:
    """Test reading character data from local JSON files."""

    def test_read_character_file_valid(self, tmp_path):
        """Read a valid character JSON file."""
        # Use the fixture file
        fixture_path = Path(__file__).parent / "fixtures" / "ddb_character_sample.json"
        result = read_character_file(str(fixture_path))

        assert isinstance(result, dict)
        assert result["name"] == "Thalion Nightbreeze"
        assert "stats" in result
        assert "classes" in result

    def test_read_character_file_not_found(self):
        """Handle missing file with clear error."""
        with pytest.raises(ImportError) as exc_info:
            read_character_file("/nonexistent/path/character.json")

        assert "not found" in str(exc_info.value).lower()

    def test_read_character_file_invalid_json(self, tmp_path):
        """Handle malformed JSON with clear error."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("this is not valid JSON {{{")

        with pytest.raises(ImportError) as exc_info:
            read_character_file(str(bad_file))

        assert "Invalid JSON" in str(exc_info.value)

    def test_read_character_file_unwraps_envelope(self, tmp_path):
        """Unwrap data envelope if present."""
        wrapped_file = tmp_path / "wrapped.json"
        wrapped_data = {
            "data": {
                "name": "Wrapped Character",
                "stats": [{"id": 1, "value": 10}],
                "classes": [{"level": 1}]
            }
        }
        wrapped_file.write_text(json.dumps(wrapped_data))

        result = read_character_file(str(wrapped_file))

        # Should unwrap the envelope
        assert result["name"] == "Wrapped Character"
        assert "data" not in result

    def test_read_character_file_missing_required_fields(self, tmp_path):
        """Reject file missing required fields."""
        incomplete_file = tmp_path / "incomplete.json"
        incomplete_data = {"name": "Incomplete Character"}
        incomplete_file.write_text(json.dumps(incomplete_data))

        with pytest.raises(ImportError) as exc_info:
            read_character_file(str(incomplete_file))

        assert "missing required fields" in str(exc_info.value).lower()
        assert "stats" in str(exc_info.value) or "classes" in str(exc_info.value)
