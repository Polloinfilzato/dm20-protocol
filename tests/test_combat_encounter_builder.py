"""
Tests for the Encounter Builder module.

Covers XP budget calculation, encounter multipliers, difficulty classification,
party size adjustments, and encounter composition building.
"""

import pytest

from dm20_protocol.combat.encounter_builder import (
    EncounterSuggestion,
    EncounterComposition,
    MonsterGroup,
    Difficulty,
    XP_THRESHOLDS,
    CR_TO_XP,
    ENCOUNTER_MULTIPLIERS,
    calculate_xp_budget,
    get_xp_thresholds,
    get_encounter_multiplier,
    classify_difficulty,
    build_encounter,
    _format_cr,
    _cr_to_xp,
    _find_cr_for_budget,
)


# =============================================================================
# XP Threshold Table Tests
# =============================================================================

class TestXPThresholds:
    """Tests for the XP threshold constants and lookup."""

    def test_xp_thresholds_has_all_levels(self):
        """XP_THRESHOLDS covers levels 1-20."""
        for level in range(1, 21):
            assert level in XP_THRESHOLDS, f"Missing level {level}"

    def test_xp_thresholds_has_all_difficulties(self):
        """Each level has all four difficulty tiers."""
        for level in range(1, 21):
            for diff in ("easy", "medium", "hard", "deadly"):
                assert diff in XP_THRESHOLDS[level], f"Missing {diff} for level {level}"

    def test_xp_thresholds_increasing_by_difficulty(self):
        """For each level, easy < medium < hard < deadly."""
        for level in range(1, 21):
            t = XP_THRESHOLDS[level]
            assert t["easy"] < t["medium"] < t["hard"] < t["deadly"], (
                f"Thresholds not strictly increasing at level {level}: {t}"
            )

    def test_xp_thresholds_known_values(self):
        """Verify specific known values from the DMG."""
        # Level 1
        assert XP_THRESHOLDS[1]["easy"] == 25
        assert XP_THRESHOLDS[1]["medium"] == 50
        assert XP_THRESHOLDS[1]["hard"] == 75
        assert XP_THRESHOLDS[1]["deadly"] == 100

        # Level 5
        assert XP_THRESHOLDS[5]["easy"] == 250
        assert XP_THRESHOLDS[5]["medium"] == 500
        assert XP_THRESHOLDS[5]["hard"] == 750
        assert XP_THRESHOLDS[5]["deadly"] == 1100

        # Level 20
        assert XP_THRESHOLDS[20]["easy"] == 2800
        assert XP_THRESHOLDS[20]["medium"] == 5700
        assert XP_THRESHOLDS[20]["hard"] == 8500
        assert XP_THRESHOLDS[20]["deadly"] == 12700


# =============================================================================
# CR to XP Table Tests
# =============================================================================

class TestCRToXP:
    """Tests for the CR to XP conversion table."""

    def test_cr_to_xp_has_standard_crs(self):
        """CR_TO_XP has all standard CRs from 0 to 30."""
        expected_crs = [0, 0.125, 0.25, 0.5] + list(range(1, 31))
        for cr in expected_crs:
            assert cr in CR_TO_XP, f"Missing CR {cr}"

    def test_cr_to_xp_known_values(self):
        """Verify specific CR->XP mappings from the DMG."""
        assert CR_TO_XP[0] == 10
        assert CR_TO_XP[0.125] == 25
        assert CR_TO_XP[0.25] == 50
        assert CR_TO_XP[0.5] == 100
        assert CR_TO_XP[1] == 200
        assert CR_TO_XP[5] == 1800
        assert CR_TO_XP[10] == 5900
        assert CR_TO_XP[20] == 25000
        assert CR_TO_XP[30] == 155000

    def test_cr_to_xp_monotonically_increasing(self):
        """XP values increase with CR."""
        sorted_crs = sorted(CR_TO_XP.keys())
        for i in range(1, len(sorted_crs)):
            assert CR_TO_XP[sorted_crs[i]] > CR_TO_XP[sorted_crs[i - 1]], (
                f"XP not increasing: CR {sorted_crs[i-1]} ({CR_TO_XP[sorted_crs[i-1]]}) "
                f">= CR {sorted_crs[i]} ({CR_TO_XP[sorted_crs[i]]})"
            )

    def test_cr_to_xp_helper_function(self):
        """_cr_to_xp helper returns correct values."""
        assert _cr_to_xp(1) == 200
        assert _cr_to_xp(0.5) == 100
        assert _cr_to_xp(5) == 1800

    def test_cr_to_xp_helper_invalid_cr(self):
        """_cr_to_xp raises ValueError for unknown CRs."""
        with pytest.raises(ValueError, match="Unknown challenge rating"):
            _cr_to_xp(0.33)


# =============================================================================
# XP Budget Calculation Tests
# =============================================================================

class TestCalculateXPBudget:
    """Tests for calculate_xp_budget()."""

    def test_single_level_1_character(self):
        """Budget for a single level 1 character."""
        assert calculate_xp_budget([1], "easy") == 25
        assert calculate_xp_budget([1], "medium") == 50
        assert calculate_xp_budget([1], "hard") == 75
        assert calculate_xp_budget([1], "deadly") == 100

    def test_standard_party_level_5(self):
        """Budget for a standard party of four level-5 characters."""
        party = [5, 5, 5, 5]
        assert calculate_xp_budget(party, "easy") == 250 * 4
        assert calculate_xp_budget(party, "medium") == 500 * 4
        assert calculate_xp_budget(party, "hard") == 750 * 4
        assert calculate_xp_budget(party, "deadly") == 1100 * 4

    def test_mixed_level_party(self):
        """Budget for a party with different levels."""
        party = [3, 4, 5, 6]
        expected_medium = 150 + 250 + 500 + 600  # sum of individual medium thresholds
        assert calculate_xp_budget(party, "medium") == expected_medium

    def test_case_insensitive_difficulty(self):
        """Difficulty parameter is case-insensitive."""
        assert calculate_xp_budget([5], "MEDIUM") == 500
        assert calculate_xp_budget([5], "Medium") == 500
        assert calculate_xp_budget([5], "medium") == 500

    def test_invalid_difficulty_raises(self):
        """Invalid difficulty strings raise ValueError."""
        with pytest.raises(ValueError, match="Invalid difficulty"):
            calculate_xp_budget([5], "impossible")

    def test_empty_party_raises(self):
        """Empty party raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            calculate_xp_budget([], "medium")

    def test_invalid_level_raises(self):
        """Invalid character levels raise ValueError."""
        with pytest.raises(ValueError, match="between 1 and 20"):
            calculate_xp_budget([0], "medium")
        with pytest.raises(ValueError, match="between 1 and 20"):
            calculate_xp_budget([21], "medium")

    def test_large_party(self):
        """Budget scales linearly with party size."""
        single = calculate_xp_budget([10], "hard")
        party_of_6 = calculate_xp_budget([10] * 6, "hard")
        assert party_of_6 == single * 6


# =============================================================================
# Get XP Thresholds Tests
# =============================================================================

class TestGetXPThresholds:
    """Tests for get_xp_thresholds()."""

    def test_single_character(self):
        """Thresholds for a single character match the table directly."""
        thresholds = get_xp_thresholds([5])
        assert thresholds == XP_THRESHOLDS[5]

    def test_party_sums_correctly(self):
        """Thresholds sum across all party members."""
        thresholds = get_xp_thresholds([3, 3])
        assert thresholds["easy"] == 75 * 2
        assert thresholds["medium"] == 150 * 2
        assert thresholds["hard"] == 225 * 2
        assert thresholds["deadly"] == 400 * 2

    def test_returns_all_four_difficulties(self):
        """Result has exactly the four standard difficulty keys."""
        thresholds = get_xp_thresholds([1])
        assert set(thresholds.keys()) == {"easy", "medium", "hard", "deadly"}


# =============================================================================
# Encounter Multiplier Tests
# =============================================================================

class TestEncounterMultiplier:
    """Tests for get_encounter_multiplier()."""

    def test_single_monster_standard_party(self):
        """1 monster, standard party (3-5) = x1.0."""
        assert get_encounter_multiplier(1, 4) == 1.0

    def test_two_monsters_standard_party(self):
        """2 monsters, standard party = x1.5."""
        assert get_encounter_multiplier(2, 4) == 1.5

    def test_three_to_six_monsters_standard_party(self):
        """3-6 monsters, standard party = x2.0."""
        for count in range(3, 7):
            assert get_encounter_multiplier(count, 4) == 2.0, f"Failed for count={count}"

    def test_seven_to_ten_monsters_standard_party(self):
        """7-10 monsters, standard party = x2.5."""
        for count in range(7, 11):
            assert get_encounter_multiplier(count, 4) == 2.5, f"Failed for count={count}"

    def test_eleven_to_fourteen_monsters_standard_party(self):
        """11-14 monsters, standard party = x3.0."""
        for count in range(11, 15):
            assert get_encounter_multiplier(count, 4) == 3.0, f"Failed for count={count}"

    def test_fifteen_plus_monsters_standard_party(self):
        """15+ monsters, standard party = x4.0."""
        assert get_encounter_multiplier(15, 4) == 4.0
        assert get_encounter_multiplier(20, 4) == 4.0
        assert get_encounter_multiplier(100, 4) == 4.0

    def test_small_party_increases_multiplier(self):
        """Party of 1-2 increases multiplier by one step."""
        # 1 monster: base x1.0, small party -> x1.5
        assert get_encounter_multiplier(1, 1) == 1.5
        assert get_encounter_multiplier(1, 2) == 1.5

        # 2 monsters: base x1.5, small party -> x2.0
        assert get_encounter_multiplier(2, 2) == 2.0

        # 3-6 monsters: base x2.0, small party -> x2.5
        assert get_encounter_multiplier(3, 1) == 2.5

    def test_large_party_decreases_multiplier(self):
        """Party of 6+ decreases multiplier by one step."""
        # 1 monster: base x1.0, large party -> x0.5
        assert get_encounter_multiplier(1, 6) == 0.5
        assert get_encounter_multiplier(1, 8) == 0.5

        # 2 monsters: base x1.5, large party -> x1.0
        assert get_encounter_multiplier(2, 6) == 1.0

        # 3-6 monsters: base x2.0, large party -> x1.5
        assert get_encounter_multiplier(4, 7) == 1.5

    def test_standard_party_no_adjustment(self):
        """Party of 3-5 gets no multiplier adjustment."""
        for party_size in (3, 4, 5):
            assert get_encounter_multiplier(1, party_size) == 1.0
            assert get_encounter_multiplier(2, party_size) == 1.5

    def test_invalid_monster_count_raises(self):
        """monster_count < 1 raises ValueError."""
        with pytest.raises(ValueError, match="monster_count"):
            get_encounter_multiplier(0, 4)

    def test_invalid_party_size_raises(self):
        """party_size < 1 raises ValueError."""
        with pytest.raises(ValueError, match="party_size"):
            get_encounter_multiplier(1, 0)

    def test_multiplier_cap_small_party(self):
        """Small party can't exceed the max multiplier step."""
        # 15+ monsters = x4.0, small party +1 step -> x5.0 (max)
        assert get_encounter_multiplier(15, 1) == 5.0

    def test_multiplier_floor_large_party(self):
        """Large party can't go below the min multiplier step."""
        # 1 monster = x1.0, large party -1 step -> x0.5 (min)
        assert get_encounter_multiplier(1, 6) == 0.5


# =============================================================================
# Difficulty Classification Tests
# =============================================================================

class TestClassifyDifficulty:
    """Tests for classify_difficulty()."""

    def test_trivial_below_easy(self):
        """XP below easy threshold is 'trivial'."""
        thresholds = {"easy": 100, "medium": 200, "hard": 300, "deadly": 400}
        assert classify_difficulty(50, thresholds) == "trivial"
        assert classify_difficulty(0, thresholds) == "trivial"

    def test_easy_at_threshold(self):
        """XP at easy threshold is 'easy'."""
        thresholds = {"easy": 100, "medium": 200, "hard": 300, "deadly": 400}
        assert classify_difficulty(100, thresholds) == "easy"

    def test_easy_between_thresholds(self):
        """XP between easy and medium is 'easy'."""
        thresholds = {"easy": 100, "medium": 200, "hard": 300, "deadly": 400}
        assert classify_difficulty(150, thresholds) == "easy"

    def test_medium(self):
        """XP at or above medium threshold is 'medium'."""
        thresholds = {"easy": 100, "medium": 200, "hard": 300, "deadly": 400}
        assert classify_difficulty(200, thresholds) == "medium"
        assert classify_difficulty(250, thresholds) == "medium"

    def test_hard(self):
        """XP at or above hard threshold is 'hard'."""
        thresholds = {"easy": 100, "medium": 200, "hard": 300, "deadly": 400}
        assert classify_difficulty(300, thresholds) == "hard"
        assert classify_difficulty(350, thresholds) == "hard"

    def test_deadly(self):
        """XP at or above deadly threshold is 'deadly'."""
        thresholds = {"easy": 100, "medium": 200, "hard": 300, "deadly": 400}
        assert classify_difficulty(400, thresholds) == "deadly"
        assert classify_difficulty(1000, thresholds) == "deadly"

    def test_with_real_thresholds(self):
        """Classification with real party thresholds."""
        # Party of 4 level 5 characters
        thresholds = get_xp_thresholds([5, 5, 5, 5])
        # easy=1000, medium=2000, hard=3000, deadly=4400

        assert classify_difficulty(500, thresholds) == "trivial"
        assert classify_difficulty(1000, thresholds) == "easy"
        assert classify_difficulty(1500, thresholds) == "easy"
        assert classify_difficulty(2000, thresholds) == "medium"
        assert classify_difficulty(3000, thresholds) == "hard"
        assert classify_difficulty(4400, thresholds) == "deadly"


# =============================================================================
# CR Format Helper Tests
# =============================================================================

class TestFormatCR:
    """Tests for _format_cr()."""

    def test_fractional_crs(self):
        assert _format_cr(0.125) == "1/8"
        assert _format_cr(0.25) == "1/4"
        assert _format_cr(0.5) == "1/2"

    def test_integer_crs(self):
        assert _format_cr(0) == "0"
        assert _format_cr(1) == "1"
        assert _format_cr(5) == "5"
        assert _format_cr(20) == "20"
        assert _format_cr(30.0) == "30"


# =============================================================================
# Build Encounter Tests (without rulebooks)
# =============================================================================

class TestBuildEncounterNoRulebooks:
    """Tests for build_encounter() without loaded rulebooks."""

    def test_returns_encounter_suggestion(self):
        """build_encounter returns an EncounterSuggestion."""
        result = build_encounter([5, 5, 5, 5], "medium")
        assert isinstance(result, EncounterSuggestion)

    def test_correct_party_info(self):
        """Result contains correct party information."""
        result = build_encounter([3, 4, 5], "hard")
        assert result.party_levels == [3, 4, 5]
        assert result.party_size == 3
        assert result.requested_difficulty == "hard"

    def test_correct_xp_budget(self):
        """XP budget matches calculate_xp_budget()."""
        party = [5, 5, 5, 5]
        result = build_encounter(party, "medium")
        expected_budget = calculate_xp_budget(party, "medium")
        assert result.xp_budget == expected_budget

    def test_correct_thresholds(self):
        """Thresholds match get_xp_thresholds()."""
        party = [5, 5, 5, 5]
        result = build_encounter(party, "medium")
        expected = get_xp_thresholds(party)
        assert result.thresholds == expected

    def test_not_loaded_flag(self):
        """rulebooks_loaded is False when no manager provided."""
        result = build_encounter([5, 5, 5, 5], "medium")
        assert result.rulebooks_loaded is False

    def test_has_no_rulebooks_note(self):
        """Notes mention no rulebooks loaded."""
        result = build_encounter([5, 5, 5, 5], "medium")
        assert any("No rulebooks loaded" in note for note in result.notes)

    def test_compositions_generated(self):
        """Even without rulebooks, CR-based placeholder compositions are generated."""
        result = build_encounter([5, 5, 5, 5], "medium")
        assert len(result.compositions) > 0

    def test_compositions_have_strategies(self):
        """Each composition has a valid strategy name."""
        result = build_encounter([5, 5, 5, 5], "medium")
        valid_strategies = {"single_powerful", "mixed_group", "swarm"}
        for comp in result.compositions:
            assert comp.strategy in valid_strategies

    def test_compositions_within_budget(self):
        """All composition adjusted XP values are within the budget."""
        result = build_encounter([5, 5, 5, 5], "medium")
        for comp in result.compositions:
            assert comp.adjusted_xp <= result.xp_budget, (
                f"Strategy '{comp.strategy}' adjusted_xp ({comp.adjusted_xp}) "
                f"exceeds budget ({result.xp_budget})"
            )

    def test_compositions_have_difficulty_classification(self):
        """Each composition has an actual difficulty classification."""
        result = build_encounter([5, 5, 5, 5], "hard")
        valid_difficulties = {"trivial", "easy", "medium", "hard", "deadly"}
        for comp in result.compositions:
            assert comp.actual_difficulty in valid_difficulties

    def test_composition_xp_math_correct(self):
        """Adjusted XP = base_xp * encounter_multiplier for each composition."""
        result = build_encounter([5, 5, 5, 5], "hard")
        for comp in result.compositions:
            expected_adjusted = int(comp.base_xp * comp.encounter_multiplier)
            assert comp.adjusted_xp == expected_adjusted, (
                f"Strategy '{comp.strategy}': {comp.adjusted_xp} != "
                f"int({comp.base_xp} * {comp.encounter_multiplier}) = {expected_adjusted}"
            )

    def test_composition_total_monsters_matches_groups(self):
        """total_monsters matches sum of group counts."""
        result = build_encounter([5, 5, 5, 5], "hard")
        for comp in result.compositions:
            group_total = sum(g.count for g in comp.monster_groups)
            assert comp.total_monsters == group_total

    def test_composition_base_xp_matches_groups(self):
        """base_xp matches sum of (count * xp_per_monster) across groups."""
        result = build_encounter([5, 5, 5, 5], "hard")
        for comp in result.compositions:
            expected_base = sum(g.count * g.xp_per_monster for g in comp.monster_groups)
            assert comp.base_xp == expected_base

    def test_invalid_difficulty_raises(self):
        """Invalid difficulty raises ValueError."""
        with pytest.raises(ValueError, match="Invalid difficulty"):
            build_encounter([5, 5, 5, 5], "nightmare")

    def test_empty_party_raises(self):
        """Empty party raises ValueError."""
        with pytest.raises(ValueError, match="must not be empty"):
            build_encounter([], "medium")

    def test_single_character_party(self):
        """Works for a solo character."""
        result = build_encounter([1], "easy")
        assert result.party_size == 1
        assert result.xp_budget == 25

    def test_large_party_adjustment(self):
        """Large party (6+) gets adjusted multipliers."""
        result = build_encounter([5] * 6, "medium")
        assert result.party_size == 6
        # Verify compositions exist and have the lower multipliers
        for comp in result.compositions:
            if comp.total_monsters == 1:
                # 1 monster with 6+ party = step down from 1.0 to 0.5
                assert comp.encounter_multiplier == 0.5

    def test_small_party_adjustment(self):
        """Small party (1-2) gets adjusted multipliers."""
        result = build_encounter([5, 5], "medium")
        assert result.party_size == 2
        for comp in result.compositions:
            if comp.total_monsters == 1:
                # 1 monster with 1-2 party = step up from 1.0 to 1.5
                assert comp.encounter_multiplier == 1.5

    def test_deadly_difficulty(self):
        """Deadly encounters generate valid compositions."""
        result = build_encounter([10, 10, 10, 10], "deadly")
        assert result.xp_budget == XP_THRESHOLDS[10]["deadly"] * 4

    def test_easy_difficulty_low_level(self):
        """Easy encounter at low level generates valid compositions."""
        result = build_encounter([1, 1, 1, 1], "easy")
        assert result.xp_budget == 25 * 4  # 100 XP
        # Should still get at least one composition
        assert len(result.compositions) >= 1

    def test_difficulty_parameter_case_insensitive(self):
        """Difficulty is case-insensitive."""
        r1 = build_encounter([5, 5, 5, 5], "MEDIUM")
        r2 = build_encounter([5, 5, 5, 5], "medium")
        assert r1.xp_budget == r2.xp_budget


# =============================================================================
# Build Encounter Tests (with mock rulebook data)
# =============================================================================

class TestBuildEncounterWithRulebooks:
    """Tests for build_encounter() with a mock RulebookManager."""

    @staticmethod
    def _make_mock_manager(monsters: list[dict]):
        """Create a mock rulebook manager that returns given monsters."""

        class MockSearchResult:
            def __init__(self, index, name):
                self.index = index
                self.name = name
                self.category = "monster"
                self.source = "mock"

        class MockMonsterDef:
            def __init__(self, data):
                self.name = data["name"]
                self.index = data["index"]
                self.challenge_rating = data["challenge_rating"]
                self.xp = data["xp"]
                self.type = data.get("type", "beast")

        class MockManager:
            def __init__(self, monsters_data):
                self._monsters = monsters_data

            def search(self, query="", categories=None, limit=50, class_filter=None):
                results = []
                for m in self._monsters:
                    if categories and "monster" not in categories:
                        continue
                    results.append(MockSearchResult(m["index"], m["name"]))
                return results[:limit]

            def get_monster(self, index):
                for m in self._monsters:
                    if m["index"] == index:
                        return MockMonsterDef(m)
                return None

        return MockManager(monsters)

    def test_rulebooks_loaded_flag(self):
        """rulebooks_loaded is True when monsters are found."""
        manager = self._make_mock_manager([
            {"name": "Goblin", "index": "goblin", "challenge_rating": 0.25, "xp": 50, "type": "humanoid"},
        ])
        result = build_encounter([5, 5, 5, 5], "medium", rulebook_manager=manager)
        assert result.rulebooks_loaded is True

    def test_uses_actual_monster_names(self):
        """Compositions use real monster names from rulebooks."""
        manager = self._make_mock_manager([
            {"name": "Goblin", "index": "goblin", "challenge_rating": 0.25, "xp": 50, "type": "humanoid"},
            {"name": "Ogre", "index": "ogre", "challenge_rating": 2, "xp": 450, "type": "giant"},
            {"name": "Owlbear", "index": "owlbear", "challenge_rating": 3, "xp": 700, "type": "monstrosity"},
        ])
        result = build_encounter([5, 5, 5, 5], "medium", rulebook_manager=manager)

        # At least one composition should have real monster names
        all_names = set()
        for comp in result.compositions:
            for group in comp.monster_groups:
                all_names.add(group.monster_name)
        assert len(all_names.intersection({"Goblin", "Ogre", "Owlbear"})) > 0

    def test_creature_type_filter(self):
        """creature_type filter limits monster selection."""
        manager = self._make_mock_manager([
            {"name": "Zombie", "index": "zombie", "challenge_rating": 0.25, "xp": 50, "type": "undead"},
            {"name": "Skeleton", "index": "skeleton", "challenge_rating": 0.25, "xp": 50, "type": "undead"},
            {"name": "Wolf", "index": "wolf", "challenge_rating": 0.25, "xp": 50, "type": "beast"},
        ])
        result = build_encounter(
            [3, 3, 3, 3], "medium",
            rulebook_manager=manager,
            creature_type="undead",
        )
        # All monsters in compositions should be undead
        for comp in result.compositions:
            for group in comp.monster_groups:
                assert group.creature_type == "undead", (
                    f"Expected undead, got {group.creature_type} for {group.monster_name}"
                )

    def test_cr_range_filter(self):
        """min_cr/max_cr filters limit monster selection."""
        manager = self._make_mock_manager([
            {"name": "Rat", "index": "rat", "challenge_rating": 0, "xp": 10, "type": "beast"},
            {"name": "Goblin", "index": "goblin", "challenge_rating": 0.25, "xp": 50, "type": "humanoid"},
            {"name": "Ogre", "index": "ogre", "challenge_rating": 2, "xp": 450, "type": "giant"},
            {"name": "Young Dragon", "index": "young-dragon", "challenge_rating": 10, "xp": 5900, "type": "dragon"},
        ])
        result = build_encounter(
            [5, 5, 5, 5], "medium",
            rulebook_manager=manager,
            min_cr=1,
            max_cr=5,
        )
        # Only Ogre (CR 2) should be selected
        for comp in result.compositions:
            for group in comp.monster_groups:
                assert 1 <= group.challenge_rating <= 5, (
                    f"CR {group.challenge_rating} outside range [1, 5] for {group.monster_name}"
                )

    def test_no_matching_monsters(self):
        """When filters exclude all monsters, falls back to no-rulebook mode."""
        manager = self._make_mock_manager([
            {"name": "Goblin", "index": "goblin", "challenge_rating": 0.25, "xp": 50, "type": "humanoid"},
        ])
        result = build_encounter(
            [5, 5, 5, 5], "medium",
            rulebook_manager=manager,
            creature_type="dragon",  # No dragons available
        )
        # Should still have budget and thresholds
        assert result.xp_budget > 0
        # Notes should mention no matching monsters
        assert any("no matching monsters" in n.lower() for n in result.notes)

    def test_single_powerful_strategy(self):
        """Single powerful strategy picks the strongest fitting monster."""
        manager = self._make_mock_manager([
            {"name": "Goblin", "index": "goblin", "challenge_rating": 0.25, "xp": 50, "type": "humanoid"},
            {"name": "Ogre", "index": "ogre", "challenge_rating": 2, "xp": 450, "type": "giant"},
            {"name": "Hill Giant", "index": "hill-giant", "challenge_rating": 5, "xp": 1800, "type": "giant"},
        ])
        # 4x level 5 medium = 2000 XP budget
        result = build_encounter([5, 5, 5, 5], "medium", rulebook_manager=manager)

        single_comps = [c for c in result.compositions if c.strategy == "single_powerful"]
        if single_comps:
            comp = single_comps[0]
            assert comp.total_monsters == 1
            assert len(comp.monster_groups) == 1
            # Should pick Hill Giant (1800 XP * 1.0 = 1800, within 2000 budget)
            assert comp.monster_groups[0].monster_name == "Hill Giant"

    def test_swarm_strategy(self):
        """Swarm strategy uses 4+ of the same weaker creature."""
        manager = self._make_mock_manager([
            {"name": "Goblin", "index": "goblin", "challenge_rating": 0.25, "xp": 50, "type": "humanoid"},
            {"name": "Skeleton", "index": "skeleton", "challenge_rating": 0.25, "xp": 50, "type": "undead"},
        ])
        result = build_encounter([5, 5, 5, 5], "medium", rulebook_manager=manager)

        swarm_comps = [c for c in result.compositions if c.strategy == "swarm"]
        if swarm_comps:
            comp = swarm_comps[0]
            assert comp.total_monsters >= 4
            assert len(comp.monster_groups) == 1  # Swarm uses one type of monster


# =============================================================================
# Find CR for Budget Tests
# =============================================================================

class TestFindCRForBudget:
    """Tests for _find_cr_for_budget() helper."""

    def test_returns_candidates_within_budget(self):
        """All returned CRs have adjusted XP <= budget."""
        candidates = _find_cr_for_budget(500, party_size=4)
        multiplier = get_encounter_multiplier(1, 4)
        for cr, xp in candidates:
            assert int(xp * multiplier) <= 500

    def test_sorted_by_xp_descending(self):
        """Results are sorted strongest first."""
        candidates = _find_cr_for_budget(2000, party_size=4)
        xp_values = [xp for _, xp in candidates]
        assert xp_values == sorted(xp_values, reverse=True)

    def test_cr_range_filter(self):
        """min_cr/max_cr filters are applied."""
        candidates = _find_cr_for_budget(10000, party_size=4, min_cr=2, max_cr=5)
        for cr, _ in candidates:
            assert 2 <= cr <= 5

    def test_empty_for_tiny_budget(self):
        """Very small budget with high min_cr returns empty."""
        candidates = _find_cr_for_budget(10, party_size=4, min_cr=5)
        assert len(candidates) == 0


# =============================================================================
# Pydantic Model Tests
# =============================================================================

class TestPydanticModels:
    """Tests for the Pydantic data models."""

    def test_monster_group_creation(self):
        """MonsterGroup can be created with valid data."""
        group = MonsterGroup(
            monster_name="Goblin",
            monster_index="goblin",
            count=4,
            challenge_rating=0.25,
            xp_per_monster=50,
            creature_type="humanoid",
        )
        assert group.monster_name == "Goblin"
        assert group.count == 4
        assert group.xp_per_monster == 50

    def test_monster_group_validation(self):
        """MonsterGroup validates constraints."""
        with pytest.raises(Exception):
            MonsterGroup(
                monster_name="Test",
                monster_index="test",
                count=0,  # Must be >= 1
                challenge_rating=1,
                xp_per_monster=200,
            )

    def test_encounter_composition_creation(self):
        """EncounterComposition can be created with valid data."""
        group = MonsterGroup(
            monster_name="Ogre",
            monster_index="ogre",
            count=1,
            challenge_rating=2,
            xp_per_monster=450,
        )
        comp = EncounterComposition(
            strategy="single_powerful",
            strategy_description="One big threat",
            monster_groups=[group],
            total_monsters=1,
            base_xp=450,
            encounter_multiplier=1.0,
            adjusted_xp=450,
            actual_difficulty="medium",
        )
        assert comp.strategy == "single_powerful"
        assert comp.adjusted_xp == 450

    def test_encounter_suggestion_creation(self):
        """EncounterSuggestion can be created with valid data."""
        suggestion = EncounterSuggestion(
            party_levels=[5, 5, 5, 5],
            party_size=4,
            requested_difficulty="medium",
            xp_budget=2000,
            thresholds={"easy": 1000, "medium": 2000, "hard": 3000, "deadly": 4400},
            compositions=[],
            rulebooks_loaded=False,
            notes=["Test note"],
        )
        assert suggestion.party_size == 4
        assert suggestion.xp_budget == 2000

    def test_difficulty_enum(self):
        """Difficulty enum has the four standard values."""
        assert Difficulty.EASY == "easy"
        assert Difficulty.MEDIUM == "medium"
        assert Difficulty.HARD == "hard"
        assert Difficulty.DEADLY == "deadly"


# =============================================================================
# Integration / Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Edge case and integration tests."""

    def test_level_1_party_easy(self):
        """Level 1 party easy encounter is very constrained."""
        result = build_encounter([1, 1, 1, 1], "easy")
        # Budget = 25*4 = 100 XP
        assert result.xp_budget == 100
        # Should still produce at least one composition
        assert len(result.compositions) >= 1

    def test_level_20_party_deadly(self):
        """Level 20 party deadly encounter has high budget."""
        result = build_encounter([20, 20, 20, 20], "deadly")
        # Budget = 12700*4 = 50800 XP
        assert result.xp_budget == 50800
        assert len(result.compositions) >= 1

    def test_single_level_20_character(self):
        """Solo level 20 character encounter."""
        result = build_encounter([20], "hard")
        assert result.party_size == 1
        # Multipliers should be increased for small party

    def test_party_of_8(self):
        """Large party of 8 characters."""
        result = build_encounter([5] * 8, "medium")
        assert result.party_size == 8
        # Should produce compositions with lower multipliers

    def test_mixed_levels_extreme(self):
        """Party with extreme level spread."""
        result = build_encounter([1, 5, 10, 20], "medium")
        expected_budget = (
            XP_THRESHOLDS[1]["medium"]
            + XP_THRESHOLDS[5]["medium"]
            + XP_THRESHOLDS[10]["medium"]
            + XP_THRESHOLDS[20]["medium"]
        )
        assert result.xp_budget == expected_budget

    def test_all_compositions_have_valid_multiplier(self):
        """Every composition has a multiplier from the standard table (possibly adjusted)."""
        result = build_encounter([5, 5, 5, 5], "hard")
        valid_multipliers = {0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0}
        for comp in result.compositions:
            assert comp.encounter_multiplier in valid_multipliers, (
                f"Invalid multiplier {comp.encounter_multiplier} in {comp.strategy}"
            )

    def test_encounter_multipliers_constant_structure(self):
        """ENCOUNTER_MULTIPLIERS constant has expected structure."""
        assert len(ENCOUNTER_MULTIPLIERS) == 6
        # Thresholds should be increasing
        thresholds = [t for t, _ in ENCOUNTER_MULTIPLIERS]
        assert thresholds == sorted(thresholds)
        # Multipliers should be increasing
        multipliers = [m for _, m in ENCOUNTER_MULTIPLIERS]
        assert multipliers == sorted(multipliers)
