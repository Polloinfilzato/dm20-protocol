"""
Integration tests for narrator-discovery integration.

Tests that the Narrator agent's scene descriptions respect discovery state,
that undiscovered features produce sensory hints, that discovery levels
produce appropriate description tiers, and that perception/investigation
checks upgrade discovery levels.
"""

import asyncio
import pytest
from pathlib import Path
from typing import Any

from dm20_protocol.consistency.discovery import (
    DiscoveryLevel,
    DiscoveryTracker,
    FeatureDiscovery,
    LocationDiscovery,
)
from dm20_protocol.consistency.narrator_discovery import (
    DiscoveryContext,
    FeatureView,
    build_discovery_context,
    filter_location_by_discovery,
    format_discovery_prompt_section,
)
from dm20_protocol.claudmaster.agents.narrator import (
    NarratorAgent,
    NarrativeStyle,
    SCENE_DESCRIPTION_TEMPLATE,
)
from dm20_protocol.models import Location


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

class MockLLM:
    """LLM client that returns a canned response and records calls."""

    def __init__(self, response: str = "You see a dimly lit corridor.") -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        return self.response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_campaign_dir(tmp_path: Path) -> Path:
    """Create a temporary campaign directory."""
    campaign_dir = tmp_path / "test_campaign"
    campaign_dir.mkdir()
    return campaign_dir


@pytest.fixture
def tracker(tmp_campaign_dir: Path) -> DiscoveryTracker:
    """Create a fresh DiscoveryTracker."""
    return DiscoveryTracker(tmp_campaign_dir)


@pytest.fixture
def sample_location() -> Location:
    """Create a sample location with multiple notable features."""
    return Location(
        name="Haunted Crypt",
        location_type="dungeon",
        description="A crumbling crypt beneath the old chapel.",
        population=0,
        notable_features=[
            "Ancient Altar",
            "Hidden Passage behind the altar",
            "Ghostly Inscription on the wall",
            "Cracked Floor revealing tunnels below",
        ],
        notes="The crypt has been sealed for centuries.",
    )


@pytest.fixture
def simple_location() -> Location:
    """Create a location with fewer features for simpler tests."""
    return Location(
        name="Village Square",
        location_type="town",
        description="A bustling town square with a central fountain.",
        population=500,
        notable_features=[
            "Central Fountain",
            "Market Stalls",
        ],
        notes="The heart of the village.",
    )


@pytest.fixture
def mock_llm() -> MockLLM:
    return MockLLM()


@pytest.fixture
def narrator(mock_llm: MockLLM) -> NarratorAgent:
    return NarratorAgent(llm=mock_llm, style=NarrativeStyle.DESCRIPTIVE)


# ---------------------------------------------------------------------------
# FeatureView Tests
# ---------------------------------------------------------------------------

class TestFeatureView:
    """Tests for FeatureView description tiers."""

    def test_undiscovered_feature_is_hidden(self):
        fv = FeatureView("Secret Door", DiscoveryLevel.UNDISCOVERED, hint_text="A cold draft...")
        assert fv.description_tier == "hidden"
        assert fv.display_text == "A cold draft..."

    def test_glimpsed_feature_is_vague(self):
        fv = FeatureView("Ancient Altar", DiscoveryLevel.GLIMPSED)
        assert fv.description_tier == "vague"
        assert "Vaguely perceived" in fv.display_text
        assert "Ancient Altar" in fv.display_text

    def test_explored_feature_is_full(self):
        fv = FeatureView("Market Stalls", DiscoveryLevel.EXPLORED)
        assert fv.description_tier == "full"
        assert fv.display_text == "Market Stalls"

    def test_fully_mapped_feature_is_complete(self):
        fv = FeatureView("Trap Mechanism", DiscoveryLevel.FULLY_MAPPED)
        assert fv.description_tier == "complete"
        assert "fully mapped" in fv.display_text.lower()
        assert "Trap Mechanism" in fv.display_text

    def test_undiscovered_without_hint(self):
        fv = FeatureView("Something", DiscoveryLevel.UNDISCOVERED)
        assert fv.description_tier == "hidden"
        assert fv.display_text == ""


# ---------------------------------------------------------------------------
# DiscoveryContext Tests
# ---------------------------------------------------------------------------

class TestDiscoveryContext:
    """Tests for DiscoveryContext properties."""

    def test_visible_features(self):
        features = [
            FeatureView("A", DiscoveryLevel.GLIMPSED),
            FeatureView("B", DiscoveryLevel.UNDISCOVERED, "hint"),
            FeatureView("C", DiscoveryLevel.EXPLORED),
        ]
        ctx = DiscoveryContext("TestLoc", DiscoveryLevel.EXPLORED, features)
        assert len(ctx.visible_features) == 2
        assert len(ctx.hidden_features) == 1
        assert ctx.total_features == 3

    def test_all_hidden(self):
        features = [
            FeatureView("A", DiscoveryLevel.UNDISCOVERED, "hint1"),
            FeatureView("B", DiscoveryLevel.UNDISCOVERED, "hint2"),
        ]
        ctx = DiscoveryContext("TestLoc", DiscoveryLevel.UNDISCOVERED, features)
        assert len(ctx.visible_features) == 0
        assert len(ctx.hidden_features) == 2

    def test_all_visible(self):
        features = [
            FeatureView("A", DiscoveryLevel.FULLY_MAPPED),
            FeatureView("B", DiscoveryLevel.EXPLORED),
        ]
        ctx = DiscoveryContext("TestLoc", DiscoveryLevel.FULLY_MAPPED, features)
        assert len(ctx.visible_features) == 2
        assert len(ctx.hidden_features) == 0


# ---------------------------------------------------------------------------
# build_discovery_context Tests
# ---------------------------------------------------------------------------

class TestBuildDiscoveryContext:
    """Tests for the main context builder function."""

    def test_first_visit_auto_glimpse(self, sample_location, tracker):
        """First visit auto-sets location to GLIMPSED and reveals obvious features."""
        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=True)

        assert ctx.overall_level == DiscoveryLevel.GLIMPSED
        assert ctx.location_name == "Haunted Crypt"

        # First half of 4 features = 2 should be GLIMPSED
        visible = ctx.visible_features
        assert len(visible) >= 1  # At least 1 obvious feature revealed

    def test_first_visit_reveals_obvious_features(self, sample_location, tracker):
        """Auto-glimpse reveals the first half of notable features."""
        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=True)

        # 4 features, obvious_count = max(1, 4//2) = 2
        visible_names = [fv.feature_name for fv in ctx.visible_features]
        assert "Ancient Altar" in visible_names
        assert "Hidden Passage behind the altar" in visible_names

        # The other 2 should be hidden
        hidden = ctx.hidden_features
        assert len(hidden) == 2

    def test_no_auto_glimpse_with_explicit_undiscovered(self, sample_location, tracker):
        """Without auto-glimpse, explicitly UNDISCOVERED location stays undiscovered."""
        # Explicitly register the location as UNDISCOVERED
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.UNDISCOVERED)
        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)

        assert ctx.overall_level == DiscoveryLevel.UNDISCOVERED
        assert len(ctx.visible_features) == 0
        assert len(ctx.hidden_features) == 4

    def test_no_auto_glimpse_untracked_gets_default(self, sample_location, tracker):
        """Without auto-glimpse, untracked location gets backward-compatible EXPLORED default."""
        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)

        # Backward compat: untracked locations default to EXPLORED
        assert ctx.overall_level == DiscoveryLevel.EXPLORED

    def test_explored_location_shows_all(self, sample_location, tracker):
        """EXPLORED location with all features explored shows everything."""
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.EXPLORED)
        for feature in sample_location.notable_features:
            tracker.discover_feature("Haunted Crypt", feature, DiscoveryLevel.EXPLORED)

        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)

        assert ctx.overall_level == DiscoveryLevel.EXPLORED
        assert len(ctx.visible_features) == 4
        assert len(ctx.hidden_features) == 0

    def test_mixed_discovery_levels(self, sample_location, tracker):
        """Features at different discovery levels produce appropriate tiers."""
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.EXPLORED)
        tracker.discover_feature("Haunted Crypt", "Ancient Altar", DiscoveryLevel.FULLY_MAPPED)
        tracker.discover_feature("Haunted Crypt", "Hidden Passage behind the altar", DiscoveryLevel.EXPLORED)
        tracker.discover_feature("Haunted Crypt", "Ghostly Inscription on the wall", DiscoveryLevel.GLIMPSED)
        # "Cracked Floor" left undiscovered

        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)

        tiers = {fv.feature_name: fv.description_tier for fv in ctx.feature_views}
        assert tiers["Ancient Altar"] == "complete"
        assert tiers["Hidden Passage behind the altar"] == "full"
        assert tiers["Ghostly Inscription on the wall"] == "vague"
        assert tiers["Cracked Floor revealing tunnels below"] == "hidden"

    def test_hidden_features_get_hints(self, sample_location, tracker):
        """Undiscovered features get sensory hint text."""
        # Explicitly track the location so features default to UNDISCOVERED
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.GLIMPSED)
        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)

        assert len(ctx.hidden_features) > 0
        for fv in ctx.hidden_features:
            assert fv.hint_text != ""
            assert fv.description_tier == "hidden"

    def test_hints_are_deterministic(self, sample_location, tracker):
        """Same feature always produces the same hint."""
        # Explicitly track so features are hidden
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.GLIMPSED)
        ctx1 = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)
        ctx2 = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)

        hints1 = {fv.feature_name: fv.hint_text for fv in ctx1.hidden_features}
        hints2 = {fv.feature_name: fv.hint_text for fv in ctx2.hidden_features}
        assert len(hints1) > 0
        assert hints1 == hints2

    def test_simple_location_auto_glimpse(self, simple_location, tracker):
        """Simple location with 2 features: auto-glimpse reveals at least 1."""
        ctx = build_discovery_context(simple_location, tracker, auto_glimpse_on_visit=True)

        assert ctx.overall_level == DiscoveryLevel.GLIMPSED
        # max(1, 2//2) = 1 obvious feature
        assert len(ctx.visible_features) >= 1

    def test_backward_compatible_default(self, sample_location, tracker):
        """Locations with no explicit tracking get EXPLORED by default."""
        # Don't register anything — the tracker should use the DEFAULT_LEVEL
        state = tracker.get_discovery_state("Some Unknown Location")
        assert DiscoveryLevel(state.overall_level) == DiscoveryLevel.EXPLORED


# ---------------------------------------------------------------------------
# format_discovery_prompt_section Tests
# ---------------------------------------------------------------------------

class TestFormatDiscoveryPromptSection:
    """Tests for formatting discovery context into prompt text."""

    def test_glimpsed_features_in_prompt(self, sample_location, tracker):
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.GLIMPSED)
        tracker.discover_feature("Haunted Crypt", "Ancient Altar", DiscoveryLevel.GLIMPSED)

        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)
        prompt = format_discovery_prompt_section(ctx)

        assert "GLIMPSED" in prompt
        assert "Ancient Altar" in prompt
        assert "vague" in prompt.lower() or "uncertain" in prompt.lower()

    def test_explored_features_in_prompt(self, sample_location, tracker):
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.EXPLORED)
        tracker.discover_feature("Haunted Crypt", "Ancient Altar", DiscoveryLevel.EXPLORED)

        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)
        prompt = format_discovery_prompt_section(ctx)

        assert "EXPLORED" in prompt
        assert "Ancient Altar" in prompt
        assert "fully" in prompt.lower() or "detailed" in prompt.lower()

    def test_fully_mapped_in_prompt(self, sample_location, tracker):
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.FULLY_MAPPED)
        tracker.discover_feature("Haunted Crypt", "Ancient Altar", DiscoveryLevel.FULLY_MAPPED)

        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)
        prompt = format_discovery_prompt_section(ctx)

        assert "FULLY MAPPED" in prompt
        assert "mechanical" in prompt.lower() or "tactical" in prompt.lower()

    def test_hidden_hints_in_prompt(self, sample_location, tracker):
        """Hidden features produce sensory hints in the prompt."""
        # Explicitly track so some features are hidden
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.GLIMPSED)
        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)
        prompt = format_discovery_prompt_section(ctx)

        assert "Sensory Hints" in prompt
        assert "do NOT reveal" in prompt

    def test_overall_guidance_glimpsed(self, sample_location, tracker):
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.GLIMPSED)
        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)
        prompt = format_discovery_prompt_section(ctx)

        assert "first impression" in prompt.lower() or "atmospheric" in prompt.lower()

    def test_overall_guidance_explored(self, sample_location, tracker):
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.EXPLORED)
        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)
        prompt = format_discovery_prompt_section(ctx)

        assert "familiar" in prompt.lower()

    def test_overall_guidance_fully_mapped(self, sample_location, tracker):
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.FULLY_MAPPED)
        ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)
        prompt = format_discovery_prompt_section(ctx)

        assert "intimately" in prompt.lower() or "tactical" in prompt.lower()

    def test_empty_context_returns_empty(self):
        """None context returns empty string."""
        assert format_discovery_prompt_section(None) == ""


# ---------------------------------------------------------------------------
# Narrator Integration Tests
# ---------------------------------------------------------------------------

class TestNarratorDiscoveryIntegration:
    """Tests that the narrator properly uses discovery context."""

    def test_scene_template_has_discovery_placeholder(self):
        """The scene description template includes discovery context placeholder."""
        assert "{discovery_context}" in SCENE_DESCRIPTION_TEMPLATE

    def test_narrator_stores_discovery_context(self, narrator):
        """Narrator stores discovery_context from context dict during reason()."""
        context = {
            "player_action": "look around",
            "location": {"name": "Crypt"},
            "discovery_context": "## Discovery State\nSome context here",
        }
        asyncio.get_event_loop().run_until_complete(narrator.reason(context))
        assert narrator._current_discovery_context == "## Discovery State\nSome context here"

    def test_discovery_context_in_prompt(self, narrator, mock_llm):
        """Discovery context is injected into the LLM prompt."""
        context = {
            "player_action": "look around",
            "location": {"name": "Crypt"},
            "discovery_context": "## Discovery State for Crypt\nOverall: GLIMPSED",
        }
        asyncio.get_event_loop().run_until_complete(narrator.reason(context))
        asyncio.get_event_loop().run_until_complete(narrator.act("Test reasoning"))

        # Check the prompt sent to the LLM
        assert len(mock_llm.calls) == 1
        prompt = mock_llm.calls[0]["prompt"]
        assert "Discovery State for Crypt" in prompt
        assert "GLIMPSED" in prompt

    def test_empty_discovery_context(self, narrator, mock_llm):
        """When no discovery context, prompt still works (empty section)."""
        context = {
            "player_action": "look around",
            "location": {"name": "Tavern"},
        }
        asyncio.get_event_loop().run_until_complete(narrator.reason(context))
        asyncio.get_event_loop().run_until_complete(narrator.act("Test reasoning"))

        assert len(mock_llm.calls) == 1
        prompt = mock_llm.calls[0]["prompt"]
        # Should not contain discovery section headers
        assert "## Discovery State" not in prompt

    def test_full_integration_flow(self, narrator, mock_llm, sample_location, tracker):
        """End-to-end: build context, format it, pass to narrator, check prompt."""
        # Setup: first visit to crypt
        discovery_ctx = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=True)
        prompt_section = format_discovery_prompt_section(discovery_ctx)

        # Pass to narrator
        context = {
            "player_action": "enter the crypt",
            "location": {"name": "Haunted Crypt"},
            "discovery_context": prompt_section,
        }
        asyncio.get_event_loop().run_until_complete(narrator.reason(context))
        asyncio.get_event_loop().run_until_complete(narrator.act("Player is entering the crypt"))

        # Verify the prompt
        prompt = mock_llm.calls[0]["prompt"]
        assert "Haunted Crypt" in prompt
        assert "GLIMPSED" in prompt
        # Visible features should be mentioned
        assert "Ancient Altar" in prompt
        # Hidden features should have hints, not names
        assert "Sensory Hints" in prompt


# ---------------------------------------------------------------------------
# Perception/Investigation Check Discovery Upgrade Tests
# ---------------------------------------------------------------------------

class TestPerceptionDiscoveryUpgrade:
    """Tests that perception/investigation checks upgrade discovery levels."""

    def test_perception_check_reveals_feature(self, sample_location, tracker):
        """A successful perception check reveals a hidden feature."""
        # Start with first visit
        build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=True)

        # "Cracked Floor" was not revealed on first visit
        state = tracker.get_discovery_state("Haunted Crypt")
        cracked_floor_disc = None
        for fd in state.feature_discoveries:
            if fd.feature_name == "Cracked Floor revealing tunnels below":
                cracked_floor_disc = fd
                break

        # Either not tracked or UNDISCOVERED
        if cracked_floor_disc:
            assert DiscoveryLevel(cracked_floor_disc.discovery_level) == DiscoveryLevel.UNDISCOVERED

        # Simulate perception check success
        tracker.discover_feature(
            "Haunted Crypt",
            "Cracked Floor revealing tunnels below",
            DiscoveryLevel.GLIMPSED,
            method="perception check (DC 15)",
            discovered_by="Aldric",
            session=1,
        )

        # Verify upgrade
        fd = None
        state = tracker.get_discovery_state("Haunted Crypt")
        for f in state.feature_discoveries:
            if f.feature_name == "Cracked Floor revealing tunnels below":
                fd = f
                break

        assert fd is not None
        assert DiscoveryLevel(fd.discovery_level) == DiscoveryLevel.GLIMPSED
        assert fd.discovered_by == "Aldric"
        assert fd.discovery_method == "perception check (DC 15)"

    def test_investigation_upgrades_to_explored(self, sample_location, tracker):
        """Investigation check can upgrade a GLIMPSED feature to EXPLORED."""
        # First: glimpse the feature
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.EXPLORED)
        tracker.discover_feature(
            "Haunted Crypt", "Ancient Altar", DiscoveryLevel.GLIMPSED,
            method="first visit",
        )

        # Then: investigation upgrades it
        tracker.discover_feature(
            "Haunted Crypt", "Ancient Altar", DiscoveryLevel.EXPLORED,
            method="investigation check (DC 12)",
            discovered_by="Elara",
            session=2,
        )

        fd = None
        state = tracker.get_discovery_state("Haunted Crypt")
        for f in state.feature_discoveries:
            if f.feature_name == "Ancient Altar":
                fd = f
                break

        assert fd is not None
        assert DiscoveryLevel(fd.discovery_level) == DiscoveryLevel.EXPLORED
        assert fd.discovered_by == "Elara"
        assert fd.discovery_method == "investigation check (DC 12)"

    def test_downgrade_is_silently_ignored(self, sample_location, tracker):
        """Attempting to downgrade discovery level is silently ignored."""
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.EXPLORED)
        tracker.discover_feature(
            "Haunted Crypt", "Ancient Altar", DiscoveryLevel.EXPLORED,
        )

        # Try to downgrade to GLIMPSED
        tracker.discover_feature(
            "Haunted Crypt", "Ancient Altar", DiscoveryLevel.GLIMPSED,
        )

        fd = None
        state = tracker.get_discovery_state("Haunted Crypt")
        for f in state.feature_discoveries:
            if f.feature_name == "Ancient Altar":
                fd = f
                break

        assert fd is not None
        assert DiscoveryLevel(fd.discovery_level) == DiscoveryLevel.EXPLORED  # Not downgraded

    def test_discovery_context_reflects_upgrades(self, sample_location, tracker):
        """After upgrading a feature, the discovery context reflects the change."""
        # First visit: auto-glimpse
        ctx1 = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=True)

        # Find a hidden feature
        hidden_names = [fv.feature_name for fv in ctx1.hidden_features]
        assert len(hidden_names) > 0

        # Upgrade one hidden feature via perception
        target_feature = hidden_names[0]
        tracker.discover_feature(
            "Haunted Crypt", target_feature, DiscoveryLevel.EXPLORED,
            method="perception check",
        )

        # Rebuild context
        ctx2 = build_discovery_context(sample_location, tracker, auto_glimpse_on_visit=False)

        # The feature should now be visible
        visible_names = [fv.feature_name for fv in ctx2.visible_features]
        assert target_feature in visible_names


# ---------------------------------------------------------------------------
# filter_location_by_discovery Tests
# ---------------------------------------------------------------------------

class TestFilterLocationByDiscovery:
    """Tests for the get_location MCP tool's discovery filter."""

    def test_filter_hides_undiscovered_features(self, sample_location, tracker):
        """Discovery filter removes undiscovered features from the output."""
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.EXPLORED)
        tracker.discover_feature("Haunted Crypt", "Ancient Altar", DiscoveryLevel.EXPLORED)
        # Only "Ancient Altar" is discovered

        result = filter_location_by_discovery(sample_location, tracker)

        assert "Ancient Altar" in result["notable_features"]
        assert len(result["notable_features"]) == 1
        assert result["hidden_features_count"] == 3
        assert result["discovery_level"] == "EXPLORED"

    def test_filter_shows_all_discovered(self, sample_location, tracker):
        """When all features are discovered, all are shown."""
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.FULLY_MAPPED)
        for feature in sample_location.notable_features:
            tracker.discover_feature("Haunted Crypt", feature, DiscoveryLevel.FULLY_MAPPED)

        result = filter_location_by_discovery(sample_location, tracker)

        assert len(result["notable_features"]) == 4
        assert result["hidden_features_count"] == 0
        assert result["discovery_level"] == "FULLY_MAPPED"

    def test_filter_backward_compatible(self, sample_location, tracker):
        """Locations without explicit discovery data show all features (EXPLORED default)."""
        # Don't register in tracker — backward compatibility should kick in
        result = filter_location_by_discovery(sample_location, tracker)

        # Default is EXPLORED, so all features should be visible
        assert len(result["notable_features"]) == 4
        assert result["hidden_features_count"] == 0
        assert result["discovery_level"] == "EXPLORED"

    def test_filter_glimpsed_features_included(self, sample_location, tracker):
        """GLIMPSED features are shown in the filter (they are visible)."""
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.GLIMPSED)
        tracker.discover_feature("Haunted Crypt", "Ancient Altar", DiscoveryLevel.GLIMPSED)
        tracker.discover_feature("Haunted Crypt", "Ghostly Inscription on the wall", DiscoveryLevel.GLIMPSED)

        result = filter_location_by_discovery(sample_location, tracker)

        assert "Ancient Altar" in result["notable_features"]
        assert "Ghostly Inscription on the wall" in result["notable_features"]
        assert len(result["notable_features"]) == 2
        assert result["hidden_features_count"] == 2

    def test_filter_output_structure(self, sample_location, tracker):
        """Verify the full output structure of filter_location_by_discovery."""
        tracker.discover_location("Haunted Crypt", DiscoveryLevel.EXPLORED)

        result = filter_location_by_discovery(sample_location, tracker)

        assert "name" in result
        assert "location_type" in result
        assert "description" in result
        assert "population" in result
        assert "government" in result
        assert "notable_features" in result
        assert "npcs" in result
        assert "connections" in result
        assert "notes" in result
        assert "discovery_level" in result
        assert "hidden_features_count" in result


# ---------------------------------------------------------------------------
# Persistence Tests
# ---------------------------------------------------------------------------

class TestDiscoveryPersistence:
    """Tests that discovery state is properly saved and loaded."""

    def test_save_and_reload(self, sample_location, tmp_campaign_dir):
        """Discovery state survives save/load cycle."""
        tracker1 = DiscoveryTracker(tmp_campaign_dir)
        tracker1.discover_location("Haunted Crypt", DiscoveryLevel.EXPLORED)
        tracker1.discover_feature(
            "Haunted Crypt", "Ancient Altar", DiscoveryLevel.FULLY_MAPPED,
            method="investigation", discovered_by="Aldric", session=3,
        )
        tracker1.save()

        # Reload
        tracker2 = DiscoveryTracker(tmp_campaign_dir)

        ctx = build_discovery_context(sample_location, tracker2, auto_glimpse_on_visit=False)

        # Verify the persisted state
        tiers = {fv.feature_name: fv.description_tier for fv in ctx.feature_views}
        assert tiers["Ancient Altar"] == "complete"

    def test_narrator_context_after_reload(self, sample_location, tmp_campaign_dir, mock_llm):
        """Full flow: discover, save, reload, narrator gets correct context."""
        # Phase 1: Discover and save
        tracker1 = DiscoveryTracker(tmp_campaign_dir)
        tracker1.discover_location("Haunted Crypt", DiscoveryLevel.EXPLORED)
        tracker1.discover_feature("Haunted Crypt", "Ancient Altar", DiscoveryLevel.EXPLORED)
        tracker1.discover_feature("Haunted Crypt", "Hidden Passage behind the altar", DiscoveryLevel.GLIMPSED)
        tracker1.save()

        # Phase 2: Reload and build context
        tracker2 = DiscoveryTracker(tmp_campaign_dir)
        ctx = build_discovery_context(sample_location, tracker2, auto_glimpse_on_visit=False)
        prompt_section = format_discovery_prompt_section(ctx)

        # Phase 3: Narrator uses it
        narrator = NarratorAgent(llm=mock_llm)
        context = {
            "player_action": "examine the crypt",
            "location": {"name": "Haunted Crypt"},
            "discovery_context": prompt_section,
        }
        asyncio.get_event_loop().run_until_complete(narrator.reason(context))
        asyncio.get_event_loop().run_until_complete(narrator.act("Examining crypt"))

        prompt = mock_llm.calls[0]["prompt"]
        # EXPLORED feature should be described fully
        assert "Ancient Altar" in prompt
        assert "EXPLORED" in prompt
        # GLIMPSED feature should be vague
        assert "Hidden Passage" in prompt
        assert "GLIMPSED" in prompt
