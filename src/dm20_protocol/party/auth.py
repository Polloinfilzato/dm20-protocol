"""
Authentication system for Party Mode web server.

Handles token generation, validation, and QR code creation for player sessions.
Each player gets a unique session token that encodes their player_id and
provides access to their character's UI.

Key components:
- Token generation from PCRegistry (one token per active PC + OBSERVER token)
- Token validation middleware for protecting routes
- QR code PNG generation for easy mobile access
- Token refresh mechanism to invalidate old tokens
"""

import logging
import secrets
import socket
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional

import qrcode
from qrcode.image.pil import PilImage

logger = logging.getLogger("dm20-protocol.party")


class TokenManager:
    """
    Manages session tokens for Party Mode authentication.

    Tokens are short, URL-safe strings that map to player_id values.
    Each token is valid for the duration of the server session unless
    explicitly refreshed.

    Attributes:
        _tokens: Dict mapping token -> player_id
        _reverse_index: Dict mapping player_id -> token for O(1) refresh
        _created_at: Dict mapping token -> creation timestamp
    """

    def __init__(self) -> None:
        """Initialize an empty TokenManager."""
        self._tokens: dict[str, str] = {}
        self._reverse_index: dict[str, str] = {}
        self._created_at: dict[str, datetime] = {}

    def generate_token(self, player_id: str) -> str:
        """
        Generate a new session token for a player.

        If a token already exists for this player_id, it is invalidated
        and a new one is created.

        Args:
            player_id: Unique identifier for the player (character_id or "OBSERVER")

        Returns:
            An 8-character URL-safe token string
        """
        # Invalidate existing token if present
        if player_id in self._reverse_index:
            old_token = self._reverse_index[player_id]
            self._tokens.pop(old_token, None)
            self._created_at.pop(old_token, None)

        # Generate new token
        token = secrets.token_urlsafe(6)  # ~8 chars

        # Store mapping
        self._tokens[token] = player_id
        self._reverse_index[player_id] = token
        self._created_at[token] = datetime.now()

        logger.info(f"Generated token for player_id={player_id}")
        return token

    def validate_token(self, token: str) -> Optional[str]:
        """
        Validate a session token and return the associated player_id.

        Args:
            token: The token to validate

        Returns:
            The player_id if token is valid, None otherwise
        """
        player_id = self._tokens.get(token)
        if player_id:
            logger.debug(f"Token validated for player_id={player_id}")
        else:
            logger.warning(f"Invalid token presented: {token[:4]}...")
        return player_id

    def refresh_token(self, player_id: str) -> str:
        """
        Invalidate the old token for a player and generate a new one.

        This is useful when a player needs to be re-authenticated
        (e.g., security concern, session timeout).

        Args:
            player_id: The player to refresh the token for

        Returns:
            The new token
        """
        logger.info(f"Refreshing token for player_id={player_id}")
        return self.generate_token(player_id)

    def revoke_token(self, player_id: str) -> bool:
        """
        Revoke the token for a specific player.

        Args:
            player_id: The player whose token should be revoked

        Returns:
            True if a token was revoked, False if no token existed
        """
        if player_id not in self._reverse_index:
            return False

        token = self._reverse_index[player_id]
        del self._tokens[token]
        del self._reverse_index[player_id]
        del self._created_at[token]

        logger.info(f"Revoked token for player_id={player_id}")
        return True

    def get_all_tokens(self) -> dict[str, str]:
        """
        Get all active tokens.

        Returns:
            Dict mapping player_id -> token
        """
        return dict(self._reverse_index)

    def clear(self) -> None:
        """Clear all tokens."""
        count = len(self._tokens)
        self._tokens.clear()
        self._reverse_index.clear()
        self._created_at.clear()
        logger.info(f"Cleared {count} tokens")


class QRCodeGenerator:
    """
    Generates QR code PNGs for Party Mode tokens.

    QR codes encode the full URL (http://host:port/play?token=xxx) for
    easy mobile access. Players can scan the code to join the session.
    """

    @staticmethod
    def generate_qr_code(
        url: str,
        output_path: Optional[Path] = None
    ) -> bytes:
        """
        Generate a QR code PNG for the given URL.

        Args:
            url: The full URL to encode in the QR code
            output_path: Optional path to save the PNG file

        Returns:
            PNG image data as bytes
        """
        qr = qrcode.QRCode(
            version=1,  # Auto-size
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        # Save to file if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(output_path))
            logger.info(f"QR code saved to {output_path}")

        # Return PNG bytes
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    @staticmethod
    def generate_player_qr(
        player_id: str,
        token: str,
        host: str,
        port: int,
        campaign_dir: Path
    ) -> Path:
        """
        Generate a QR code for a specific player's session.

        The QR code is saved to {campaign_dir}/party/qr-{player_id}.png
        and encodes the URL: http://{host}:{port}/play?token={token}

        Args:
            player_id: The player's identifier
            token: The session token
            host: Server host IP address
            port: Server port
            campaign_dir: Campaign directory for saving QR codes

        Returns:
            Path to the generated QR code PNG
        """
        url = f"http://{host}:{port}/play?token={token}"
        output_path = campaign_dir / "party" / f"qr-{player_id}.png"

        QRCodeGenerator.generate_qr_code(url, output_path)
        return output_path


def detect_host_ip() -> str:
    """
    Detect the host's LAN IP address for QR code generation.

    Uses socket.gethostbyname(socket.gethostname()) to get the LAN IP.
    Falls back to 127.0.0.1 if detection fails.

    Returns:
        The host IP address as a string
    """
    try:
        hostname = socket.gethostname()
        host_ip = socket.gethostbyname(hostname)

        # Sanity check: if we got localhost, try to find a better IP
        if host_ip.startswith("127."):
            # Try alternative method using a dummy socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # Connect to a public DNS server (doesn't actually send data)
                s.connect(("8.8.8.8", 80))
                host_ip = s.getsockname()[0]
            finally:
                s.close()

        logger.info(f"Detected host IP: {host_ip}")
        return host_ip
    except Exception as e:
        logger.warning(f"Failed to detect host IP: {e}, falling back to 127.0.0.1")
        return "127.0.0.1"


__all__ = [
    "TokenManager",
    "QRCodeGenerator",
    "detect_host_ip",
]
