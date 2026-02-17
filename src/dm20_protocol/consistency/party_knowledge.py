"""
Party knowledge tracking as a filtered view over the FactDatabase.

This module tracks what the adventuring party collectively knows about the
game world. Rather than duplicating data, it marks facts in the FactDatabase
with a 'party_known' tag and maintains additional metadata about how each
fact was learned.

Key components:
- AcquisitionMethod: Enum for how the party learned a fact
- KnowledgeRecord: Metadata about a party-known fact
- PartyKnowledge: Manager class that wraps FactDatabase
"""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("dm20-protocol")

# Tag used to mark facts as known by the party in FactDatabase
PARTY_KNOWN_TAG = "party_known"


class AcquisitionMethod(str, Enum):
    """How the party acquired a piece of knowledge."""
    TOLD_BY_NPC = "told_by_npc"
    OBSERVED = "observed"
    INVESTIGATED = "investigated"
    READ = "read"
    OVERHEARD = "overheard"
    DEDUCED = "deduced"
    MAGICAL = "magical"
    COMMON_KNOWLEDGE = "common_knowledge"


class KnowledgeRecord(BaseModel):
    """
    Metadata about a fact known by the party.

    Tracks the source, method, and context of how the party learned
    a particular fact. The fact content itself lives in FactDatabase;
    this record only stores acquisition metadata.

    Attributes:
        fact_id: ID of the fact in FactDatabase
        source: Who or what provided this knowledge (NPC name, book title, etc.)
        method: How the knowledge was acquired
        learned_session: Session number when the party learned this
        learned_at: Timestamp when the knowledge was acquired
        location: Where the party learned this (optional)
        notes: Additional context about the acquisition (optional)
    """
    fact_id: str = Field(description="ID of the fact in FactDatabase")
    source: str = Field(description="Who or what provided this knowledge")
    method: AcquisitionMethod = Field(description="How the knowledge was acquired")
    learned_session: int = Field(ge=1, description="Session when the party learned this")
    learned_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the knowledge was acquired"
    )
    location: Optional[str] = Field(
        default=None,
        description="Where the party learned this"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional context about the acquisition"
    )


class PartyKnowledge:
    """
    Manages what the adventuring party collectively knows.

    PartyKnowledge is a filtered view over FactDatabase. When a fact is
    learned by the party, it is tagged with 'party_known' in the FactDatabase
    and a KnowledgeRecord is created to track how it was learned.

    This design avoids duplicating fact data while still providing rich
    querying capabilities for party knowledge.

    Attributes:
        _fact_db: Reference to the FactDatabase
        _campaign_path: Path to the campaign directory for persistence
        _records: Mapping of fact_id to KnowledgeRecord
    """

    def __init__(self, fact_db: "FactDatabase", campaign_path: Path) -> None:
        """
        Initialize the party knowledge tracker.

        Args:
            fact_db: Reference to the FactDatabase for resolving facts
            campaign_path: Path to campaign directory for persistence
        """
        # Import here to avoid circular imports at module level
        from dm20_protocol.claudmaster.consistency.fact_database import FactDatabase as _FDB
        if not isinstance(fact_db, _FDB):
            raise TypeError(
                f"fact_db must be a FactDatabase instance, got {type(fact_db).__name__}"
            )

        self._fact_db = fact_db
        self._campaign_path = Path(campaign_path)
        self._records: dict[str, KnowledgeRecord] = {}

        self._campaign_path.mkdir(parents=True, exist_ok=True)
        self.load()

    @property
    def _knowledge_path(self) -> Path:
        """Path to the party knowledge JSON file."""
        return self._campaign_path / "party_knowledge.json"

    @property
    def known_fact_count(self) -> int:
        """Number of facts known by the party."""
        return len(self._records)

    def learn_fact(
        self,
        fact_id: str,
        source: str,
        method: AcquisitionMethod | str,
        session: int,
        location: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Mark a fact as known by the party.

        Adds the 'party_known' tag to the fact in FactDatabase and creates
        a KnowledgeRecord to track how the party learned it.

        If the party already knows this fact, the operation is skipped
        and False is returned.

        Args:
            fact_id: ID of the fact in FactDatabase
            source: Who or what provided this knowledge
            method: How the knowledge was acquired (AcquisitionMethod or string)
            session: Session number when the party learned this
            location: Where the party learned this (optional)
            notes: Additional context (optional)

        Returns:
            True if the fact was newly learned, False if already known

        Raises:
            KeyError: If the fact_id does not exist in FactDatabase
        """
        # Validate fact exists
        fact = self._fact_db.get_fact(fact_id)
        if fact is None:
            raise KeyError(f"Fact '{fact_id}' not found in FactDatabase")

        # Skip if already known
        if fact_id in self._records:
            logger.debug(f"Party already knows fact {fact_id}, skipping")
            return False

        # Normalize method to enum
        if isinstance(method, str):
            method = AcquisitionMethod(method)

        # Tag the fact in FactDatabase
        if PARTY_KNOWN_TAG not in fact.tags:
            fact.tags.append(PARTY_KNOWN_TAG)

        # Create knowledge record
        record = KnowledgeRecord(
            fact_id=fact_id,
            source=source,
            method=method,
            learned_session=session,
            location=location,
            notes=notes,
        )
        self._records[fact_id] = record

        logger.debug(
            f"Party learned fact {fact_id} via {method.value} "
            f"from '{source}' (session {session})"
        )
        return True

    def party_knows(self, fact_id: str) -> bool:
        """
        Check if the party knows a specific fact.

        Args:
            fact_id: The fact ID to check

        Returns:
            True if the party knows this fact, False otherwise
        """
        return fact_id in self._records

    def get_record(self, fact_id: str) -> Optional[KnowledgeRecord]:
        """
        Get the knowledge record for a specific fact.

        Args:
            fact_id: The fact ID to look up

        Returns:
            KnowledgeRecord if known, None otherwise
        """
        return self._records.get(fact_id)

    def knows_about(self, topic: str) -> list[dict]:
        """
        Query party knowledge by topic.

        Searches the content of all party-known facts for the given topic
        string (case-insensitive). Returns a list of dicts containing both
        the fact data and the acquisition metadata.

        Args:
            topic: Search term to match against fact content

        Returns:
            List of dicts with 'fact' and 'record' keys, sorted by
            relevance score (highest first)
        """
        topic_lower = topic.lower()
        results = []

        for fact_id, record in self._records.items():
            fact = self._fact_db.get_fact(fact_id)
            if fact is None:
                logger.warning(
                    f"Fact {fact_id} in party knowledge not found in FactDatabase"
                )
                continue

            # Match against fact content, tags, and category
            if (
                topic_lower in fact.content.lower()
                or topic_lower in fact.category.value.lower()
                or any(topic_lower in tag.lower() for tag in fact.tags)
            ):
                results.append({
                    "fact": fact,
                    "record": record,
                })

        # Sort by relevance score (highest first)
        results.sort(key=lambda r: -r["fact"].relevance_score)
        return results

    def get_all_known_facts(self) -> list[dict]:
        """
        Get all facts known by the party with their acquisition metadata.

        Returns:
            List of dicts with 'fact' and 'record' keys, sorted by
            the session when they were learned (most recent first)
        """
        results = []
        for fact_id, record in self._records.items():
            fact = self._fact_db.get_fact(fact_id)
            if fact is None:
                continue
            results.append({
                "fact": fact,
                "record": record,
            })

        # Sort by learned session (most recent first)
        results.sort(key=lambda r: -r["record"].learned_session)
        return results

    def get_knowledge_by_source(self, source: str) -> list[dict]:
        """
        Get all facts the party learned from a specific source.

        Args:
            source: The source to filter by (case-insensitive)

        Returns:
            List of dicts with 'fact' and 'record' keys
        """
        source_lower = source.lower()
        results = []
        for fact_id, record in self._records.items():
            if record.source.lower() == source_lower:
                fact = self._fact_db.get_fact(fact_id)
                if fact is not None:
                    results.append({"fact": fact, "record": record})

        results.sort(key=lambda r: -r["record"].learned_session)
        return results

    def get_knowledge_by_method(self, method: AcquisitionMethod | str) -> list[dict]:
        """
        Get all facts the party learned via a specific method.

        Args:
            method: The acquisition method to filter by

        Returns:
            List of dicts with 'fact' and 'record' keys
        """
        if isinstance(method, str):
            method = AcquisitionMethod(method)

        results = []
        for fact_id, record in self._records.items():
            if record.method == method:
                fact = self._fact_db.get_fact(fact_id)
                if fact is not None:
                    results.append({"fact": fact, "record": record})

        results.sort(key=lambda r: -r["record"].learned_session)
        return results

    def share_with_npc(
        self,
        npc_tracker: "NPCKnowledgeTracker",
        npc_id: str,
        fact_id: str,
        shared_by: str,
        session: int,
    ) -> bool:
        """
        Share a fact the party knows with an NPC.

        The party can only share facts they actually know. Uses the
        NPCKnowledgeTracker to add the knowledge to the NPC.

        Args:
            npc_tracker: The NPCKnowledgeTracker to update
            npc_id: The NPC's identifier
            fact_id: ID of the fact to share
            shared_by: Name of the player character sharing the info
            session: Session number when the sharing occurs

        Returns:
            True if the fact was shared, False if party doesn't know it
            or the NPC already knows it
        """
        # Import KnowledgeSource here to avoid circular imports
        from dm20_protocol.claudmaster.consistency.models import KnowledgeSource

        # Party must know this fact
        if not self.party_knows(fact_id):
            logger.debug(
                f"Party tried to share fact {fact_id} with {npc_id}, "
                f"but party doesn't know it"
            )
            return False

        # Check if NPC already knows
        if npc_tracker.npc_knows_fact(npc_id, fact_id):
            logger.debug(f"NPC {npc_id} already knows fact {fact_id}")
            return False

        # Add to NPC knowledge
        npc_tracker.add_knowledge(
            npc_id=npc_id,
            fact_id=fact_id,
            source=KnowledgeSource.TOLD_BY_PLAYER,
            session=session,
            confidence=1.0,
            source_entity=shared_by,
        )

        logger.debug(
            f"Party shared fact {fact_id} with NPC {npc_id} "
            f"(via {shared_by}, session {session})"
        )
        return True

    def save(self) -> None:
        """Persist party knowledge records to party_knowledge.json."""
        data = {
            "version": "1.0",
            "records": [
                record.model_dump(mode="json")
                for record in self._records.values()
            ],
            "metadata": {
                "total_known_facts": len(self._records),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            },
        }

        with open(self._knowledge_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(
            f"Saved {len(self._records)} party knowledge records "
            f"to {self._knowledge_path}"
        )

    def load(self) -> None:
        """
        Load party knowledge records from party_knowledge.json.

        If the file doesn't exist, initializes with no records.
        If the file is corrupt, logs a warning and starts fresh.
        """
        if not self._knowledge_path.exists():
            logger.debug(
                f"No existing party knowledge at {self._knowledge_path}, "
                f"starting empty"
            )
            self._records = {}
            return

        try:
            with open(self._knowledge_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict) or "records" not in data:
                raise ValueError("Invalid party knowledge structure")

            self._records = {}
            for record_data in data["records"]:
                record = KnowledgeRecord(**record_data)
                self._records[record.fact_id] = record

            logger.info(
                f"Loaded {len(self._records)} party knowledge records "
                f"from {self._knowledge_path}"
            )

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(
                f"Failed to load party knowledge from {self._knowledge_path}: {e}"
            )
            logger.warning("Starting with empty party knowledge")
            self._records = {}


__all__ = [
    "PARTY_KNOWN_TAG",
    "AcquisitionMethod",
    "KnowledgeRecord",
    "PartyKnowledge",
]
