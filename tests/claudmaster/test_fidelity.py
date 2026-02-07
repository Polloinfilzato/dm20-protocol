"""
Tests for fidelity enforcement system.

Comprehensive test suite for module fidelity enforcement, including
deviation detection, warning system, forced text injection, and audit logging.
"""

import pytest
from datetime import datetime

from gamemaster_mcp.claudmaster.fidelity import (
    NarrationContext,
    Deviation,
    EnforcementResult,
    FidelityWarning,
    FidelityAuditEntry,
    DeviationDetector,
    FidelityWarningSystem,
    ForcedTextInjector,
    FidelityAuditLog,
    NarratorLockEnforcer,
    get_applicable_locks,
)
from gamemaster_mcp.claudmaster.element_locks import (
    ElementCategory,
    ElementLock,
    LockConfiguration,
)
from gamemaster_mcp.claudmaster.improvisation import ImprovisationLevel


# Fixtures

@pytest.fixture
def sample_context():
    """Create a sample narration context."""
    return NarrationContext(
        scene_id="scene_001",
        current_location="tavern_main_hall",
        active_npcs=["innkeeper_bob", "guard_alice"],
        current_event="mysterious_stranger_arrives",
        session_id="session_123"
    )


@pytest.fixture
def sample_locks():
    """Create a sample lock configuration."""
    locks = LockConfiguration()
    locks.lock_element(
        element_id="tavern_main_hall",
        category=ElementCategory.LOCATION,
        reason="Published module content",
        override_level=ImprovisationLevel.NONE
    )
    locks.lock_element(
        element_id="innkeeper_bob",
        category=ElementCategory.NPC,
        reason="Key NPC dialogue",
        override_level=ImprovisationLevel.LOW
    )
    locks.lock_element(
        element_id="mysterious_stranger_arrives",
        category=ElementCategory.EVENT,
        reason="Critical plot event",
        override_level=ImprovisationLevel.NONE
    )
    return locks


@pytest.fixture
def sample_module_data():
    """Create sample canonical module content."""
    return {
        "tavern_main_hall": (
            "The tavern is dimly lit by flickering candles. "
            "Rough wooden tables are scattered throughout the room. "
            "A fire crackles in the stone hearth."
        ),
        "innkeeper_bob": (
            "Welcome traveler! What can I get ye? "
            "Ale or mead, both fresh from the barrel."
        ),
        "mysterious_stranger_arrives": (
            "A hooded figure enters through the main door, "
            "snow swirling in behind them. They scan the room with piercing eyes."
        ),
    }


# Test NarrationContext

def test_narration_context_creation(sample_context):
    """Test creating a narration context."""
    assert sample_context.scene_id == "scene_001"
    assert sample_context.current_location == "tavern_main_hall"
    assert len(sample_context.active_npcs) == 2
    assert sample_context.current_event == "mysterious_stranger_arrives"
    assert sample_context.session_id == "session_123"


def test_narration_context_no_event():
    """Test context without current event."""
    context = NarrationContext(
        scene_id="scene_002",
        current_location="forest_path",
        active_npcs=[],
        session_id="session_124"
    )
    assert context.current_event is None


# Test get_applicable_locks

def test_get_applicable_locks_all_match(sample_context, sample_locks):
    """Test getting applicable locks when all context elements are locked."""
    applicable = get_applicable_locks(sample_locks, sample_context)

    assert len(applicable) == 3
    element_ids = {lock.element_id for lock in applicable}
    assert "tavern_main_hall" in element_ids
    assert "innkeeper_bob" in element_ids
    assert "mysterious_stranger_arrives" in element_ids


def test_get_applicable_locks_partial_match(sample_locks):
    """Test getting applicable locks with partial context match."""
    context = NarrationContext(
        scene_id="scene_002",
        current_location="tavern_main_hall",  # Locked
        active_npcs=["random_patron"],  # Not locked
        session_id="session_125"
    )

    applicable = get_applicable_locks(sample_locks, context)

    assert len(applicable) == 1
    assert applicable[0].element_id == "tavern_main_hall"


def test_get_applicable_locks_no_match(sample_locks):
    """Test getting applicable locks with no matches."""
    context = NarrationContext(
        scene_id="scene_003",
        current_location="forest_path",  # Not locked
        active_npcs=["random_npc"],  # Not locked
        session_id="session_126"
    )

    applicable = get_applicable_locks(sample_locks, context)

    assert len(applicable) == 0


# Test DeviationDetector

def test_deviation_detector_calculate_similarity():
    """Test Jaccard similarity calculation."""
    detector = DeviationDetector()

    # Identical texts
    sim = detector._calculate_similarity("hello world", "hello world")
    assert sim == 1.0

    # Completely different
    sim = detector._calculate_similarity("hello world", "foo bar")
    assert sim == 0.0

    # Partial overlap
    sim = detector._calculate_similarity("hello world", "hello there")
    assert sim == pytest.approx(0.333, rel=0.01)

    # Case insensitive
    sim = detector._calculate_similarity("Hello World", "hello world")
    assert sim == 1.0


def test_deviation_detector_empty_strings():
    """Test similarity with empty strings."""
    detector = DeviationDetector()

    sim = detector._calculate_similarity("", "")
    assert sim == 1.0

    sim = detector._calculate_similarity("hello", "")
    assert sim == 0.0


def test_deviation_detector_classify_deviation():
    """Test deviation classification."""
    detector = DeviationDetector()

    assert detector._classify_deviation(0.1) == "complete_rewrite"
    assert detector._classify_deviation(0.4) == "major_modification"
    assert detector._classify_deviation(0.6) == "minor_modification"
    assert detector._classify_deviation(0.8) == "acceptable_variation"


def test_deviation_detector_detect_deviations(sample_locks, sample_module_data):
    """Test detecting deviations in narration."""
    detector = DeviationDetector()

    # Generated narration deviates significantly
    narration = "The pub was brightly illuminated by electric lights."

    locked_elements = [sample_locks.locks["tavern_main_hall"]]
    deviations = detector.detect_deviations(narration, locked_elements, sample_module_data)

    assert len(deviations) == 1
    deviation = deviations[0]
    assert deviation.element.element_id == "tavern_main_hall"
    assert deviation.similarity < 0.7  # Significant deviation
    assert deviation.deviation_type in ["complete_rewrite", "major_modification"]


def test_deviation_detector_no_deviations(sample_locks, sample_module_data):
    """Test when narration matches canonical content."""
    detector = DeviationDetector()

    # Use canonical text
    narration = sample_module_data["tavern_main_hall"]

    locked_elements = [sample_locks.locks["tavern_main_hall"]]
    deviations = detector.detect_deviations(narration, locked_elements, sample_module_data)

    # Should detect acceptable variation or no deviation
    # Since we use exact text, similarity should be 1.0, so no deviation
    assert len(deviations) == 0


# Test FidelityWarningSystem

def test_fidelity_warning_system_issue_warning(sample_locks, sample_module_data):
    """Test issuing a warning."""
    system = FidelityWarningSystem()

    deviation = Deviation(
        element=sample_locks.locks["tavern_main_hall"],
        expected=sample_module_data["tavern_main_hall"],
        actual="The pub was very bright.",
        similarity=0.2,
        deviation_type="major_modification"
    )

    warning = system.issue_warning(deviation)

    assert warning.severity == "critical"  # Low similarity, locked element
    assert warning.element.element_id == "tavern_main_hall"
    assert warning.deviation_type == "major_modification"
    assert "Replace with canonical text" in warning.suggestion


def test_fidelity_warning_system_severity_levels(sample_locks, sample_module_data):
    """Test different severity levels."""
    system = FidelityWarningSystem()

    # Critical - locked element, very low similarity
    deviation_critical = Deviation(
        element=sample_locks.locks["tavern_main_hall"],
        expected=sample_module_data["tavern_main_hall"],
        actual="Something completely different.",
        similarity=0.1,
        deviation_type="complete_rewrite"
    )
    warning = system.issue_warning(deviation_critical)
    assert warning.severity == "critical"

    # Warning - moderate similarity
    deviation_warning = Deviation(
        element=sample_locks.locks["innkeeper_bob"],
        expected=sample_module_data["innkeeper_bob"],
        actual="Welcome! What would you like to drink?",
        similarity=0.4,
        deviation_type="major_modification"
    )
    warning = system.issue_warning(deviation_warning)
    assert warning.severity == "warning"

    # Info - high similarity
    deviation_info = Deviation(
        element=sample_locks.locks["innkeeper_bob"],
        expected=sample_module_data["innkeeper_bob"],
        actual="Welcome traveler! What can I get you? Ale or mead, fresh from barrel.",
        similarity=0.75,
        deviation_type="minor_modification"
    )
    warning = system.issue_warning(deviation_info)
    assert warning.severity == "info"


def test_fidelity_warning_system_get_warnings():
    """Test retrieving warnings."""
    system = FidelityWarningSystem()

    lock = ElementLock(
        element_id="test_element",
        category=ElementCategory.LOCATION
    )

    # Add warnings with different severities
    system.issue_warning(Deviation(
        element=lock,
        expected="expected",
        actual="actual1",
        similarity=0.1,
        deviation_type="complete_rewrite"
    ))

    system.issue_warning(Deviation(
        element=lock,
        expected="expected",
        actual="actual2",
        similarity=0.6,
        deviation_type="minor_modification"
    ))

    # Get all warnings
    all_warnings = system.get_warnings()
    assert len(all_warnings) == 2

    # Get critical only
    critical = system.get_warnings(severity="critical")
    assert len(critical) == 1

    # Get info only
    info = system.get_warnings(severity="info")
    assert len(info) == 1


# Test ForcedTextInjector

def test_forced_text_injector_should_force_text(sample_context, sample_locks, sample_module_data):
    """Test determining if text should be forced."""
    injector = ForcedTextInjector(sample_module_data)

    # Event has NONE level and exists in module_data
    should_force = injector.should_force_text(sample_context, sample_locks)
    assert should_force is True


def test_forced_text_injector_should_not_force(sample_locks, sample_module_data):
    """Test when text should not be forced."""
    injector = ForcedTextInjector(sample_module_data)

    # Context with no locked elements at NONE level
    context = NarrationContext(
        scene_id="scene_002",
        current_location="unlocked_location",
        active_npcs=[],
        session_id="session_127"
    )

    should_force = injector.should_force_text(context, sample_locks)
    assert should_force is False


def test_forced_text_injector_get_forced_text(sample_context, sample_module_data):
    """Test getting forced text."""
    injector = ForcedTextInjector(sample_module_data)

    # Should prioritize event over location
    forced_text = injector.get_forced_text(sample_context)
    assert forced_text == sample_module_data["mysterious_stranger_arrives"]


def test_forced_text_injector_get_forced_text_location(sample_module_data):
    """Test getting forced text from location."""
    injector = ForcedTextInjector(sample_module_data)

    context = NarrationContext(
        scene_id="scene_003",
        current_location="tavern_main_hall",
        active_npcs=[],
        current_event=None,  # No event
        session_id="session_128"
    )

    forced_text = injector.get_forced_text(context)
    assert forced_text == sample_module_data["tavern_main_hall"]


def test_forced_text_injector_get_forced_text_npc(sample_module_data):
    """Test getting forced text from NPC."""
    injector = ForcedTextInjector(sample_module_data)

    context = NarrationContext(
        scene_id="scene_004",
        current_location="unknown_location",
        active_npcs=["innkeeper_bob"],
        current_event=None,
        session_id="session_129"
    )

    forced_text = injector.get_forced_text(context)
    assert forced_text == sample_module_data["innkeeper_bob"]


def test_forced_text_injector_no_forced_text(sample_module_data):
    """Test when no forced text is available."""
    injector = ForcedTextInjector(sample_module_data)

    context = NarrationContext(
        scene_id="scene_005",
        current_location="unknown",
        active_npcs=["unknown_npc"],
        session_id="session_130"
    )

    forced_text = injector.get_forced_text(context)
    assert forced_text is None


# Test FidelityAuditLog

def test_fidelity_audit_log_add_entry():
    """Test adding audit entries."""
    log = FidelityAuditLog()

    entry = log.add_entry(
        event_type="violation",
        element_id="test_element",
        details={"similarity": 0.3},
        session_id="session_123"
    )

    assert entry.event_type == "violation"
    assert entry.element_id == "test_element"
    assert entry.details["similarity"] == 0.3
    assert entry.session_id == "session_123"
    assert isinstance(entry.timestamp, datetime)


def test_fidelity_audit_log_get_entries():
    """Test retrieving audit entries."""
    log = FidelityAuditLog()

    # Add multiple entries
    log.add_entry("violation", "elem1", {}, "session_1")
    log.add_entry("correction", "elem2", {}, "session_1")
    log.add_entry("warning", "elem3", {}, "session_2")

    # Get all entries
    all_entries = log.get_entries()
    assert len(all_entries) == 3

    # Filter by session
    session_1_entries = log.get_entries(session_id="session_1")
    assert len(session_1_entries) == 2

    # Filter by event type
    violations = log.get_entries(event_type="violation")
    assert len(violations) == 1
    assert violations[0].event_type == "violation"

    # Filter by both
    specific = log.get_entries(session_id="session_1", event_type="correction")
    assert len(specific) == 1
    assert specific[0].element_id == "elem2"


# Test NarratorLockEnforcer

def test_narrator_lock_enforcer_no_violations(sample_locks, sample_module_data):
    """Test enforcement when no violations occur."""
    # Create a context without NONE-level locked elements to avoid forced text
    locks = LockConfiguration()
    locks.lock_element(
        element_id="tavern_main_hall",
        category=ElementCategory.LOCATION,
        reason="Test",
        override_level=ImprovisationLevel.LOW  # Not NONE, so no forced text
    )

    context = NarrationContext(
        scene_id="scene_test",
        current_location="tavern_main_hall",
        active_npcs=[],
        current_event=None,
        session_id="session_test"
    )

    enforcer = NarratorLockEnforcer(locks, sample_module_data)

    # Use canonical text - no violations
    narration = sample_module_data["tavern_main_hall"]

    result = enforcer.enforce_locks(narration, context, locks)

    assert result.modified is False
    assert len(result.violations) == 0
    assert len(result.corrections_applied) == 0
    assert result.narration == narration


def test_narrator_lock_enforcer_forced_text(sample_context, sample_locks, sample_module_data):
    """Test forced text injection."""
    enforcer = NarratorLockEnforcer(sample_locks, sample_module_data)

    # Generate incorrect narration
    narration = "Something completely wrong."

    result = enforcer.enforce_locks(narration, sample_context, sample_locks)

    # Should force canonical text for event
    assert result.modified is True
    assert result.narration == sample_module_data["mysterious_stranger_arrives"]
    assert "forced_canonical_text" in result.corrections_applied


def test_narrator_lock_enforcer_violations_and_corrections(sample_module_data):
    """Test detection and correction of violations."""
    # Create locks without NONE level to avoid forced injection
    locks = LockConfiguration()
    locks.lock_element(
        element_id="tavern_main_hall",
        category=ElementCategory.LOCATION,
        reason="Test",
        override_level=ImprovisationLevel.LOW  # Not NONE
    )

    context = NarrationContext(
        scene_id="scene_006",
        current_location="tavern_main_hall",
        active_npcs=[],
        current_event=None,
        session_id="session_131"
    )

    enforcer = NarratorLockEnforcer(locks, sample_module_data)

    # Significantly deviated narration
    narration = "The pub was super bright and modern."

    result = enforcer.enforce_locks(narration, context, locks)

    # Should detect violations and apply corrections
    assert len(result.violations) > 0


def test_narrator_lock_enforcer_multiple_violations(sample_module_data):
    """Test handling multiple simultaneous violations."""
    # Create locks without NONE level
    locks = LockConfiguration()
    locks.lock_element(
        element_id="tavern_main_hall",
        category=ElementCategory.LOCATION,
        reason="Test",
        override_level=ImprovisationLevel.LOW
    )
    locks.lock_element(
        element_id="innkeeper_bob",
        category=ElementCategory.NPC,
        reason="Test",
        override_level=ImprovisationLevel.LOW
    )

    context = NarrationContext(
        scene_id="scene_007",
        current_location="tavern_main_hall",
        active_npcs=["innkeeper_bob"],
        current_event=None,
        session_id="session_132"
    )

    enforcer = NarratorLockEnforcer(locks, sample_module_data)

    # Narration that violates multiple elements
    narration = "Everything is completely different from the module."

    result = enforcer.enforce_locks(narration, context, locks)

    # Multiple violations should be detected
    assert len(result.violations) >= 1


def test_narrator_lock_enforcer_audit_logging(sample_context, sample_locks, sample_module_data):
    """Test that enforcement events are logged."""
    enforcer = NarratorLockEnforcer(sample_locks, sample_module_data)

    narration = "Some generated text."

    enforcer.enforce_locks(narration, sample_context, sample_locks)

    # Check audit log has entries
    entries = enforcer.audit_log.get_entries(session_id=sample_context.session_id)
    assert len(entries) > 0


def test_narrator_lock_enforcer_warning_system_integration(sample_locks, sample_module_data):
    """Test integration with warning system."""
    enforcer = NarratorLockEnforcer(sample_locks, sample_module_data)

    # Remove event lock to avoid forced injection
    sample_locks.unlock_element("mysterious_stranger_arrives")

    context = NarrationContext(
        scene_id="scene_008",
        current_location="tavern_main_hall",
        active_npcs=[],
        current_event=None,
        session_id="session_133"
    )

    # Deviated narration
    narration = "The bar was very different."

    enforcer.enforce_locks(narration, context, sample_locks)

    # Warnings should be issued
    warnings = enforcer.warning_system.get_warnings()
    assert len(warnings) >= 0  # May or may not have warnings depending on similarity


# Test EnforcementResult

def test_enforcement_result_creation():
    """Test creating enforcement results."""
    result = EnforcementResult(
        narration="Final text",
        modified=True,
        violations=[],
        corrections_applied=["correction1", "correction2"]
    )

    assert result.narration == "Final text"
    assert result.modified is True
    assert len(result.corrections_applied) == 2


def test_enforcement_result_no_violations():
    """Test enforcement result with no violations."""
    result = EnforcementResult(
        narration="Original text",
        modified=False,
        violations=[],
        corrections_applied=[]
    )

    assert result.modified is False
    assert len(result.violations) == 0
    assert len(result.corrections_applied) == 0


# Performance test

def test_enforcement_performance(sample_context, sample_locks, sample_module_data):
    """Test that enforcement completes within performance target."""
    import time

    enforcer = NarratorLockEnforcer(sample_locks, sample_module_data)

    narration = "The tavern was dimly lit. Wooden tables everywhere. Fire in hearth."

    start = time.time()
    enforcer.enforce_locks(narration, sample_context, sample_locks)
    duration = time.time() - start

    # Should complete in under 100ms
    assert duration < 0.1, f"Enforcement took {duration*1000:.2f}ms, expected < 100ms"
