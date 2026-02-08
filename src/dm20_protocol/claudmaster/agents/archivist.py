"""
Archivist Agent for the Claudmaster multi-agent system.

The Archivist is the game state knowledge keeper, responsible for:
- Querying character stats, HP, inventory, and conditions
- Tracking and reporting combat state (initiative, turns, conditions)
- Looking up rules from loaded rulebooks
- Caching frequently accessed data for performance

Implements the ReAct pattern: reason about what information is needed,
retrieve it from the game state / rulebooks, then observe/validate the result.
"""

import asyncio
import fnmatch
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional

from pydantic import BaseModel, Field

from dm20_protocol.models import Campaign, Character, GameState, Item
from ..base import Agent, AgentRole

logger = logging.getLogger("dm20-protocol")


# ------------------------------------------------------------------
# Query result types
# ------------------------------------------------------------------

class HPStatus(BaseModel):
    """Current hit point status for a character."""
    name: str = Field(description="Character name")
    hp_current: int = Field(description="Current hit points")
    hp_max: int = Field(description="Maximum hit points")
    hp_temp: int = Field(description="Temporary hit points")
    is_conscious: bool = Field(description="Whether the character is conscious (HP > 0)")
    percentage: float = Field(ge=0.0, le=100.0, description="HP percentage (current / max * 100)")


class CharacterStats(BaseModel):
    """Full character statistics snapshot."""
    name: str = Field(description="Character name")
    race: str = Field(description="Character race")
    character_class: str = Field(description="Character class name")
    level: int = Field(description="Character level")
    ability_scores: dict[str, int] = Field(
        default_factory=dict,
        description="Ability scores as {ability_name: score}"
    )
    hp_current: int = Field(description="Current hit points")
    hp_max: int = Field(description="Maximum hit points")
    hp_temp: int = Field(default=0, description="Temporary hit points")
    armor_class: int = Field(description="Armor class")
    speed: int = Field(default=30, description="Movement speed in feet")
    conditions: list[str] = Field(
        default_factory=list,
        description="Active conditions on the character"
    )
    proficiency_bonus: int = Field(default=2, description="Proficiency bonus")


class InventoryItem(BaseModel):
    """Simplified inventory item for query results."""
    name: str = Field(description="Item name")
    quantity: int = Field(default=1, description="Item quantity")
    item_type: str = Field(default="misc", description="Item type category")
    description: str | None = Field(default=None, description="Item description")
    weight: float | None = Field(default=None, description="Item weight")


class Inventory(BaseModel):
    """Character inventory query result."""
    character_name: str = Field(description="Character name")
    items: list[InventoryItem] = Field(default_factory=list, description="Inventory items")
    total_items: int = Field(default=0, description="Total number of items")
    equipped: dict[str, str | None] = Field(
        default_factory=dict,
        description="Currently equipped items by slot"
    )


class Condition(BaseModel):
    """Active condition on a character or entity."""
    name: str = Field(description="Condition name (e.g., 'poisoned', 'stunned')")
    source: str = Field(default="unknown", description="Source of the condition")
    duration: str | None = Field(default=None, description="Duration description")


class InitiativeEntry(BaseModel):
    """A single entry in the initiative order."""
    name: str = Field(description="Combatant name")
    initiative: int = Field(description="Initiative roll value")
    is_current: bool = Field(default=False, description="Whether this is the current turn")
    is_player: bool = Field(default=True, description="Whether this is a player character")


class CombatState(BaseModel):
    """Current combat state snapshot."""
    is_active: bool = Field(description="Whether combat is currently active")
    round_number: int = Field(default=0, description="Current combat round")
    current_turn: str | None = Field(default=None, description="Name of the combatant whose turn it is")
    initiative_order: list[InitiativeEntry] = Field(
        default_factory=list,
        description="Initiative order entries"
    )
    conditions_in_effect: dict[str, list[Condition]] = Field(
        default_factory=dict,
        description="Active conditions per combatant"
    )


class AvailableAction(BaseModel):
    """An action available to a combatant."""
    name: str = Field(description="Action name")
    action_type: str = Field(
        default="action",
        description="Action economy type: action, bonus_action, reaction, movement, free"
    )
    description: str = Field(default="", description="Brief description of the action")


class RuleResult(BaseModel):
    """Result of a rules lookup query."""
    query: str = Field(description="The original search query")
    found: bool = Field(description="Whether relevant rules were found")
    rules_text: str = Field(default="", description="The relevant rules text")
    source: str = Field(default="", description="Source of the rules (e.g., 'PHB p.123')")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Confidence in the relevance of the result"
    )


class QueryResult(BaseModel):
    """Generic wrapper for archivist query results."""
    query_type: str = Field(description="Type of query performed")
    success: bool = Field(description="Whether the query succeeded")
    data: Any = Field(default=None, description="The query result data")
    error: str | None = Field(default=None, description="Error message if query failed")


# ------------------------------------------------------------------
# StateCache
# ------------------------------------------------------------------

class StateCache:
    """TTL-based cache for frequently accessed game state.

    Thread-safe cache that stores query results with time-to-live expiration.
    Uses an asyncio lock for safe concurrent access.
    """

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        """Initialize the cache.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds.
        """
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()

    @property
    def ttl(self) -> float:
        """Return the cache TTL in seconds."""
        return self._ttl

    async def get(self, key: str) -> Any | None:
        """Get a value from the cache if it exists and hasn't expired.

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found or expired.
        """
        async with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if time.monotonic() - timestamp < self._ttl:
                    return value
                else:
                    del self._cache[key]
            return None

    async def set(self, key: str, value: Any) -> None:
        """Store a value in the cache.

        Args:
            key: Cache key.
            value: Value to store.
        """
        async with self._lock:
            self._cache[key] = (value, time.monotonic())

    async def get_or_fetch(
        self,
        key: str,
        fetcher: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        """Get a value from cache, or fetch and cache it.

        Args:
            key: Cache key.
            fetcher: Async callable that returns the value to cache.

        Returns:
            Cached or freshly fetched value.
        """
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = await fetcher()
        await self.set(key, value)
        return value

    async def invalidate(self, pattern: str = "*") -> int:
        """Invalidate cache entries matching a glob pattern.

        Args:
            pattern: Glob pattern for keys to invalidate. Default '*' clears all.

        Returns:
            Number of entries invalidated.
        """
        async with self._lock:
            if pattern == "*":
                count = len(self._cache)
                self._cache.clear()
                return count

            keys_to_remove = [
                k for k in self._cache if fnmatch.fnmatch(k, pattern)
            ]
            for k in keys_to_remove:
                del self._cache[k]
            return len(keys_to_remove)

    async def size(self) -> int:
        """Return the number of entries in the cache (including expired)."""
        async with self._lock:
            return len(self._cache)


# ------------------------------------------------------------------
# Query type classification
# ------------------------------------------------------------------

class QueryType:
    """Constants for classifying archivist queries."""
    CHARACTER_STATS = "character_stats"
    CHARACTER_HP = "character_hp"
    INVENTORY = "inventory"
    CONDITIONS = "conditions"
    COMBAT_STATE = "combat_state"
    INITIATIVE_ORDER = "initiative_order"
    AVAILABLE_ACTIONS = "available_actions"
    RULE_LOOKUP = "rule_lookup"
    UNKNOWN = "unknown"


# ------------------------------------------------------------------
# ArchivistAgent
# ------------------------------------------------------------------

class ArchivistAgent(Agent):
    """Agent responsible for game state knowledge and rules lookup.

    The Archivist serves as the knowledge keeper for the AI DM system,
    providing accurate information about character stats, inventory,
    conditions, rules, and combat state when other agents need to make
    informed decisions.

    Args:
        campaign: The active D&D campaign to query.
        rules_lookup_fn: Optional async function for searching rulebooks.
            Signature: async (query: str) -> list[dict[str, Any]]
    """

    def __init__(
        self,
        campaign: Campaign,
        rules_lookup_fn: Callable[
            [str], Coroutine[Any, Any, list[dict[str, Any]]]
        ] | None = None,
        cache_ttl: float = 30.0,
    ) -> None:
        super().__init__(name="archivist", role=AgentRole.ARCHIVIST)
        self.campaign = campaign
        self._rules_lookup_fn = rules_lookup_fn
        self._cache = StateCache(ttl_seconds=cache_ttl)

    # ------------------------------------------------------------------
    # ReAct: reason → act → observe
    # ------------------------------------------------------------------

    async def reason(self, context: dict[str, Any]) -> str:
        """Determine what information is needed from the game state.

        Examines the context (player input, intent, game state) and
        decides which query to perform.

        Args:
            context: Game context dict with keys like 'player_input',
                'intent', 'game_state', etc.

        Returns:
            A reasoning string describing what information to retrieve.
        """
        player_input = context.get("player_input", "")
        intent = context.get("intent", {})
        intent_type = intent.get("intent_type", "")
        game_state = context.get("game_state", {})
        in_combat = game_state.get("in_combat", False)

        input_lower = player_input.lower()

        # Combat-related queries
        if in_combat or intent_type == "combat":
            if any(kw in input_lower for kw in ["initiative", "turn order", "who goes"]):
                return f"query:{QueryType.INITIATIVE_ORDER}|Combat initiative order requested."
            if any(kw in input_lower for kw in ["what can i do", "available actions", "my options"]):
                return (
                    f"query:{QueryType.AVAILABLE_ACTIONS}|"
                    f"Player wants to know available combat actions."
                )
            return f"query:{QueryType.COMBAT_STATE}|Combat state information needed."

        # Character stat queries
        if any(kw in input_lower for kw in ["stats", "character sheet", "ability scores"]):
            return f"query:{QueryType.CHARACTER_STATS}|Character statistics requested."

        # HP queries
        if any(kw in input_lower for kw in ["hp", "hit points", "health", "how hurt"]):
            return f"query:{QueryType.CHARACTER_HP}|Hit point status requested."

        # Inventory queries
        if any(kw in input_lower for kw in ["inventory", "items", "equipment", "backpack", "bag"]):
            return f"query:{QueryType.INVENTORY}|Inventory information requested."

        # Condition queries
        if any(kw in input_lower for kw in ["condition", "status effect", "poisoned", "stunned"]):
            return f"query:{QueryType.CONDITIONS}|Active conditions requested."

        # Rules lookup
        if any(kw in input_lower for kw in ["rule", "how does", "can i", "what happens when"]):
            return f"query:{QueryType.RULE_LOOKUP}|query_text={player_input}|Rules lookup requested."

        # System intents default to character stats
        if intent_type == "system":
            return f"query:{QueryType.CHARACTER_STATS}|System query - providing character overview."

        # Default: provide general game state
        return f"query:{QueryType.COMBAT_STATE}|General game state query."

    async def act(self, reasoning: str) -> Any:
        """Execute the information retrieval based on reasoning.

        Parses the reasoning string to determine the query type and
        dispatches to the appropriate query method.

        Args:
            reasoning: Output from the reason() phase.

        Returns:
            A QueryResult wrapping the retrieved data.
        """
        # Parse the query type from reasoning format: "query:TYPE|..."
        query_type = QueryType.UNKNOWN
        query_extra = ""
        if reasoning.startswith("query:"):
            parts = reasoning.split("|", 2)
            query_type = parts[0].replace("query:", "")
            if len(parts) > 1 and parts[1].startswith("query_text="):
                query_extra = parts[1].replace("query_text=", "")

        try:
            if query_type == QueryType.CHARACTER_STATS:
                data = await self._get_first_character_stats()
                return QueryResult(
                    query_type=query_type, success=True, data=data
                )

            elif query_type == QueryType.CHARACTER_HP:
                data = await self._get_first_character_hp()
                return QueryResult(
                    query_type=query_type, success=True, data=data
                )

            elif query_type == QueryType.INVENTORY:
                data = await self._get_first_character_inventory()
                return QueryResult(
                    query_type=query_type, success=True, data=data
                )

            elif query_type == QueryType.CONDITIONS:
                data = await self._get_first_character_conditions()
                return QueryResult(
                    query_type=query_type, success=True, data=data
                )

            elif query_type == QueryType.COMBAT_STATE:
                data = await self.get_combat_state()
                return QueryResult(
                    query_type=query_type, success=True, data=data
                )

            elif query_type == QueryType.INITIATIVE_ORDER:
                data = await self.get_initiative_order()
                return QueryResult(
                    query_type=query_type, success=True, data=data
                )

            elif query_type == QueryType.AVAILABLE_ACTIONS:
                data = await self._get_first_character_actions()
                return QueryResult(
                    query_type=query_type, success=True, data=data
                )

            elif query_type == QueryType.RULE_LOOKUP:
                query_text = query_extra or "general rule"
                data = await self.lookup_rule(query_text)
                return QueryResult(
                    query_type=query_type, success=True, data=data
                )

            else:
                # Unknown query — return combat state as fallback
                data = await self.get_combat_state()
                return QueryResult(
                    query_type=QueryType.COMBAT_STATE, success=True, data=data
                )

        except Exception as e:
            logger.error(f"Archivist query failed ({query_type}): {e}")
            return QueryResult(
                query_type=query_type, success=False, error=str(e)
            )

    async def observe(self, result: Any) -> dict[str, Any]:
        """Process and validate the query result.

        Extracts observations and state changes from the result.

        Args:
            result: The QueryResult from act().

        Returns:
            Dict with observations about the query.
        """
        if not isinstance(result, QueryResult):
            return {"success": False, "error": "Unexpected result type"}

        observations: dict[str, Any] = {
            "query_type": result.query_type,
            "success": result.success,
        }

        if result.error:
            observations["error"] = result.error
            return observations

        # Extract state changes that might be relevant to the orchestrator
        state_changes: list[dict[str, Any]] = []

        if result.query_type == QueryType.COMBAT_STATE and result.data:
            combat: CombatState = result.data
            observations["in_combat"] = combat.is_active
            observations["combat_round"] = combat.round_number
            observations["current_turn"] = combat.current_turn

        elif result.query_type == QueryType.CHARACTER_HP and result.data:
            hp: HPStatus = result.data
            observations["character_name"] = hp.name
            observations["hp_percentage"] = hp.percentage
            if hp.hp_current <= 0:
                observations["unconscious"] = True

        elif result.query_type == QueryType.CHARACTER_STATS and result.data:
            stats: CharacterStats = result.data
            observations["character_name"] = stats.name
            observations["level"] = stats.level
            observations["class"] = stats.character_class

        observations["state_changes"] = state_changes
        return observations

    # ------------------------------------------------------------------
    # Character query methods
    # ------------------------------------------------------------------

    async def get_character_stats(self, name_or_id: str) -> CharacterStats:
        """Get full character statistics.

        Args:
            name_or_id: Character name or ID.

        Returns:
            CharacterStats snapshot.

        Raises:
            KeyError: If character is not found.
        """
        cache_key = f"stats:{name_or_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        character = self._find_character(name_or_id)
        stats = CharacterStats(
            name=character.name,
            race=character.race.name,
            character_class=character.character_class.name,
            level=character.character_class.level,
            ability_scores={
                name: ability.score
                for name, ability in character.abilities.items()
            },
            hp_current=character.hit_points_current,
            hp_max=character.hit_points_max,
            hp_temp=character.temporary_hit_points,
            armor_class=character.armor_class,
            speed=30,  # Default D&D speed; not stored on Character model
            conditions=[],  # Conditions are tracked via GameState
            proficiency_bonus=character.proficiency_bonus,
        )

        await self._cache.set(cache_key, stats)
        return stats

    async def get_character_hp(self, name_or_id: str) -> HPStatus:
        """Get current HP status for a character.

        Args:
            name_or_id: Character name or ID.

        Returns:
            HPStatus with current, max, and temporary HP.

        Raises:
            KeyError: If character is not found.
        """
        cache_key = f"hp:{name_or_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        character = self._find_character(name_or_id)
        max_hp = max(character.hit_points_max, 1)  # Avoid division by zero
        hp_status = HPStatus(
            name=character.name,
            hp_current=character.hit_points_current,
            hp_max=character.hit_points_max,
            hp_temp=character.temporary_hit_points,
            is_conscious=character.hit_points_current > 0,
            percentage=round((character.hit_points_current / max_hp) * 100.0, 1),
        )

        await self._cache.set(cache_key, hp_status)
        return hp_status

    async def get_inventory(self, name_or_id: str) -> Inventory:
        """Get character inventory with item details.

        Args:
            name_or_id: Character name or ID.

        Returns:
            Inventory with items and equipped slots.

        Raises:
            KeyError: If character is not found.
        """
        cache_key = f"inventory:{name_or_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        character = self._find_character(name_or_id)

        items = [
            InventoryItem(
                name=item.name,
                quantity=item.quantity,
                item_type=item.item_type,
                description=item.description,
                weight=item.weight,
            )
            for item in character.inventory
        ]

        equipped = {
            slot: (item.name if item else None)
            for slot, item in character.equipment.items()
        }

        inventory = Inventory(
            character_name=character.name,
            items=items,
            total_items=sum(i.quantity for i in items),
            equipped=equipped,
        )

        await self._cache.set(cache_key, inventory)
        return inventory

    async def get_conditions(self, name_or_id: str) -> list[Condition]:
        """Get active conditions on a character.

        Currently conditions are not deeply tracked on the Character model,
        so this returns an empty list. Future integration will pull from
        the GameState combat tracking.

        Args:
            name_or_id: Character name or ID.

        Returns:
            List of active Condition objects.

        Raises:
            KeyError: If character is not found.
        """
        cache_key = f"conditions:{name_or_id}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        # Verify character exists
        self._find_character(name_or_id)

        # Currently no per-character condition tracking in the model
        conditions: list[Condition] = []

        await self._cache.set(cache_key, conditions)
        return conditions

    # ------------------------------------------------------------------
    # Combat query methods
    # ------------------------------------------------------------------

    async def get_combat_state(self) -> CombatState:
        """Get current combat status.

        Reads from the campaign's GameState to determine if combat is
        active and returns the current initiative order and conditions.

        Returns:
            CombatState snapshot.
        """
        cache_key = "combat_state"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        gs = self.campaign.game_state

        initiative_order: list[InitiativeEntry] = []
        for entry in gs.initiative_order:
            init_entry = InitiativeEntry(
                name=entry.get("name", "Unknown"),
                initiative=entry.get("initiative", 0),
                is_current=(entry.get("name", "") == gs.current_turn),
                is_player=entry.get("is_player", True),
            )
            initiative_order.append(init_entry)

        combat_state = CombatState(
            is_active=gs.in_combat,
            round_number=gs.current_session if gs.in_combat else 0,
            current_turn=gs.current_turn,
            initiative_order=initiative_order,
            conditions_in_effect={},
        )

        await self._cache.set(cache_key, combat_state)
        return combat_state

    async def get_initiative_order(self) -> list[InitiativeEntry]:
        """Get current initiative order.

        Returns:
            List of InitiativeEntry in initiative order.
        """
        combat = await self.get_combat_state()
        return combat.initiative_order

    async def get_available_actions(self, name_or_id: str) -> list[AvailableAction]:
        """Get available actions for a combatant.

        Returns a standard set of D&D actions. Future versions will
        account for conditions, class features, and spell slots.

        Args:
            name_or_id: Character name or ID.

        Returns:
            List of available actions.
        """
        # Verify character exists
        self._find_character(name_or_id)

        combat = await self.get_combat_state()
        actions: list[AvailableAction] = []

        if not combat.is_active:
            actions.append(AvailableAction(
                name="No Combat",
                action_type="free",
                description="Combat is not currently active.",
            ))
            return actions

        # Standard D&D combat actions
        actions.extend([
            AvailableAction(
                name="Attack",
                action_type="action",
                description="Make a melee or ranged attack.",
            ),
            AvailableAction(
                name="Cast a Spell",
                action_type="action",
                description="Cast a spell with a casting time of 1 action.",
            ),
            AvailableAction(
                name="Dash",
                action_type="action",
                description="Double your movement speed for this turn.",
            ),
            AvailableAction(
                name="Disengage",
                action_type="action",
                description="Your movement doesn't provoke opportunity attacks.",
            ),
            AvailableAction(
                name="Dodge",
                action_type="action",
                description="Attack rolls against you have disadvantage.",
            ),
            AvailableAction(
                name="Help",
                action_type="action",
                description="Give an ally advantage on their next ability check or attack.",
            ),
            AvailableAction(
                name="Hide",
                action_type="action",
                description="Attempt to hide using a Stealth check.",
            ),
            AvailableAction(
                name="Ready",
                action_type="action",
                description="Prepare a reaction for a specified trigger.",
            ),
            AvailableAction(
                name="Use an Object",
                action_type="action",
                description="Interact with an object requiring your action.",
            ),
            AvailableAction(
                name="Movement",
                action_type="movement",
                description="Move up to your speed.",
            ),
        ])

        return actions

    # ------------------------------------------------------------------
    # Rules lookup
    # ------------------------------------------------------------------

    async def lookup_rule(self, query: str) -> RuleResult:
        """Search rulebooks for relevant rules.

        Delegates to the configured rules_lookup_fn if available. Falls
        back to a "no rulebooks" result otherwise.

        Args:
            query: Natural language rules query.

        Returns:
            RuleResult with the search findings.
        """
        cache_key = f"rule:{query.lower().strip()}"
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        if self._rules_lookup_fn is None:
            result = RuleResult(
                query=query,
                found=False,
                rules_text="No rulebook search is configured.",
                source="",
                confidence=0.0,
            )
            await self._cache.set(cache_key, result)
            return result

        try:
            search_results = await self._rules_lookup_fn(query)
            if search_results:
                # Combine top results
                combined_text = "\n\n".join(
                    r.get("content", r.get("text", ""))
                    for r in search_results[:3]
                )
                source = search_results[0].get("source", "rulebook")
                result = RuleResult(
                    query=query,
                    found=True,
                    rules_text=combined_text,
                    source=source,
                    confidence=min(
                        search_results[0].get("score", 0.5), 1.0
                    ),
                )
            else:
                result = RuleResult(
                    query=query,
                    found=False,
                    rules_text="No matching rules found.",
                    source="",
                    confidence=0.0,
                )
        except Exception as e:
            logger.error(f"Rules lookup failed for '{query}': {e}")
            result = RuleResult(
                query=query,
                found=False,
                rules_text=f"Rules lookup error: {e}",
                source="",
                confidence=0.0,
            )

        await self._cache.set(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    async def invalidate_cache(self, pattern: str = "*") -> int:
        """Invalidate cached entries.

        Args:
            pattern: Glob pattern for keys to invalidate. Default '*' clears all.

        Returns:
            Number of entries invalidated.
        """
        count = await self._cache.invalidate(pattern)
        logger.debug(f"Archivist cache invalidated: {count} entries (pattern='{pattern}')")
        return count

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_character(self, name_or_id: str) -> Character:
        """Find a character by name or ID in the campaign.

        Searches by ID first (dict key), then by name (case-insensitive).

        Args:
            name_or_id: Character name or ID string.

        Returns:
            The matching Character.

        Raises:
            KeyError: If no matching character is found.
        """
        # Direct key lookup
        if name_or_id in self.campaign.characters:
            return self.campaign.characters[name_or_id]

        # Name-based lookup (case-insensitive)
        name_lower = name_or_id.lower()
        for key, char in self.campaign.characters.items():
            if char.name.lower() == name_lower:
                return char

        available = [c.name for c in self.campaign.characters.values()]
        raise KeyError(
            f"Character '{name_or_id}' not found. "
            f"Available characters: {available}"
        )

    def _get_first_character_name(self) -> str:
        """Get the name/key of the first character in the campaign.

        Returns:
            Character key string.

        Raises:
            KeyError: If campaign has no characters.
        """
        if not self.campaign.characters:
            raise KeyError("No characters in campaign")
        return next(iter(self.campaign.characters))

    async def _get_first_character_stats(self) -> CharacterStats:
        """Get stats for the first character (convenience for ReAct)."""
        key = self._get_first_character_name()
        return await self.get_character_stats(key)

    async def _get_first_character_hp(self) -> HPStatus:
        """Get HP for the first character (convenience for ReAct)."""
        key = self._get_first_character_name()
        return await self.get_character_hp(key)

    async def _get_first_character_inventory(self) -> Inventory:
        """Get inventory for the first character (convenience for ReAct)."""
        key = self._get_first_character_name()
        return await self.get_inventory(key)

    async def _get_first_character_conditions(self) -> list[Condition]:
        """Get conditions for the first character (convenience for ReAct)."""
        key = self._get_first_character_name()
        return await self.get_conditions(key)

    async def _get_first_character_actions(self) -> list[AvailableAction]:
        """Get available actions for the first character (convenience for ReAct)."""
        key = self._get_first_character_name()
        return await self.get_available_actions(key)


__all__ = [
    "ArchivistAgent",
    "HPStatus",
    "CharacterStats",
    "InventoryItem",
    "Inventory",
    "Condition",
    "InitiativeEntry",
    "CombatState",
    "AvailableAction",
    "RuleResult",
    "QueryResult",
    "QueryType",
    "StateCache",
]
