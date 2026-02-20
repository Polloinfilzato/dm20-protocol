"""
Tests for STT (Speech-to-Text) integration in Party Mode.

Verifies:
- Player UI contains mic button and STT JavaScript
- Action endpoint accepts voice-sourced actions identically to typed ones
- Static assets include STT-related styles
- Graceful fallback: text input always works regardless of STT availability
"""

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from dm20_protocol.party.server import PartyServer

from .conftest import PLAYER_IDS


# ===================================================================
# Static Asset Tests
# ===================================================================


class TestSTTStaticAssets:
    """Verify STT elements are present in player UI static files."""

    @pytest.fixture(autouse=True)
    def _load_static(self) -> None:
        static_dir = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "dm20_protocol"
            / "party"
            / "static"
        )
        self.html = (static_dir / "index.html").read_text()
        self.js = (static_dir / "app.js").read_text()
        self.css = (static_dir / "style.css").read_text()

    def test_html_contains_mic_button(self) -> None:
        """Mic button must be in the action bar HTML."""
        assert 'class="action-bar__mic"' in self.html
        assert 'class="mic-icon"' in self.html
        assert 'class="mic-listening-dot"' in self.html

    def test_html_mic_button_hidden_by_default(self) -> None:
        """Mic button starts hidden (shown by JS if STT is supported)."""
        assert 'class="action-bar__mic"' in self.html
        # The button should have a hidden attribute by default
        mic_idx = self.html.index('class="action-bar__mic"')
        mic_line = self.html[max(0, mic_idx - 100) : mic_idx + 100]
        assert "hidden" in mic_line

    def test_html_has_transcript_preview(self) -> None:
        """Voice transcript preview element must exist."""
        assert 'class="voice-transcript-preview"' in self.html

    def test_js_contains_stt_initialization(self) -> None:
        """JavaScript must contain STT setup code."""
        assert "initSTT" in self.js
        assert "SpeechRecognition" in self.js
        assert "webkitSpeechRecognition" in self.js

    def test_js_contains_stt_feature_detection(self) -> None:
        """JS must check for browser STT support before enabling."""
        assert "sttSupported" in self.js

    def test_js_contains_mic_toggle(self) -> None:
        """JS must have toggle function for mic button."""
        assert "toggleSTT" in self.js
        assert "startSTT" in self.js
        assert "stopSTT" in self.js

    def test_js_handles_permission_denied(self) -> None:
        """JS must handle microphone permission denial gracefully."""
        assert "not-allowed" in self.js
        assert "sttDenied" in self.js

    def test_js_sends_voice_source_field(self) -> None:
        """JS must include source: 'voice' when submitting voice actions."""
        assert "source: 'voice'" in self.js or 'source: "voice"' in self.js

    def test_js_submits_voice_action_via_fetch(self) -> None:
        """Voice actions use the same /action endpoint as typed actions."""
        assert "submitVoiceAction" in self.js
        assert "/action" in self.js

    def test_js_shows_interim_transcription(self) -> None:
        """JS must show interim transcription as preview."""
        assert "interimResults" in self.js
        assert "showTranscriptPreview" in self.js

    def test_css_contains_mic_styles(self) -> None:
        """CSS must include mic button and listening indicator styles."""
        assert ".action-bar__mic" in self.css
        assert ".action-bar__mic--listening" in self.css
        assert ".mic-listening-dot" in self.css

    def test_css_contains_transcript_preview_styles(self) -> None:
        """CSS must include voice transcript preview styles."""
        assert ".voice-transcript-preview" in self.css

    def test_css_has_mic_pulse_animation(self) -> None:
        """CSS must include a pulse animation for listening state."""
        assert "mic-pulse" in self.css

    def test_text_input_always_present(self) -> None:
        """Text input must always exist regardless of STT support (fallback)."""
        assert 'class="action-bar__input"' in self.html
        assert 'class="action-bar__send"' in self.html


# ===================================================================
# Server Integration Tests
# ===================================================================


class TestSTTServerIntegration:
    """Verify the server handles voice-sourced actions correctly."""

    def test_action_with_voice_source_accepted(
        self, e2e_server: PartyServer, e2e_tokens: dict[str, str]
    ) -> None:
        """Server must accept actions with source: 'voice' field."""
        client = TestClient(e2e_server.app)
        token = e2e_tokens["thorin"]

        resp = client.post(
            "/action",
            json={"action": "I cast fireball", "source": "voice"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["player_id"] == "thorin"
        assert data["action_id"]

    def test_voice_action_queued_identically(
        self, e2e_server: PartyServer, e2e_tokens: dict[str, str]
    ) -> None:
        """Voice actions must be queued identically to typed actions."""
        client = TestClient(e2e_server.app)
        token = e2e_tokens["elara"]

        # Submit typed action
        resp1 = client.post(
            "/action",
            json={"action": "I search the chest"},
            headers={"Authorization": f"Bearer {token}"},
        )
        typed_id = resp1.json()["action_id"]

        # Submit voice action
        resp2 = client.post(
            "/action",
            json={"action": "I open the door", "source": "voice"},
            headers={"Authorization": f"Bearer {token}"},
        )
        voice_id = resp2.json()["action_id"]

        # Both should be in the queue
        action1 = e2e_server.action_queue.pop()
        action2 = e2e_server.action_queue.pop()
        assert action1 is not None
        assert action2 is not None
        assert {action1["id"], action2["id"]} == {typed_id, voice_id}

    def test_empty_voice_action_rejected(
        self, e2e_server: PartyServer, e2e_tokens: dict[str, str]
    ) -> None:
        """Empty transcriptions must be rejected."""
        client = TestClient(e2e_server.app)
        token = e2e_tokens["vex"]

        resp = client.post(
            "/action",
            json={"action": "", "source": "voice"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
        assert "Empty action" in resp.json()["error"]

    def test_whitespace_voice_action_rejected(
        self, e2e_server: PartyServer, e2e_tokens: dict[str, str]
    ) -> None:
        """Whitespace-only transcriptions must be rejected."""
        client = TestClient(e2e_server.app)
        token = e2e_tokens["gorm"]

        resp = client.post(
            "/action",
            json={"action": "   ", "source": "voice"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_player_page_serves_with_mic_button(
        self, e2e_server: PartyServer, e2e_tokens: dict[str, str]
    ) -> None:
        """Player page served by the server must include mic button."""
        client = TestClient(e2e_server.app)
        token = e2e_tokens["thorin"]

        resp = client.get(f"/play?token={token}")
        assert resp.status_code == 200
        html = resp.text
        assert "action-bar__mic" in html
        assert "mic-icon" in html


# ===================================================================
# Combat Gating with STT
# ===================================================================


class TestSTTCombatGating:
    """Verify STT respects combat turn gating (same as typed actions)."""

    def test_voice_action_uses_same_gating_as_typed(
        self, e2e_server: PartyServer, e2e_tokens: dict[str, str]
    ) -> None:
        """Voice and typed actions share the same turn gating logic.

        Without an active TurnManager, both typed and voice actions are allowed.
        The _check_turn_gate method treats them identically since the action
        endpoint doesn't distinguish between sources.
        """
        client = TestClient(e2e_server.app)
        token = e2e_tokens["thorin"]

        # No TurnManager set -> both typed and voice actions pass
        resp_typed = client.post(
            "/action",
            json={"action": "I search the room"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp_voice = client.post(
            "/action",
            json={"action": "I search the room", "source": "voice"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_typed.status_code == resp_voice.status_code == 200
