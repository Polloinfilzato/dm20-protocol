"""
Output filtering system for multi-user MCP sessions.

Filters tool responses based on the caller's role and character identity,
ensuring that DM-only content is stripped from player-visible responses.
Integrates with the PermissionResolver (role checks), DiscoveryTracker
(location visibility), and PrivateInfoManager (per-player info filtering).

Key components:
- OutputFilter: Main class that wraps tool responses and strips restricted content
- SessionParticipant: Tracks a connected participant's metadata
- SessionCoordinator: Manages session participants, turns, and private messaging
- FilterResult: Container for a filtered response with optional private addenda
"""

import logging
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from .permissions import PermissionResolver, PlayerRole
from .models import NPC, Location

logger = logging.getLogger("dm20-protocol")


# ---------------------------------------------------------------------------
# NPC fields visible to each role
# ---------------------------------------------------------------------------

# Fields that PLAYER and OBSERVER roles can see on an NPC
_NPC_PUBLIC_FIELDS: set[str] = {
    "id",
    "name",
    "description",
    "race",
    "occupation",
    "attitude",
    "location",
}

# Fields that only the DM can see (stripped for non-DM callers)
_NPC_DM_ONLY_FIELDS: set[str] = {
    "bio",
    "notes",
    "stats",
    "relationships",
}


class FilterResult(BaseModel):
    """Container for a filtered tool response.

    Attributes:
        content: The filtered response content (string or dict).
        private_addenda: Optional per-player private content, keyed by player_id.
        was_filtered: Whether any content was actually removed/modified.
    """
    content: str = ""
    private_addenda: dict[str, str] = Field(default_factory=dict)
    was_filtered: bool = False


class SessionParticipant(BaseModel):
    """Tracks a connected session participant.

    Attributes:
        player_id: Unique identifier for the participant.
        role: The participant's role (DM, PLAYER, OBSERVER).
        character_id: The character this participant controls (None for DM/OBSERVER).
        connected_at: Timestamp when the participant connected.
        last_active: Timestamp of the participant's last action.
        is_connected: Whether the participant is currently connected.
    """
    player_id: str
    role: PlayerRole = PlayerRole.PLAYER
    character_id: Optional[str] = None
    connected_at: datetime = Field(default_factory=datetime.now)
    last_active: datetime = Field(default_factory=datetime.now)
    is_connected: bool = True


class SessionCoordinator:
    """Manages session participants, turn tracking, and private messaging.

    The SessionCoordinator sits alongside the OutputFilter and provides:
    - Participant tracking (join, leave, heartbeat)
    - Turn-based notification context (whose turn it is)
    - DM private messaging to individual players

    Attributes:
        _participants: Maps player_id -> SessionParticipant
        _current_turn_player: The player_id whose turn it currently is (if any)
        _turn_active: Whether structured turn-based play is active
        _private_messages: List of (sender_id, recipient_id, content, timestamp)
    """

    def __init__(self) -> None:
        """Initialize an empty SessionCoordinator."""
        self._participants: dict[str, SessionParticipant] = {}
        self._current_turn_player: Optional[str] = None
        self._turn_active: bool = False
        self._private_messages: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Participant Management
    # ------------------------------------------------------------------

    def join_session(
        self,
        player_id: str,
        role: PlayerRole = PlayerRole.PLAYER,
        character_id: Optional[str] = None,
    ) -> SessionParticipant:
        """Register a participant joining the session.

        If the participant was previously connected and disconnected, their
        entry is updated rather than duplicated.

        Args:
            player_id: Unique participant identifier.
            role: The role of this participant.
            character_id: The character they control (None for DM/OBSERVER).

        Returns:
            The SessionParticipant record.
        """
        now = datetime.now()

        if player_id in self._participants:
            # Re-joining: update existing record
            participant = self._participants[player_id]
            participant.is_connected = True
            participant.last_active = now
            participant.role = role
            if character_id is not None:
                participant.character_id = character_id
            logger.info(f"Participant rejoined session: {player_id} ({role.value})")
        else:
            participant = SessionParticipant(
                player_id=player_id,
                role=role,
                character_id=character_id,
                connected_at=now,
                last_active=now,
            )
            self._participants[player_id] = participant
            logger.info(f"Participant joined session: {player_id} ({role.value})")

        return participant

    def leave_session(self, player_id: str) -> bool:
        """Mark a participant as disconnected.

        Does not remove the participant record; they can rejoin later.

        Args:
            player_id: The participant to disconnect.

        Returns:
            True if the participant was found and disconnected, False otherwise.
        """
        if player_id not in self._participants:
            return False

        self._participants[player_id].is_connected = False
        logger.info(f"Participant left session: {player_id}")
        return True

    def heartbeat(self, player_id: str) -> bool:
        """Update a participant's last_active timestamp.

        Args:
            player_id: The participant sending the heartbeat.

        Returns:
            True if the participant was found and updated, False otherwise.
        """
        if player_id not in self._participants:
            return False

        participant = self._participants[player_id]
        if not participant.is_connected:
            return False

        participant.last_active = datetime.now()
        return True

    def get_participant(self, player_id: str) -> Optional[SessionParticipant]:
        """Get a participant's record.

        Args:
            player_id: The participant to look up.

        Returns:
            The SessionParticipant, or None if not found.
        """
        return self._participants.get(player_id)

    def get_connected_participants(self) -> list[SessionParticipant]:
        """Get all currently connected participants.

        Returns:
            List of connected SessionParticipant objects.
        """
        return [p for p in self._participants.values() if p.is_connected]

    def get_connected_players(self) -> list[SessionParticipant]:
        """Get all currently connected participants with PLAYER role.

        Returns:
            List of connected PLAYER SessionParticipant objects.
        """
        return [
            p for p in self._participants.values()
            if p.is_connected and p.role == PlayerRole.PLAYER
        ]

    @property
    def participant_count(self) -> int:
        """Get the total number of participants (connected or not)."""
        return len(self._participants)

    @property
    def connected_count(self) -> int:
        """Get the number of currently connected participants."""
        return len(self.get_connected_participants())

    # ------------------------------------------------------------------
    # Turn Tracking
    # ------------------------------------------------------------------

    def set_current_turn(self, player_id: Optional[str]) -> None:
        """Set whose turn it currently is.

        Args:
            player_id: The player whose turn it is, or None to clear.
        """
        self._current_turn_player = player_id
        self._turn_active = player_id is not None
        if player_id:
            logger.debug(f"Turn set to: {player_id}")
        else:
            logger.debug("Turn cleared")

    def get_turn_context(self) -> Optional[str]:
        """Get a turn notification string for the current active turn.

        Returns:
            A formatted turn notification string, or None if no active turn.
        """
        if not self._turn_active or not self._current_turn_player:
            return None

        participant = self._participants.get(self._current_turn_player)
        if not participant:
            return f"It's {self._current_turn_player}'s turn."

        char_name = participant.character_id or participant.player_id
        return f"It's {char_name}'s turn."

    @property
    def current_turn_player(self) -> Optional[str]:
        """Get the player_id of the current turn holder."""
        return self._current_turn_player

    @property
    def is_turn_active(self) -> bool:
        """Whether structured turn-based play is currently active."""
        return self._turn_active

    # ------------------------------------------------------------------
    # Private Messaging
    # ------------------------------------------------------------------

    def send_private_message(
        self,
        sender_id: str,
        recipient_id: str,
        content: str,
    ) -> dict[str, Any]:
        """Send a private message from one participant to another.

        Typically used by the DM to send information to individual players.

        Args:
            sender_id: The sender's player_id.
            recipient_id: The recipient's player_id.
            content: The message content.

        Returns:
            The message record dict.

        Raises:
            ValueError: If the recipient is not a known participant.
        """
        if recipient_id not in self._participants:
            raise ValueError(f"Recipient '{recipient_id}' is not a session participant.")

        message = {
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        self._private_messages.append(message)
        logger.debug(f"Private message: {sender_id} -> {recipient_id}")
        return message

    def get_pending_messages(self, player_id: str) -> list[dict[str, Any]]:
        """Get all private messages for a player.

        Args:
            player_id: The player to get messages for.

        Returns:
            List of message dicts addressed to this player.
        """
        return [
            m for m in self._private_messages
            if m["recipient_id"] == player_id
        ]


class OutputFilter:
    """Filters MCP tool responses based on caller role and identity.

    The OutputFilter is the main integration point that ties together:
    - PermissionResolver: For determining the caller's role
    - DiscoveryTracker: For filtering location content by discovery state
    - PrivateInfoManager: For per-player private information

    In single-player (DM) mode (player_id=None), all filtering is bypassed
    for zero overhead, matching the PermissionResolver's design.

    Usage:
        filter = OutputFilter(permission_resolver)
        result = filter.filter_npc_response(npc, player_id="alice")
        # result.content has bio/notes stripped for PLAYER role
    """

    def __init__(
        self,
        permission_resolver: PermissionResolver,
        session_coordinator: Optional[SessionCoordinator] = None,
    ) -> None:
        """Initialize the OutputFilter.

        Args:
            permission_resolver: The resolver for looking up player roles.
            session_coordinator: Optional session coordinator for turn context.
        """
        self._resolver = permission_resolver
        self._coordinator = session_coordinator or SessionCoordinator()

    @property
    def session(self) -> SessionCoordinator:
        """Access the session coordinator."""
        return self._coordinator

    # ------------------------------------------------------------------
    # Core filtering
    # ------------------------------------------------------------------

    def filter_response(
        self,
        raw_response: str,
        player_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> FilterResult:
        """Generic response filter that adds turn context for players.

        For most tools, the raw response is returned unchanged. Turn context
        is prepended when structured play is active and the caller is the
        current turn holder.

        Args:
            raw_response: The unfiltered tool response string.
            player_id: The calling player's ID (None = DM/single-player).
            tool_name: The tool that produced this response.

        Returns:
            FilterResult with potentially augmented content.
        """
        # Single-player bypass
        if player_id is None:
            return FilterResult(content=raw_response, was_filtered=False)

        # Update heartbeat for the participant
        self._coordinator.heartbeat(player_id)

        content = raw_response
        was_filtered = False

        # Prepend turn context if this player is the current turn holder
        turn_ctx = self._coordinator.get_turn_context()
        if turn_ctx and self._coordinator.current_turn_player == player_id:
            content = f"*{turn_ctx}*\n\n{content}"
            was_filtered = True

        return FilterResult(content=content, was_filtered=was_filtered)

    def filter_npc_response(
        self,
        npc: NPC,
        player_id: Optional[str] = None,
    ) -> FilterResult:
        """Filter an NPC's information based on the caller's role.

        DM sees everything. PLAYER and OBSERVER see only public fields
        (name, description, race, occupation, attitude, location).
        Bio, notes, stats, and relationships are stripped.

        Args:
            npc: The full NPC model.
            player_id: The calling player's ID (None = DM/single-player).

        Returns:
            FilterResult with filtered NPC information.
        """
        # Single-player / DM bypass
        if player_id is None:
            return FilterResult(
                content=_format_npc_full(npc),
                was_filtered=False,
            )

        role = self._resolver.get_player_role(player_id)
        if role == PlayerRole.DM:
            return FilterResult(
                content=_format_npc_full(npc),
                was_filtered=False,
            )

        # PLAYER / OBSERVER: strip DM-only fields
        return FilterResult(
            content=_format_npc_public(npc),
            was_filtered=True,
        )

    def filter_location_response(
        self,
        location: Location,
        player_id: Optional[str] = None,
        discovery_tracker: Any = None,
    ) -> FilterResult:
        """Filter a location's information based on role and discovery state.

        Combines two filtering layers:
        1. Discovery filter: Only shows features the party has discovered
        2. Permission filter: Strips DM-only notes for non-DM callers

        Args:
            location: The full Location model.
            player_id: The calling player's ID (None = DM/single-player).
            discovery_tracker: Optional DiscoveryTracker for feature filtering.

        Returns:
            FilterResult with filtered location information.
        """
        # Single-player / DM bypass
        if player_id is None:
            return FilterResult(
                content=_format_location_full(location),
                was_filtered=False,
            )

        role = self._resolver.get_player_role(player_id)
        if role == PlayerRole.DM:
            return FilterResult(
                content=_format_location_full(location),
                was_filtered=False,
            )

        # For PLAYER / OBSERVER: apply discovery filter if available
        if discovery_tracker is not None:
            from .consistency.narrator_discovery import filter_location_by_discovery
            filtered = filter_location_by_discovery(location, discovery_tracker)
            return FilterResult(
                content=_format_location_filtered(filtered),
                was_filtered=True,
            )

        # No discovery tracker: show location without DM notes
        return FilterResult(
            content=_format_location_public(location),
            was_filtered=True,
        )

    def filter_game_state_response(
        self,
        raw_response: str,
        player_id: Optional[str] = None,
    ) -> FilterResult:
        """Filter game state response based on caller role.

        DM sees full state with notes. Players see state without DM notes.

        Args:
            raw_response: The raw game state response string.
            player_id: The calling player's ID (None = DM/single-player).

        Returns:
            FilterResult with the response.
        """
        if player_id is None:
            return FilterResult(content=raw_response, was_filtered=False)

        role = self._resolver.get_player_role(player_id)
        if role == PlayerRole.DM:
            return FilterResult(content=raw_response, was_filtered=False)

        # For PLAYER / OBSERVER: strip DM notes section
        filtered = _strip_dm_notes_section(raw_response)
        return FilterResult(
            content=filtered,
            was_filtered=filtered != raw_response,
        )

    def get_role(self, player_id: Optional[str]) -> PlayerRole:
        """Convenience method to get a player's role.

        Args:
            player_id: The player to look up (None returns DM).

        Returns:
            The player's role.
        """
        if player_id is None:
            return PlayerRole.DM
        return self._resolver.get_player_role(player_id)


# ---------------------------------------------------------------------------
# NPC formatting helpers
# ---------------------------------------------------------------------------

def _format_npc_full(npc: NPC) -> str:
    """Format full NPC info (all fields) for the DM."""
    stats_text = ""
    if npc.stats:
        stats_lines = [f"  - {k}: {v}" for k, v in npc.stats.items()]
        stats_text = "\n**Stats:**\n" + "\n".join(stats_lines)

    relationships_text = ""
    if npc.relationships:
        rel_lines = [f"  - {char_name}: {rel}" for char_name, rel in npc.relationships.items()]
        relationships_text = "\n**Relationships:**\n" + "\n".join(rel_lines)

    return f"""**{npc.name}** (`{npc.id}`)
**Race:** {npc.race or 'Unknown'}
**Occupation:** {npc.occupation or 'Unknown'}
**Location:** {npc.location or 'Unknown'}
**Attitude:** {npc.attitude or 'Neutral'}

**Description:** {npc.description or 'No description available.'}
**Bio:** {npc.bio or 'No bio available.'}
{stats_text}
{relationships_text}
**Notes:** {npc.notes or 'No additional notes.'}
"""


def _format_npc_public(npc: NPC) -> str:
    """Format public NPC info (no bio, notes, stats, relationships) for players."""
    return f"""**{npc.name}** (`{npc.id}`)
**Race:** {npc.race or 'Unknown'}
**Occupation:** {npc.occupation or 'Unknown'}
**Location:** {npc.location or 'Unknown'}
**Attitude:** {npc.attitude or 'Neutral'}

**Description:** {npc.description or 'No description available.'}
"""


# ---------------------------------------------------------------------------
# Location formatting helpers
# ---------------------------------------------------------------------------

def _format_location_full(location: Location) -> str:
    """Format full location info (all fields) for the DM."""
    features_text = (
        "\n".join(["- " + f for f in location.notable_features])
        if location.notable_features
        else "None listed"
    )

    return f"""**{location.name}** ({location.location_type})

**Description:** {location.description}

**Population:** {location.population or 'Unknown'}
**Government:** {location.government or 'Unknown'}

**Notable Features:**
{features_text}

**Notes:** {location.notes or 'No additional notes.'}
"""


def _format_location_public(location: Location) -> str:
    """Format location info without DM notes for players."""
    features_text = (
        "\n".join(["- " + f for f in location.notable_features])
        if location.notable_features
        else "None listed"
    )

    return f"""**{location.name}** ({location.location_type})

**Description:** {location.description}

**Population:** {location.population or 'Unknown'}
**Government:** {location.government or 'Unknown'}

**Notable Features:**
{features_text}
"""


def _format_location_filtered(filtered: dict) -> str:
    """Format a discovery-filtered location dict for players."""
    features = filtered.get("notable_features", [])
    features_text = "\n".join(["- " + f for f in features]) if features else "None listed"
    hidden_count = filtered.get("hidden_features_count", 0)
    hidden_note = (
        f"\n*({hidden_count} undiscovered feature(s) remain hidden)*"
        if hidden_count > 0
        else ""
    )
    discovery_level = filtered.get("discovery_level", "EXPLORED")

    return f"""**{filtered['name']}** ({filtered['location_type']})

**Discovery Level:** {discovery_level}

**Description:** {filtered['description']}

**Population:** {filtered.get('population') or 'Unknown'}
**Government:** {filtered.get('government') or 'Unknown'}

**Notable Features:**
{features_text}{hidden_note}
"""


def _strip_dm_notes_section(text: str) -> str:
    """Remove DM notes from a text block.

    Looks for lines containing '**Notes:**' or '**DM Notes:**' and strips
    that line and any following content until the next section header
    (any line starting with '**' that is a different field).

    Args:
        text: The raw response text.

    Returns:
        The text with DM notes sections removed.
    """
    lines = text.split("\n")
    result_lines: list[str] = []
    skip = False

    for line in lines:
        stripped = line.strip().lower()
        if stripped.startswith("**notes:**") or stripped.startswith("**dm notes:**"):
            skip = True
            continue
        # Stop skipping at the next section header (any bold-prefixed field)
        if skip and stripped.startswith("**") and ":**" in stripped:
            skip = False
        if not skip:
            result_lines.append(line)

    return "\n".join(result_lines)


__all__ = [
    "FilterResult",
    "SessionParticipant",
    "SessionCoordinator",
    "OutputFilter",
]
