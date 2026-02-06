"""
Fact database for storing and querying narrative facts.

This module provides the FactDatabase class, which manages a collection
of narrative facts with support for querying, filtering, and persistence.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .models import Fact, FactCategory

logger = logging.getLogger("gamemaster-mcp")


class FactDatabase:
    """
    Stores and manages narrative facts for consistency tracking.

    The FactDatabase maintains a collection of facts that are established
    during gameplay, enabling agents to query past events, NPC information,
    and other narrative details to maintain consistency.

    Attributes:
        campaign_path: Path to the campaign directory
        facts: Dictionary mapping fact IDs to Fact objects
        campaign_id: Name/ID of the campaign
    """

    def __init__(self, campaign_path: Path) -> None:
        """
        Initialize the fact database.

        Args:
            campaign_path: Path to the campaign directory where facts will be stored
        """
        self.campaign_path = Path(campaign_path)
        self.facts: dict[str, Fact] = {}
        self.campaign_id = self.campaign_path.name

        # Ensure the campaign directory exists
        self.campaign_path.mkdir(parents=True, exist_ok=True)

        # Try to load existing facts
        self.load()

    @property
    def _db_path(self) -> Path:
        """Path to the fact database JSON file."""
        return self.campaign_path / "fact_database.json"

    def add_fact(self, fact: Fact) -> str:
        """
        Add a new fact to the database.

        If the fact has an empty ID, one will be auto-generated.

        Args:
            fact: The fact to add

        Returns:
            The ID of the added fact
        """
        # Auto-generate ID if not provided
        if not fact.id:
            fact.id = f"fact_{uuid4().hex[:8]}"

        # Store the fact
        self.facts[fact.id] = fact

        logger.debug(f"Added fact {fact.id} ({fact.category}): {fact.content[:50]}...")

        return fact.id

    def get_fact(self, fact_id: str) -> Optional[Fact]:
        """
        Retrieve a specific fact by ID.

        Args:
            fact_id: The ID of the fact to retrieve

        Returns:
            The fact if found, None otherwise
        """
        return self.facts.get(fact_id)

    def query_facts(
        self,
        category: Optional[FactCategory] = None,
        session: Optional[int] = None,
        min_relevance: float = 0.0,
        tags: Optional[list[str]] = None,
        limit: int = 50
    ) -> list[Fact]:
        """
        Query facts with optional filters.

        Filters are combined with AND logic. Results are sorted by
        relevance score (descending) and limited to the specified count.

        Args:
            category: Filter by fact category
            session: Filter by session number
            min_relevance: Minimum relevance score (inclusive)
            tags: Filter by tags (fact must have ALL specified tags)
            limit: Maximum number of results to return

        Returns:
            List of matching facts, sorted by relevance (highest first)
        """
        results = list(self.facts.values())

        # Apply category filter
        if category is not None:
            results = [f for f in results if f.category == category]

        # Apply session filter
        if session is not None:
            results = [f for f in results if f.session_number == session]

        # Apply relevance filter
        results = [f for f in results if f.relevance_score >= min_relevance]

        # Apply tags filter (fact must have ALL specified tags)
        if tags:
            results = [
                f for f in results
                if all(tag in f.tags for tag in tags)
            ]

        # Sort by relevance (highest first), then by timestamp (newest first)
        results.sort(key=lambda f: (-f.relevance_score, -f.timestamp.timestamp()))

        # Apply limit
        return results[:limit]

    def get_related_facts(self, fact_id: str) -> list[Fact]:
        """
        Get all facts related to a given fact.

        Args:
            fact_id: The ID of the fact whose relations to retrieve

        Returns:
            List of related facts (empty if fact not found)
        """
        fact = self.get_fact(fact_id)
        if not fact:
            return []

        related = []
        for related_id in fact.related_facts:
            related_fact = self.get_fact(related_id)
            if related_fact:
                related.append(related_fact)

        return related

    def update_relevance(self, fact_id: str, new_score: float) -> None:
        """
        Update the relevance score of a fact.

        Args:
            fact_id: The ID of the fact to update
            new_score: The new relevance score

        Raises:
            KeyError: If the fact ID is not found
        """
        if fact_id not in self.facts:
            raise KeyError(f"Fact {fact_id} not found in database")

        old_score = self.facts[fact_id].relevance_score
        self.facts[fact_id].relevance_score = new_score

        logger.debug(f"Updated relevance for {fact_id}: {old_score} -> {new_score}")

    def link_facts(self, fact_id_1: str, fact_id_2: str) -> None:
        """
        Create a bidirectional link between two facts.

        Each fact will have the other's ID added to its related_facts list,
        if not already present.

        Args:
            fact_id_1: First fact ID
            fact_id_2: Second fact ID

        Raises:
            KeyError: If either fact ID is not found
        """
        if fact_id_1 not in self.facts:
            raise KeyError(f"Fact {fact_id_1} not found in database")
        if fact_id_2 not in self.facts:
            raise KeyError(f"Fact {fact_id_2} not found in database")

        # Add bidirectional links
        if fact_id_2 not in self.facts[fact_id_1].related_facts:
            self.facts[fact_id_1].related_facts.append(fact_id_2)

        if fact_id_1 not in self.facts[fact_id_2].related_facts:
            self.facts[fact_id_2].related_facts.append(fact_id_1)

        logger.debug(f"Linked facts {fact_id_1} <-> {fact_id_2}")

    def save(self) -> None:
        """
        Persist facts to fact_database.json.

        The database is saved as a JSON file with metadata about
        the total number of facts and last update time.
        """
        data = {
            "version": "1.0",
            "campaign_id": self.campaign_id,
            "facts": [fact.model_dump(mode="json") for fact in self.facts.values()],
            "metadata": {
                "total_facts": len(self.facts),
                "last_updated": datetime.now().isoformat()
            }
        }

        with open(self._db_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(self.facts)} facts to {self._db_path}")

    def load(self) -> None:
        """
        Load facts from fact_database.json.

        If the file doesn't exist, initializes an empty database.
        If the file is corrupt or invalid, logs an error and starts with an empty database.
        """
        if not self._db_path.exists():
            logger.debug(f"No existing fact database at {self._db_path}, starting empty")
            self.facts = {}
            return

        try:
            with open(self._db_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate structure
            if not isinstance(data, dict) or "facts" not in data:
                raise ValueError("Invalid database structure")

            # Load facts
            self.facts = {}
            for fact_data in data["facts"]:
                fact = Fact(**fact_data)
                self.facts[fact.id] = fact

            logger.info(f"Loaded {len(self.facts)} facts from {self._db_path}")

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.error(f"Failed to load fact database from {self._db_path}: {e}")
            logger.warning("Starting with empty fact database")
            self.facts = {}


__all__ = [
    "FactDatabase",
]
