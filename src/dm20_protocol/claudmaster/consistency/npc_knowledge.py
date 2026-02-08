"""
NPC knowledge tracking for the consistency system.

This module provides the NPCKnowledgeTracker class, which manages what each
NPC knows about the game world. It tracks knowledge acquisition, interactions
with players, and enables knowledge propagation between NPCs.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .fact_database import FactDatabase
from .models import KnowledgeEntry, KnowledgeSource, PlayerInteraction

logger = logging.getLogger("dm20-protocol")


class NPCKnowledgeTracker:
    """
    Tracks what each NPC knows and their interactions with players.

    The NPCKnowledgeTracker maintains a mapping of NPC IDs to their known facts
    and interaction history. This enables realistic dialogue generation where
    NPCs only reference information they could plausibly know.

    Attributes:
        _fact_db: Reference to the fact database for resolving fact IDs
        _campaign_path: Path to the campaign directory
        _npc_knowledge: Mapping of NPC ID to list of knowledge entries
        _npc_interactions: Mapping of NPC ID to list of player interactions
    """

    def __init__(self, fact_database: FactDatabase, campaign_path: Path) -> None:
        """
        Initialize the NPC knowledge tracker.

        Args:
            fact_database: Reference to the fact database for resolving fact IDs
            campaign_path: Path to campaign directory where npc_knowledge.json is stored
        """
        self._fact_db = fact_database
        self._campaign_path = Path(campaign_path)
        self._npc_knowledge: dict[str, list[KnowledgeEntry]] = {}
        self._npc_interactions: dict[str, list[PlayerInteraction]] = {}

        # Ensure the campaign directory exists
        self._campaign_path.mkdir(parents=True, exist_ok=True)

        # Load existing knowledge
        self.load()

    @property
    def _knowledge_path(self) -> Path:
        """Path to the NPC knowledge JSON file."""
        return self._campaign_path / "npc_knowledge.json"

    def get_npc_knowledge(self, npc_id: str) -> list[KnowledgeEntry]:
        """
        Get all facts an NPC knows.

        Args:
            npc_id: The NPC's identifier

        Returns:
            List of knowledge entries for this NPC (empty if NPC has no knowledge)
        """
        return self._npc_knowledge.get(npc_id, [])

    def npc_knows_fact(self, npc_id: str, fact_id: str) -> bool:
        """
        Check if an NPC knows a specific fact.

        Args:
            npc_id: The NPC's identifier
            fact_id: The fact ID to check

        Returns:
            True if the NPC knows this fact, False otherwise
        """
        knowledge = self._npc_knowledge.get(npc_id, [])
        return any(entry.fact_id == fact_id for entry in knowledge)

    def add_knowledge(
        self,
        npc_id: str,
        fact_id: str,
        source: KnowledgeSource,
        session: int,
        confidence: float = 1.0,
        source_entity: str | None = None
    ) -> None:
        """
        Add knowledge to an NPC.

        If the NPC already knows this fact, the operation is skipped silently.

        Args:
            npc_id: The NPC's identifier
            fact_id: ID of the fact to add
            source: How the NPC acquired this knowledge
            session: Session number when knowledge was acquired
            confidence: Certainty level (0.0-1.0+), default 1.0
            source_entity: Who told them (for TOLD_BY_PLAYER/NPC sources)
        """
        # Skip if NPC already knows this fact
        if self.npc_knows_fact(npc_id, fact_id):
            logger.debug(f"NPC {npc_id} already knows fact {fact_id}, skipping")
            return

        # Create knowledge entry
        entry = KnowledgeEntry(
            fact_id=fact_id,
            source=source,
            acquired_session=session,
            acquired_timestamp=datetime.now(timezone.utc),
            confidence=confidence,
            source_entity=source_entity
        )

        # Add to NPC's knowledge
        if npc_id not in self._npc_knowledge:
            self._npc_knowledge[npc_id] = []

        self._npc_knowledge[npc_id].append(entry)

        logger.debug(
            f"Added knowledge to {npc_id}: fact {fact_id} via {source} "
            f"(session {session}, confidence {confidence})"
        )

    def reveal_to_npc(
        self,
        npc_id: str,
        fact_id: str,
        revealed_by: str,
        session: int
    ) -> None:
        """
        Record that information was revealed to an NPC by a player.

        This is a convenience wrapper around add_knowledge with
        source=TOLD_BY_PLAYER.

        Args:
            npc_id: The NPC's identifier
            fact_id: ID of the fact being revealed
            revealed_by: Player character name who revealed the information
            session: Session number when revelation occurred
        """
        self.add_knowledge(
            npc_id=npc_id,
            fact_id=fact_id,
            source=KnowledgeSource.TOLD_BY_PLAYER,
            session=session,
            confidence=1.0,
            source_entity=revealed_by
        )

    def propagate_knowledge(
        self,
        from_npc: str,
        to_npc: str,
        fact_ids: list[str],
        session: int
    ) -> None:
        """
        Transfer knowledge from one NPC to another.

        Only facts that from_npc actually knows will be propagated.
        Facts already known by to_npc are skipped.

        Args:
            from_npc: NPC ID who is sharing the knowledge
            to_npc: NPC ID who is receiving the knowledge
            fact_ids: List of fact IDs to propagate
            session: Session number when propagation occurred
        """
        from_knowledge = self.get_npc_knowledge(from_npc)
        known_fact_ids = {entry.fact_id for entry in from_knowledge}

        for fact_id in fact_ids:
            # Only propagate if from_npc actually knows this fact
            if fact_id not in known_fact_ids:
                logger.debug(
                    f"Skipping propagation of {fact_id} from {from_npc} to {to_npc}: "
                    f"{from_npc} doesn't know this fact"
                )
                continue

            # Add knowledge to receiving NPC
            self.add_knowledge(
                npc_id=to_npc,
                fact_id=fact_id,
                source=KnowledgeSource.TOLD_BY_NPC,
                session=session,
                confidence=1.0,
                source_entity=from_npc
            )

        logger.debug(f"Propagated knowledge from {from_npc} to {to_npc} (session {session})")

    def record_interaction(
        self,
        npc_id: str,
        interaction: PlayerInteraction
    ) -> None:
        """
        Record a player-NPC interaction.

        Args:
            npc_id: The NPC's identifier
            interaction: The interaction to record
        """
        if npc_id not in self._npc_interactions:
            self._npc_interactions[npc_id] = []

        self._npc_interactions[npc_id].append(interaction)

        logger.debug(
            f"Recorded {interaction.interaction_type} interaction with {npc_id} "
            f"(session {interaction.session_number})"
        )

    def get_interactions(
        self,
        npc_id: str,
        session: int | None = None
    ) -> list[PlayerInteraction]:
        """
        Get NPC's interaction history, optionally filtered by session.

        Args:
            npc_id: The NPC's identifier
            session: Optional session number to filter by

        Returns:
            List of interactions (empty if NPC has no interactions)
        """
        interactions = self._npc_interactions.get(npc_id, [])

        if session is not None:
            interactions = [i for i in interactions if i.session_number == session]

        return interactions

    def query_npcs_who_know(self, fact_id: str) -> list[str]:
        """
        Find all NPC IDs who know a specific fact.

        Args:
            fact_id: The fact ID to search for

        Returns:
            List of NPC IDs who know this fact
        """
        npcs = []
        for npc_id, knowledge in self._npc_knowledge.items():
            if any(entry.fact_id == fact_id for entry in knowledge):
                npcs.append(npc_id)

        return npcs

    def get_knowledge_context(self, npc_id: str) -> dict:
        """
        Get full knowledge context for dialogue generation.

        Resolves fact IDs to full Fact objects from the fact database
        to provide complete context for NPC dialogue.

        Args:
            npc_id: The NPC's identifier

        Returns:
            Dictionary containing:
                - known_facts: List of Fact objects (resolved from fact_database)
                - knowledge_entries: List of KnowledgeEntry objects
                - interactions: List of PlayerInteraction objects
                - fact_count: Number of facts known
                - interaction_count: Number of interactions recorded
        """
        knowledge_entries = self.get_npc_knowledge(npc_id)
        interactions = self.get_interactions(npc_id)

        # Resolve fact IDs to full Fact objects
        known_facts = []
        for entry in knowledge_entries:
            fact = self._fact_db.get_fact(entry.fact_id)
            if fact:
                known_facts.append(fact)
            else:
                logger.warning(
                    f"Fact {entry.fact_id} known by {npc_id} not found in fact database"
                )

        return {
            "known_facts": known_facts,
            "knowledge_entries": knowledge_entries,
            "interactions": interactions,
            "fact_count": len(knowledge_entries),
            "interaction_count": len(interactions)
        }

    def save(self) -> None:
        """
        Persist NPC knowledge to npc_knowledge.json.

        Saves both knowledge entries and interaction history with metadata
        about the last update time.
        """
        # Convert to serializable format
        npc_data = {}
        for npc_id in set(self._npc_knowledge.keys()) | set(self._npc_interactions.keys()):
            npc_data[npc_id] = {
                "known_facts": [
                    entry.model_dump(mode="json")
                    for entry in self._npc_knowledge.get(npc_id, [])
                ],
                "interactions": [
                    interaction.model_dump(mode="json")
                    for interaction in self._npc_interactions.get(npc_id, [])
                ]
            }

        data = {
            "version": "1.0",
            "npc_knowledge": npc_data,
            "metadata": {
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
        }

        with open(self._knowledge_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(
            f"Saved knowledge for {len(npc_data)} NPCs to {self._knowledge_path}"
        )

    def load(self) -> None:
        """
        Load NPC knowledge from npc_knowledge.json.

        Handles missing files gracefully by initializing empty structures.
        If the file is corrupt or invalid, logs an error and starts with
        empty knowledge.
        """
        if not self._knowledge_path.exists():
            logger.debug(
                f"No existing NPC knowledge at {self._knowledge_path}, starting empty"
            )
            self._npc_knowledge = {}
            self._npc_interactions = {}
            return

        try:
            with open(self._knowledge_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate structure
            if not isinstance(data, dict) or "npc_knowledge" not in data:
                raise ValueError("Invalid knowledge database structure")

            # Load NPC knowledge
            self._npc_knowledge = {}
            self._npc_interactions = {}

            for npc_id, npc_data in data["npc_knowledge"].items():
                # Load knowledge entries
                if "known_facts" in npc_data:
                    self._npc_knowledge[npc_id] = [
                        KnowledgeEntry(**entry_data)
                        for entry_data in npc_data["known_facts"]
                    ]

                # Load interactions
                if "interactions" in npc_data:
                    self._npc_interactions[npc_id] = [
                        PlayerInteraction(**interaction_data)
                        for interaction_data in npc_data["interactions"]
                    ]

            logger.info(
                f"Loaded knowledge for {len(data['npc_knowledge'])} NPCs "
                f"from {self._knowledge_path}"
            )

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(
                f"Failed to load NPC knowledge from {self._knowledge_path}: {e}"
            )
            logger.warning("Starting with empty NPC knowledge")
            self._npc_knowledge = {}
            self._npc_interactions = {}


__all__ = [
    "NPCKnowledgeTracker",
]
