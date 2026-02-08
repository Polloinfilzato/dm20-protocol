"""
Split Party Handling system for the Claudmaster multi-agent framework.

This module provides split party management for multi-player sessions,
allowing the GM to handle situations where the party divides into separate
groups exploring different locations simultaneously. It manages group creation,
time tracking per group, scene switching, and eventual reunification.

Key components:
- PartyGroup: Represents a subset of the party in a specific location
- SplitEvent/ReunificationEvent: Track party split/merge history
- SplitPartyManager: Main engine for split party management
"""

from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field
from shortuuid import random as shortuuid_random

from .pc_tracking import PCRegistry, MultiPlayerConfig
from .turn_manager import TurnManager, TurnPhase


class PartyGroup(BaseModel):
    """Represents a group of PCs operating together in a specific location."""

    group_id: str = Field(description="Unique identifier for this group")
    member_ids: set[str] = Field(
        default_factory=set,
        description="Set of character IDs in this group"
    )
    location: str = Field(description="Current location of the group")
    scene_description: Optional[str] = Field(
        default=None,
        description="Current scene description for this group"
    )
    is_active: bool = Field(
        default=True,
        description="Whether this group is currently active"
    )
    time_elapsed: timedelta = Field(
        default_factory=lambda: timedelta(seconds=0),
        description="Time elapsed for this group relative to session start"
    )
    pending_events: list[str] = Field(
        default_factory=list,
        description="Events that affect this group but haven't been narrated yet"
    )


class SplitEvent(BaseModel):
    """Record of a party split event."""

    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When the split occurred"
    )
    groups_created: list[str] = Field(
        description="Group IDs created by this split"
    )
    trigger: str = Field(description="What caused the split")
    departing_pcs: set[str] = Field(
        description="Character IDs of PCs who left the main group"
    )
    destination: str = Field(
        description="Where the departing PCs went"
    )


class ReunificationEvent(BaseModel):
    """Record of groups merging back together."""

    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When the reunification occurred"
    )
    groups_merged: list[str] = Field(
        description="Group IDs that were merged"
    )
    location: str = Field(
        description="Where the groups reunited"
    )
    trigger: str = Field(
        default="voluntary",
        description="What caused the reunification"
    )
    time_adjustment: timedelta = Field(
        default_factory=lambda: timedelta(seconds=0),
        description="Time differential that was synced"
    )
    shared_discoveries: list[str] = Field(
        default_factory=list,
        description="Information shared when groups reunited"
    )


class MessageResult(BaseModel):
    """Result of an attempted message between PCs."""

    success: bool = Field(description="Whether the message was delivered")
    delay: timedelta = Field(
        default_factory=lambda: timedelta(seconds=0),
        description="Delay before message reaches recipient"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Explanation for the result (especially if failed)"
    )


class SplitProposal(BaseModel):
    """Proposal for a party split."""

    departing_pcs: set[str] = Field(
        description="Character IDs planning to depart"
    )
    destination: str = Field(
        description="Where the departing PCs want to go"
    )
    reason: str = Field(
        description="Why this split is happening"
    )


class SplitPartyManager:
    """
    Main split party management engine for multi-player sessions.

    Handles party splitting into separate groups, time tracking per group,
    scene switching between groups, cross-group messaging, and eventual
    reunification. Designed to work with PCRegistry and TurnManager.
    """

    def __init__(self, pc_registry: PCRegistry, turn_manager: TurnManager):
        """
        Initialize the split party manager.

        Args:
            pc_registry: PC registry for tracking characters
            turn_manager: Turn manager for coordinating turns across groups
        """
        self.pc_registry = pc_registry
        self.turn_manager = turn_manager
        self.groups: dict[str, PartyGroup] = {}
        self.active_group_id: Optional[str] = None
        self.split_history: list[SplitEvent] = []
        self.reunification_history: list[ReunificationEvent] = []
        self._base_time: datetime = datetime.now()

    def is_party_split(self) -> bool:
        """
        Check if the party is currently split into multiple groups.

        Returns:
            True if more than one group exists, False otherwise
        """
        return len(self.groups) > 1

    def get_group_for_pc(self, pc_id: str) -> Optional[PartyGroup]:
        """
        Find which group a PC belongs to.

        Args:
            pc_id: Character ID to look up

        Returns:
            The PartyGroup containing this PC, or None if not in any group
        """
        for group in self.groups.values():
            if pc_id in group.member_ids:
                return group
        return None

    def execute_split(
        self,
        departing_pcs: set[str],
        destination: str,
        remaining_location: str = "current"
    ) -> PartyGroup:
        """
        Split PCs into a new group.

        Creates a new group from departing PCs. If no groups exist yet,
        also creates a "remaining" group from non-departing PCs.

        Args:
            departing_pcs: Set of character IDs departing
            destination: Where the departing PCs are going
            remaining_location: Location label for remaining PCs

        Returns:
            The newly created departing group

        Raises:
            ValueError: If departing_pcs contains invalid character IDs
        """
        # Validate all departing PCs are registered
        all_pc_ids = {pc.character_id for pc in self.pc_registry.get_all_pcs()}
        invalid_pcs = departing_pcs - all_pc_ids
        if invalid_pcs:
            raise ValueError(f"Invalid character IDs: {invalid_pcs}")

        # If no groups exist yet, create a "remaining" group first
        if not self.groups:
            remaining_pcs = all_pc_ids - departing_pcs
            if remaining_pcs:
                remaining_group_id = shortuuid_random()
                remaining_group = PartyGroup(
                    group_id=remaining_group_id,
                    member_ids=remaining_pcs,
                    location=remaining_location,
                    is_active=True,
                    time_elapsed=timedelta(seconds=0)
                )
                self.groups[remaining_group_id] = remaining_group
                # Set as active initially
                self.active_group_id = remaining_group_id

        # Create new departing group
        departing_group_id = shortuuid_random()
        departing_group = PartyGroup(
            group_id=departing_group_id,
            member_ids=departing_pcs,
            location=destination,
            is_active=True,
            time_elapsed=timedelta(seconds=0)
        )
        self.groups[departing_group_id] = departing_group

        # Remove departing PCs from any existing groups
        for group in list(self.groups.values()):
            if group.group_id != departing_group_id:
                group.member_ids -= departing_pcs
                # Clean up empty groups
                if not group.member_ids:
                    del self.groups[group.group_id]
                    if self.active_group_id == group.group_id:
                        self.active_group_id = None

        # Record the split event
        groups_created = [departing_group_id]
        if len(self.groups) == 2:  # First split, both groups are "new"
            groups_created = list(self.groups.keys())

        split_event = SplitEvent(
            timestamp=datetime.now(),
            groups_created=groups_created,
            trigger=f"Group split: {len(departing_pcs)} PCs to {destination}",
            departing_pcs=departing_pcs,
            destination=destination
        )
        self.split_history.append(split_event)

        return departing_group

    def switch_to_group(self, group_id: str) -> PartyGroup:
        """
        Switch the active focus to a different group.

        Args:
            group_id: ID of the group to switch to

        Returns:
            The newly active group

        Raises:
            KeyError: If group_id doesn't exist
        """
        if group_id not in self.groups:
            raise KeyError(f"Group {group_id} does not exist")

        self.active_group_id = group_id
        return self.groups[group_id]

    def get_switch_narration(self, from_group: str, to_group: str) -> str:
        """
        Generate transition narration for switching between groups.

        Args:
            from_group: Group ID we're switching from
            to_group: Group ID we're switching to

        Returns:
            Transition text suitable for narration

        Raises:
            KeyError: If either group doesn't exist
        """
        if from_group not in self.groups:
            raise KeyError(f"Group {from_group} does not exist")
        if to_group not in self.groups:
            raise KeyError(f"Group {to_group} does not exist")

        to_location = self.groups[to_group].location
        from_location = self.groups[from_group].location

        # Generate varied transition text
        transitions = [
            f"Meanwhile, at {to_location}...",
            f"Cutting to the group at {to_location}...",
            f"We shift our focus to {to_location}, where...",
            f"Back at {to_location}...",
            f"At the same time, in {to_location}..."
        ]

        # Pick based on hash of group IDs for consistency
        index = hash((from_group, to_group)) % len(transitions)
        return transitions[index]

    def advance_group_time(self, group_id: str, duration: timedelta) -> None:
        """
        Advance the elapsed time for a specific group.

        Args:
            group_id: Group whose time to advance
            duration: Amount of time to add

        Raises:
            KeyError: If group_id doesn't exist
        """
        if group_id not in self.groups:
            raise KeyError(f"Group {group_id} does not exist")

        self.groups[group_id].time_elapsed += duration

    def sync_all_groups(self) -> timedelta:
        """
        Sync all groups to the same time (the maximum time elapsed).

        Useful when you want to "fast forward" slower groups to catch up.

        Returns:
            The maximum time_elapsed value that all groups were synced to

        Raises:
            ValueError: If no groups exist
        """
        if not self.groups:
            raise ValueError("No groups to sync")

        max_time = max(group.time_elapsed for group in self.groups.values())

        for group in self.groups.values():
            group.time_elapsed = max_time

        return max_time

    def get_time_differential(self, group_a: str, group_b: str) -> timedelta:
        """
        Get the time difference between two groups.

        Args:
            group_a: First group ID
            group_b: Second group ID

        Returns:
            Absolute time difference between the groups

        Raises:
            KeyError: If either group doesn't exist
        """
        if group_a not in self.groups:
            raise KeyError(f"Group {group_a} does not exist")
        if group_b not in self.groups:
            raise KeyError(f"Group {group_b} does not exist")

        time_a = self.groups[group_a].time_elapsed
        time_b = self.groups[group_b].time_elapsed

        return abs(time_a - time_b)

    def execute_reunification(
        self,
        groups_to_merge: list[str],
        location: str,
        trigger: str = "voluntary"
    ) -> PartyGroup:
        """
        Merge multiple groups back together.

        Combines member_ids, syncs time to the maximum, merges pending_events,
        and creates a new unified group.

        Args:
            groups_to_merge: List of group IDs to merge
            location: Where the groups are reuniting
            trigger: What caused the reunification

        Returns:
            The newly created unified group

        Raises:
            ValueError: If fewer than 2 groups specified or if any group doesn't exist
        """
        if len(groups_to_merge) < 2:
            raise ValueError("Must specify at least 2 groups to merge")

        # Validate all groups exist
        for group_id in groups_to_merge:
            if group_id not in self.groups:
                raise ValueError(f"Group {group_id} does not exist")

        # Collect all members and pending events
        all_members: set[str] = set()
        all_events: list[str] = []
        max_time = timedelta(seconds=0)

        for group_id in groups_to_merge:
            group = self.groups[group_id]
            all_members.update(group.member_ids)
            all_events.extend(group.pending_events)
            max_time = max(max_time, group.time_elapsed)

        # Create unified group
        unified_group_id = shortuuid_random()
        unified_group = PartyGroup(
            group_id=unified_group_id,
            member_ids=all_members,
            location=location,
            is_active=True,
            time_elapsed=max_time,
            pending_events=all_events
        )
        self.groups[unified_group_id] = unified_group

        # Remove merged groups
        for group_id in groups_to_merge:
            del self.groups[group_id]

        # Update active group if needed
        if self.active_group_id in groups_to_merge:
            self.active_group_id = unified_group_id

        # Record reunification
        reunification_event = ReunificationEvent(
            timestamp=datetime.now(),
            groups_merged=groups_to_merge,
            location=location,
            trigger=trigger,
            time_adjustment=max_time,
            shared_discoveries=[]  # Could be populated by caller
        )
        self.reunification_history.append(reunification_event)

        return unified_group

    def generate_catchup_summary(self, reunification: ReunificationEvent) -> str:
        """
        Generate a summary of what each group experienced during the split.

        Args:
            reunification: The reunification event to summarize

        Returns:
            A narrative summary suitable for the GM to present
        """
        summary_parts = [
            f"The groups reunite at {reunification.location}.",
            f"Trigger: {reunification.trigger}",
        ]

        if reunification.time_adjustment.total_seconds() > 0:
            minutes = int(reunification.time_adjustment.total_seconds() / 60)
            summary_parts.append(
                f"Time differential of {minutes} minutes was synced."
            )

        if reunification.shared_discoveries:
            summary_parts.append("Shared discoveries:")
            for discovery in reunification.shared_discoveries:
                summary_parts.append(f"  - {discovery}")

        return "\n".join(summary_parts)

    def send_message(
        self,
        from_pc: str,
        to_pc: str,
        message: str
    ) -> MessageResult:
        """
        Attempt to send a message from one PC to another.

        Same-group messages are instant. Cross-group messages may have delays
        or fail depending on circumstances.

        Args:
            from_pc: Character ID sending the message
            to_pc: Character ID receiving the message
            message: Message content

        Returns:
            Result indicating success, delay, and reason

        Raises:
            ValueError: If either PC is not in any group
        """
        from_group = self.get_group_for_pc(from_pc)
        to_group = self.get_group_for_pc(to_pc)

        if from_group is None:
            raise ValueError(f"PC {from_pc} is not in any group")
        if to_group is None:
            raise ValueError(f"PC {to_pc} is not in any group")

        # Same group: instant success
        if from_group.group_id == to_group.group_id:
            return MessageResult(
                success=True,
                delay=timedelta(seconds=0),
                reason="Same group - instant delivery"
            )

        # Cross-group: assume success with delay
        # In a real system, this might check for magical communication,
        # distance, etc.
        delay = timedelta(minutes=5)  # Default 5 minute delay
        return MessageResult(
            success=True,
            delay=delay,
            reason=f"Cross-group message - {int(delay.total_seconds() / 60)} minute delay"
        )

    def broadcast_event(
        self,
        event: str,
        affected_groups: Optional[list[str]] = None
    ) -> None:
        """
        Broadcast an event to multiple groups' pending_events.

        Args:
            event: Event description to add
            affected_groups: If provided, only add to these groups.
                           If None, add to all groups.

        Raises:
            ValueError: If any specified group doesn't exist
        """
        target_groups = affected_groups if affected_groups else list(self.groups.keys())

        for group_id in target_groups:
            if group_id not in self.groups:
                raise ValueError(f"Group {group_id} does not exist")
            self.groups[group_id].pending_events.append(event)

    def get_active_groups(self) -> list[PartyGroup]:
        """
        Get all active groups.

        Returns:
            List of all active PartyGroup objects
        """
        return [group for group in self.groups.values() if group.is_active]

    def get_group(self, group_id: str) -> Optional[PartyGroup]:
        """
        Lookup a group by ID.

        Args:
            group_id: Group ID to look up

        Returns:
            The PartyGroup if found, None otherwise
        """
        return self.groups.get(group_id)


__all__ = [
    "PartyGroup",
    "SplitEvent",
    "ReunificationEvent",
    "MessageResult",
    "SplitProposal",
    "SplitPartyManager",
]
