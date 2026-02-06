"""
Module Keeper Agent for the Claudmaster multi-agent system.

The Module Keeper is responsible for RAG-based retrieval of adventure module
content. It provides knowledge about NPCs, locations, encounters, and plot
context by querying the vector store with awareness of current game state.

This agent does NOT generate content - it only retrieves and structures
information from the indexed adventure module.
"""

import logging
from typing import Any, Optional
from pydantic import BaseModel, Field

from ..base import Agent, AgentRole
from ..vector_store import VectorStoreManager
from ..models.module import ModuleStructure, ContentType

logger = logging.getLogger("gamemaster-mcp")


# ------------------------------------------------------------------
# Response data models
# ------------------------------------------------------------------

class NPCKnowledge(BaseModel):
    """Structured knowledge about an NPC from the module.

    This model aggregates RAG query results about a specific NPC,
    including personality, goals, relationships, and relevant quotes.
    """
    npc_name: str = Field(description="The NPC's name")
    personality: str = Field(default="", description="Personality traits and demeanor")
    goals: str = Field(default="", description="NPC's goals and motivations")
    secrets: str = Field(default="", description="Hidden information the NPC knows")
    relationships: dict[str, str] = Field(
        default_factory=dict,
        description="Relationships with other characters (name -> relationship)"
    )
    current_location: str = Field(default="", description="Where the NPC is located")
    knowledge_about_topic: str = Field(
        default="",
        description="What the NPC knows about a specific topic"
    )
    relevant_quotes: list[str] = Field(
        default_factory=list,
        description="Direct quotes from the module about this NPC"
    )


class LocationDescription(BaseModel):
    """Structured description of a location from the module.

    Provides different levels of detail suitable for read-aloud text,
    DM-only information, or full descriptions.
    """
    name: str = Field(description="Location name")
    read_aloud_text: str = Field(
        default="",
        description="Text meant to be read aloud to players"
    )
    dm_description: str = Field(
        default="",
        description="DM-only information about the location"
    )
    features: list[str] = Field(
        default_factory=list,
        description="Notable features of the location"
    )
    exits: list[str] = Field(
        default_factory=list,
        description="Available exits and connections"
    )
    hazards: list[str] = Field(
        default_factory=list,
        description="Traps, environmental hazards, or dangers"
    )
    creatures_present: list[str] = Field(
        default_factory=list,
        description="NPCs or creatures in this location"
    )
    treasure: list[str] = Field(
        default_factory=list,
        description="Items or treasure available here"
    )


class EncounterTrigger(BaseModel):
    """Information about an encounter and its trigger conditions.

    Describes when and how an encounter should be triggered,
    along with setup information and resolution options.
    """
    name: str = Field(description="Encounter name")
    trigger_condition: str = Field(
        default="",
        description="What triggers this encounter"
    )
    setup: str = Field(
        default="",
        description="How to set up the encounter"
    )
    creatures: list[str] = Field(
        default_factory=list,
        description="Creatures involved in the encounter"
    )
    tactics: str = Field(
        default="",
        description="Tactics and behavior of creatures"
    )
    resolution_options: list[str] = Field(
        default_factory=list,
        description="Ways the encounter can be resolved"
    )


class PlotContext(BaseModel):
    """Contextual information about the current plot state.

    Aggregates information about the current chapter, objectives,
    upcoming events, and relevant NPCs/locations for the current situation.
    """
    current_chapter_summary: str = Field(
        default="",
        description="Summary of the current chapter"
    )
    key_objectives: list[str] = Field(
        default_factory=list,
        description="Main objectives in the current chapter"
    )
    upcoming_events: list[str] = Field(
        default_factory=list,
        description="Events that may occur soon"
    )
    relevant_npcs: list[str] = Field(
        default_factory=list,
        description="NPCs relevant to current situation"
    )
    relevant_locations: list[str] = Field(
        default_factory=list,
        description="Locations relevant to current situation"
    )
    foreshadowing_hints: list[str] = Field(
        default_factory=list,
        description="Hints or foreshadowing elements"
    )


# ------------------------------------------------------------------
# ModuleKeeperAgent
# ------------------------------------------------------------------

class ModuleKeeperAgent(Agent):
    """Agent responsible for RAG-based adventure module content retrieval.

    The Module Keeper maintains awareness of the current game context
    (chapter, location) and uses that context to filter RAG queries,
    ensuring retrieved information is relevant to the current situation.

    It tracks what content has been revealed to players to avoid repetition
    and provides structured responses about NPCs, locations, encounters,
    and plot context.

    Args:
        vector_store: The VectorStoreManager for RAG queries.
        module_structure: Parsed structure of the adventure module.
        current_chapter: Optional initial chapter name.
        current_location: Optional initial location name.
    """

    def __init__(
        self,
        vector_store: VectorStoreManager,
        module_structure: ModuleStructure,
        current_chapter: str | None = None,
        current_location: str | None = None,
    ) -> None:
        super().__init__(name="ModuleKeeper", role=AgentRole.MODULE_KEEPER)
        self._vector_store = vector_store
        self._module_structure = module_structure
        self._current_chapter = current_chapter
        self._current_location = current_location

        # Track revealed content to avoid repetition
        self._revealed_content: set[tuple[str, str]] = set()

        logger.info(
            "ModuleKeeperAgent initialized for module '%s' (chapter=%s, location=%s)",
            module_structure.module_id,
            current_chapter or "none",
            current_location or "none",
        )

    async def reason(self, context: dict[str, Any]) -> str:
        """Analyze the context to determine what knowledge to retrieve.

        Examines the request type and parameters to decide what kind of
        RAG query or queries are needed.

        Args:
            context: Request context with keys like 'request_type',
                'npc_name', 'location_name', 'query', etc.

        Returns:
            Reasoning string describing the retrieval strategy.
        """
        request_type = context.get("request_type", "unknown")

        if request_type == "npc_knowledge":
            npc_name = context.get("npc_name", "unknown")
            topic = context.get("topic")
            if topic:
                return f"Retrieve knowledge about NPC '{npc_name}' related to topic '{topic}'"
            return f"Retrieve general knowledge about NPC '{npc_name}'"

        elif request_type == "location_description":
            location_name = context.get("location_name", "unknown")
            detail_level = context.get("detail_level", "full")
            return f"Retrieve {detail_level} description of location '{location_name}'"

        elif request_type == "encounter_trigger":
            location = context.get("location", self._current_location or "unknown")
            actions = context.get("player_actions", "")
            return f"Check for encounters triggered at '{location}' by actions: {actions}"

        elif request_type == "plot_context":
            query = context.get("query", "")
            return f"Retrieve plot context for query: {query}"

        else:
            return f"Unknown request type '{request_type}', will attempt generic retrieval"

    async def act(self, reasoning: str) -> Any:
        """Execute RAG queries to retrieve module content.

        Based on the reasoning, performs one or more vector store queries
        to gather relevant information from the adventure module.

        Args:
            reasoning: The reasoning output describing what to retrieve.

        Returns:
            Raw query results from the vector store.
        """
        # The action result will be processed in observe()
        # For now, return the reasoning as a signal to observe()
        return {"reasoning": reasoning, "timestamp": "now"}

    async def observe(self, result: Any) -> dict[str, Any]:
        """Process query results and extract structured observations.

        Transforms raw vector store results into structured knowledge
        based on the request type.

        Args:
            result: The result from act(), containing reasoning.

        Returns:
            Dictionary with observations about the retrieved content.
        """
        reasoning = result.get("reasoning", "")

        # Basic observation: track what was requested
        observations = {
            "reasoning_summary": reasoning,
            "current_chapter": self._current_chapter,
            "current_location": self._current_location,
            "revealed_count": len(self._revealed_content),
        }

        return observations

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_npc_knowledge(
        self,
        npc_name: str,
        topic: str | None = None,
    ) -> NPCKnowledge:
        """Retrieve structured knowledge about an NPC.

        Queries the vector store for information about a specific NPC,
        optionally filtered by topic. Combines multiple query results
        to build a complete knowledge profile.

        Args:
            npc_name: Name of the NPC to query.
            topic: Optional specific topic to focus on.

        Returns:
            NPCKnowledge object with structured information.
        """
        # Build query text
        if topic:
            query_text = f"{npc_name} {topic}"
        else:
            query_text = npc_name

        # Build filter for NPC content
        where_filter = self._build_query_filter(content_type=ContentType.NPC)

        # Query vector store
        results = self._vector_store.query(
            module_id=self._module_structure.module_id,
            query_text=query_text,
            n_results=5,
            where=where_filter if where_filter else None,
        )

        # Extract knowledge from results
        knowledge = NPCKnowledge(npc_name=npc_name)

        # Find NPC reference in module structure
        for npc_ref in self._module_structure.npcs:
            if npc_ref.name.lower() == npc_name.lower():
                knowledge.current_location = npc_ref.location or ""
                break

        # Aggregate information from query results
        for result in results:
            doc_text = result.get("document", "")
            metadata = result.get("metadata", {})

            # Extract relevant quotes
            if doc_text and len(doc_text) > 20:
                knowledge.relevant_quotes.append(doc_text[:200])

            # Try to categorize content
            if "personality" in doc_text.lower() or "character" in doc_text.lower():
                knowledge.personality += f" {doc_text[:150]}"

            if "goal" in doc_text.lower() or "want" in doc_text.lower() or "seek" in doc_text.lower():
                knowledge.goals += f" {doc_text[:150]}"

            if "secret" in doc_text.lower() or "hidden" in doc_text.lower():
                knowledge.secrets += f" {doc_text[:150]}"

        # Store topic-specific knowledge
        if topic:
            knowledge.knowledge_about_topic = " ".join(
                result.get("document", "")[:200] for result in results[:3]
            )

        logger.info("Retrieved knowledge about NPC '%s' (%d results)", npc_name, len(results))
        return knowledge

    def get_location_description(
        self,
        location_name: str,
        detail_level: str = "full",
    ) -> LocationDescription:
        """Retrieve structured description of a location.

        Queries for location information and structures it according to
        the requested detail level: 'brief', 'full', or 'dm_only'.

        Args:
            location_name: Name of the location.
            detail_level: Level of detail: 'brief', 'full', or 'dm_only'.

        Returns:
            LocationDescription object with structured information.
        """
        # Query vector store for location
        where_filter = self._build_query_filter(content_type=ContentType.LOCATION)

        results = self._vector_store.query(
            module_id=self._module_structure.module_id,
            query_text=location_name,
            n_results=5,
            where=where_filter if where_filter else None,
        )

        description = LocationDescription(name=location_name)

        # Find location reference in module structure
        for loc_ref in self._module_structure.locations:
            if loc_ref.name.lower() == location_name.lower():
                description.exits = loc_ref.sub_locations
                break

        # Aggregate information from query results
        for result in results:
            doc_text = result.get("document", "")

            # Extract different types of information
            if "read aloud" in doc_text.lower() or "players see" in doc_text.lower():
                description.read_aloud_text += f" {doc_text[:300]}"

            if "dm note" in doc_text.lower() or "dm info" in doc_text.lower():
                description.dm_description += f" {doc_text[:300]}"

            if "treasure" in doc_text.lower() or "loot" in doc_text.lower():
                description.treasure.append(doc_text[:100])

            if "trap" in doc_text.lower() or "hazard" in doc_text.lower():
                description.hazards.append(doc_text[:100])

            # Default: add to general description
            if not description.read_aloud_text:
                description.read_aloud_text = doc_text[:300]

        # Filter based on detail level
        if detail_level == "brief":
            description.dm_description = ""
            description.hazards = []
            description.treasure = []
        elif detail_level == "dm_only":
            description.read_aloud_text = ""

        logger.info(
            "Retrieved %s description of location '%s' (%d results)",
            detail_level,
            location_name,
            len(results),
        )
        return description

    def check_encounter_trigger(
        self,
        current_location: str,
        player_actions: str,
    ) -> Optional[EncounterTrigger]:
        """Check if player actions trigger an encounter.

        Queries for encounters at the current location and analyzes
        whether the given player actions match any trigger conditions.

        Args:
            current_location: Current location name.
            player_actions: Description of what players are doing.

        Returns:
            EncounterTrigger if triggered, None otherwise.
        """
        # Query for encounters at this location
        query_text = f"{current_location} encounter {player_actions}"
        where_filter = self._build_query_filter(content_type=ContentType.ENCOUNTER)

        results = self._vector_store.query(
            module_id=self._module_structure.module_id,
            query_text=query_text,
            n_results=3,
            where=where_filter if where_filter else None,
        )

        # Check encounters in module structure
        for enc_ref in self._module_structure.encounters:
            if enc_ref.location.lower() == current_location.lower():
                # Found an encounter at this location
                # Extract details from RAG results
                trigger = EncounterTrigger(name=enc_ref.name)

                for result in results:
                    doc_text = result.get("document", "")

                    if "trigger" in doc_text.lower():
                        trigger.trigger_condition = doc_text[:200]

                    if "creature" in doc_text.lower() or "enemy" in doc_text.lower():
                        # Extract creature names (simplified)
                        trigger.creatures.append(doc_text[:100])

                    if "tactic" in doc_text.lower() or "strategy" in doc_text.lower():
                        trigger.tactics = doc_text[:200]

                    if not trigger.setup:
                        trigger.setup = doc_text[:200]

                logger.info("Encounter '%s' triggered at '%s'", enc_ref.name, current_location)
                return trigger

        logger.info("No encounter triggered at '%s'", current_location)
        return None

    def get_plot_context(self, query: str) -> PlotContext:
        """Retrieve plot context relevant to a query.

        Performs a broad RAG query to gather context about the current
        chapter, objectives, upcoming events, and relevant NPCs/locations.

        Args:
            query: Natural language query about the plot.

        Returns:
            PlotContext object with aggregated information.
        """
        # Query with current chapter context
        where_filter = self._build_query_filter()

        results = self._vector_store.query(
            module_id=self._module_structure.module_id,
            query_text=query,
            n_results=10,
            where=where_filter if where_filter else None,
        )

        context = PlotContext()

        # If current chapter is set, get its summary
        if self._current_chapter:
            context.current_chapter_summary = f"Chapter: {self._current_chapter}"

        # Extract plot elements from results
        for result in results:
            doc_text = result.get("document", "")
            metadata = result.get("metadata", {})

            if "objective" in doc_text.lower() or "goal" in doc_text.lower():
                context.key_objectives.append(doc_text[:150])

            if "foreshadow" in doc_text.lower() or "hint" in doc_text.lower():
                context.foreshadowing_hints.append(doc_text[:150])

            # Extract NPC names mentioned
            for npc_ref in self._module_structure.npcs:
                if npc_ref.name.lower() in doc_text.lower():
                    if npc_ref.name not in context.relevant_npcs:
                        context.relevant_npcs.append(npc_ref.name)

            # Extract location names mentioned
            for loc_ref in self._module_structure.locations:
                if loc_ref.name.lower() in doc_text.lower():
                    if loc_ref.name not in context.relevant_locations:
                        context.relevant_locations.append(loc_ref.name)

        logger.info("Retrieved plot context for query '%s' (%d results)", query, len(results))
        return context

    def set_context(
        self,
        chapter: str | None = None,
        location: str | None = None,
    ) -> None:
        """Update the current game context for filtering queries.

        Args:
            chapter: Current chapter name (or None to keep existing).
            location: Current location name (or None to keep existing).
        """
        if chapter is not None:
            self._current_chapter = chapter
            logger.info("Updated current chapter to '%s'", chapter)

        if location is not None:
            self._current_location = location
            logger.info("Updated current location to '%s'", location)

    def mark_revealed(self, content_type: str, content_id: str) -> None:
        """Mark content as revealed to players to avoid repetition.

        Args:
            content_type: Type of content (e.g., 'npc', 'location', 'secret').
            content_id: Identifier for the specific content.
        """
        self._revealed_content.add((content_type, content_id))
        logger.debug("Marked %s '%s' as revealed", content_type, content_id)

    def _build_query_filter(
        self,
        content_type: ContentType | None = None,
    ) -> dict[str, Any] | None:
        """Build ChromaDB where filter from current context.

        Creates a metadata filter that includes current chapter/location
        and optionally restricts to a specific content type.

        Args:
            content_type: Optional content type to filter by.

        Returns:
            ChromaDB where filter dict, or None if no filtering.
        """
        conditions: list[dict[str, Any]] = []

        # Filter by current chapter if set
        if self._current_chapter:
            conditions.append({"chapter": self._current_chapter})

        # Filter by content type if specified
        if content_type:
            conditions.append({"content_type": content_type.value})

        # Build combined filter
        if not conditions:
            return None

        if len(conditions) == 1:
            return conditions[0]

        # ChromaDB uses $and for multiple conditions
        return {"$and": conditions}


__all__ = [
    "ModuleKeeperAgent",
    "NPCKnowledge",
    "LocationDescription",
    "EncounterTrigger",
    "PlotContext",
]
