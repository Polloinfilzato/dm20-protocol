# Integrations Roadmap

> Inspired by [mnehmos.rpg.mcp](https://github.com/Mnehmos/mnehmos.rpg.mcp) - A rules-enforced RPG backend with 28 consolidated tools.

This document tracks potential integrations to enhance gamemaster-mcp with features from other RPG MCP projects.

## Current State Analysis

**gamemaster-mcp** (49 tools) is primarily a **campaign tracker** that helps manage D&D campaigns, characters, NPCs, locations, quests, and sessions. It excels at:
- ✅ Rulebook management (SRD + Custom + PDF Library)
- ✅ Campaign state persistence
- ✅ Session notes and event tracking

**Gap identified**: Core D&D mechanics (combat resolution, rest mechanics, party management) are not automated.

---

## High Priority Integrations

### 1. Party Management

**Status**: 🔴 Not Started
**Effort**: Medium (M)
**Files to create/modify**: `models.py`, `storage.py`, `main.py`

#### Description
Manage adventuring parties as a unit, enabling shared resources, marching order, and group dynamics.

#### Proposed Tools
```python
@mcp.tool
def create_party(name: str, description: str = "") -> str:
    """Create a new adventuring party."""

@mcp.tool
def add_party_member(party_id: str, character_id: str, role: str = "member") -> str:
    """Add a character to a party. Roles: leader, member, npc_ally."""

@mcp.tool
def remove_party_member(party_id: str, character_id: str) -> str:
    """Remove a character from a party."""

@mcp.tool
def set_party_leader(party_id: str, character_id: str) -> str:
    """Set the party leader."""

@mcp.tool
def get_party_context(party_id: str) -> str:
    """Get full party context: members, inventory, current location, active quests."""

@mcp.tool
def set_marching_order(party_id: str, order: list[str]) -> str:
    """Set marching order for travel and dungeon exploration."""
```

#### Data Model
```python
@dataclass
class Party:
    id: str
    name: str
    description: str
    leader_id: str | None
    member_ids: list[str]
    shared_inventory: list[Item]
    shared_gold: int
    marching_order: list[str]
    current_location_id: str | None
    created_at: datetime
    updated_at: datetime
```

#### Why This Matters
- D&D is a group game; parties are fundamental
- Enables shared inventory and resources
- Marching order affects surprise and trap encounters
- Party context helps LLM understand group dynamics

---

### 2. Combat Actions

**Status**: 🔴 Not Started
**Effort**: Large (L)
**Files to create/modify**: `combat.py` (new), `models.py`, `storage.py`, `main.py`

#### Description
Extend the combat tracker to resolve actions mechanically. Currently, combat only tracks turns; this would add attack resolution, damage calculation, and action economy.

#### Proposed Tools
```python
@mcp.tool
def combat_attack(
    attacker_id: str,
    target_id: str,
    weapon: str | None = None,
    advantage: bool = False,
    disadvantage: bool = False
) -> str:
    """
    Resolve an attack action.
    Rolls to hit, compares to AC, rolls damage if hit.
    Returns detailed breakdown.
    """

@mcp.tool
def combat_cast_spell(
    caster_id: str,
    spell_name: str,
    target_ids: list[str],
    slot_level: int | None = None
) -> str:
    """
    Cast a spell in combat.
    Handles attack rolls or saving throws, damage/effects.
    Tracks spell slot usage and concentration.
    """

@mcp.tool
def combat_move(
    character_id: str,
    distance: int,
    direction: str | None = None
) -> str:
    """Move a character, tracking movement speed usage."""

@mcp.tool
def combat_action(
    character_id: str,
    action: Literal["dash", "dodge", "disengage", "help", "hide", "ready", "search", "use_object"]
) -> str:
    """Execute a standard action that doesn't require resolution."""

@mcp.tool
def combat_saving_throw(
    character_id: str,
    ability: Literal["str", "dex", "con", "int", "wis", "cha"],
    dc: int
) -> str:
    """Roll a saving throw against a DC."""
```

#### Combat Resolution Engine
```python
class CombatResolver:
    def resolve_attack(self, attacker: Character, target: Character, weapon: Weapon) -> AttackResult:
        # Roll d20 + attack modifier
        roll = self.roll_d20(advantage, disadvantage)
        attack_mod = self._calculate_attack_modifier(attacker, weapon)
        total = roll + attack_mod

        # Compare to AC
        hits = total >= target.armor_class

        # Roll damage if hit
        damage = 0
        if hits:
            damage = self._roll_damage(weapon, critical=(roll == 20))

        return AttackResult(roll, attack_mod, total, hits, damage)
```

#### Architectural Decision Required
> **Question**: Should gamemaster-mcp become a rules engine (strict enforcement) or remain a flexible tracker (DM decides)?

| Approach | Pros | Cons |
|----------|------|------|
| **Strict Engine** | Consistent rules, no cheating | Less flexibility, may conflict with homebrew |
| **Flexible Tracker** | DM has final say, homebrew friendly | LLM might make mistakes, less automation |
| **Hybrid** | Optional enforcement, best of both | More complex implementation |

**Recommendation**: Hybrid approach with `strict_mode` flag.

---

### 3. Rest Mechanics

**Status**: 🔴 Not Started
**Effort**: Small (S)
**Files to create/modify**: `rest.py` (new), `models.py`, `main.py`

#### Description
Implement short and long rest mechanics that restore HP, spell slots, and class features.

#### Proposed Tools
```python
@mcp.tool
def short_rest(
    character_ids: list[str],
    hit_dice_to_spend: dict[str, int] | None = None
) -> str:
    """
    Take a short rest (1 hour).
    - Spend hit dice to recover HP
    - Recover some class features (e.g., Fighter's Second Wind)
    - Warlocks recover spell slots
    """

@mcp.tool
def long_rest(character_ids: list[str]) -> str:
    """
    Take a long rest (8 hours).
    - Recover all HP
    - Recover all spell slots
    - Recover all class features
    - Recover up to half max hit dice
    - Reset death saves
    """
```

#### Recovery Logic
```python
class RestManager:
    def long_rest(self, character: Character) -> RestResult:
        changes = []

        # Full HP recovery
        old_hp = character.current_hp
        character.current_hp = character.max_hp
        changes.append(f"HP: {old_hp} → {character.max_hp}")

        # Spell slot recovery (if spellcaster)
        if character.spell_slots:
            for level, slots in character.spell_slots.items():
                slots.current = slots.maximum
            changes.append("All spell slots recovered")

        # Hit dice recovery (half max, rounded down)
        hd_recovered = character.level // 2 or 1
        character.hit_dice.current = min(
            character.hit_dice.current + hd_recovered,
            character.hit_dice.maximum
        )
        changes.append(f"Recovered {hd_recovered} hit dice")

        return RestResult(character.id, "long", changes)
```

#### Prerequisites
- Character model needs: `current_hp`, `max_hp`, `hit_dice`, `spell_slots`
- These may already exist or need to be added

---

## Medium Priority Integrations

### 4. Advanced Inventory Management

**Status**: 🔴 Not Started
**Effort**: Medium (M)

#### Current State
Only `add_item_to_character` exists. No equip, use, or transfer.

#### Proposed Tools
```python
@mcp.tool
def equip_item(character_id: str, item_id: str, slot: str) -> str:
    """Equip an item to a slot (main_hand, off_hand, armor, etc.)."""

@mcp.tool
def unequip_item(character_id: str, slot: str) -> str:
    """Unequip an item from a slot."""

@mcp.tool
def use_item(character_id: str, item_id: str, target_id: str | None = None) -> str:
    """Use a consumable item (potion, scroll, etc.)."""

@mcp.tool
def transfer_item(
    from_id: str,
    to_id: str,
    item_id: str,
    quantity: int = 1
) -> str:
    """Transfer item between characters or to/from party inventory."""

@mcp.tool
def drop_item(character_id: str, item_id: str) -> str:
    """Drop an item at current location."""
```

---

### 5. Concentration Management

**Status**: 🔴 Not Started
**Effort**: Small (S)

#### Description
Track concentration spells and handle concentration saves when taking damage.

#### Proposed Tools
```python
@mcp.tool
def check_concentration(character_id: str, damage_taken: int) -> str:
    """
    Roll concentration save after taking damage.
    DC = max(10, damage_taken // 2)
    """

@mcp.tool
def break_concentration(character_id: str) -> str:
    """Manually break concentration (casting new spell, incapacitated, etc.)."""

@mcp.tool
def get_concentration_status(character_id: str) -> str:
    """Check if character is concentrating and on what spell."""
```

#### Data Model Addition
```python
@dataclass
class ConcentrationState:
    active: bool
    spell_name: str | None
    started_at: datetime | None
    duration_remaining: int | None  # rounds
```

---

### 6. NPC Relationships & Memory

**Status**: 🔴 Not Started
**Effort**: Medium (M)

#### Description
Track NPC attitudes toward party members and remember past interactions.

#### Proposed Tools
```python
@mcp.tool
def get_npc_relationship(npc_id: str, character_id: str) -> str:
    """Get NPC's attitude and history with a character."""

@mcp.tool
def update_npc_relationship(
    npc_id: str,
    character_id: str,
    attitude_change: int,
    reason: str
) -> str:
    """
    Update relationship. Attitude scale: -100 (hostile) to +100 (allied).
    """

@mcp.tool
def record_npc_memory(npc_id: str, memory: str, importance: int = 5) -> str:
    """Record something the NPC witnessed or learned."""

@mcp.tool
def get_npc_memories(npc_id: str, relevance_filter: str | None = None) -> str:
    """Retrieve NPC memories, optionally filtered by relevance."""
```

#### Data Model Addition
```python
@dataclass
class NPCRelationship:
    npc_id: str
    character_id: str
    attitude: int  # -100 to +100
    history: list[str]
    last_interaction: datetime

@dataclass
class NPCMemory:
    id: str
    npc_id: str
    content: str
    importance: int  # 1-10
    timestamp: datetime
    tags: list[str]
```

---

## Low Priority / Nice-to-Have

### 7. Spatial/Dungeon Management
- Procedural room generation
- Exit/connection tracking
- "Look" command for room descriptions

### 8. Travel System
- Random encounter rolls during travel
- Distance and time tracking
- Terrain effects

### 9. Corpse/Loot System
- Loot tables for defeated enemies
- Body decay over time
- Harvest components (monster parts)

### 10. Theft/Crime System
- Pickpocket mechanics
- Recognition system (NPCs remember thieves)
- Bounty tracking

---

## Implementation Order Recommendation

```
Phase 1 (Foundation):
├── Party Management ──────────── enables group play
└── Rest Mechanics ────────────── basic D&D loop

Phase 2 (Combat Enhancement):
├── Combat Actions ────────────── mechanical resolution
├── Concentration ─────────────── spell tracking
└── Advanced Inventory ────────── equip/use items

Phase 3 (World Building):
├── NPC Relationships ─────────── deeper roleplay
└── Spatial Management ────────── dungeon crawling
```

---

## References

- [mnehmos.rpg.mcp](https://github.com/Mnehmos/mnehmos.rpg.mcp) - Original inspiration
- [D&D 5e SRD](https://www.dndbeyond.com/sources/basic-rules) - Rules reference

---

*Last updated: 2026-02-02*
