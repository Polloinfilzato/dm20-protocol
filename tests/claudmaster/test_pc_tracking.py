"""
Tests for the PC Tracking system.

This module tests multi-PC registration, state tracking, and action identification
for the Claudmaster multi-agent framework.
"""

import pytest
from datetime import datetime
from dm20_protocol.claudmaster.pc_tracking import (
    PCState,
    MultiPlayerConfig,
    PCRegistry,
    PCIdentifier,
)


# --- PCRegistry Tests ---


def test_register_pc():
    """Test registering a PC and verifying state."""
    config = MultiPlayerConfig(max_players=4)
    registry = PCRegistry(config)

    state = registry.register_pc("gandalf", "John")

    assert state.character_id == "gandalf"
    assert state.player_name == "John"
    assert state.is_active is True
    assert state.current_action is None
    assert state.location is None
    assert state.last_action_time is None
    assert state.status_effects == []
    assert state.private_notes == []


def test_register_max_players():
    """Test exceeding max_players limit."""
    config = MultiPlayerConfig(max_players=2)
    registry = PCRegistry(config)

    registry.register_pc("pc1", "Player1")
    registry.register_pc("pc2", "Player2")

    with pytest.raises(ValueError, match="Maximum 2 players reached"):
        registry.register_pc("pc3", "Player3")


def test_register_duplicate():
    """Test registering same character_id twice."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    registry.register_pc("gandalf", "John")

    with pytest.raises(ValueError, match="Character gandalf already registered"):
        registry.register_pc("gandalf", "Jane")


def test_unregister_pc():
    """Test removing a PC from the session."""
    config = MultiPlayerConfig(allow_dynamic_join=True)
    registry = PCRegistry(config)

    registry.register_pc("gandalf", "John")
    assert registry.count == 1

    registry.unregister_pc("gandalf")
    assert registry.count == 0


def test_unregister_disabled():
    """Test unregistering when allow_dynamic_join=False."""
    config = MultiPlayerConfig(allow_dynamic_join=False)
    registry = PCRegistry(config)

    registry.register_pc("gandalf", "John")

    with pytest.raises(RuntimeError, match="Dynamic join/leave is disabled"):
        registry.unregister_pc("gandalf")


def test_unregister_unknown():
    """Test unregistering a character that doesn't exist."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    with pytest.raises(KeyError, match="Character gandalf not registered"):
        registry.unregister_pc("gandalf")


def test_unregister_clears_active_pc():
    """Test that unregistering the active PC clears it."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    registry.register_pc("gandalf", "John")
    registry.active_pc = "gandalf"
    assert registry.active_pc == "gandalf"

    registry.unregister_pc("gandalf")
    assert registry.active_pc is None


def test_get_pc_state():
    """Test getting state for a registered PC."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    registry.register_pc("gandalf", "John")
    state = registry.get_pc_state("gandalf")

    assert state.character_id == "gandalf"
    assert state.player_name == "John"


def test_get_pc_state_unknown():
    """Test getting state for unknown PC."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    with pytest.raises(KeyError, match="Character gandalf not registered"):
        registry.get_pc_state("gandalf")


def test_update_pc_state():
    """Test updating various PC state fields."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    registry.register_pc("gandalf", "John")

    # Update multiple fields
    state = registry.update_pc_state(
        "gandalf",
        current_action="casting fireball",
        location="Moria",
        status_effects=["blessed", "hasted"]
    )

    assert state.current_action == "casting fireball"
    assert state.location == "Moria"
    assert state.status_effects == ["blessed", "hasted"]
    assert state.last_action_time is not None
    assert isinstance(state.last_action_time, datetime)


def test_update_pc_state_invalid_field():
    """Test updating non-existent field."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    registry.register_pc("gandalf", "John")

    with pytest.raises(AttributeError, match="PCState has no attribute 'invalid_field'"):
        registry.update_pc_state("gandalf", invalid_field="value")


def test_update_pc_state_unknown():
    """Test updating state for unknown PC."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    with pytest.raises(KeyError, match="Character gandalf not registered"):
        registry.update_pc_state("gandalf", location="Moria")


def test_get_all_active():
    """Test filtering active PCs only."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    registry.register_pc("gandalf", "John")
    registry.register_pc("aragorn", "Jane")
    registry.register_pc("legolas", "Bob")

    # Deactivate one PC
    registry.update_pc_state("aragorn", is_active=False)

    active_pcs = registry.get_all_active()

    assert len(active_pcs) == 2
    character_ids = [pc.character_id for pc in active_pcs]
    assert "gandalf" in character_ids
    assert "legolas" in character_ids
    assert "aragorn" not in character_ids


def test_get_all_pcs():
    """Test getting all registered PCs."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    registry.register_pc("gandalf", "John")
    registry.register_pc("aragorn", "Jane")

    all_pcs = registry.get_all_pcs()

    assert len(all_pcs) == 2
    character_ids = [pc.character_id for pc in all_pcs]
    assert "gandalf" in character_ids
    assert "aragorn" in character_ids


def test_active_pc_property():
    """Test setting and getting active PC."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    registry.register_pc("gandalf", "John")
    registry.register_pc("aragorn", "Jane")

    # Initially None
    assert registry.active_pc is None

    # Set active PC
    registry.active_pc = "gandalf"
    assert registry.active_pc == "gandalf"

    # Change active PC
    registry.active_pc = "aragorn"
    assert registry.active_pc == "aragorn"

    # Clear active PC
    registry.active_pc = None
    assert registry.active_pc is None


def test_active_pc_invalid():
    """Test setting active PC to unknown character."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    with pytest.raises(ValueError, match="Character gandalf not registered"):
        registry.active_pc = "gandalf"


def test_count_properties():
    """Test count and active_count properties."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    assert registry.count == 0
    assert registry.active_count == 0

    registry.register_pc("gandalf", "John")
    registry.register_pc("aragorn", "Jane")

    assert registry.count == 2
    assert registry.active_count == 2

    registry.update_pc_state("aragorn", is_active=False)

    assert registry.count == 2
    assert registry.active_count == 1


# --- PCIdentifier Tests ---


def test_identify_by_character_name():
    """Test identifying PC by character name in input."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)
    registry.register_pc("gandalf", "John")
    registry.register_pc("aragorn", "Jane")

    identifier = PCIdentifier(registry)

    # Case-insensitive match
    result = identifier.identify_acting_pc("Gandalf attacks the orc")
    assert result == "gandalf"

    result = identifier.identify_acting_pc("aragorn moves forward")
    assert result == "aragorn"


def test_identify_by_player_mapping():
    """Test identifying PC by player name prefix."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)
    registry.register_pc("gandalf", "John")
    registry.register_pc("aragorn", "Jane")

    identifier = PCIdentifier(registry)

    # Player name prefix
    result = identifier.identify_acting_pc("John: I cast fireball")
    assert result == "gandalf"

    result = identifier.identify_acting_pc("Jane: I shoot an arrow")
    assert result == "aragorn"


def test_identify_last_speaker():
    """Test pronoun resolution using last speaker tracking."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)
    registry.register_pc("gandalf", "John")
    registry.register_pc("aragorn", "Jane")

    identifier = PCIdentifier(registry)

    # First set last speaker explicitly
    identifier.set_last_speaker("gandalf")

    # Generic input should resolve to last speaker
    result = identifier.identify_acting_pc("I attack")
    assert result == "gandalf"


def test_identify_active_pc():
    """Test falling back to registry active PC."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)
    registry.register_pc("gandalf", "John")
    registry.register_pc("aragorn", "Jane")

    registry.active_pc = "aragorn"

    identifier = PCIdentifier(registry)

    # No name, no last speaker -> should use active PC
    result = identifier.identify_acting_pc("I move forward")
    assert result == "aragorn"


def test_identify_first_active():
    """Test falling back to first active PC."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)
    registry.register_pc("gandalf", "John")
    registry.register_pc("aragorn", "Jane")

    identifier = PCIdentifier(registry)

    # No name, no last speaker, no active PC -> use first active
    result = identifier.identify_acting_pc("I do something")
    assert result in ["gandalf", "aragorn"]  # One of the active PCs


def test_identify_no_pcs():
    """Test identification when no PCs registered."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)

    identifier = PCIdentifier(registry)

    result = identifier.identify_acting_pc("I attack")
    assert result is None


def test_identify_inactive_last_speaker():
    """Test that inactive PCs are not returned as last speaker."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)
    registry.register_pc("gandalf", "John")
    registry.register_pc("aragorn", "Jane")

    identifier = PCIdentifier(registry)
    identifier.set_last_speaker("gandalf")

    # Deactivate gandalf
    registry.update_pc_state("gandalf", is_active=False)

    # Should not return inactive last speaker, fall back to active PC
    result = identifier.identify_acting_pc("I attack")
    assert result == "aragorn"  # The only active PC


def test_clear_last_speaker():
    """Test clearing last speaker tracking."""
    config = MultiPlayerConfig()
    registry = PCRegistry(config)
    registry.register_pc("gandalf", "John")

    identifier = PCIdentifier(registry)
    identifier.set_last_speaker("gandalf")

    identifier.clear_last_speaker()

    # Should not use last speaker anymore
    assert identifier._last_speaker is None


# --- MultiPlayerConfig Tests ---


def test_config_defaults():
    """Test default configuration values."""
    config = MultiPlayerConfig()

    assert config.max_players == 6
    assert config.allow_dynamic_join is True
    assert config.turn_timeout_seconds == 300
    assert config.simultaneous_actions is False
    assert config.pc_list == []


def test_config_custom():
    """Test custom configuration."""
    config = MultiPlayerConfig(
        max_players=4,
        allow_dynamic_join=False,
        turn_timeout_seconds=120,
        simultaneous_actions=True,
        pc_list=["gandalf", "aragorn"]
    )

    assert config.max_players == 4
    assert config.allow_dynamic_join is False
    assert config.turn_timeout_seconds == 120
    assert config.simultaneous_actions is True
    assert config.pc_list == ["gandalf", "aragorn"]


def test_config_max_players_validation():
    """Test max_players field validation."""
    # Valid range
    config = MultiPlayerConfig(max_players=1)
    assert config.max_players == 1

    config = MultiPlayerConfig(max_players=12)
    assert config.max_players == 12

    # Invalid: below minimum
    with pytest.raises(ValueError):
        MultiPlayerConfig(max_players=0)

    # Invalid: above maximum
    with pytest.raises(ValueError):
        MultiPlayerConfig(max_players=13)


def test_config_turn_timeout_validation():
    """Test turn_timeout_seconds field validation."""
    # Valid: at minimum
    config = MultiPlayerConfig(turn_timeout_seconds=30)
    assert config.turn_timeout_seconds == 30

    # Valid: above minimum
    config = MultiPlayerConfig(turn_timeout_seconds=600)
    assert config.turn_timeout_seconds == 600

    # Invalid: below minimum
    with pytest.raises(ValueError):
        MultiPlayerConfig(turn_timeout_seconds=29)
