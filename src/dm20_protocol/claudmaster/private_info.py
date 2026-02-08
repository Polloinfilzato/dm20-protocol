"""
Player-Specific Information Management system for the Claudmaster multi-agent framework.

This module handles private information, secret knowledge, hidden rolls, and
private messaging in multi-PC sessions. It ensures that information is only
revealed to appropriate players based on visibility rules.

Key components:
- InfoVisibility: Enum defining information visibility levels
- PrivateInfo: Represents a piece of information with visibility rules
- PrivateMessage: DM-to-player private messages
- HiddenRoll: Hidden dice rolls for passive checks
- SecretKnowledge: Character-specific secret knowledge
- PrivateInfoManager: Manages all private information flows
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from .pc_tracking import PCRegistry, PCState, MultiPlayerConfig


class InfoVisibility(str, Enum):
    """Defines the visibility level of information."""

    PUBLIC = "public"  # Everyone can see
    PARTY = "party"  # All active party members can see
    PRIVATE = "private"  # Only specific PC can see
    DM_ONLY = "dm_only"  # Only DM knows (not revealed to any PC)
    SUBSET = "subset"  # Visible to a subset of PCs


class PrivateInfo(BaseModel):
    """Represents a piece of information with visibility rules."""

    info_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier")
    content: str = Field(description="The actual information content")
    visibility: InfoVisibility = Field(description="Visibility level")
    visible_to: list[str] = Field(
        default_factory=list,
        description="PC IDs who can see this (if SUBSET or PRIVATE)"
    )
    source: str = Field(default="dm", description="Source of the information")
    learned_at: datetime = Field(
        default_factory=datetime.now,
        description="When this info was learned"
    )
    can_share: bool = Field(
        default=True,
        description="Whether PCs can share this info with others"
    )
    expires: Optional[datetime] = Field(
        default=None,
        description="When this info expires (if temporary)"
    )


class PrivateMessage(BaseModel):
    """Represents a private message from DM to one or more players."""

    message_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier")
    content: str = Field(description="Message content")
    recipients: list[str] = Field(description="PC IDs who should receive this message")
    message_type: str = Field(
        default="dm_note",
        description="Type of message (dm_note, roll_result, secret, etc.)"
    )
    timestamp: datetime = Field(default_factory=datetime.now, description="When sent")
    read_by: list[str] = Field(
        default_factory=list,
        description="PC IDs who have read this message"
    )


class HiddenRoll(BaseModel):
    """Represents a hidden dice roll for passive checks."""

    roll_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier")
    pc_id: str = Field(description="PC who made the roll")
    roll_type: str = Field(description="Type of roll (perception, insight, stealth, etc.)")
    result: int = Field(description="Roll result")
    dc: Optional[int] = Field(default=None, description="Difficulty class (if applicable)")
    success: Optional[bool] = Field(default=None, description="Whether roll succeeded")
    revealed_to: list[str] = Field(
        default_factory=list,
        description="PC IDs who know about this roll"
    )


class SecretKnowledge(BaseModel):
    """Represents character-specific secret knowledge."""

    knowledge_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique identifier")
    pc_id: str = Field(description="PC who has this knowledge")
    category: str = Field(
        default="background",
        description="Category (background, discovered, overheard)"
    )
    subject: str = Field(description="Subject of the secret")
    content: str = Field(description="The secret content")
    source: str = Field(description="Where/how this was learned")
    relevance_tags: list[str] = Field(
        default_factory=list,
        description="Keywords for relevance detection"
    )
    shared_with: list[str] = Field(
        default_factory=list,
        description="PC IDs this secret has been shared with"
    )


class PrivateInfoManager:
    """Manages private information, messages, rolls, and secrets for multi-PC sessions."""

    def __init__(self, pc_registry: PCRegistry):
        """
        Initialize the private info manager.

        Args:
            pc_registry: The PCRegistry to use for PC lookups
        """
        self.pc_registry = pc_registry
        self._info_store: dict[str, list[PrivateInfo]] = {}  # PC ID -> info list
        self._messages: list[PrivateMessage] = []
        self._hidden_rolls: list[HiddenRoll] = []
        self._secrets: dict[str, list[SecretKnowledge]] = {}  # PC ID -> secrets

    def add_private_info(
        self,
        pc_id: str,
        content: str,
        visibility: InfoVisibility = InfoVisibility.PRIVATE,
        source: str = "dm",
        visible_to: Optional[list[str]] = None,
        can_share: bool = True,
        expires: Optional[datetime] = None
    ) -> PrivateInfo:
        """
        Add a piece of private information.

        Args:
            pc_id: Primary PC this info is about/for
            content: The information content
            visibility: Visibility level
            source: Source of the information
            visible_to: List of PC IDs (for SUBSET visibility)
            can_share: Whether PCs can share this info
            expires: When this info expires

        Returns:
            The created PrivateInfo object

        Raises:
            KeyError: If pc_id not registered
        """
        # Validate PC exists
        self.pc_registry.get_pc_state(pc_id)

        # Set visible_to based on visibility
        if visible_to is None:
            visible_to = []
        if visibility == InfoVisibility.PRIVATE and not visible_to:
            visible_to = [pc_id]

        info = PrivateInfo(
            content=content,
            visibility=visibility,
            visible_to=visible_to,
            source=source,
            can_share=can_share,
            expires=expires
        )

        # Store info
        if pc_id not in self._info_store:
            self._info_store[pc_id] = []
        self._info_store[pc_id].append(info)

        return info

    def get_visible_info(self, pc_id: str) -> list[PrivateInfo]:
        """
        Get all information visible to a specific PC.

        Includes:
        - Info with visibility PRIVATE where pc_id in visible_to
        - Info with visibility PUBLIC
        - Info with visibility PARTY (all active PCs)
        - Info with visibility SUBSET where pc_id in visible_to

        Args:
            pc_id: The PC ID to get visible info for

        Returns:
            List of PrivateInfo objects visible to this PC

        Raises:
            KeyError: If pc_id not registered
        """
        # Validate PC exists
        pc_state = self.pc_registry.get_pc_state(pc_id)

        visible = []
        all_info = []

        # Collect all info from all PCs
        for info_list in self._info_store.values():
            all_info.extend(info_list)

        # Filter by visibility rules
        for info in all_info:
            # Skip expired info
            if info.expires and datetime.now() > info.expires:
                continue

            if info.visibility == InfoVisibility.PUBLIC:
                visible.append(info)
            elif info.visibility == InfoVisibility.PARTY and pc_state.is_active:
                visible.append(info)
            elif info.visibility == InfoVisibility.PRIVATE and pc_id in info.visible_to:
                visible.append(info)
            elif info.visibility == InfoVisibility.SUBSET and pc_id in info.visible_to:
                visible.append(info)
            # DM_ONLY is never visible to PCs

        return visible

    def share_info(self, from_pc: str, to_pc: str, info_id: str) -> bool:
        """
        Share a piece of information from one PC to another.

        Args:
            from_pc: PC ID sharing the info (must have access to it)
            to_pc: PC ID receiving the info
            info_id: ID of the info to share

        Returns:
            True if sharing succeeded, False if not allowed

        Raises:
            KeyError: If either PC not registered
            ValueError: If info_id not found or from_pc doesn't have access
        """
        # Validate both PCs exist
        self.pc_registry.get_pc_state(from_pc)
        self.pc_registry.get_pc_state(to_pc)

        # Find the info
        info = None
        for info_list in self._info_store.values():
            for i in info_list:
                if i.info_id == info_id:
                    info = i
                    break
            if info:
                break

        if not info:
            raise ValueError(f"Info {info_id} not found")

        # Check if from_pc has access
        visible_to_from = self.get_visible_info(from_pc)
        if info not in visible_to_from:
            raise ValueError(f"PC {from_pc} does not have access to info {info_id}")

        # Check if sharing is allowed
        if not info.can_share:
            return False

        # Add to_pc to visible_to if not already there
        if to_pc not in info.visible_to:
            info.visible_to.append(to_pc)

        return True

    def check_knowledge(self, pc_id: str, topic: str) -> Optional[PrivateInfo]:
        """
        Check if a PC has knowledge about a specific topic.

        Args:
            pc_id: PC ID to check
            topic: Topic keyword to search for

        Returns:
            First matching PrivateInfo, or None if no match

        Raises:
            KeyError: If pc_id not registered
        """
        # Validate PC exists
        self.pc_registry.get_pc_state(pc_id)

        visible = self.get_visible_info(pc_id)
        topic_lower = topic.lower()

        for info in visible:
            if topic_lower in info.content.lower():
                return info

        return None

    def send_private_message(
        self,
        content: str,
        recipients: list[str],
        message_type: str = "dm_note"
    ) -> PrivateMessage:
        """
        Send a private message to one or more PCs.

        Args:
            content: Message content
            recipients: List of PC IDs to receive the message
            message_type: Type of message

        Returns:
            The created PrivateMessage

        Raises:
            KeyError: If any recipient PC not registered
        """
        # Validate all recipients exist
        for pc_id in recipients:
            self.pc_registry.get_pc_state(pc_id)

        message = PrivateMessage(
            content=content,
            recipients=recipients,
            message_type=message_type
        )

        self._messages.append(message)
        return message

    def get_pending_messages(self, pc_id: str) -> list[PrivateMessage]:
        """
        Get all unread messages for a PC.

        Args:
            pc_id: PC ID to get messages for

        Returns:
            List of unread PrivateMessage objects

        Raises:
            KeyError: If pc_id not registered
        """
        # Validate PC exists
        self.pc_registry.get_pc_state(pc_id)

        pending = []
        for msg in self._messages:
            if pc_id in msg.recipients and pc_id not in msg.read_by:
                pending.append(msg)

        return pending

    def mark_message_read(self, message_id: str, pc_id: str) -> None:
        """
        Mark a message as read by a specific PC.

        Args:
            message_id: Message ID to mark as read
            pc_id: PC ID who read it

        Raises:
            ValueError: If message not found or PC not a recipient
            KeyError: If pc_id not registered
        """
        # Validate PC exists
        self.pc_registry.get_pc_state(pc_id)

        # Find message
        message = None
        for msg in self._messages:
            if msg.message_id == message_id:
                message = msg
                break

        if not message:
            raise ValueError(f"Message {message_id} not found")

        if pc_id not in message.recipients:
            raise ValueError(f"PC {pc_id} is not a recipient of message {message_id}")

        if pc_id not in message.read_by:
            message.read_by.append(pc_id)

    def format_dm_whisper(self, pc_id: str, content: str) -> str:
        """
        Format a DM whisper message for a specific player.

        Args:
            pc_id: PC ID to whisper to
            content: Whisper content

        Returns:
            Formatted whisper string

        Raises:
            KeyError: If pc_id not registered
        """
        pc_state = self.pc_registry.get_pc_state(pc_id)
        return f"[Private to {pc_state.player_name}]: {content}"

    def create_hidden_roll(
        self,
        pc_id: str,
        roll_type: str,
        result: int,
        dc: Optional[int] = None
    ) -> HiddenRoll:
        """
        Create a hidden dice roll for passive checks.

        Args:
            pc_id: PC who made the roll
            roll_type: Type of roll (perception, insight, etc.)
            result: Roll result
            dc: Difficulty class (if applicable)

        Returns:
            The created HiddenRoll

        Raises:
            KeyError: If pc_id not registered
        """
        # Validate PC exists
        self.pc_registry.get_pc_state(pc_id)

        success = None
        if dc is not None:
            success = result >= dc

        roll = HiddenRoll(
            pc_id=pc_id,
            roll_type=roll_type,
            result=result,
            dc=dc,
            success=success
        )

        self._hidden_rolls.append(roll)
        return roll

    def get_hidden_roll_message(self, roll: HiddenRoll) -> tuple[str, str]:
        """
        Generate messages for a hidden roll.

        Args:
            roll: The HiddenRoll object

        Returns:
            Tuple of (private_message, public_message)
            - private_message: What the PC sees
            - public_message: What everyone else sees
        """
        pc_state = self.pc_registry.get_pc_state(roll.pc_id)

        # Private message shows the result
        if roll.success is not None:
            result_text = "succeeded" if roll.success else "failed"
            private_msg = f"Your {roll.roll_type} check: {roll.result} (DC {roll.dc}) - {result_text}"
        else:
            private_msg = f"Your {roll.roll_type} check: {roll.result}"

        # Public message is generic
        public_msg = f"{pc_state.player_name} makes a {roll.roll_type} check."

        return (private_msg, public_msg)

    def reveal_roll(self, roll_id: str, reveal_to: list[str]) -> None:
        """
        Reveal a hidden roll to specific PCs.

        Args:
            roll_id: Roll ID to reveal
            reveal_to: List of PC IDs to reveal to

        Raises:
            ValueError: If roll not found
            KeyError: If any PC in reveal_to not registered
        """
        # Find roll
        roll = None
        for r in self._hidden_rolls:
            if r.roll_id == roll_id:
                roll = r
                break

        if not roll:
            raise ValueError(f"Roll {roll_id} not found")

        # Validate all PCs exist
        for pc_id in reveal_to:
            self.pc_registry.get_pc_state(pc_id)

        # Add to revealed_to
        for pc_id in reveal_to:
            if pc_id not in roll.revealed_to:
                roll.revealed_to.append(pc_id)

    def add_character_secret(
        self,
        pc_id: str,
        subject: str,
        content: str,
        source: str = "background",
        category: str = "background",
        relevance_tags: Optional[list[str]] = None
    ) -> SecretKnowledge:
        """
        Add secret knowledge to a character.

        Args:
            pc_id: PC who has this secret
            subject: Subject of the secret
            content: Secret content
            source: Where/how this was learned
            category: Category (background, discovered, overheard)
            relevance_tags: Keywords for relevance detection

        Returns:
            The created SecretKnowledge

        Raises:
            KeyError: If pc_id not registered
        """
        # Validate PC exists
        self.pc_registry.get_pc_state(pc_id)

        if relevance_tags is None:
            relevance_tags = []

        secret = SecretKnowledge(
            pc_id=pc_id,
            category=category,
            subject=subject,
            content=content,
            source=source,
            relevance_tags=relevance_tags
        )

        if pc_id not in self._secrets:
            self._secrets[pc_id] = []
        self._secrets[pc_id].append(secret)

        return secret

    def check_secret_relevance(self, context: str) -> list[SecretKnowledge]:
        """
        Check if any secrets are relevant to the current context.

        Args:
            context: Current context (scene description, dialogue, etc.)

        Returns:
            List of potentially relevant SecretKnowledge objects
        """
        relevant = []
        context_lower = context.lower()

        for secrets_list in self._secrets.values():
            for secret in secrets_list:
                # Check relevance tags
                for tag in secret.relevance_tags:
                    if tag.lower() in context_lower:
                        relevant.append(secret)
                        break  # Don't add same secret multiple times

        return relevant

    def prompt_secret_share(self, pc_id: str, knowledge_id: str) -> str:
        """
        Generate a prompt text asking if PC wants to share secret knowledge.

        Args:
            pc_id: PC who has the secret
            knowledge_id: Secret knowledge ID

        Returns:
            Prompt text for the player

        Raises:
            ValueError: If knowledge not found or doesn't belong to this PC
            KeyError: If pc_id not registered
        """
        # Validate PC exists
        pc_state = self.pc_registry.get_pc_state(pc_id)

        # Find secret
        secret = None
        if pc_id in self._secrets:
            for s in self._secrets[pc_id]:
                if s.knowledge_id == knowledge_id:
                    secret = s
                    break

        if not secret:
            raise ValueError(f"Secret {knowledge_id} not found for PC {pc_id}")

        prompt = (
            f"[Private to {pc_state.player_name}]: Your knowledge about "
            f"\"{secret.subject}\" might be relevant here. "
            f"Do you want to share what you know?"
        )

        return prompt

    def format_response_with_private(
        self,
        public_content: str,
        private_additions: dict[str, str]
    ) -> dict[str, str]:
        """
        Format a response with public and private components.

        Args:
            public_content: Content visible to everyone
            private_additions: Dict mapping PC ID to their private content

        Returns:
            Dict mapping PC ID to their full view (public + private)

        Raises:
            KeyError: If any PC in private_additions not registered
        """
        # Validate all PCs exist
        for pc_id in private_additions.keys():
            self.pc_registry.get_pc_state(pc_id)

        result = {}

        # Get all active PCs
        all_pcs = self.pc_registry.get_all_active()

        for pc_state in all_pcs:
            pc_id = pc_state.character_id

            # Start with public content
            full_content = public_content

            # Add private content if exists
            if pc_id in private_additions:
                private_msg = self.format_dm_whisper(pc_id, private_additions[pc_id])
                full_content = f"{full_content}\n\n{private_msg}"

            result[pc_id] = full_content

        return result

    def remove_expired_info(self) -> int:
        """
        Remove all expired information.

        Returns:
            Count of info pieces removed
        """
        removed_count = 0
        now = datetime.now()

        for pc_id in list(self._info_store.keys()):
            original_count = len(self._info_store[pc_id])
            self._info_store[pc_id] = [
                info for info in self._info_store[pc_id]
                if info.expires is None or info.expires > now
            ]
            removed_count += original_count - len(self._info_store[pc_id])

            # Clean up empty lists
            if not self._info_store[pc_id]:
                del self._info_store[pc_id]

        return removed_count


__all__ = [
    "InfoVisibility",
    "PrivateInfo",
    "PrivateMessage",
    "HiddenRoll",
    "SecretKnowledge",
    "PrivateInfoManager",
]
