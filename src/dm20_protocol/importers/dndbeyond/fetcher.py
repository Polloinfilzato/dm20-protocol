"""
Fetch and read D&D Beyond character data.

This module handles both online fetching (via API) and local file reading
of D&D Beyond character JSON exports.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from ..base import ImportError
from .schema import DDB_API_BASE_URL, DDB_CHARACTER_URL_PATTERN


def extract_character_id(url_or_id: str) -> int:
    """
    Extract character ID from a D&D Beyond URL or bare numeric ID.

    Accepts:
    - Full URL: https://www.dndbeyond.com/characters/12345678
    - Builder URL: https://www.dndbeyond.com/characters/12345678/builder
    - Bare ID: "12345678"

    Args:
        url_or_id: D&D Beyond character URL or numeric ID string

    Returns:
        Character ID as integer

    Raises:
        ImportError: If the input doesn't match expected format
    """
    # Try regex pattern first
    match = DDB_CHARACTER_URL_PATTERN.search(url_or_id)
    if match:
        return int(match.group(1))

    # Try parsing as bare integer
    try:
        return int(url_or_id)
    except ValueError:
        raise ImportError(
            f"Invalid D&D Beyond character URL or ID: '{url_or_id}'. "
            "Expected format: https://www.dndbeyond.com/characters/12345678 or just the numeric ID."
        ) from None


async def fetch_character(url_or_id: str) -> dict:
    """
    Fetch character JSON from D&D Beyond API.

    Args:
        url_or_id: D&D Beyond character URL or numeric ID

    Returns:
        Raw character data as dictionary

    Raises:
        ImportError: If fetch fails, character not found, or character is private
    """
    character_id = extract_character_id(url_or_id)
    api_url = f"{DDB_API_BASE_URL}/{character_id}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, timeout=10.0)

            # Handle specific HTTP errors with actionable messages
            if response.status_code == 404:
                raise ImportError(
                    f"Character not found. Check the ID or URL: {character_id}"
                )
            elif response.status_code == 403:
                raise ImportError(
                    "Character is private. Set it to Public on D&D Beyond, or use file import."
                )

            # Raise for other HTTP errors
            response.raise_for_status()

            data = response.json()

    except httpx.TimeoutException:
        raise ImportError(
            "D&D Beyond is not responding. Try again later or use file import."
        ) from None
    except httpx.HTTPStatusError as e:
        raise ImportError(
            f"D&D Beyond returned HTTP {e.response.status_code}: {e.response.reason_phrase}"
        ) from None
    except httpx.RequestError as e:
        raise ImportError(
            f"Failed to connect to D&D Beyond: {e}"
        ) from None

    # Unwrap {"data": {...}} envelope if present
    if isinstance(data, dict) and "data" in data:
        data = data["data"]

    # Validate structure
    if not isinstance(data, dict):
        raise ImportError("Invalid response from D&D Beyond: expected JSON object")

    if "name" not in data or "stats" not in data or "classes" not in data:
        raise ImportError(
            "Invalid character data from D&D Beyond: missing required fields (name, stats, classes)"
        )

    return data


def read_character_file(file_path: str) -> dict:
    """
    Read and validate a local D&D Beyond character JSON file.

    Args:
        file_path: Path to the JSON file

    Returns:
        Raw character data as dictionary

    Raises:
        ImportError: If file not found, invalid JSON, or unrecognized format
    """
    path = Path(file_path)

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ImportError(
            f"Character file not found: {file_path}"
        ) from None
    except json.JSONDecodeError as e:
        raise ImportError(
            f"Invalid JSON in character file: {e}"
        ) from None
    except OSError as e:
        raise ImportError(
            f"Failed to read character file: {e}"
        ) from None

    # Unwrap {"data": {...}} envelope if present
    if isinstance(data, dict) and "data" in data:
        data = data["data"]

    # Validate structure
    if not isinstance(data, dict):
        raise ImportError(
            f"Invalid character file format: expected JSON object, got {type(data).__name__}"
        )

    if "stats" not in data or "classes" not in data:
        raise ImportError(
            "Unrecognized character file format: missing required fields (stats, classes). "
            "Ensure this is a valid D&D Beyond character export."
        )

    return data
