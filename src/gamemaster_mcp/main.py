"""
D&D MCP Server
A comprehensive D&D campaign management server built with modern FastMCP framework.
"""

import logging
import random
import re
import os
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Literal
from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import Field

from .storage import DnDStorage
from .models import (
    Character, NPC, Location, Quest, SessionNote, AdventureEvent, EventType,
    AbilityScore, CharacterClass, Race, Item
)
from .rulebooks import RulebookManager
from .rulebooks.sources.srd import SRDSource
from .rulebooks.sources.custom import CustomSource
from .rulebooks.validators import CharacterValidator
from .library import LibraryManager, TOCExtractor, ContentExtractor, SearchResult

logger = logging.getLogger("gamemaster-mcp")

logging.basicConfig(
    level=logging.DEBUG,
    )

if not load_dotenv():
    logger.warning("❌ .env file invalid or not found! Please see README.md for instructions. Using project root instead.")

data_path = Path(os.getenv("GAMEMASTER_STORAGE_DIR", "")).resolve()
logger.debug(f"📂 Data path: {data_path}")


# Initialize storage and FastMCP server
storage = DnDStorage(data_dir=data_path)
logger.debug("✅ Storage layer initialized")

# Initialize library manager for PDF rulebook library
library_dir = data_path / "library" if data_path else Path("dnd_data/library")
library_manager = LibraryManager(library_dir)
library_manager.ensure_directories()
loaded_indexes = library_manager.load_all_indexes()
logger.debug(f"📚 Library manager initialized ({loaded_indexes} indexes loaded)")

mcp = FastMCP(
    name="gamemaster-mcp"
)
logger.debug("✅ Server initialized, registering tools")



# ----------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------

# Campaign management tools
@mcp.tool
def create_campaign(
    name: Annotated[str, Field(description="Campaign name")],
    description: Annotated[str, Field(description="Brief decription of the campaign, or a tagline")],
    dm_name: Annotated[str | None, Field(description="Dungeon Master name")] = None,
    setting: Annotated[str | Path | None, Field(description="""
        Campaign setting - a full description of the setting of the campaign in markdown format, or the path to a `.txt` or `.md` file containing the same.
        """)] = None,
) -> str:
    """Create a new D&D campaign."""
    campaign = storage.create_campaign(
        name=name,
        description=description,
        dm_name=dm_name,
        setting=setting
    )
    return f"🌟 Created campaign: '{campaign.name} and set as active 🌟'"

@mcp.tool
def get_campaign_info() -> str:
    """Get information about the current campaign.

    Returns campaign information including name, description, counts of various entities,
    and current game state.
    """
    campaign = storage.get_current_campaign()
    if not campaign:
        return "No active campaign."

    info = {
        "name": campaign.name,
        "description": campaign.description,
        "dm_name": campaign.dm_name,
        "setting": campaign.get_setting(),
        "character_count": len(campaign.characters),
        "npc_count": len(campaign.npcs),
        "location_count": len(campaign.locations),
        "quest_count": len(campaign.quests),
        "session_count": len(campaign.sessions),
        "current_session": campaign.game_state.current_session,
        "current_location": campaign.game_state.current_location,
        "party_level": campaign.game_state.party_level,
        "in_combat": campaign.game_state.in_combat
    }

    return f"**Campaign: {campaign.name}**\n\n" + \
           "\n".join([f"**{k.replace('_', ' ').title()}:** {v}" for k, v in info.items()])

@mcp.tool
def list_campaigns() -> str:
    """List all available campaigns."""
    campaigns = storage.list_campaigns()
    if not campaigns:
        return f"❌ No campaigns found in {storage.data_dir}!"

    current = storage.get_current_campaign()
    current_name = current.name if current else None

    campaign_list = []
    for campaign in campaigns:
        marker = " (current)" if campaign == current_name else ""
        campaign_list.append(f"• {campaign}{marker}")

    return "**Available Campaigns:**\n" + "\n".join(campaign_list)

@mcp.tool
def load_campaign(
    name: Annotated[str, Field(description="Campaign name to load")]
) -> str:
    """Load a specific campaign."""
    campaign = storage.load_campaign(name)
    return f"📖 Loaded campaign: '{campaign.name}'. Campaign is now active!"

# Character Management Tools
@mcp.tool
def create_character(
    name: Annotated[str, Field(description="Character name")],
    character_class: Annotated[str, Field(description="Character class")],
    class_level: Annotated[int, Field(description="Class level", ge=1, le=20)],
    race: Annotated[str, Field(description="Character race")],
    player_name: Annotated[str | None, Field(description="The name of the player in control of this character")] = None,
    description: Annotated[str | None, Field(description="A brief description of the character's appearance and demeanor.")] = None,
    bio: Annotated[str | None, Field(description="The character's backstory, personality, and motivations.")] = None,
    background: Annotated[str | None, Field(description="Character background")] = None,
    alignment: Annotated[str | None, Field(description="Character alignment")] = None,
    strength: Annotated[int, Field(description="Strength score", ge=1, le=30)] = 10,
    dexterity: Annotated[int, Field(description="Dexterity score", ge=1, le=30)] = 10,
    constitution: Annotated[int, Field(description="Constitution score", ge=1, le=30)] = 10,
    intelligence: Annotated[int, Field(description="Intelligence score", ge=1, le=30)] = 10,
    wisdom: Annotated[int, Field(description="Wisdom score", ge=1, le=30)] = 10,
    charisma: Annotated[int, Field(description="Charisma score", ge=1, le=30)] = 10,
) -> str:
    """Create a new player character."""
    # Build ability scores
    abilities = {
        "strength": AbilityScore(score=strength),
        "dexterity": AbilityScore(score=dexterity),
        "constitution": AbilityScore(score=constitution),
        "intelligence": AbilityScore(score=intelligence),
        "wisdom": AbilityScore(score=wisdom),
        "charisma": AbilityScore(score=charisma),
    }

    character = Character(
        name=name,
        player_name=player_name,
        character_class=CharacterClass(name=character_class, level=class_level),
        race=Race(name=race),
        background=background,
        alignment=alignment,
        abilities=abilities,
        description=description,
        bio=bio,
    )

    storage.add_character(character)
    return f"Created character '{character.name}' (Level {character.character_class.level} {character.race.name} {character.character_class.name})"

@mcp.tool
def get_character(
    name_or_id: Annotated[str, Field(description="Character name, ID, or player name")]
) -> str:
    """Get detailed character information. Accepts character name, ID, or player name."""
    character = storage.get_character(name_or_id)
    if not character:
        return f"❌ Character '{name_or_id}' not found."

    char_info = f"""**{character.name}** (`{character.id}`)
Level {character.character_class.level} {character.race.name} {character.character_class.name}
**Player:** {character.player_name or 'N/A'}
**Background:** {character.background or 'N/A'}
**Alignment:** {character.alignment or 'N/A'}

**Description:** {character.description or 'No description provided.'}
**Bio:** {character.bio or 'No bio provided.'}

**Ability Scores:**
• STR: {character.abilities['strength'].score} ({character.abilities['strength'].mod:+d})
• DEX: {character.abilities['dexterity'].score} ({character.abilities['dexterity'].mod:+d})
• CON: {character.abilities['constitution'].score} ({character.abilities['constitution'].mod:+d})
• INT: {character.abilities['intelligence'].score} ({character.abilities['intelligence'].mod:+d})
• WIS: {character.abilities['wisdom'].score} ({character.abilities['wisdom'].mod:+d})
• CHA: {character.abilities['charisma'].score} ({character.abilities['charisma'].mod:+d})

**Combat Stats:**
• AC: {character.armor_class}
• HP: {character.hit_points_current}/{character.hit_points_max}
• Temp HP: {character.temporary_hit_points}

**Inventory:** {len(character.inventory)} items
"""

    return char_info

@mcp.tool
def update_character(
    name_or_id: Annotated[str, Field(description="Character name, ID, or player name.")],
    name: Annotated[str | None, Field(description="New character name. If you change this, you must use the character's ID to identify them.")] = None,
    player_name: Annotated[str | None, Field(description="The name of the player in control of this character")] = None,
    description: Annotated[str | None, Field(description="A brief description of the character's appearance and demeanor.")] = None,
    bio: Annotated[str | None, Field(description="The character's backstory, personality, and motivations.")] = None,
    background: Annotated[str | None, Field(description="Character background")] = None,
    alignment: Annotated[str | None, Field(description="Character alignment")] = None,
    hit_points_current: Annotated[int | None, Field(description="Current hit points", ge=0)] = None,
    hit_points_max: Annotated[int | None, Field(description="Maximum hit points", ge=1)] = None,
    temporary_hit_points: Annotated[int | None, Field(description="Temporary hit points", ge=0)] = None,
    armor_class: Annotated[int | None, Field(description="Armor class")] = None,
    inspiration: Annotated[bool | None, Field(description="Inspiration status")] = None,
    notes: Annotated[str | None, Field(description="Additional notes about the character")] = None,
    strength: Annotated[int | None, Field(description="Strength score", ge=1, le=30)] = None,
    dexterity: Annotated[int | None, Field(description="Dexterity score", ge=1, le=30)] = None,
    constitution: Annotated[int | None, Field(description="Constitution score", ge=1, le=30)] = None,
    intelligence: Annotated[int | None, Field(description="Intelligence score", ge=1, le=30)] = None,
    wisdom: Annotated[int | None, Field(description="Wisdom score", ge=1, le=30)] = None,
    charisma: Annotated[int | None, Field(description="Charisma score", ge=1, le=30)] = None,
) -> str:
    """Update a character's properties."""
    character = storage.get_character(name_or_id)
    if not character:
        return f"❌ Character '{name_or_id}' not found."

    updates = {k: v for k, v in locals().items() if v is not None and k not in ["name_or_id", "character"]}
    updated_fields = [f"{key.replace('_', ' ')}: {value}" for key, value in updates.items()]

    if not updates:
        return f"No updates provided for {character.name}."

    storage.update_character(str(character.id), **updates)

    return f"Updated {character.name}'s properties: {'; '.join(updated_fields)}."

@mcp.tool
def bulk_update_characters(
    names_or_ids: Annotated[list[str], Field(description="List of character names, IDs, or player names to update.")],
    hp_change: Annotated[int | None, Field(description="Amount to change current HP by (positive or negative).")] = None,
    temp_hp_change: Annotated[int | None, Field(description="Amount to change temporary HP by (positive or negative).")] = None,
    strength_change: Annotated[int | None, Field(description="Amount to change strength by.")] = None,
    dexterity_change: Annotated[int | None, Field(description="Amount to change dexterity by.")] = None,
    constitution_change: Annotated[int | None, Field(description="Amount to change constitution by.")] = None,
    intelligence_change: Annotated[int | None, Field(description="Amount to change intelligence by.")] = None,
    wisdom_change: Annotated[int | None, Field(description="Amount to change wisdom by.")] = None,
    charisma_change: Annotated[int | None, Field(description="Amount to change charisma by.")] = None,
) -> str:
    """Update properties for multiple characters at once by a given amount."""
    updates_log = []
    not_found_log = []

    changes = {
        "hp_change": hp_change,
        "temp_hp_change": temp_hp_change,
        "strength_change": strength_change,
        "dexterity_change": dexterity_change,
        "constitution_change": constitution_change,
        "intelligence_change": intelligence_change,
        "wisdom_change": wisdom_change,
        "charisma_change": charisma_change,
    }

    # Filter out None changes
    active_changes = {k: v for k, v in changes.items() if v is not None}
    if not active_changes:
        return "No changes specified."

    # Use batch mode for single save at the end instead of N saves
    with storage.batch_update():
        for name_or_id in names_or_ids:
            character = storage.get_character(name_or_id)
            if not character:
                not_found_log.append(name_or_id)
                continue

            char_updates = {}
            char_log = [f"{character.name}:"]

            if hp_change is not None:
                new_hp = character.hit_points_current + hp_change
                # Clamp HP between 0 and max HP
                new_hp = max(0, min(new_hp, character.hit_points_max))
                char_updates['hit_points_current'] = new_hp
                char_log.append(f"HP -> {new_hp}")

            if temp_hp_change is not None:
                new_temp_hp = character.temporary_hit_points + temp_hp_change
                # Temp HP cannot be negative
                new_temp_hp = max(0, new_temp_hp)
                char_updates['temporary_hit_points'] = new_temp_hp
                char_log.append(f"Temp HP -> {new_temp_hp}")

            abilities_updated = False
            ability_changes = {
                "strength": strength_change, "dexterity": dexterity_change,
                "constitution": constitution_change, "intelligence": intelligence_change,
                "wisdom": wisdom_change, "charisma": charisma_change
            }
            for ability, change in ability_changes.items():
                if change is not None:
                    new_score = character.abilities[ability].score + change
                    new_score = max(1, min(new_score, 30)) # Clamp score
                    character.abilities[ability].score = new_score
                    abilities_updated = True
                    char_log.append(f"{ability.capitalize()} -> {new_score}")

            if abilities_updated:
                char_updates['abilities'] = character.abilities

            if char_updates:
                storage.update_character(str(character.id), **char_updates)
                updates_log.append(" ".join(char_log))
    # Single save happens here when exiting batch_update context

    response_parts = []
    if updates_log:
        response_parts.append("Characters updated:\n" + "\n".join(updates_log))
    if not_found_log:
        response_parts.append(f"Characters not found: {', '.join(not_found_log)}")

    return "\n".join(response_parts) if response_parts else "No characters found to update."

@mcp.tool
def add_item_to_character(
    character_name_or_id: Annotated[str, Field(description="Character name, ID, or player name.")],
    item_name: Annotated[str, Field(description="Item name")],
    description: Annotated[str | None, Field(description="Item description")] = None,
    quantity: Annotated[int, Field(description="Quantity", ge=1)] = 1,
    item_type: Annotated[Literal["weapon", "armor", "consumable", "misc"], Field(description="Item type")] = "misc",
    weight: Annotated[float | None, Field(description="Item weight", ge=0)] = None,
    value: Annotated[str | None, Field(description="Item value (e.g., '50 gp')")] = None,
) -> str:
    """Add an item to a character's inventory."""
    character = storage.get_character(character_name_or_id)
    if not character:
        return f"❌ Character '{character_name_or_id}' not found!"

    item = Item(
        name=item_name,
        description=description,
        quantity=quantity,
        item_type=item_type,
        weight=weight,
        value=value
    )

    character.inventory.append(item)
    storage.update_character(str(character.id), inventory=character.inventory)

    return f"Added {item.quantity}x {item.name} to {character.name}'s inventory"

@mcp.tool
def list_characters() -> str:
    """List all characters in the current campaign.

    Returns a list of all player characters with their basic information.
    """
    characters = storage.list_characters_detailed()  # O(n) instead of O(2n)
    if not characters:
        return "No characters in the current campaign."

    char_list = [
        f"• {char.name} (Level {char.character_class.level} {char.race.name} {char.character_class.name})"
        for char in characters
    ]

    return "**Characters:**\n" + "\n".join(char_list)

@mcp.tool
def delete_character(
    name_or_id: Annotated[str, Field(description="Character name, ID, or player name.")]
) -> str:
    """Delete a character from the current campaign. Accepts character name, ID, or player name."""
    character = storage.get_character(name_or_id)
    if not character:
        return f"❌ Character '{name_or_id}' not found."

    char_name = character.name
    storage.remove_character(name_or_id)
    return f"🗑️ Character '{char_name}' has been deleted from the campaign."

# NPC Management Tools
@mcp.tool
def create_npc(
    name: Annotated[str, Field(description="NPC name")],
    description: Annotated[str | None, Field(description="A brief, public description of the NPC.")] = None,
    bio: Annotated[str | None, Field(description="A detailed, private bio for the NPC, including secrets.")] = None,
    race: Annotated[str | None, Field(description="NPC race")] = None,
    occupation: Annotated[str | None, Field(description="NPC occupation")] = None,
    location: Annotated[str | None, Field(description="Current location")] = None,
    attitude: Annotated[Literal["friendly", "neutral", "hostile", "unknown"] | None, Field(description="Attitude towards party")] = None,
    notes: Annotated[str, Field(description="Additional notes")] = "",
) -> str:
    """Create a new NPC."""
    npc = NPC(
        name=name,
        description=description,
        bio=bio,
        race=race,
        occupation=occupation,
        location=location,
        attitude=attitude,
        notes=notes
    )

    storage.add_npc(npc)
    return f"Created NPC '{npc.name}'"

@mcp.tool
def get_npc(
    name: Annotated[str, Field(description="NPC name")]
) -> str:
    """Get NPC information."""
    npc = storage.get_npc(name)
    if not npc:
        return f"NPC '{name}' not found."

    npc_info = f"""**{npc.name}** (`{npc.id}`)
**Race:** {npc.race or 'Unknown'}
**Occupation:** {npc.occupation or 'Unknown'}
**Location:** {npc.location or 'Unknown'}
**Attitude:** {npc.attitude or 'Neutral'}

**Description:** {npc.description or 'No description available.'}
**Bio:** {npc.bio or 'No bio available.'}

**Notes:** {npc.notes or 'No additional notes.'}
"""

    return npc_info

@mcp.tool
def list_npcs() -> str:
    """List all NPCs in the current campaign.

    Returns a list of all non-player characters with their basic information.
    """
    npcs = storage.list_npcs_detailed()  # O(n) instead of O(2n)
    if not npcs:
        return "No NPCs in the current campaign."

    npc_list = [
        f"• {npc.name}{f' ({npc.location})' if npc.location else ''}"
        for npc in npcs
    ]

    return "**NPCs:**\n" + "\n".join(npc_list)

# Location Management Tools
@mcp.tool
def create_location(
    name: Annotated[str, Field(description="Location name")],
    location_type: Annotated[str, Field(description="Type of location (city, town, village, dungeon, etc.)")],
    description: Annotated[str, Field(description="Location description")],
    population: Annotated[int | None, Field(description="Population (if applicable)", ge=0)] = None,
    government: Annotated[str | None, Field(description="Government type")] = None,
    notable_features: Annotated[list[str] | None, Field(description="Notable features")] = None,
    notes: Annotated[str, Field(description="Additional notes")] = "",
) -> str:
    """Create a new location."""
    location = Location(
        name=name,
        location_type=location_type,
        description=description,
        population=population,
        government=government,
        notable_features=notable_features or [],
        notes=notes
    )

    storage.add_location(location)
    return f"Created location '{location.name}' ({location.location_type})"

@mcp.tool
def get_location(
    name: Annotated[str, Field(description="Location name")]
) -> str:
    """Get location information."""
    location = storage.get_location(name)
    if not location:
        return f"Location '{name}' not found."

    loc_info = f"""**{location.name}** ({location.location_type})

**Description:** {location.description}

**Population:** {location.population or 'Unknown'}
**Government:** {location.government or 'Unknown'}

**Notable Features:**
{chr(10).join(['• ' + feature for feature in location.notable_features]) if location.notable_features else 'None listed'}

**Notes:** {location.notes or 'No additional notes.'}
"""

    return loc_info

@mcp.tool
def list_locations() -> str:
    """List all locations in the current campaign.

    Returns a list of all locations with their basic information.
    """
    locations = storage.list_locations_detailed()  # O(n) instead of O(2n)
    if not locations:
        return "No locations in the current campaign."

    loc_list = [
        f"• {loc.name} ({loc.location_type})"
        for loc in locations
    ]

    return "**Locations:**\n" + "\n".join(loc_list)

# Quest Management Tools
@mcp.tool
def create_quest(
    title: Annotated[str, Field(description="Quest title")],
    description: Annotated[str, Field(description="Quest description")],
    giver: Annotated[str | None, Field(description="Quest giver (NPC name)")] = None,
    objectives: Annotated[list[str] | None, Field(description="Quest objectives")] = None,
    reward: Annotated[str | None, Field(description="Quest reward")] = None,
    notes: Annotated[str, Field(description="Additional notes")] = "",
) -> str:
    """Create a new quest."""
    quest = Quest(
        title=title,
        description=description,
        giver=giver,
        objectives=objectives or [],
        reward=reward,
        notes=notes
    )

    storage.add_quest(quest)
    return f"Created quest '{quest.title}'"

@mcp.tool
def update_quest(
    title: Annotated[str, Field(description="Quest title")],
    status: Annotated[Literal["active", "completed", "failed", "on_hold"] | None, Field(description="New quest status")] = None,
    completed_objective: Annotated[str | None, Field(description="Objective to mark as completed")] = None,
) -> str:
    """Update quest status or complete objectives."""
    quest = storage.get_quest(title)
    if not quest:
        return f"Quest '{title}' not found."

    if status:
        storage.update_quest_status(title, status)

    if completed_objective:
        if completed_objective in quest.objectives and completed_objective not in quest.completed_objectives:
            quest.completed_objectives.append(completed_objective)
            storage._save_campaign()  # Direct save since we modified the object

    return f"Updated quest '{title}'"

@mcp.tool
def list_quests(
    status: Annotated[Literal["active", "completed", "failed", "on_hold"] | None, Field(description="Filter by status")] = None,
) -> str:
    """List quests, optionally filtered by status.

    Returns a list of quests with their basic information and status.
    """
    quests = storage.list_quests(status)

    if not quests:
        filter_text = f" with status '{status}'" if status else ""
        return f"No quests found{filter_text}."

    quest_list = []
    for quest_title in quests:
        quest = storage.get_quest(quest_title)
        if quest:
            status_text = f" [{quest.status}]"
            quest_list.append(f"• {quest.title}{status_text}")

    return "**Quests:**\n" + "\n".join(quest_list)

# Game State Management Tools
@mcp.tool
def update_game_state(
    current_location: Annotated[str | None, Field(description="Current party location")] = None,
    current_session: Annotated[int | None, Field(description="Current session number", ge=1)] = None,
    current_date_in_game: Annotated[str | None, Field(description="Current in-game date")] = None,
    party_level: Annotated[int | None, Field(description="Average party level", ge=1, le=20)] = None,
    party_funds: Annotated[str | None, Field(description="Party treasure/funds")] = None,
    in_combat: Annotated[bool | None, Field(description="Whether party is in combat")] = None,
    notes: Annotated[str | None, Field(description="Current situation notes")] = None,
) -> str:
    """Update the current game state."""
    kwargs = {}
    if current_location is not None:
        kwargs["current_location"] = current_location
    if current_session is not None:
        kwargs["current_session"] = current_session
    if current_date_in_game is not None:
        kwargs["current_date_in_game"] = current_date_in_game
    if party_level is not None:
        kwargs["party_level"] = party_level
    if party_funds is not None:
        kwargs["party_funds"] = party_funds
    if in_combat is not None:
        kwargs["in_combat"] = in_combat
    if notes is not None:
        kwargs["notes"] = notes

    storage.update_game_state(**kwargs)
    return "Updated game state"

@mcp.tool
def get_game_state() -> str:
    """Get the current game state."""
    game_state = storage.get_game_state()
    if not game_state:
        return "No game state available."

    state_info = f"""**Game State**
**Campaign:** {game_state.campaign_name}
**Session:** {game_state.current_session}
**Location:** {game_state.current_location or 'Unknown'}
**Date (In-Game):** {game_state.current_date_in_game or 'Unknown'}
**Party Level:** {game_state.party_level}
**Party Funds:** {game_state.party_funds}
**In Combat:** {'Yes' if game_state.in_combat else 'No'}

**Active Quests:** {len(game_state.active_quests)}

**Notes:** {game_state.notes or 'No current notes.'}
"""

    return state_info

# Combat Management Tools
@mcp.tool
def start_combat(
    participants: Annotated[list[dict], Field(description="Combat participants with initiative order")]
) -> str:
    """Start a combat encounter."""
    # Sort by initiative (highest first)
    initiative_order = sorted(participants, key=lambda x: x.get("initiative", 0), reverse=True)

    storage.update_game_state(
        in_combat=True,
        initiative_order=initiative_order,
        current_turn=initiative_order[0]["name"] if initiative_order else None
    )

    order_text = "\n".join([
        f"{i+1}. {p['name']} (Initiative: {p.get('initiative', 0)})"
        for i, p in enumerate(initiative_order)
    ])

    return f"**Combat Started!**\n\n**Initiative Order:**\n{order_text}\n\n**Current Turn:** {initiative_order[0]['name'] if initiative_order else 'None'}"

@mcp.tool
def end_combat() -> str:
    """End the current combat encounter."""
    storage.update_game_state(
        in_combat=False,
        initiative_order=[],
        current_turn=None
    )
    return "Combat ended."

@mcp.tool
def next_turn() -> str:
    """Advance to the next turn in combat."""
    game_state = storage.get_game_state()
    if not game_state or not game_state.in_combat:
        return "Not currently in combat."

    if not game_state.initiative_order:
        return "No initiative order set."

    # Find current turn index and advance
    current_index = 0
    if game_state.current_turn:
        for i, participant in enumerate(game_state.initiative_order):
            if participant["name"] == game_state.current_turn:
                current_index = i
                break

    next_index = (current_index + 1) % len(game_state.initiative_order)
    next_participant = game_state.initiative_order[next_index]

    storage.update_game_state(current_turn=next_participant["name"])

    return f"**Next Turn:** {next_participant['name']}"

# Session Management Tools
@mcp.tool
def add_session_note(
    session_number: Annotated[int, Field(description="Session number", ge=1)],
    summary: Annotated[str, Field(description="Session summary")],
    title: Annotated[str | None, Field(description="Session title")] = None,
    events: Annotated[list[str] | None, Field(description="Key events that occurred")] = None,
    characters_present: Annotated[list[str] | None, Field(description="Characters present in session")] = None,
    npcs_encountered: Annotated[list[str] | None, Field(description="NPCs encountered in session")] = None,
    quest_updates: Annotated[dict[str, str] | None, Field(description="Quest name to progress mapping")] = None,
    combat_encounters: Annotated[list[str] | None, Field(description="Combat encounter summaries")] = None,
    experience_gained: Annotated[int | None, Field(description="Experience points gained", ge=0)] = None,
    treasure_found: Annotated[list[str] | None, Field(description="Treasure or items found")] = None,
    notes: Annotated[str, Field(description="Additional notes")] = "",
) -> str:
    """Add notes for a game session."""
    session_note = SessionNote(
        session_number=session_number,
        title=title,
        summary=summary,
        events=events or [],
        characters_present=characters_present or [],
        npcs_encountered=npcs_encountered or [],
        quest_updates=quest_updates or {},
        combat_encounters=combat_encounters or [],
        experience_gained=experience_gained,
        treasure_found=treasure_found or [],
        notes=notes
    )

    storage.add_session_note(session_note)
    return f"Added session note for Session {session_note.session_number}"

def _summarize_session_impl(
    transcription: str,
    session_number: int,
    detail_level: Literal["brief", "medium", "detailed"] = "medium",
    speaker_map: dict[str, str] | None = None
) -> str:
    """Implementation of summarize_session tool (separated for testing).

    Args:
        transcription: Raw text or file path containing session transcription
        session_number: Session number for this recording
        detail_level: Amount of detail in the generated summary
        speaker_map: Optional mapping of generic speaker labels to character names

    Returns:
        Formatted prompt for LLM processing
    """
    # Step 1: Detect if transcription is file path or raw text
    transcription_text = transcription
    source_type = "raw text"

    # Only check for file if input is reasonable path length (< 1000 chars)
    # and doesn't contain newlines (which wouldn't be in a valid path)
    if len(transcription) < 1000 and '\n' not in transcription:
        transcription_path = Path(transcription.strip())
        try:
            if transcription_path.exists() and transcription_path.is_file():
                transcription_text = transcription_path.read_text(encoding='utf-8')
                source_type = f"file: {transcription_path.name}"
                logger.info(f"Loaded transcription from file: {transcription_path}")
        except (OSError, Exception) as e:
            # Path validation failed or read failed - treat as raw text
            logger.debug(f"Not a valid file path: {e}. Treating input as raw text.")
            transcription_text = transcription
            source_type = "raw text"

    # Step 2: Apply speaker mapping if provided
    if speaker_map:
        logger.info(f"Applying speaker mapping: {speaker_map}")
        for speaker_label, character_name in speaker_map.items():
            # Replace speaker labels case-insensitively
            import re
            pattern = re.compile(re.escape(speaker_label), re.IGNORECASE)
            transcription_text = pattern.sub(character_name, transcription_text)

    # Step 3: Load campaign context
    logger.info("Loading campaign context for enrichment")

    characters = storage.list_characters_detailed()
    npcs = storage.list_npcs_detailed()
    locations = storage.list_locations_detailed()
    quests = storage.list_quests()

    # Create compact context
    context = {
        "characters": [{"name": c.name, "class": c.character_class.name, "level": c.character_class.level} for c in characters],
        "npcs": [{"name": n.name, "location": n.location, "attitude": n.attitude} for n in npcs],
        "locations": [{"name": l.name, "type": l.location_type} for l in locations],
        "quests": []
    }

    # Get quest details
    for quest_title in quests:
        quest = storage.get_quest(quest_title)
        if quest:
            context["quests"].append({
                "title": quest.title,
                "status": quest.status,
                "objectives": quest.objectives
            })

    import json
    context_encoded = json.dumps(context, separators=(',', ':'))

    # Step 4: Handle large transcriptions with chunking
    CHUNK_SIZE = 40000  # ~10k tokens per chunk
    OVERLAP_SIZE = 4000  # ~1k token overlap
    LARGE_THRESHOLD = 200000  # ~50k tokens

    if len(transcription_text) > LARGE_THRESHOLD:
        logger.info(f"Large transcription detected ({len(transcription_text)} chars). Using chunking strategy.")
        chunks = _create_overlapping_chunks(transcription_text, CHUNK_SIZE, OVERLAP_SIZE)
        logger.info(f"Created {len(chunks)} overlapping chunks")

        # Return instructions for processing chunks
        prompt = _generate_chunked_summary_prompt(
            chunks=chunks,
            context=context_encoded,
            session_number=session_number,
            detail_level=detail_level,
            source_type=source_type
        )
    else:
        # Single-pass processing
        prompt = _generate_summary_prompt(
            transcription=transcription_text,
            context=context_encoded,
            session_number=session_number,
            detail_level=detail_level,
            source_type=source_type
        )

    # Return the prompt for the MCP client to process with an LLM
    return prompt


@mcp.tool
def summarize_session(
    transcription: Annotated[str, Field(description="Raw transcription text or path to transcription file")],
    session_number: Annotated[int, Field(description="Session number", ge=1)],
    detail_level: Annotated[Literal["brief", "medium", "detailed"], Field(description="Detail level for the summary")] = "medium",
    speaker_map: Annotated[dict[str, str] | None, Field(description="Speaker label to character mapping (e.g., {'Speaker 1': 'Gandalf'})")] = None
) -> str:
    """Generate structured SessionNote from a raw session transcription.

    This tool accepts either raw transcription text or a path to a transcription file,
    then generates a comprehensive structured summary including events, NPCs encountered,
    quest updates, and combat encounters. The tool leverages campaign context (characters,
    NPCs, locations, quests) to enrich the summary.

    For large transcriptions (>200k characters ≈ 50k tokens), the tool automatically
    chunks the input into overlapping segments for processing.

    Args:
        transcription: Raw text or file path containing session transcription
        session_number: Session number for this recording
        detail_level: Amount of detail in the generated summary
        speaker_map: Optional mapping of generic speaker labels to character names

    Returns:
        Prompt for LLM to generate SessionNote
    """
    return _summarize_session_impl(transcription, session_number, detail_level, speaker_map)


def _create_overlapping_chunks(text: str, chunk_size: int, overlap_size: int) -> list[str]:
    """Split text into overlapping chunks for large transcription processing.

    Args:
        text: Full transcription text
        chunk_size: Size of each chunk in characters
        overlap_size: Size of overlap between chunks

    Returns:
        List of text chunks with overlaps
    """
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)

        # Try to find a natural break point (paragraph or sentence) only if not at the end
        if end < text_length:
            # Look for paragraph break within last 500 chars
            search_start = max(start, end - 500)
            last_para = text.rfind('\n\n', search_start, end)
            if last_para > start:
                end = last_para
            else:
                # Look for sentence break within last 200 chars
                search_start = max(start, end - 200)
                last_period = max(
                    text.rfind('. ', search_start, end),
                    text.rfind('! ', search_start, end),
                    text.rfind('? ', search_start, end)
                )
                if last_period > start:
                    end = last_period + 2

        chunks.append(text[start:end])

        # If we've reached the end, break
        if end >= text_length:
            break

        # Move start forward with overlap
        new_start = end - overlap_size

        # Ensure we're making progress (avoid infinite loop)
        if new_start <= start:
            new_start = start + 1

        start = new_start

    return chunks


def _generate_summary_prompt(transcription: str, context: str, session_number: int, detail_level: str, source_type: str) -> str:
    """Generate prompt for single-pass transcription summarization.

    Args:
        transcription: Full transcription text
        context: JSON-encoded campaign context
        session_number: Session number
        detail_level: Detail level (brief/medium/detailed)
        source_type: Description of transcription source

    Returns:
        Formatted prompt for LLM processing
    """
    detail_instructions = {
        "brief": "Create a concise summary focusing on major plot points and decisions.",
        "medium": "Create a balanced summary with key events, NPC interactions, and quest progress.",
        "detailed": "Create a comprehensive summary capturing dialogue nuances, character development, and all significant interactions."
    }

    return f"""# Session Transcription Summary Request

**Session Number:** {session_number}
**Source:** {source_type}
**Detail Level:** {detail_level}

## Campaign Context
{context}

## Instructions
{detail_instructions[detail_level]}

Generate a structured SessionNote with the following fields:
1. **title**: A catchy title for the session (max 60 chars)
2. **summary**: A narrative summary of the session
3. **events**: List of key events (bullet points)
4. **characters_present**: List of PC names who participated
5. **npcs_encountered**: List of NPC names who appeared
6. **quest_updates**: Dictionary mapping quest titles to progress descriptions
7. **combat_encounters**: List of combat summaries (if any)
8. **experience_gained**: Estimated XP earned (optional)
9. **treasure_found**: List of loot/items acquired
10. **notes**: Additional DM notes or observations

## Transcription
{transcription}

---

Please analyze the transcription above and generate a SessionNote object following the structure described. Use the campaign context to identify known characters, NPCs, locations, and quests."""


def _generate_chunked_summary_prompt(chunks: list[str], context: str, session_number: int, detail_level: str, source_type: str) -> str:
    """Generate prompt for chunked transcription summarization.

    Args:
        chunks: List of transcription chunks
        context: JSON-encoded campaign context
        session_number: Session number
        detail_level: Detail level (brief/medium/detailed)
        source_type: Description of transcription source

    Returns:
        Formatted prompt for LLM processing with chunking instructions
    """
    detail_instructions = {
        "brief": "Create a concise summary focusing on major plot points and decisions.",
        "medium": "Create a balanced summary with key events, NPC interactions, and quest progress.",
        "detailed": "Create a comprehensive summary capturing dialogue nuances, character development, and all significant interactions."
    }

    chunk_summaries = "\n\n".join([
        f"### Chunk {i+1} of {len(chunks)}\n{chunk}"
        for i, chunk in enumerate(chunks)
    ])

    return f"""# Large Session Transcription Summary Request (Chunked)

**Session Number:** {session_number}
**Source:** {source_type}
**Detail Level:** {detail_level}
**Chunks:** {len(chunks)} overlapping segments

## Campaign Context
{context}

## Instructions
This transcription has been split into {len(chunks)} overlapping chunks for processing.

**Phase 1: Extract events from each chunk**
- Process each chunk independently
- Extract key events with normalized titles (e.g., "Combat with goblins" not "Combat with goblins in chunk 2")
- Note: Events may appear in multiple chunks due to overlap

**Phase 2: Merge and deduplicate**
- Combine events from all chunks
- Remove duplicates by comparing normalized event titles
- Maintain chronological order

**Phase 3: Generate final SessionNote**
{detail_instructions[detail_level]}

Generate a structured SessionNote with the following fields:
1. **title**: A catchy title for the session (max 60 chars)
2. **summary**: A narrative summary of the entire session
3. **events**: Deduplicated list of key events from all chunks
4. **characters_present**: List of PC names who participated
5. **npcs_encountered**: List of NPC names who appeared
6. **quest_updates**: Dictionary mapping quest titles to progress descriptions
7. **combat_encounters**: List of combat summaries
8. **experience_gained**: Estimated XP earned (optional)
9. **treasure_found**: List of loot/items acquired
10. **notes**: Additional DM notes or observations

## Transcription Chunks
{chunk_summaries}

---

Please analyze all chunks above and generate a single cohesive SessionNote object following the structure described. Use the campaign context to identify known characters, NPCs, locations, and quests. Remember to deduplicate events that appear in multiple chunks."""

@mcp.tool
def get_sessions() -> str:
    """Get all session notes."""
    sessions = storage.get_sessions()
    if not sessions:
        return "No session notes recorded."

    session_list = []
    for session in sorted(sessions, key=lambda s: s.session_number):
        title = session.title or "No title"
        date = session.date.strftime("%Y-%m-%d")
        session_list.append(f"**Session {session.session_number}** ({date}): {title}")
        session_list.append(f"  {session.summary[:100]}{'...' if len(session.summary) > 100 else ''}")
        session_list.append("")

    return "**Session Notes:**\n\n" + "\n".join(session_list)

# Adventure Log Tools
@mcp.tool
def add_event(
    event_type: Annotated[Literal["combat", "roleplay", "exploration", "quest", "character", "world", "session"], Field(description="Type of event")],
    title: Annotated[str, Field(description="Event title")],
    description: Annotated[str, Field(description="Event description")],
    session_number: Annotated[int | None, Field(description="Session number", ge=1)] = None,
    characters_involved: Annotated[list[str] | None, Field(description="Characters involved in the event")] = None,
    location: Annotated[str | None, Field(description="Location where event occurred")] = None,
    importance: Annotated[int, Field(description="Event importance (1-5)", ge=1, le=5)] = 3,
    tags: Annotated[list[str] | None, Field(description="Tags for categorizing the event")] = None,
) -> str:
    """Add an event to the adventure log."""
    event = AdventureEvent(
        event_type=EventType(event_type),
        title=title,
        description=description,
        session_number=session_number,
        characters_involved=characters_involved or [],
        location=location,
        importance=importance,
        tags=tags or []
    )

    storage.add_event(event)
    return f"Added {event_type.lower()} event: '{event.title}'"

@mcp.tool
def get_events(
    limit: Annotated[int | None, Field(description="Maximum number of events to return", ge=1)] = None,
    event_type: Annotated[Literal["combat", "roleplay", "exploration", "quest", "character", "world", "session"] | None, Field(description="Filter by event type")] = None,
    search: Annotated[str | None, Field(description="Search events by title/description")] = None,
) -> str:
    """Get events from the adventure log."""
    if search:
        events = storage.search_events(search)
    else:
        events = storage.get_events(limit=limit, event_type=event_type)

    if not events:
        return "No events found."

    event_list = []
    for event in events:
        timestamp = event.timestamp.strftime("%Y-%m-%d %H:%M")
        session_text = f" (Session {event.session_number})" if event.session_number else ""
        importance_stars = "★" * event.importance

        event_list.append(f"**{event.title}** [{event.event_type}] {importance_stars}")
        event_list.append(f"  {timestamp}{session_text}")
        event_list.append(f"  {event.description[:150]}{'...' if len(event.description) > 150 else ''}")
        if event.location:
            event_list.append(f"  📍 {event.location}")
        event_list.append("")

    return "**Adventure Log:**\n\n" + "\n".join(event_list)

# ----------------------------------------------------------------------
# Rulebook Management Tools
# ----------------------------------------------------------------------

@mcp.tool
async def load_rulebook(
    source: Annotated[
        Literal["srd", "custom"],
        Field(description="Source type: 'srd' for official D&D 5e SRD, 'custom' for local files")
    ],
    version: Annotated[
        str | None,
        Field(description="SRD version: '2014' (default) or '2024'. Ignored for custom sources.")
    ] = "2014",
    path: Annotated[
        str | None,
        Field(description="Path to custom rulebook file (JSON). Required for custom sources.")
    ] = None,
) -> str:
    """Load a rulebook into the current campaign."""
    if not storage._current_campaign:
        return "❌ No campaign loaded. Use `load_campaign` first."

    # Initialize manager if not exists
    if not storage.rulebook_manager:
        from .rulebooks import RulebookManager
        campaign_dir = storage._split_backend._get_campaign_dir(storage._current_campaign.name)
        storage._rulebook_manager = RulebookManager(campaign_dir)

    if source == "srd":
        srd_source = SRDSource(version=version or "2014", cache_dir=storage.rulebook_cache_dir)
        await storage.rulebook_manager.load_source(srd_source)
        counts = srd_source.content_counts()
        return f"✅ Loaded SRD {version} rulebook\n📚 {counts.classes} classes, {counts.races} races, {counts.spells} spells, {counts.monsters} monsters"

    elif source == "custom":
        if not path:
            return "❌ Custom source requires 'path' parameter"
        full_path = storage.rulebooks_dir / path if storage.rulebooks_dir else Path(path)
        custom_source = CustomSource(full_path)
        await storage.rulebook_manager.load_source(custom_source)
        counts = custom_source.content_counts()
        return f"✅ Loaded custom rulebook: {path}\n📚 {counts.classes} classes, {counts.races} races, {counts.spells} spells"

    return "❌ Invalid source type. Use 'srd' or 'custom'."

@mcp.tool
def list_rulebooks() -> str:
    """List all active rulebooks in the current campaign."""
    if not storage._current_campaign:
        return "❌ No campaign loaded."

    if not storage.rulebook_manager or not storage.rulebook_manager.sources:
        return "📚 No rulebooks loaded. Use `load_rulebook` to add one."

    rulebooks = []
    for source_id, source in storage.rulebook_manager.sources.items():
        counts = source.content_counts()
        rulebooks.append({
            "id": source_id,
            "type": source.source_type.value,
            "loaded_at": source.loaded_at.isoformat() if source.loaded_at else None,
            "content": {
                "classes": counts.classes,
                "races": counts.races,
                "spells": counts.spells,
                "monsters": counts.monsters,
            }
        })

    # Markdown output
    lines = ["# Active Rulebooks\n"]
    for rb in rulebooks:
        lines.append(f"## {rb['id']}")
        lines.append(f"- **Type:** {rb['type']}")
        if rb['loaded_at']:
            lines.append(f"- **Loaded:** {rb['loaded_at']}")
        lines.append(f"- **Content:** {rb['content']['classes']} classes, {rb['content']['races']} races, {rb['content']['spells']} spells, {rb['content']['monsters']} monsters")
        lines.append("")

    return "\n".join(lines)

@mcp.tool
def unload_rulebook(
    source_id: Annotated[
        str,
        Field(description="ID of the rulebook to unload (from list_rulebooks)")
    ],
) -> str:
    """Remove a rulebook from the current campaign."""
    if not storage._current_campaign:
        return "❌ No campaign loaded."

    if not storage.rulebook_manager:
        return "❌ No rulebooks loaded."

    if storage.rulebook_manager.unload_source(source_id):
        return f"✅ Unloaded rulebook: {source_id}"
    else:
        return f"❌ Rulebook not found: {source_id}"

# ----------------------------------------------------------------------
# Rulebook Query Tools
# ----------------------------------------------------------------------

@mcp.tool
def search_rules(
    query: Annotated[str, Field(description="Search term (name, partial match). Can be empty if class_filter is provided.")] = "",
    category: Annotated[
        Literal["all", "class", "race", "spell", "monster", "feat", "item"] | None,
        Field(description="Filter by category. Default: all")
    ] = "all",
    limit: Annotated[int, Field(description="Max results", ge=1, le=50)] = 20,
    class_filter: Annotated[
        str | None,
        Field(description="Filter spells by class (e.g., 'ranger', 'wizard'). Only applies to spell category.")
    ] = None,
) -> str:
    """Search for rules content across all loaded rulebooks.

    Examples:
        - search_rules(query="fire", category="spell") - Find spells with 'fire' in name
        - search_rules(class_filter="ranger", category="spell") - All ranger spells
        - search_rules(query="cure", class_filter="ranger", category="spell") - Ranger spells with 'cure' in name
    """
    if not storage.rulebook_manager:
        return "❌ No rulebooks loaded. Use `load_rulebook` first."

    if not query and not class_filter:
        return "❌ Please provide either a search query or a class_filter."

    categories = [category] if category and category != "all" else None
    results = storage.rulebook_manager.search(
        query=query,
        categories=categories,
        limit=limit,
        class_filter=class_filter,
    )

    if not results:
        filter_desc = f"class='{class_filter}'" if class_filter else f"'{query}'"
        return f"No results found for {filter_desc}."

    # Build header
    if class_filter and query:
        header = f"# Search Results: '{query}' (class: {class_filter})\n"
    elif class_filter:
        header = f"# Spells for class: {class_filter}\n"
    else:
        header = f"# Search Results: '{query}'\n"

    lines = [header]
    for r in results:
        lines.append(f"- **{r.name}** ({r.category}) — _{r.source}_")

    return "\n".join(lines)

@mcp.tool
def get_class_info(
    name: Annotated[str, Field(description="Class name (e.g., 'wizard', 'fighter')")],
    level: Annotated[int | None, Field(description="Show features up to this level", ge=1, le=20)] = None,
) -> str:
    """Get full class definition from loaded rulebooks."""
    if not storage.rulebook_manager:
        return "❌ No rulebooks loaded."

    class_def = storage.rulebook_manager.get_class(name.lower())
    if not class_def:
        return f"❌ Class '{name}' not found in loaded rulebooks."

    # Markdown format
    lines = [f"# {class_def.name}\n"]
    lines.append(f"**Hit Die:** d{class_def.hit_die}")
    lines.append(f"**Saving Throws:** {', '.join(class_def.saving_throws)}")
    if class_def.spellcasting:
        lines.append(f"**Spellcasting:** {class_def.spellcasting.spellcasting_ability}")
    lines.append(f"\n**Subclasses:** {', '.join(class_def.subclasses) if class_def.subclasses else 'None in SRD'}")
    lines.append(f"\n*Source: {class_def.source}*")

    return "\n".join(lines)

@mcp.tool
def get_race_info(
    name: Annotated[str, Field(description="Race name (e.g., 'elf', 'dwarf')")],
) -> str:
    """Get full race definition from loaded rulebooks."""
    if not storage.rulebook_manager:
        return "❌ No rulebooks loaded."

    race_def = storage.rulebook_manager.get_race(name.lower())
    if not race_def:
        return f"❌ Race '{name}' not found in loaded rulebooks."

    lines = [f"# {race_def.name}\n"]
    lines.append(f"**Size:** {race_def.size.value}")
    lines.append(f"**Speed:** {race_def.speed} ft.")
    if race_def.ability_bonuses:
        bonuses = ", ".join([f"{b.ability_score} +{b.bonus}" for b in race_def.ability_bonuses])
        lines.append(f"**Ability Bonuses:** {bonuses}")
    if race_def.traits:
        lines.append(f"\n**Traits:**")
        for trait in race_def.traits:
            lines.append(f"- **{trait.name}:** {trait.desc[0] if trait.desc else 'No description'}")
    if race_def.subraces:
        lines.append(f"\n**Subraces:** {', '.join(race_def.subraces)}")
    lines.append(f"\n*Source: {race_def.source}*")

    return "\n".join(lines)

@mcp.tool
def get_spell_info(
    name: Annotated[str, Field(description="Spell name (e.g., 'fireball', 'cure wounds')")],
) -> str:
    """Get spell details from loaded rulebooks."""
    if not storage.rulebook_manager:
        return "❌ No rulebooks loaded."

    # Normalize name for lookup
    spell_index = name.lower().replace(" ", "-")
    spell = storage.rulebook_manager.get_spell(spell_index)
    if not spell:
        return f"❌ Spell '{name}' not found."

    # D&D-style spell card format
    components = ", ".join(spell.components)
    if spell.material:
        components += f" ({spell.material})"

    lines = [f"# {spell.name}"]
    lines.append(f"*{spell.level_text} {spell.school.value}*\n")
    lines.append(f"**Casting Time:** {spell.casting_time}")
    lines.append(f"**Range:** {spell.range}")
    lines.append(f"**Components:** {components}")
    lines.append(f"**Duration:** {spell.duration}")
    if spell.concentration:
        lines.append("**Concentration:** Yes")
    if spell.ritual:
        lines.append("**Ritual:** Yes")
    lines.append(f"\n{chr(10).join(spell.desc)}")
    if spell.higher_level:
        lines.append(f"\n**At Higher Levels:** {chr(10).join(spell.higher_level)}")
    lines.append(f"\n*Source: {spell.source}*")

    return "\n".join(lines)

@mcp.tool
def get_monster_info(
    name: Annotated[str, Field(description="Monster name (e.g., 'goblin', 'adult red dragon')")],
) -> str:
    """Get monster stat block from loaded rulebooks."""
    if not storage.rulebook_manager:
        return "❌ No rulebooks loaded."

    monster_index = name.lower().replace(" ", "-")
    monster = storage.rulebook_manager.get_monster(monster_index)
    if not monster:
        return f"❌ Monster '{name}' not found."

    # D&D stat block format
    lines = [f"# {monster.name}"]
    lines.append(f"*{monster.size.value} {monster.type}, {monster.alignment}*\n")
    lines.append(f"**Armor Class:** {monster.armor_class[0].value}")
    lines.append(f"**Hit Points:** {monster.hit_points} ({monster.hit_dice})")
    speeds = ", ".join([f"{k} {v}" for k, v in monster.speed.items()])
    lines.append(f"**Speed:** {speeds}\n")

    # Ability scores
    lines.append("| STR | DEX | CON | INT | WIS | CHA |")
    lines.append("|-----|-----|-----|-----|-----|-----|")
    lines.append(f"| {monster.strength} ({monster.get_ability_modifier('strength'):+d}) | {monster.dexterity} ({monster.get_ability_modifier('dexterity'):+d}) | {monster.constitution} ({monster.get_ability_modifier('constitution'):+d}) | {monster.intelligence} ({monster.get_ability_modifier('intelligence'):+d}) | {monster.wisdom} ({monster.get_ability_modifier('wisdom'):+d}) | {monster.charisma} ({monster.get_ability_modifier('charisma'):+d}) |\n")

    lines.append(f"**Challenge:** {monster.challenge_rating} ({monster.xp} XP)")
    lines.append(f"\n*Source: {monster.source}*")

    return "\n".join(lines)

@mcp.tool
def validate_character_rules(
    name_or_id: Annotated[str, Field(description="Character name or ID to validate")],
) -> str:
    """Validate a character against loaded rulebooks."""
    character = storage.get_character(name_or_id)
    if not character:
        return f"❌ Character '{name_or_id}' not found."

    if not storage.rulebook_manager:
        return "⚠️ No rulebooks loaded. Cannot validate without rules."

    validator = CharacterValidator(storage.rulebook_manager)
    report = validator.validate(character)

    # Markdown format
    status = "✅ Valid" if report.valid else "❌ Invalid"
    lines = [f"# Validation Report: {character.name}"]
    lines.append(f"**Status:** {status}\n")

    if report.errors:
        lines.append("## Errors")
        for issue in report.errors:
            lines.append(f"- **{issue.type}:** {issue.message}")
            if issue.suggestion:
                lines.append(f"  💡 {issue.suggestion}")

    if report.warnings:
        lines.append("\n## Warnings")
        for issue in report.warnings:
            lines.append(f"- **{issue.type}:** {issue.message}")
            if issue.suggestion:
                lines.append(f"  💡 {issue.suggestion}")

    info_issues = [i for i in report.issues if i.severity.value == "info"]
    if info_issues:
        lines.append("\n## Info")
        for issue in info_issues:
            lines.append(f"- {issue.message}")

    return "\n".join(lines)

# ----------------------------------------------------------------------
# Utility Tools
# ----------------------------------------------------------------------
@mcp.tool
def roll_dice(
    dice_notation: Annotated[str, Field(description="Dice notation (e.g., '1d20', '3d6+2')")],
    advantage: Annotated[bool, Field(description="Roll with advantage")] = False,
    disadvantage: Annotated[bool, Field(description="Roll with disadvantage")] = False,
) -> str:
    """Roll dice with D&D notation."""
    dice_notation = dice_notation.lower().strip()

    # Parse dice notation (e.g., "1d20", "3d6+2", "2d8-1")
    pattern = r'(\d+)d(\d+)([+-]\d+)?'
    match = re.match(pattern, dice_notation)

    if not match:
        return f"Invalid dice notation: {dice_notation}"

    num_dice = int(match.group(1))
    die_size = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0

    # Roll dice
    if advantage or disadvantage:
        if num_dice != 1 or die_size != 20:
            return "Advantage/disadvantage only applies to single d20 rolls"

        roll1 = random.randint(1, 20)
        roll2 = random.randint(1, 20)

        if advantage:
            result = max(roll1, roll2)
            roll_text = f"Advantage: {roll1}, {roll2} (taking {result})"
        else:
            result = min(roll1, roll2)
            roll_text = f"Disadvantage: {roll1}, {roll2} (taking {result})"

        total = result + modifier
        modifier_text = f" {modifier:+d}" if modifier != 0 else ""

        return f"🎲 **{dice_notation}** {roll_text}{modifier_text} = **{total}**"
    else:
        rolls = [random.randint(1, die_size) for _ in range(num_dice)]
        roll_sum = sum(rolls)
        total = roll_sum + modifier

        rolls_text = ", ".join(map(str, rolls)) if num_dice > 1 else str(rolls[0])
        modifier_text = f" {modifier:+d}" if modifier != 0 else ""

        return f"🎲 **{dice_notation}** [{rolls_text}]{modifier_text} = **{total}**"

@mcp.tool
def calculate_experience(
    party_size: Annotated[int, Field(description="Number of party members", ge=1)],
    party_level: Annotated[int, Field(description="Average party level", ge=1, le=20)],
    encounter_xp: Annotated[int, Field(description="Total encounter XP value", ge=0)],
) -> str:
    """Calculate experience points for an encounter."""
    # D&D 5e encounter multipliers based on party size
    if party_size < 3:
        multiplier = 1.5
    elif party_size > 5:
        multiplier = 0.5
    else:
        multiplier = 1.0

    adjusted_xp = int(encounter_xp * multiplier)
    xp_per_player = adjusted_xp // party_size

    return f"""**Experience Calculation:**
Base Encounter XP: {encounter_xp}
Party Size Multiplier: {multiplier}x
Adjusted XP: {adjusted_xp}
**XP per Player: {xp_per_player}**"""

# ----------------------------------------------------------------------
# PDF Library Tools
# ----------------------------------------------------------------------

@mcp.tool
def scan_library() -> str:
    """Scan the library folder for new PDF/Markdown files and index them.

    Scans the library/pdfs/ directory for PDF and Markdown files,
    extracts table of contents from new or modified files,
    and saves indexes for quick searching.

    Returns a summary of files found and indexed.
    """
    # Scan for files
    files = library_manager.scan_library()

    if not files:
        return "📚 No PDF or Markdown files found in library.\n\nAdd files to: " + str(library_manager.pdfs_dir)

    indexed_count = 0
    skipped_count = 0
    errors: list[str] = []

    for file_path in files:
        from .library.manager import generate_source_id
        source_id = generate_source_id(file_path.name)

        # Check if needs indexing
        if not library_manager.needs_reindex(source_id):
            skipped_count += 1
            continue

        # Index the file
        try:
            if file_path.suffix.lower() == ".pdf":
                extractor = TOCExtractor(file_path)
                index_entry = extractor.extract()
                library_manager.save_index(index_entry)
                indexed_count += 1
            elif file_path.suffix.lower() in (".md", ".markdown"):
                from .library.extractors import MarkdownTOCExtractor
                md_extractor = MarkdownTOCExtractor(file_path)
                index_entry = md_extractor.extract()
                library_manager.save_index(index_entry)
                indexed_count += 1
            else:
                # Unknown file type, skip
                skipped_count += 1
        except Exception as e:
            errors.append(f"{file_path.name}: {str(e)}")

    # Build response
    lines = ["# 📚 Library Scan Complete", ""]
    lines.append(f"**Total files:** {len(files)}")
    lines.append(f"**Newly indexed:** {indexed_count}")
    lines.append(f"**Skipped (up-to-date):** {skipped_count}")

    if errors:
        lines.append(f"\n**Errors ({len(errors)}):**")
        for error in errors:
            lines.append(f"- {error}")

    return "\n".join(lines)


@mcp.tool
def list_library() -> str:
    """List all sources in the library with their content summaries.

    Returns a formatted list of all PDF and Markdown sources
    in the library, showing their index status and content counts.
    """
    sources = library_manager.list_library()

    if not sources:
        return "📚 Library is empty.\n\nAdd PDF or Markdown files to: " + str(library_manager.pdfs_dir)

    lines = ["# 📚 Library Sources", ""]

    indexed = [s for s in sources if s.is_indexed]
    not_indexed = [s for s in sources if not s.is_indexed]

    if indexed:
        lines.append("## Indexed Sources")
        for source in indexed:
            summary = source.index_entry.content_summary if source.index_entry else None
            content_info = ""
            if summary and summary.total > 0:
                parts = []
                if summary.classes:
                    parts.append(f"{summary.classes} classes")
                if summary.races:
                    parts.append(f"{summary.races} races")
                if summary.spells:
                    parts.append(f"{summary.spells} spells")
                if summary.monsters:
                    parts.append(f"{summary.monsters} monsters")
                if summary.feats:
                    parts.append(f"{summary.feats} feats")
                if summary.items:
                    parts.append(f"{summary.items} items")
                content_info = f" — {', '.join(parts)}"

            pages = f" ({source.index_entry.total_pages} pages)" if source.index_entry else ""
            lines.append(f"- **{source.source_id}**{pages}{content_info}")
            lines.append(f"  _{source.filename}_")
        lines.append("")

    if not_indexed:
        lines.append("## Not Yet Indexed")
        lines.append("_Run `scan_library` to index these files._")
        for source in not_indexed:
            size_mb = source.file_size / (1024 * 1024)
            lines.append(f"- {source.filename} ({size_mb:.1f} MB)")

    return "\n".join(lines)


@mcp.tool
def get_library_toc(
    source_id: Annotated[str, Field(description="The source identifier (e.g., 'tome-of-heroes')")]
) -> str:
    """Get the table of contents for a specific library source.

    Returns the full hierarchical table of contents extracted from
    the PDF or Markdown source, with page numbers and content types.

    Args:
        source_id: The source identifier (use list_library to see available sources)
    """
    toc = library_manager.get_toc_formatted(source_id)

    if not toc:
        # Try to find similar source IDs
        sources = library_manager.list_library()
        available = [s.source_id for s in sources if s.is_indexed]

        if available:
            return f"❌ Source '{source_id}' not found.\n\nAvailable sources:\n" + "\n".join(f"- {s}" for s in available)
        else:
            return f"❌ Source '{source_id}' not found. No sources are indexed yet.\n\nRun `scan_library` first."

    return toc


@mcp.tool
def search_library(
    query: Annotated[str, Field(description="Search term (searches titles)")] = "",
    content_type: Annotated[
        Literal["all", "class", "race", "spell", "monster", "feat", "item", "background", "subclass"],
        Field(description="Filter by content type")
    ] = "all",
    limit: Annotated[int, Field(description="Maximum results to return", ge=1, le=100)] = 20,
) -> str:
    """Search across all indexed library content.

    Searches TOC entries by title across all indexed PDF and Markdown sources.
    Can filter by content type (class, race, spell, etc.).

    Args:
        query: Search term (case-insensitive, searches in titles)
        content_type: Filter by content type (default: all)
        limit: Maximum results to return (default: 20)
    """
    if not query and content_type == "all":
        return "❌ Please provide a search query or specify a content_type filter."

    results = library_manager.search(
        query=query,
        content_type=content_type if content_type != "all" else None,
        limit=limit,
    )

    if not results:
        filter_desc = f"'{query}'" if query else f"type={content_type}"
        return f"No results found for {filter_desc}."

    # Group by source
    by_source: dict[str, list[dict]] = {}
    for r in results:
        source = r["source_id"]
        if source not in by_source:
            by_source[source] = []
        by_source[source].append(r)

    # Build output
    header = f"# Search Results"
    if query:
        header += f": '{query}'"
    if content_type != "all":
        header += f" (type: {content_type})"

    lines = [header, f"_Found {len(results)} results_", ""]

    for source_id, source_results in by_source.items():
        lines.append(f"## {source_id}")
        for r in source_results:
            type_badge = f"[{r['content_type']}]" if r['content_type'] != "unknown" else ""
            lines.append(f"- **{r['title']}** (p. {r['page']}) {type_badge}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool
def ask_books(
    query: Annotated[str, Field(description="Natural language question about your rulebooks")],
    limit: Annotated[int, Field(description="Maximum number of results to return", ge=1, le=50)] = 10,
) -> str:
    """Ask a natural language question across all your rulebooks.

    Uses keyword expansion with D&D concept synonyms and TF-IDF scoring
    to find relevant content across all indexed PDF and Markdown sources.

    Examples:
        - "What options do I have for a melee spellcaster?"
        - "Find a class good for a dragon-themed character"
        - "What healing spells are available?"
        - "Show me tanky fighter options"
        - "Classes with nature magic"

    Args:
        query: Natural language question or search query
        limit: Maximum number of results to return (default: 10)

    Returns:
        Formatted search results grouped by source
    """
    if not query or not query.strip():
        return "Please provide a search query."

    # Use semantic search
    results = library_manager.semantic_search.search(query, limit)

    if not results:
        return f"No results found for: '{query}'\n\nTry different keywords or check that your library has indexed content."

    # Build output
    output: list[str] = [f"**Search Results for:** {query}\n"]
    output.append(f"_Found {len(results)} results_\n")

    # Group results by source
    grouped: dict[str, list[SearchResult]] = defaultdict(list)
    for result in results:
        grouped[result.source_name].append(result)

    for source_name, source_results in grouped.items():
        output.append(f"\n### From {source_name}:\n")
        for r in source_results:
            # Status indicator: checkmark if extracted, bracket hint if not
            status = "+" if r.is_extracted else "[Extract]"
            # Page info
            page_info = f"(p.{r.page})" if r.page else ""
            # Content type badge
            type_badge = f"[{r.content_type}]" if r.content_type and r.content_type != "unknown" else ""
            # Score indicator (relative strength)
            score_bars = "#" * min(5, int(r.score / 0.5) + 1)

            output.append(f"- **{r.title}** {page_info} {type_badge} {status} `{score_bars}`")

    output.append("\n---")
    output.append("_Use `extract_content` to extract specific content for use in campaigns._")

    return "\n".join(output)


@mcp.tool
def extract_content(
    source_id: Annotated[str, Field(description="The source identifier (e.g., 'tome-of-heroes')")],
    content_name: Annotated[str, Field(description="Name of the content to extract (e.g., 'Fighter', 'Elf')")],
    content_type: Annotated[
        Literal["class", "race", "spell", "monster", "feat", "item"],
        Field(description="Type of content to extract")
    ],
) -> str:
    """Extract content from a PDF source and save as CustomSource JSON.

    Extracts the full content definition from a PDF source based on the
    table of contents entry. The extracted content is saved to the
    library/extracted/{source_id}/ directory in CustomSource JSON format,
    ready to be loaded by the rulebook system.

    Examples:
        - extract_content("tome-of-heroes", "Fighter", "class")
        - extract_content("phb", "Elf", "race")
        - extract_content("phb", "Fireball", "spell")

    Args:
        source_id: The source identifier (use list_library to see available sources)
        content_name: Name of the content to extract (as shown in TOC)
        content_type: Type of content (class, race, spell, monster, feat, item)

    Returns:
        Success message with path to extracted file, or error message
    """
    # Verify source exists and is indexed
    source = library_manager.get_source(source_id)
    if not source:
        sources = library_manager.list_library()
        available = [s.source_id for s in sources]
        if available:
            return f"❌ Source '{source_id}' not found.\n\nAvailable sources:\n" + "\n".join(f"- {s}" for s in available)
        return f"❌ Source '{source_id}' not found. Library is empty."

    if not source.is_indexed:
        return f"❌ Source '{source_id}' is not indexed. Run `scan_library` first."

    # Verify source is a PDF (extraction only works for PDFs)
    if not source.file_path.suffix.lower() == ".pdf":
        return f"❌ Content extraction only supports PDF files. '{source.filename}' is not a PDF."

    # Create extractor and extract content
    extractor = ContentExtractor(library_manager)

    try:
        output_path = extractor.save_extracted_content(source_id, content_name, content_type)
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return f"❌ Extraction failed: {str(e)}"

    if not output_path:
        # Try to find similar content in the TOC
        results = library_manager.search(
            query=content_name,
            content_type=content_type,
            limit=5,
        )
        similar = [r for r in results if r["source_id"] == source_id]

        if similar:
            suggestions = "\n".join(f"- {r['title']} (p. {r['page']})" for r in similar)
            return f"❌ Content '{content_name}' ({content_type}) not found in {source_id}.\n\nSimilar content:\n{suggestions}"
        return f"❌ Content '{content_name}' ({content_type}) not found in {source_id}."

    # Read the extracted JSON to show a summary
    try:
        import json
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        content_key = f"{content_type}s" if content_type != "class" else "classes"
        if content_type == "race":
            content_key = "races"

        extracted_items = data.get("content", {}).get(content_key, [])
        if extracted_items:
            item = extracted_items[0]
            item_name = item.get("name", content_name)
            item_index = item.get("index", "")

            # Build summary based on content type
            summary_parts = [f"**{item_name}** (`{item_index}`)"]

            if content_type == "class":
                hit_die = item.get("hit_die", "?")
                saves = item.get("saving_throws", [])
                summary_parts.append(f"Hit Die: d{hit_die}")
                if saves:
                    summary_parts.append(f"Saves: {', '.join(saves)}")

            elif content_type == "race":
                speed = item.get("speed", 30)
                size = item.get("size", "Medium")
                bonuses = item.get("ability_bonuses", [])
                summary_parts.append(f"Size: {size}, Speed: {speed} ft.")
                if bonuses:
                    bonus_text = ", ".join(f"{b['ability_score']} +{b['bonus']}" for b in bonuses)
                    summary_parts.append(f"Abilities: {bonus_text}")

            elif content_type == "spell":
                level = item.get("level", 0)
                school = item.get("school", "?")
                level_text = "Cantrip" if level == 0 else f"{level}-level"
                summary_parts.append(f"{level_text} {school}")

            summary = "\n".join(summary_parts)
        else:
            summary = "Content extracted successfully."

    except Exception:
        summary = "Content extracted successfully."

    return f"""# ✅ Content Extracted

{summary}

**Saved to:** `{output_path}`

**Usage:** Load this content into a campaign with:
```
load_rulebook(source="custom", path="{output_path.name}")
```"""


# ----------------------------------------------------------------------
# Library Bindings Tools
# ----------------------------------------------------------------------

@mcp.tool
def enable_library_source(
    source_id: Annotated[str, Field(description="The source identifier (e.g., 'tome-of-heroes')")],
    content_type: Annotated[
        Literal["all", "class", "race", "spell", "monster", "feat", "item", "background", "subclass"] | None,
        Field(description="Filter by content type. Use 'all' or omit to enable entire source.")
    ] = "all",
    content_names: Annotated[
        list[str] | None,
        Field(description="Specific content names to enable (e.g., ['dragon-knight', 'shadow-dancer']). Only used if content_type is specified.")
    ] = None,
) -> str:
    """Enable a library source for the current campaign.

    Adds a library source to the campaign's enabled content. You can enable
    the entire source or filter by content type and specific items.

    Examples:
        - enable_library_source("tome-of-heroes") - Enable all content
        - enable_library_source("tome-of-heroes", content_type="class") - Enable all classes
        - enable_library_source("tome-of-heroes", content_type="class", content_names=["dragon-knight"]) - Enable specific class
    """
    if not storage._current_campaign:
        return "❌ No campaign loaded. Use `load_campaign` first."

    # Verify source exists in library
    source = library_manager.get_source(source_id)
    if not source:
        # Try to find similar sources
        sources = library_manager.list_library()
        available = [s.source_id for s in sources if s.is_indexed]
        if available:
            return f"❌ Source '{source_id}' not found.\n\nAvailable sources:\n" + "\n".join(f"- {s}" for s in available)
        else:
            return f"❌ Source '{source_id}' not found. Library is empty or not indexed.\n\nRun `scan_library` first."

    try:
        storage.enable_library_source(
            source_id=source_id,
            content_type=content_type if content_type != "all" else None,
            content_names=content_names,
        )
    except ValueError as e:
        return f"❌ {str(e)}"

    # Build response
    if content_type and content_type != "all":
        if content_names:
            return f"✅ Enabled {len(content_names)} {content_type}(s) from **{source_id}** for this campaign."
        else:
            return f"✅ Enabled all {content_type}s from **{source_id}** for this campaign."
    else:
        return f"✅ Enabled all content from **{source_id}** for this campaign."


@mcp.tool
def disable_library_source(
    source_id: Annotated[str, Field(description="The source identifier to disable")]
) -> str:
    """Disable a library source for the current campaign.

    Removes a library source from the campaign's enabled content.
    The source will no longer be available for use in this campaign.

    Args:
        source_id: The source identifier (use list_enabled_library to see enabled sources)
    """
    if not storage._current_campaign:
        return "❌ No campaign loaded. Use `load_campaign` first."

    if not storage.library_bindings:
        return "❌ Library bindings not initialized."

    # Check if source is currently enabled
    enabled = storage.get_enabled_library_sources()
    if source_id not in enabled:
        return f"⚠️ Source '{source_id}' is not currently enabled for this campaign."

    try:
        storage.disable_library_source(source_id)
    except ValueError as e:
        return f"❌ {str(e)}"

    return f"🚫 Disabled **{source_id}** for this campaign."


@mcp.tool
def list_enabled_library() -> str:
    """List all library sources enabled for the current campaign.

    Returns a formatted list of all library sources that have been
    enabled for use in the current campaign, including any content filters.
    """
    if not storage._current_campaign:
        return "❌ No campaign loaded. Use `load_campaign` first."

    if not storage.library_bindings:
        return "❌ Library bindings not initialized."

    enabled_sources = storage.get_enabled_library_sources()

    if not enabled_sources:
        return "📚 No library sources enabled for this campaign.\n\nUse `enable_library_source` to add sources from the library."

    lines = ["# 📚 Enabled Library Sources", ""]

    for source_id in enabled_sources:
        binding = storage.library_bindings.get_source_binding(source_id)
        if not binding:
            continue

        # Get source info from library manager
        source = library_manager.get_source(source_id)
        filename = source.filename if source else "Unknown file"

        lines.append(f"## {source_id}")
        lines.append(f"_Source: {filename}_")

        # Show content filters if any
        if binding.content_filter:
            lines.append("**Content filters:**")
            for content_type, filter_value in binding.content_filter.items():
                type_name = content_type.value if hasattr(content_type, 'value') else str(content_type)
                if filter_value == "*":
                    lines.append(f"- {type_name}: all enabled")
                elif isinstance(filter_value, list):
                    lines.append(f"- {type_name}: {', '.join(filter_value)}")
        else:
            lines.append("_All content enabled_")

        lines.append("")

    return "\n".join(lines)


# ----------------------------------------------------------------------
# Claudmaster Configuration Tools
# ----------------------------------------------------------------------

def _configure_claudmaster_impl(
    storage_ref,
    llm_model=None,
    temperature=None,
    max_tokens=None,
    narrative_style=None,
    dialogue_style=None,
    difficulty=None,
    improvisation_level=None,
    agent_timeout=None,
    fudge_rolls=None,
    reset_to_defaults=False,
) -> str:
    """Implementation for configure_claudmaster (testable without MCP wrapper)."""
    from gamemaster_mcp.claudmaster.config import ClaudmasterConfig

    if not storage_ref._current_campaign:
        return "No active campaign. Load or create a campaign first."

    if reset_to_defaults:
        config = ClaudmasterConfig()
        storage_ref.save_claudmaster_config(config)
        return _format_claudmaster_config(config, header="Claudmaster Configuration Reset to Defaults")

    config = storage_ref.get_claudmaster_config()

    updates: dict = {}
    if llm_model is not None:
        updates["llm_model"] = llm_model
    if temperature is not None:
        updates["temperature"] = temperature
    if max_tokens is not None:
        updates["max_tokens"] = max_tokens
    if narrative_style is not None:
        updates["narrative_style"] = narrative_style
    if dialogue_style is not None:
        updates["dialogue_style"] = dialogue_style
    if difficulty is not None:
        updates["difficulty"] = difficulty
    if improvisation_level is not None:
        updates["improvisation_level"] = improvisation_level
    if agent_timeout is not None:
        updates["agent_timeout"] = agent_timeout
    if fudge_rolls is not None:
        updates["fudge_rolls"] = fudge_rolls

    if not updates:
        return _format_claudmaster_config(config, header="Claudmaster Configuration (Current)")

    try:
        merged = config.model_dump()
        merged.update(updates)
        config = ClaudmasterConfig.model_validate(merged)
    except Exception as e:
        return f"Configuration error: {e}"

    storage_ref.save_claudmaster_config(config)
    changed = ", ".join(updates.keys())
    return _format_claudmaster_config(config, header=f"Claudmaster Configuration Updated ({changed})")


@mcp.tool
def configure_claudmaster(
    llm_model: Annotated[str | None, Field(description="LLM model identifier (e.g., 'claude-sonnet-4-5-20250929')")] = None,
    temperature: Annotated[float | None, Field(description="LLM temperature (0.0-2.0)")] = None,
    max_tokens: Annotated[int | None, Field(description="Maximum tokens in LLM response (256-200000)")] = None,
    narrative_style: Annotated[str | None, Field(description="Narrative style: descriptive, concise, dramatic, cinematic, etc.")] = None,
    dialogue_style: Annotated[str | None, Field(description="Dialogue style: natural, theatrical, formal, casual, etc.")] = None,
    difficulty: Annotated[Literal["easy", "normal", "hard", "deadly"] | None, Field(description="Game difficulty")] = None,
    improvisation_level: Annotated[int | None, Field(description="AI improvisation level: 0=None, 1=Low, 2=Medium, 3=High, 4=Full")] = None,
    agent_timeout: Annotated[float | None, Field(description="Maximum seconds per agent call (> 0)")] = None,
    fudge_rolls: Annotated[bool | None, Field(description="Whether DM can fudge dice rolls for narrative purposes")] = None,
    reset_to_defaults: Annotated[bool, Field(description="Reset all settings to defaults")] = False,
) -> str:
    """Configure the Claudmaster AI DM settings for the current campaign.

    Call with no arguments to view current configuration.
    Provide specific fields to update only those settings (partial update).
    Set reset_to_defaults=True to restore all settings to their default values.
    """
    return _configure_claudmaster_impl(
        storage, llm_model=llm_model, temperature=temperature, max_tokens=max_tokens,
        narrative_style=narrative_style, dialogue_style=dialogue_style, difficulty=difficulty,
        improvisation_level=improvisation_level, agent_timeout=agent_timeout,
        fudge_rolls=fudge_rolls, reset_to_defaults=reset_to_defaults,
    )


def _format_claudmaster_config(config, header: str = "Claudmaster Configuration") -> str:
    """Format ClaudmasterConfig as a readable string."""
    improv_labels = {0: "None", 1: "Low", 2: "Medium", 3: "High", 4: "Full"}
    improv_display = improv_labels.get(config.improvisation_level, str(config.improvisation_level))

    lines = [
        f"**{header}**",
        "",
        "**LLM Settings:**",
        f"  Provider: {config.llm_provider}",
        f"  Model: {config.llm_model}",
        f"  Temperature: {config.temperature}",
        f"  Max Tokens: {config.max_tokens}",
        "",
        "**Narrative Settings:**",
        f"  Style: {config.narrative_style}",
        f"  Dialogue: {config.dialogue_style}",
        "",
        "**Game Settings:**",
        f"  Difficulty: {config.difficulty}",
        f"  Fudge Rolls: {'enabled' if config.fudge_rolls else 'disabled'}",
        "",
        "**Agent Settings:**",
        f"  Improvisation Level: {improv_display} ({config.improvisation_level}/4)",
        f"  Agent Timeout: {config.agent_timeout}s",
        "",
        "**Intent Classification:**",
        f"  Ambiguity Threshold: {config.ambiguity_threshold}",
        f"  Fallback Confidence: {config.fallback_confidence}",
    ]

    if config.house_rules:
        lines.append("")
        lines.append("**House Rules:**")
        for key, value in config.house_rules.items():
            lines.append(f"  {key}: {value}")

    return "\n".join(lines)


logger.debug("✅ All tools successfully registered. Gamemaster-MCP server running! 🎲")

def main() -> None:
    """Main entry point for the D&D MCP Server."""
    mcp.run()

if __name__ == "__main__":
    main()
