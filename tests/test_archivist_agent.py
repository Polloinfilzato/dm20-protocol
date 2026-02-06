"""
Unit tests for the ArchivistAgent.

Tests cover:
- Initialization and base class integration
- Character queries (stats, HP, inventory, conditions)
- Combat state queries (initiative, actions)
- Rules lookup with and without configured search function
- StateCache TTL, invalidation, and concurrent access
- Full ReAct cycle
- Error handling for missing characters and campaigns

All tests use mock campaign data; no external API calls are made.
"""

import asyncio
import time
import pytest
from typing import Any

from gamemaster_mcp.claudmaster.base import AgentResponse, AgentRole
from gamemaster_mcp.claudmaster.agents.archivist import (
    ArchivistAgent,
    CharacterStats,
    CombatState,
    HPStatus,
    Inventory,
    InventoryItem,
    Condition,
    InitiativeEntry,
    AvailableAction,
    RuleResult,
    QueryResult,
    QueryType,
    StateCache,
)
from gamemaster_mcp.models import (
    Campaign,
    Character,
    CharacterClass,
    Race,
    GameState,
    Item,
    AbilityScore,
)


# ---------------------------------------------------------------------------
# Mock data helpers
# ---------------------------------------------------------------------------

_SENTINEL = object()


def make_character(
    name: str = "Thorin",
    class_name: str = "Fighter",
    level: int = 5,
    hp_current: int = 40,
    hp_max: int = 50,
    hp_temp: int = 0,
    ac: int = 18,
    items: list[Item] | None | object = _SENTINEL,
) -> Character:
    """Create a test character with sensible defaults."""
    if items is _SENTINEL:
        inventory = [
            Item(name="Longsword", item_type="weapon", weight=3.0),
            Item(name="Shield", item_type="armor", weight=6.0),
            Item(name="Healing Potion", item_type="consumable", quantity=2, weight=0.5),
        ]
    else:
        inventory = items if items is not None else []

    return Character(
        name=name,
        character_class=CharacterClass(name=class_name, level=level, hit_dice="1d10"),
        race=Race(name="Dwarf", subrace="Mountain"),
        background="Soldier",
        alignment="Lawful Good",
        abilities={
            "strength": AbilityScore(score=18),
            "dexterity": AbilityScore(score=12),
            "constitution": AbilityScore(score=16),
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=14),
            "charisma": AbilityScore(score=8),
        },
        armor_class=ac,
        hit_points_max=hp_max,
        hit_points_current=hp_current,
        temporary_hit_points=hp_temp,
        proficiency_bonus=3,
        inventory=inventory,
    )


def make_campaign(
    characters: dict[str, Character] | None = None,
    in_combat: bool = False,
    initiative_order: list[dict[str, Any]] | None = None,
    current_turn: str | None = None,
) -> Campaign:
    """Create a test campaign with sensible defaults."""
    if characters is None:
        char = make_character()
        characters = {char.id: char}

    gs = GameState(
        campaign_name="Test Campaign",
        in_combat=in_combat,
        initiative_order=initiative_order or [],
        current_turn=current_turn,
    )

    return Campaign(
        name="Test Campaign",
        description="A campaign for testing the archivist agent.",
        game_state=gs,
        characters=characters,
    )


# ---------------------------------------------------------------------------
# Mock rules lookup function
# ---------------------------------------------------------------------------

async def mock_rules_lookup(query: str) -> list[dict[str, Any]]:
    """Simulated rulebook search returning canned results."""
    if "grapple" in query.lower():
        return [
            {
                "content": "To grapple, make a Strength (Athletics) check contested by the target's Strength (Athletics) or Dexterity (Acrobatics) check.",
                "source": "PHB p.195",
                "score": 0.95,
            }
        ]
    return []


async def failing_rules_lookup(query: str) -> list[dict[str, Any]]:
    """Simulated rulebook search that always raises."""
    raise RuntimeError("Search index unavailable")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def character() -> Character:
    return make_character()


@pytest.fixture
def campaign(character: Character) -> Campaign:
    return make_campaign(characters={character.id: character})


@pytest.fixture
def combat_campaign(character: Character) -> Campaign:
    return make_campaign(
        characters={character.id: character},
        in_combat=True,
        initiative_order=[
            {"name": "Thorin", "initiative": 18, "is_player": True},
            {"name": "Goblin", "initiative": 12, "is_player": False},
        ],
        current_turn="Thorin",
    )


@pytest.fixture
def archivist(campaign: Campaign) -> ArchivistAgent:
    return ArchivistAgent(campaign=campaign)


@pytest.fixture
def archivist_with_rules(campaign: Campaign) -> ArchivistAgent:
    return ArchivistAgent(campaign=campaign, rules_lookup_fn=mock_rules_lookup)


@pytest.fixture
def combat_archivist(combat_campaign: Campaign) -> ArchivistAgent:
    return ArchivistAgent(campaign=combat_campaign)


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestArchivistInit:
    """Tests for ArchivistAgent initialization."""

    def test_default_init(self, campaign: Campaign) -> None:
        agent = ArchivistAgent(campaign=campaign)
        assert agent.name == "archivist"
        assert agent.role == AgentRole.ARCHIVIST
        assert agent.campaign is campaign

    def test_custom_cache_ttl(self, campaign: Campaign) -> None:
        agent = ArchivistAgent(campaign=campaign, cache_ttl=10.0)
        assert agent._cache.ttl == 10.0

    def test_with_rules_lookup(self, campaign: Campaign) -> None:
        agent = ArchivistAgent(campaign=campaign, rules_lookup_fn=mock_rules_lookup)
        assert agent._rules_lookup_fn is mock_rules_lookup


# ---------------------------------------------------------------------------
# Character queries
# ---------------------------------------------------------------------------

class TestGetCharacterStats:
    """Tests for get_character_stats()."""

    def test_stats_by_id(self, archivist: ArchivistAgent, character: Character) -> None:
        stats = asyncio.run(archivist.get_character_stats(character.id))
        assert isinstance(stats, CharacterStats)
        assert stats.name == "Thorin"
        assert stats.race == "Dwarf"
        assert stats.character_class == "Fighter"
        assert stats.level == 5
        assert stats.hp_current == 40
        assert stats.hp_max == 50
        assert stats.armor_class == 18
        assert stats.proficiency_bonus == 3

    def test_stats_by_name(self, archivist: ArchivistAgent) -> None:
        stats = asyncio.run(archivist.get_character_stats("Thorin"))
        assert stats.name == "Thorin"

    def test_stats_by_name_case_insensitive(self, archivist: ArchivistAgent) -> None:
        stats = asyncio.run(archivist.get_character_stats("thorin"))
        assert stats.name == "Thorin"

    def test_stats_not_found(self, archivist: ArchivistAgent) -> None:
        with pytest.raises(KeyError, match="not found"):
            asyncio.run(archivist.get_character_stats("NonExistent"))

    def test_ability_scores(self, archivist: ArchivistAgent) -> None:
        stats = asyncio.run(archivist.get_character_stats("Thorin"))
        assert stats.ability_scores["strength"] == 18
        assert stats.ability_scores["dexterity"] == 12
        assert stats.ability_scores["charisma"] == 8

    def test_stats_cached(self, archivist: ArchivistAgent) -> None:
        stats1 = asyncio.run(archivist.get_character_stats("Thorin"))
        stats2 = asyncio.run(archivist.get_character_stats("Thorin"))
        # Should return identical object from cache
        assert stats1 is stats2


class TestGetCharacterHP:
    """Tests for get_character_hp()."""

    def test_hp_status(self, archivist: ArchivistAgent) -> None:
        hp = asyncio.run(archivist.get_character_hp("Thorin"))
        assert isinstance(hp, HPStatus)
        assert hp.name == "Thorin"
        assert hp.hp_current == 40
        assert hp.hp_max == 50
        assert hp.hp_temp == 0
        assert hp.is_conscious is True
        assert hp.percentage == 80.0

    def test_hp_unconscious(self, campaign: Campaign) -> None:
        char = make_character(name="Wounded", hp_current=0, hp_max=30)
        campaign.characters[char.id] = char
        agent = ArchivistAgent(campaign=campaign)
        hp = asyncio.run(agent.get_character_hp("Wounded"))
        assert hp.is_conscious is False
        assert hp.percentage == 0.0

    def test_hp_with_temp(self, campaign: Campaign) -> None:
        char = make_character(name="Buffed", hp_current=30, hp_max=30, hp_temp=10)
        campaign.characters[char.id] = char
        agent = ArchivistAgent(campaign=campaign)
        hp = asyncio.run(agent.get_character_hp("Buffed"))
        assert hp.hp_temp == 10
        assert hp.percentage == 100.0


class TestGetInventory:
    """Tests for get_inventory()."""

    def test_inventory_items(self, archivist: ArchivistAgent) -> None:
        inv = asyncio.run(archivist.get_inventory("Thorin"))
        assert isinstance(inv, Inventory)
        assert inv.character_name == "Thorin"
        assert len(inv.items) == 3
        assert inv.total_items == 4  # Longsword(1) + Shield(1) + Potion(2)

    def test_inventory_item_types(self, archivist: ArchivistAgent) -> None:
        inv = asyncio.run(archivist.get_inventory("Thorin"))
        item_names = {i.name for i in inv.items}
        assert "Longsword" in item_names
        assert "Shield" in item_names
        assert "Healing Potion" in item_names

    def test_empty_inventory(self, campaign: Campaign) -> None:
        char = make_character(name="Empty", items=[])
        campaign.characters[char.id] = char
        agent = ArchivistAgent(campaign=campaign)
        inv = asyncio.run(agent.get_inventory("Empty"))
        assert len(inv.items) == 0
        assert inv.total_items == 0


class TestGetConditions:
    """Tests for get_conditions()."""

    def test_conditions_empty(self, archivist: ArchivistAgent) -> None:
        conditions = asyncio.run(archivist.get_conditions("Thorin"))
        assert isinstance(conditions, list)
        assert len(conditions) == 0

    def test_conditions_not_found(self, archivist: ArchivistAgent) -> None:
        with pytest.raises(KeyError, match="not found"):
            asyncio.run(archivist.get_conditions("Ghost"))


# ---------------------------------------------------------------------------
# Combat queries
# ---------------------------------------------------------------------------

class TestGetCombatState:
    """Tests for get_combat_state()."""

    def test_no_combat(self, archivist: ArchivistAgent) -> None:
        combat = asyncio.run(archivist.get_combat_state())
        assert isinstance(combat, CombatState)
        assert combat.is_active is False
        assert combat.current_turn is None
        assert len(combat.initiative_order) == 0

    def test_active_combat(self, combat_archivist: ArchivistAgent) -> None:
        combat = asyncio.run(combat_archivist.get_combat_state())
        assert combat.is_active is True
        assert combat.current_turn == "Thorin"
        assert len(combat.initiative_order) == 2

    def test_initiative_entries(self, combat_archivist: ArchivistAgent) -> None:
        combat = asyncio.run(combat_archivist.get_combat_state())
        thorin = next(e for e in combat.initiative_order if e.name == "Thorin")
        goblin = next(e for e in combat.initiative_order if e.name == "Goblin")
        assert thorin.initiative == 18
        assert thorin.is_current is True
        assert thorin.is_player is True
        assert goblin.initiative == 12
        assert goblin.is_current is False
        assert goblin.is_player is False


class TestGetInitiativeOrder:
    """Tests for get_initiative_order()."""

    def test_initiative_order(self, combat_archivist: ArchivistAgent) -> None:
        order = asyncio.run(combat_archivist.get_initiative_order())
        assert len(order) == 2
        assert order[0].name == "Thorin"
        assert order[1].name == "Goblin"

    def test_initiative_order_no_combat(self, archivist: ArchivistAgent) -> None:
        order = asyncio.run(archivist.get_initiative_order())
        assert len(order) == 0


class TestGetAvailableActions:
    """Tests for get_available_actions()."""

    def test_actions_in_combat(self, combat_archivist: ArchivistAgent) -> None:
        actions = asyncio.run(combat_archivist.get_available_actions("Thorin"))
        assert len(actions) > 0
        action_names = {a.name for a in actions}
        assert "Attack" in action_names
        assert "Dash" in action_names
        assert "Dodge" in action_names

    def test_actions_not_in_combat(self, archivist: ArchivistAgent) -> None:
        actions = asyncio.run(archivist.get_available_actions("Thorin"))
        assert len(actions) == 1
        assert actions[0].name == "No Combat"

    def test_actions_character_not_found(self, combat_archivist: ArchivistAgent) -> None:
        with pytest.raises(KeyError, match="not found"):
            asyncio.run(combat_archivist.get_available_actions("Ghost"))

    def test_action_types(self, combat_archivist: ArchivistAgent) -> None:
        actions = asyncio.run(combat_archivist.get_available_actions("Thorin"))
        action_types = {a.action_type for a in actions}
        assert "action" in action_types
        assert "movement" in action_types


# ---------------------------------------------------------------------------
# Rules lookup
# ---------------------------------------------------------------------------

class TestLookupRule:
    """Tests for lookup_rule()."""

    def test_no_rulebook_configured(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.lookup_rule("grapple rules"))
        assert isinstance(result, RuleResult)
        assert result.found is False
        assert "no rulebook search" in result.rules_text.lower()

    def test_successful_lookup(self, archivist_with_rules: ArchivistAgent) -> None:
        result = asyncio.run(archivist_with_rules.lookup_rule("grapple rules"))
        assert result.found is True
        assert "Athletics" in result.rules_text
        assert result.source == "PHB p.195"
        assert result.confidence > 0.9

    def test_no_results(self, archivist_with_rules: ArchivistAgent) -> None:
        result = asyncio.run(archivist_with_rules.lookup_rule("flying spaghetti monster"))
        assert result.found is False
        assert "No matching" in result.rules_text

    def test_failing_lookup(self, campaign: Campaign) -> None:
        agent = ArchivistAgent(campaign=campaign, rules_lookup_fn=failing_rules_lookup)
        result = asyncio.run(agent.lookup_rule("anything"))
        assert result.found is False
        assert "error" in result.rules_text.lower()

    def test_lookup_cached(self, archivist_with_rules: ArchivistAgent) -> None:
        r1 = asyncio.run(archivist_with_rules.lookup_rule("grapple rules"))
        r2 = asyncio.run(archivist_with_rules.lookup_rule("grapple rules"))
        assert r1 is r2  # Same cached object


# ---------------------------------------------------------------------------
# StateCache
# ---------------------------------------------------------------------------

class TestStateCache:
    """Tests for the StateCache class."""

    def test_set_and_get(self) -> None:
        cache = StateCache(ttl_seconds=5.0)
        asyncio.run(cache.set("key1", "value1"))
        result = asyncio.run(cache.get("key1"))
        assert result == "value1"

    def test_get_missing_key(self) -> None:
        cache = StateCache()
        result = asyncio.run(cache.get("nonexistent"))
        assert result is None

    def test_ttl_expiration(self) -> None:
        cache = StateCache(ttl_seconds=0.05)  # 50ms
        asyncio.run(cache.set("key1", "value1"))
        time.sleep(0.1)  # Wait for expiration
        result = asyncio.run(cache.get("key1"))
        assert result is None

    def test_invalidate_all(self) -> None:
        cache = StateCache()

        async def fill_and_clear():
            await cache.set("a", 1)
            await cache.set("b", 2)
            await cache.set("c", 3)
            count = await cache.invalidate("*")
            return count

        count = asyncio.run(fill_and_clear())
        assert count == 3
        assert asyncio.run(cache.get("a")) is None

    def test_invalidate_pattern(self) -> None:
        cache = StateCache()

        async def fill_and_clear():
            await cache.set("stats:Thorin", 1)
            await cache.set("stats:Elara", 2)
            await cache.set("hp:Thorin", 3)
            count = await cache.invalidate("stats:*")
            return count, await cache.get("hp:Thorin")

        count, hp = asyncio.run(fill_and_clear())
        assert count == 2
        assert hp == 3  # hp entry not affected

    def test_get_or_fetch(self) -> None:
        cache = StateCache()
        call_count = 0

        async def fetcher():
            nonlocal call_count
            call_count += 1
            return "computed_value"

        async def run_test():
            v1 = await cache.get_or_fetch("key", fetcher)
            v2 = await cache.get_or_fetch("key", fetcher)
            return v1, v2

        v1, v2 = asyncio.run(run_test())
        assert v1 == "computed_value"
        assert v2 == "computed_value"
        assert call_count == 1  # Fetcher called only once

    def test_size(self) -> None:
        cache = StateCache()

        async def run_test():
            await cache.set("a", 1)
            await cache.set("b", 2)
            return await cache.size()

        assert asyncio.run(run_test()) == 2

    def test_concurrent_access(self) -> None:
        """Test that concurrent cache access does not corrupt state."""
        cache = StateCache(ttl_seconds=10.0)

        async def writer(key: str, value: int):
            await cache.set(key, value)

        async def reader(key: str) -> Any:
            return await cache.get(key)

        async def run_test():
            # Write many keys concurrently
            write_tasks = [writer(f"key_{i}", i) for i in range(50)]
            await asyncio.gather(*write_tasks)

            # Read them all back concurrently
            read_tasks = [reader(f"key_{i}") for i in range(50)]
            results = await asyncio.gather(*read_tasks)
            return results

        results = asyncio.run(run_test())
        for i, result in enumerate(results):
            assert result == i, f"key_{i} expected {i}, got {result}"


# ---------------------------------------------------------------------------
# ReAct: reason()
# ---------------------------------------------------------------------------

class TestReason:
    """Tests for the reason() phase."""

    def test_stats_query(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.reason({
            "player_input": "Show me my character stats",
            "intent": {"intent_type": "system"},
            "game_state": {"in_combat": False},
        }))
        assert QueryType.CHARACTER_STATS in result

    def test_hp_query(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.reason({
            "player_input": "How many hit points do I have?",
            "intent": {},
            "game_state": {"in_combat": False},
        }))
        assert QueryType.CHARACTER_HP in result

    def test_inventory_query(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.reason({
            "player_input": "Check my inventory",
            "intent": {},
            "game_state": {"in_combat": False},
        }))
        assert QueryType.INVENTORY in result

    def test_combat_query(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.reason({
            "player_input": "attack the goblin",
            "intent": {"intent_type": "combat"},
            "game_state": {"in_combat": True},
        }))
        assert QueryType.COMBAT_STATE in result

    def test_initiative_query(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.reason({
            "player_input": "What is the initiative order?",
            "intent": {"intent_type": "combat"},
            "game_state": {"in_combat": True},
        }))
        assert QueryType.INITIATIVE_ORDER in result

    def test_actions_query(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.reason({
            "player_input": "What can I do on my turn? What are my options?",
            "intent": {"intent_type": "combat"},
            "game_state": {"in_combat": True},
        }))
        assert QueryType.AVAILABLE_ACTIONS in result

    def test_rule_query(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.reason({
            "player_input": "How does grappling work?",
            "intent": {},
            "game_state": {"in_combat": False},
        }))
        assert QueryType.RULE_LOOKUP in result

    def test_condition_query(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.reason({
            "player_input": "Am I poisoned? What conditions do I have?",
            "intent": {},
            "game_state": {"in_combat": False},
        }))
        assert QueryType.CONDITIONS in result

    def test_system_intent_fallback(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.reason({
            "player_input": "show status",
            "intent": {"intent_type": "system"},
            "game_state": {"in_combat": False},
        }))
        assert QueryType.CHARACTER_STATS in result


# ---------------------------------------------------------------------------
# ReAct: act()
# ---------------------------------------------------------------------------

class TestAct:
    """Tests for the act() phase."""

    def test_act_character_stats(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.act(
            f"query:{QueryType.CHARACTER_STATS}|Character statistics requested."
        ))
        assert isinstance(result, QueryResult)
        assert result.success is True
        assert isinstance(result.data, CharacterStats)

    def test_act_combat_state(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.act(
            f"query:{QueryType.COMBAT_STATE}|Combat state requested."
        ))
        assert isinstance(result, QueryResult)
        assert result.success is True
        assert isinstance(result.data, CombatState)

    def test_act_hp(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.act(
            f"query:{QueryType.CHARACTER_HP}|HP status requested."
        ))
        assert isinstance(result, QueryResult)
        assert result.success is True
        assert isinstance(result.data, HPStatus)

    def test_act_inventory(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.act(
            f"query:{QueryType.INVENTORY}|Inventory requested."
        ))
        assert isinstance(result, QueryResult)
        assert result.success is True
        assert isinstance(result.data, Inventory)

    def test_act_rule_lookup(self, archivist_with_rules: ArchivistAgent) -> None:
        result = asyncio.run(archivist_with_rules.act(
            f"query:{QueryType.RULE_LOOKUP}|query_text=grapple rules|Rules lookup."
        ))
        assert isinstance(result, QueryResult)
        assert result.success is True
        assert isinstance(result.data, RuleResult)
        assert result.data.found is True

    def test_act_unknown_type(self, archivist: ArchivistAgent) -> None:
        result = asyncio.run(archivist.act("some unknown reasoning"))
        assert isinstance(result, QueryResult)
        assert result.success is True  # Falls back to combat state

    def test_act_error_handling(self) -> None:
        """Test act with campaign that has no characters."""
        campaign = make_campaign(characters={})
        agent = ArchivistAgent(campaign=campaign)
        result = asyncio.run(agent.act(
            f"query:{QueryType.CHARACTER_STATS}|Stats requested."
        ))
        assert result.success is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# ReAct: observe()
# ---------------------------------------------------------------------------

class TestObserve:
    """Tests for the observe() phase."""

    def test_observe_combat_state(self, archivist: ArchivistAgent) -> None:
        result = QueryResult(
            query_type=QueryType.COMBAT_STATE,
            success=True,
            data=CombatState(is_active=True, round_number=3, current_turn="Thorin"),
        )
        obs = asyncio.run(archivist.observe(result))
        assert obs["success"] is True
        assert obs["in_combat"] is True
        assert obs["combat_round"] == 3
        assert obs["current_turn"] == "Thorin"

    def test_observe_hp(self, archivist: ArchivistAgent) -> None:
        result = QueryResult(
            query_type=QueryType.CHARACTER_HP,
            success=True,
            data=HPStatus(
                name="Thorin", hp_current=0, hp_max=50, hp_temp=0,
                is_conscious=False, percentage=0.0,
            ),
        )
        obs = asyncio.run(archivist.observe(result))
        assert obs["unconscious"] is True

    def test_observe_error(self, archivist: ArchivistAgent) -> None:
        result = QueryResult(
            query_type=QueryType.CHARACTER_STATS,
            success=False,
            error="Character not found",
        )
        obs = asyncio.run(archivist.observe(result))
        assert obs["success"] is False
        assert obs["error"] == "Character not found"

    def test_observe_unexpected_type(self, archivist: ArchivistAgent) -> None:
        obs = asyncio.run(archivist.observe("not a QueryResult"))
        assert obs["success"] is False

    def test_observe_stats(self, archivist: ArchivistAgent) -> None:
        result = QueryResult(
            query_type=QueryType.CHARACTER_STATS,
            success=True,
            data=CharacterStats(
                name="Thorin", race="Dwarf", character_class="Fighter",
                level=5, hp_current=40, hp_max=50, armor_class=18,
            ),
        )
        obs = asyncio.run(archivist.observe(result))
        assert obs["character_name"] == "Thorin"
        assert obs["level"] == 5
        assert obs["class"] == "Fighter"


# ---------------------------------------------------------------------------
# Full ReAct cycle
# ---------------------------------------------------------------------------

class TestFullCycle:
    """Tests for the complete run() cycle."""

    def test_run_returns_agent_response(self, archivist: ArchivistAgent) -> None:
        context = {
            "player_input": "Show me my stats",
            "intent": {"intent_type": "system"},
            "game_state": {"in_combat": False},
        }
        response = asyncio.run(archivist.run(context))
        assert isinstance(response, AgentResponse)
        assert response.agent_name == "archivist"
        assert response.agent_role == AgentRole.ARCHIVIST

    def test_run_combat_context(self, combat_archivist: ArchivistAgent) -> None:
        context = {
            "player_input": "I attack the goblin",
            "intent": {"intent_type": "combat"},
            "game_state": {"in_combat": True},
        }
        response = asyncio.run(combat_archivist.run(context))
        assert isinstance(response, AgentResponse)
        assert response.observations.get("in_combat") is True

    def test_run_hp_query(self, archivist: ArchivistAgent) -> None:
        context = {
            "player_input": "How many hit points do I have left?",
            "intent": {},
            "game_state": {"in_combat": False},
        }
        response = asyncio.run(archivist.run(context))
        assert isinstance(response, AgentResponse)
        assert response.observations.get("hp_percentage") is not None

    def test_run_inventory_query(self, archivist: ArchivistAgent) -> None:
        context = {
            "player_input": "Check my inventory",
            "intent": {},
            "game_state": {"in_combat": False},
        }
        response = asyncio.run(archivist.run(context))
        assert isinstance(response, AgentResponse)
        assert response.observations.get("success") is True

    def test_run_rule_lookup(self, archivist_with_rules: ArchivistAgent) -> None:
        context = {
            "player_input": "How does grappling work? What are the rules?",
            "intent": {},
            "game_state": {"in_combat": False},
        }
        response = asyncio.run(archivist_with_rules.run(context))
        assert isinstance(response, AgentResponse)
        assert response.observations.get("success") is True


# ---------------------------------------------------------------------------
# Cache invalidation via agent
# ---------------------------------------------------------------------------

class TestCacheInvalidation:
    """Tests for cache invalidation through the agent."""

    def test_invalidate_all(self, archivist: ArchivistAgent) -> None:
        # Populate cache
        asyncio.run(archivist.get_character_stats("Thorin"))
        asyncio.run(archivist.get_character_hp("Thorin"))

        count = asyncio.run(archivist.invalidate_cache("*"))
        assert count >= 2

    def test_invalidate_pattern(self, archivist: ArchivistAgent) -> None:
        # Populate cache
        asyncio.run(archivist.get_character_stats("Thorin"))
        asyncio.run(archivist.get_character_hp("Thorin"))

        count = asyncio.run(archivist.invalidate_cache("stats:*"))
        assert count == 1

    def test_fresh_data_after_invalidation(self, archivist: ArchivistAgent) -> None:
        # Get initial stats
        stats1 = asyncio.run(archivist.get_character_stats("Thorin"))

        # Modify the character's HP
        char = archivist._find_character("Thorin")
        char.hit_points_current = 10

        # Cached version still has old HP
        stats_cached = asyncio.run(archivist.get_character_stats("Thorin"))
        assert stats_cached.hp_current == 40  # Old value from cache

        # Invalidate and re-fetch
        asyncio.run(archivist.invalidate_cache("stats:*"))
        stats_fresh = asyncio.run(archivist.get_character_stats("Thorin"))
        assert stats_fresh.hp_current == 10  # New value


# ---------------------------------------------------------------------------
# Multiple characters
# ---------------------------------------------------------------------------

class TestMultipleCharacters:
    """Tests with multiple characters in the campaign."""

    def test_multiple_characters(self) -> None:
        thorin = make_character(name="Thorin", class_name="Fighter", hp_current=40)
        elara = make_character(name="Elara", class_name="Wizard", hp_current=20, hp_max=25, ac=12)

        campaign = make_campaign(characters={
            thorin.id: thorin,
            elara.id: elara,
        })
        agent = ArchivistAgent(campaign=campaign)

        thorin_stats = asyncio.run(agent.get_character_stats("Thorin"))
        elara_stats = asyncio.run(agent.get_character_stats("Elara"))

        assert thorin_stats.name == "Thorin"
        assert thorin_stats.character_class == "Fighter"
        assert elara_stats.name == "Elara"
        assert elara_stats.character_class == "Wizard"
        assert elara_stats.armor_class == 12

    def test_hp_for_multiple(self) -> None:
        thorin = make_character(name="Thorin", hp_current=40, hp_max=50)
        elara = make_character(name="Elara", hp_current=5, hp_max=25)

        campaign = make_campaign(characters={
            thorin.id: thorin,
            elara.id: elara,
        })
        agent = ArchivistAgent(campaign=campaign)

        thorin_hp = asyncio.run(agent.get_character_hp("Thorin"))
        elara_hp = asyncio.run(agent.get_character_hp("Elara"))

        assert thorin_hp.percentage == 80.0
        assert elara_hp.percentage == 20.0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests."""

    def test_empty_campaign(self) -> None:
        campaign = make_campaign(characters={})
        agent = ArchivistAgent(campaign=campaign)

        # Combat state should still work
        combat = asyncio.run(agent.get_combat_state())
        assert combat.is_active is False

    def test_character_with_no_items(self) -> None:
        char = make_character(name="Naked", items=[])
        campaign = make_campaign(characters={char.id: char})
        agent = ArchivistAgent(campaign=campaign)

        inv = asyncio.run(agent.get_inventory("Naked"))
        assert inv.total_items == 0

    def test_zero_max_hp(self) -> None:
        """Ensure no division by zero when max HP is 0 (edge case)."""
        char = make_character(name="ZeroHP", hp_current=0, hp_max=0)
        # Pydantic field says hit_points_max: int = 1, so 0 is technically
        # possible if set directly. The code guards with max(hp_max, 1).
        char.hit_points_max = 0
        campaign = make_campaign(characters={char.id: char})
        agent = ArchivistAgent(campaign=campaign)

        hp = asyncio.run(agent.get_character_hp("ZeroHP"))
        assert hp.percentage == 0.0  # No crash
