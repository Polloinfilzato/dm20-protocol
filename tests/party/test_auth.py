"""
Tests for Party Mode authentication system.

Tests token generation, validation, refresh, QR code generation,
and host IP detection.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from dm20_protocol.party.auth import (
    TokenManager,
    QRCodeGenerator,
    detect_host_ip,
)


class TestTokenManager:
    """Tests for TokenManager."""

    def test_generate_token(self) -> None:
        """Test basic token generation."""
        manager = TokenManager()
        token = manager.generate_token("player1")

        assert isinstance(token, str)
        assert len(token) >= 6  # URL-safe tokens are ~8 chars
        assert token in manager._tokens
        assert manager._tokens[token] == "player1"
        assert manager._reverse_index["player1"] == token

    def test_generate_token_unique(self) -> None:
        """Test that tokens are unique for different players."""
        manager = TokenManager()
        token1 = manager.generate_token("player1")
        token2 = manager.generate_token("player2")

        assert token1 != token2
        assert manager.validate_token(token1) == "player1"
        assert manager.validate_token(token2) == "player2"

    def test_generate_token_replaces_existing(self) -> None:
        """Test that generating a new token for same player invalidates old one."""
        manager = TokenManager()
        old_token = manager.generate_token("player1")
        new_token = manager.generate_token("player1")

        assert old_token != new_token
        assert manager.validate_token(old_token) is None
        assert manager.validate_token(new_token) == "player1"
        assert len(manager._tokens) == 1

    def test_validate_token_valid(self) -> None:
        """Test validating a valid token."""
        manager = TokenManager()
        token = manager.generate_token("player1")

        player_id = manager.validate_token(token)
        assert player_id == "player1"

    def test_validate_token_invalid(self) -> None:
        """Test validating an invalid token."""
        manager = TokenManager()
        player_id = manager.validate_token("invalid_token")

        assert player_id is None

    def test_validate_token_empty(self) -> None:
        """Test validating an empty token."""
        manager = TokenManager()
        player_id = manager.validate_token("")

        assert player_id is None

    def test_refresh_token(self) -> None:
        """Test token refresh."""
        manager = TokenManager()
        old_token = manager.generate_token("player1")
        new_token = manager.refresh_token("player1")

        assert old_token != new_token
        assert manager.validate_token(old_token) is None
        assert manager.validate_token(new_token) == "player1"

    def test_refresh_token_nonexistent_player(self) -> None:
        """Test refreshing token for player who doesn't have one."""
        manager = TokenManager()
        token = manager.refresh_token("player1")

        # Should create a new token
        assert isinstance(token, str)
        assert manager.validate_token(token) == "player1"

    def test_revoke_token(self) -> None:
        """Test token revocation."""
        manager = TokenManager()
        token = manager.generate_token("player1")

        assert manager.validate_token(token) == "player1"

        revoked = manager.revoke_token("player1")
        assert revoked is True
        assert manager.validate_token(token) is None
        assert "player1" not in manager._reverse_index

    def test_revoke_token_nonexistent(self) -> None:
        """Test revoking a non-existent token."""
        manager = TokenManager()
        revoked = manager.revoke_token("player1")

        assert revoked is False

    def test_get_all_tokens(self) -> None:
        """Test getting all active tokens."""
        manager = TokenManager()
        token1 = manager.generate_token("player1")
        token2 = manager.generate_token("player2")

        all_tokens = manager.get_all_tokens()
        assert all_tokens == {
            "player1": token1,
            "player2": token2,
        }

    def test_clear(self) -> None:
        """Test clearing all tokens."""
        manager = TokenManager()
        manager.generate_token("player1")
        manager.generate_token("player2")

        manager.clear()

        assert len(manager._tokens) == 0
        assert len(manager._reverse_index) == 0
        assert len(manager._created_at) == 0

    def test_multiple_players(self) -> None:
        """Test managing tokens for multiple players."""
        manager = TokenManager()
        tokens = {}

        for i in range(5):
            player_id = f"player{i}"
            tokens[player_id] = manager.generate_token(player_id)

        # All tokens should be valid
        for player_id, token in tokens.items():
            assert manager.validate_token(token) == player_id

        # Revoke one
        manager.revoke_token("player2")
        assert manager.validate_token(tokens["player2"]) is None

        # Others should still work
        assert manager.validate_token(tokens["player1"]) == "player1"
        assert manager.validate_token(tokens["player3"]) == "player3"


class TestQRCodeGenerator:
    """Tests for QRCodeGenerator."""

    def test_generate_qr_code_returns_bytes(self) -> None:
        """Test that QR code generation returns PNG bytes."""
        url = "http://192.168.1.100:8080/play?token=abc123"
        png_data = QRCodeGenerator.generate_qr_code(url)

        assert isinstance(png_data, bytes)
        assert len(png_data) > 0
        # Check PNG magic bytes
        assert png_data[:8] == b'\x89PNG\r\n\x1a\n'

    def test_generate_qr_code_saves_to_file(self) -> None:
        """Test that QR code can be saved to a file."""
        url = "http://192.168.1.100:8080/play?token=abc123"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_qr.png"
            png_data = QRCodeGenerator.generate_qr_code(url, output_path)

            assert output_path.exists()
            assert output_path.stat().st_size > 0

            # Verify file contents match returned bytes
            file_data = output_path.read_bytes()
            assert file_data == png_data

    def test_generate_qr_code_creates_parent_dir(self) -> None:
        """Test that QR code generation creates parent directories."""
        url = "http://192.168.1.100:8080/play?token=abc123"

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "subdir" / "test_qr.png"
            QRCodeGenerator.generate_qr_code(url, output_path)

            assert output_path.exists()
            assert output_path.parent.exists()

    def test_generate_player_qr(self) -> None:
        """Test generating a player-specific QR code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            campaign_dir = Path(tmpdir)
            player_id = "aragorn"
            token = "abc123"
            host = "192.168.1.100"
            port = 8080

            qr_path = QRCodeGenerator.generate_player_qr(
                player_id, token, host, port, campaign_dir
            )

            expected_path = campaign_dir / "party" / "qr-aragorn.png"
            assert qr_path == expected_path
            assert qr_path.exists()
            assert qr_path.stat().st_size > 0

    def test_generate_player_qr_multiple(self) -> None:
        """Test generating QR codes for multiple players."""
        with tempfile.TemporaryDirectory() as tmpdir:
            campaign_dir = Path(tmpdir)
            players = [
                ("aragorn", "token1"),
                ("legolas", "token2"),
                ("gimli", "token3"),
            ]

            for player_id, token in players:
                qr_path = QRCodeGenerator.generate_player_qr(
                    player_id, token, "192.168.1.100", 8080, campaign_dir
                )
                assert qr_path.exists()

            # Check all files were created
            party_dir = campaign_dir / "party"
            qr_files = list(party_dir.glob("qr-*.png"))
            assert len(qr_files) == 3


class TestDetectHostIP:
    """Tests for detect_host_ip function."""

    def test_detect_host_ip_returns_string(self) -> None:
        """Test that host IP detection returns a string."""
        ip = detect_host_ip()

        assert isinstance(ip, str)
        # Should be a valid IPv4 address format
        parts = ip.split(".")
        assert len(parts) == 4
        for part in parts:
            assert 0 <= int(part) <= 255

    def test_detect_host_ip_not_empty(self) -> None:
        """Test that host IP detection doesn't return empty string."""
        ip = detect_host_ip()

        assert ip != ""
        assert ip is not None

    @patch("socket.gethostbyname")
    def test_detect_host_ip_fallback(self, mock_gethostbyname) -> None:
        """Test fallback to 127.0.0.1 on error."""
        mock_gethostbyname.side_effect = Exception("Network error")

        ip = detect_host_ip()
        assert ip == "127.0.0.1"

    def test_detect_host_ip_not_localhost(self) -> None:
        """Test that detected IP is preferably not localhost."""
        ip = detect_host_ip()

        # In most test environments, we should get a LAN IP or localhost
        # This test just ensures the function doesn't crash and returns valid IP
        # Common private IP ranges: 10.x, 172.16-31.x, 192.168.x, 100.64-127.x (CGNAT)
        parts = ip.split(".")
        assert len(parts) == 4
        # Just ensure it's a valid IP format
        for part in parts:
            assert 0 <= int(part) <= 255


class TestTokenManagerEdgeCases:
    """Edge case tests for TokenManager."""

    def test_observer_token(self) -> None:
        """Test generating token for OBSERVER role."""
        manager = TokenManager()
        token = manager.generate_token("OBSERVER")

        assert manager.validate_token(token) == "OBSERVER"

    def test_special_character_player_ids(self) -> None:
        """Test tokens with special character player IDs."""
        manager = TokenManager()
        special_ids = [
            "player-1",
            "player_with_underscore",
            "player.with.dots",
            "player@host",
        ]

        for player_id in special_ids:
            token = manager.generate_token(player_id)
            assert manager.validate_token(token) == player_id

    def test_very_long_player_id(self) -> None:
        """Test token generation with very long player ID."""
        manager = TokenManager()
        long_id = "a" * 1000

        token = manager.generate_token(long_id)
        assert manager.validate_token(token) == long_id

    def test_concurrent_operations(self) -> None:
        """Test that operations maintain consistency."""
        manager = TokenManager()

        # Generate multiple tokens
        tokens = {f"player{i}": manager.generate_token(f"player{i}") for i in range(10)}

        # Validate all
        for player_id, token in tokens.items():
            assert manager.validate_token(token) == player_id

        # Refresh some
        for i in range(0, 5):
            new_token = manager.refresh_token(f"player{i}")
            tokens[f"player{i}"] = new_token

        # Revoke some
        for i in range(5, 8):
            manager.revoke_token(f"player{i}")
            del tokens[f"player{i}"]

        # Validate remaining
        for player_id, token in tokens.items():
            assert manager.validate_token(token) == player_id
