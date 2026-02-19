"""
Tests for Issue #170: Party-Mode Stable Tokens + QR Terminal Display.

Covers:
- Deterministic token generation (token = player_id)
- OBSERVER token is the fixed string "OBSERVER"
- Token stability across simulated restarts (new TokenManager instances)
- QR terminal ASCII rendering
- Graceful fallback on rendering failure
- Existing party-mode functionality unchanged (validate, revoke, refresh, clear)
"""

import io
from unittest.mock import patch

import pytest

from dm20_protocol.party.auth import QRCodeGenerator, TokenManager


# ---------------------------------------------------------------------------
# Stable Token Tests
# ---------------------------------------------------------------------------


class TestStableTokens:
    """Token = player_id, deterministic across restarts."""

    def test_token_equals_player_id(self):
        """Token for a character should be the character's ID."""
        tm = TokenManager()
        token = tm.generate_token("Gandalf")
        assert token == "Gandalf"

    def test_token_equals_player_id_various_names(self):
        """Various character names all produce token == name."""
        tm = TokenManager()
        names = ["Aragorn", "Legolas", "Gimli", "Frodo Baggins", "Sam-wise"]
        for name in names:
            token = tm.generate_token(name)
            assert token == name, f"Expected token '{name}', got '{token}'"

    def test_observer_token_is_fixed_string(self):
        """OBSERVER token must always be the literal string 'OBSERVER'."""
        tm = TokenManager()
        token = tm.generate_token("OBSERVER")
        assert token == "OBSERVER"

    def test_token_stable_across_restarts(self):
        """Same character produces the same token in a new TokenManager (simulated restart)."""
        # First "session"
        tm1 = TokenManager()
        token1 = tm1.generate_token("Gandalf")

        # Second "session" (new TokenManager = simulated server restart)
        tm2 = TokenManager()
        token2 = tm2.generate_token("Gandalf")

        assert token1 == token2
        assert token1 == "Gandalf"

    def test_observer_token_stable_across_restarts(self):
        """OBSERVER token stays 'OBSERVER' across restarts."""
        tm1 = TokenManager()
        obs1 = tm1.generate_token("OBSERVER")

        tm2 = TokenManager()
        obs2 = tm2.generate_token("OBSERVER")

        assert obs1 == obs2 == "OBSERVER"

    def test_multiple_characters_stable(self):
        """Multiple characters all get stable tokens across restarts."""
        names = ["Gandalf", "Frodo", "OBSERVER"]

        tm1 = TokenManager()
        tokens1 = {name: tm1.generate_token(name) for name in names}

        tm2 = TokenManager()
        tokens2 = {name: tm2.generate_token(name) for name in names}

        for name in names:
            assert tokens1[name] == tokens2[name] == name


# ---------------------------------------------------------------------------
# Token Validation Tests (existing functionality)
# ---------------------------------------------------------------------------


class TestTokenValidation:
    """Ensure existing validate/revoke/refresh/clear work with stable tokens."""

    def test_validate_token(self):
        """Validating a stable token returns the correct player_id."""
        tm = TokenManager()
        tm.generate_token("Gandalf")
        assert tm.validate_token("Gandalf") == "Gandalf"

    def test_validate_invalid_token(self):
        """Invalid token returns None."""
        tm = TokenManager()
        tm.generate_token("Gandalf")
        assert tm.validate_token("nonexistent") is None

    def test_validate_observer(self):
        """OBSERVER token validates to 'OBSERVER'."""
        tm = TokenManager()
        tm.generate_token("OBSERVER")
        assert tm.validate_token("OBSERVER") == "OBSERVER"

    def test_revoke_token(self):
        """Revoking a token makes it invalid."""
        tm = TokenManager()
        tm.generate_token("Gandalf")
        assert tm.revoke_token("Gandalf") is True
        assert tm.validate_token("Gandalf") is None

    def test_revoke_nonexistent(self):
        """Revoking a nonexistent token returns False."""
        tm = TokenManager()
        assert tm.revoke_token("nobody") is False

    def test_refresh_token(self):
        """Refreshing a token returns a new (same) token and remains valid."""
        tm = TokenManager()
        old_token = tm.generate_token("Gandalf")
        new_token = tm.refresh_token("Gandalf")
        # With deterministic tokens, refresh returns the same value
        assert new_token == "Gandalf"
        assert tm.validate_token("Gandalf") == "Gandalf"

    def test_clear_tokens(self):
        """Clearing all tokens invalidates everything."""
        tm = TokenManager()
        tm.generate_token("Gandalf")
        tm.generate_token("OBSERVER")
        tm.clear()
        assert tm.validate_token("Gandalf") is None
        assert tm.validate_token("OBSERVER") is None

    def test_get_all_tokens(self):
        """get_all_tokens returns player_id -> token mapping."""
        tm = TokenManager()
        tm.generate_token("Gandalf")
        tm.generate_token("Frodo")
        tm.generate_token("OBSERVER")
        all_tokens = tm.get_all_tokens()
        assert all_tokens == {
            "Gandalf": "Gandalf",
            "Frodo": "Frodo",
            "OBSERVER": "OBSERVER",
        }

    def test_token_lookup_is_o1(self):
        """Token validation uses dict lookup (O(1))."""
        tm = TokenManager()
        # Generate many tokens
        for i in range(1000):
            tm.generate_token(f"player_{i}")
        # Validate one — this is a dict.get() call, inherently O(1)
        assert tm.validate_token("player_500") == "player_500"

    def test_regenerate_replaces_old_mapping(self):
        """Generating token for same player_id replaces old mapping cleanly."""
        tm = TokenManager()
        tm.generate_token("Gandalf")
        # Generate again (same player)
        token2 = tm.generate_token("Gandalf")
        assert token2 == "Gandalf"
        assert tm.validate_token("Gandalf") == "Gandalf"
        # Only one entry in _tokens
        assert len(tm._tokens) == 1


# ---------------------------------------------------------------------------
# QR Terminal Rendering Tests
# ---------------------------------------------------------------------------


class TestQRTerminalRendering:
    """Tests for QR code ASCII/Unicode art rendering in terminal."""

    def test_render_qr_terminal_returns_string(self):
        """render_qr_terminal returns a non-empty string."""
        result = QRCodeGenerator.render_qr_terminal(
            "http://192.168.1.5:8080/play?token=Gandalf", "Gandalf"
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_qr_terminal_contains_label(self):
        """Output includes the character label."""
        result = QRCodeGenerator.render_qr_terminal(
            "http://192.168.1.5:8080/play?token=Gandalf", "Gandalf"
        )
        assert "Gandalf" in result

    def test_render_qr_terminal_contains_url(self):
        """Output includes the URL."""
        url = "http://192.168.1.5:8080/play?token=Gandalf"
        result = QRCodeGenerator.render_qr_terminal(url, "Gandalf")
        assert url in result

    def test_render_qr_terminal_contains_unicode_blocks(self):
        """Output contains Unicode block characters used by qrcode ASCII mode."""
        result = QRCodeGenerator.render_qr_terminal(
            "http://192.168.1.5:8080/play?token=Test", "Test"
        )
        # qrcode.print_ascii uses half-block characters
        assert any(c in result for c in ["\u2580", "\u2584", "\u2588", "\u2591"])

    def test_render_qr_terminal_observer(self):
        """OBSERVER QR renders correctly."""
        result = QRCodeGenerator.render_qr_terminal(
            "http://192.168.1.5:8080/play?token=OBSERVER", "OBSERVER (read-only)"
        )
        assert "OBSERVER (read-only)" in result
        assert "OBSERVER" in result

    def test_render_qr_terminal_has_separators(self):
        """Output has visual separator lines."""
        result = QRCodeGenerator.render_qr_terminal(
            "http://192.168.1.5:8080/play?token=Gandalf", "Gandalf"
        )
        assert "---" in result  # separator dashes

    def test_render_qr_terminal_graceful_fallback(self):
        """If QR rendering fails, a URL-only fallback is returned."""
        with patch("dm20_protocol.party.auth.qrcode.QRCode", side_effect=RuntimeError("mock failure")):
            result = QRCodeGenerator.render_qr_terminal(
                "http://192.168.1.5:8080/play?token=Gandalf", "Gandalf"
            )
        assert "Gandalf" in result
        assert "http://192.168.1.5:8080/play?token=Gandalf" in result
        assert "QR terminal rendering failed" in result

    def test_render_multiple_qr_codes(self):
        """Multiple QR codes can be rendered sequentially."""
        names = ["Gandalf", "Frodo", "OBSERVER"]
        results = []
        for name in names:
            url = f"http://192.168.1.5:8080/play?token={name}"
            result = QRCodeGenerator.render_qr_terminal(url, name)
            results.append(result)

        # Each result should contain its own label
        for i, name in enumerate(names):
            assert name in results[i]


# ---------------------------------------------------------------------------
# QR File Generation Tests (existing functionality preserved)
# ---------------------------------------------------------------------------


class TestQRFileGeneration:
    """Ensure file-based QR code saving still works."""

    def test_generate_qr_code_returns_bytes(self):
        """generate_qr_code returns PNG bytes."""
        data = QRCodeGenerator.generate_qr_code("http://example.com")
        assert isinstance(data, bytes)
        assert len(data) > 0
        # PNG magic bytes
        assert data[:4] == b"\x89PNG"

    def test_generate_qr_code_saves_to_file(self, tmp_path):
        """generate_qr_code saves PNG to file when output_path is given."""
        output = tmp_path / "qr-test.png"
        QRCodeGenerator.generate_qr_code("http://example.com", output_path=output)
        assert output.exists()
        assert output.read_bytes()[:4] == b"\x89PNG"

    def test_generate_player_qr(self, tmp_path):
        """generate_player_qr saves QR to campaign_dir/party/qr-{name}.png."""
        qr_path = QRCodeGenerator.generate_player_qr(
            player_id="Gandalf",
            token="Gandalf",
            host="192.168.1.5",
            port=8080,
            campaign_dir=tmp_path,
        )
        assert qr_path.exists()
        assert "qr-Gandalf.png" in str(qr_path)
        assert qr_path.read_bytes()[:4] == b"\x89PNG"

    def test_generate_observer_qr(self, tmp_path):
        """Observer QR code is generated with correct filename."""
        qr_path = QRCodeGenerator.generate_player_qr(
            player_id="OBSERVER",
            token="OBSERVER",
            host="192.168.1.5",
            port=8080,
            campaign_dir=tmp_path,
        )
        assert qr_path.exists()
        assert "qr-OBSERVER.png" in str(qr_path)
