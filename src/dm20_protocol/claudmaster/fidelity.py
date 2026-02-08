"""
Module Fidelity Enforcement for Claudmaster AI DM.

This module provides fidelity enforcement to ensure AI agents respect locked
elements and module adherence settings. It detects deviations from canonical
module content, issues warnings, and applies corrections when needed.

The system integrates with the element locking and improvisation level systems
to enforce module fidelity at runtime during narration generation.
"""

from datetime import datetime, UTC
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .element_locks import ElementCategory, ElementLock, LockConfiguration
from .improvisation import ImprovisationLevel


class NarrationContext(BaseModel):
    """Context information for a narration scene."""
    scene_id: str = Field(description="Unique identifier for the scene")
    current_location: str = Field(description="Current location ID")
    active_npcs: list[str] = Field(default_factory=list, description="Active NPC IDs")
    current_event: Optional[str] = Field(default=None, description="Current event ID if any")
    session_id: str = Field(description="Session identifier for audit logging")


class Deviation(BaseModel):
    """Detected deviation from canonical module content."""
    element: ElementLock = Field(description="The locked element that was violated")
    expected: str = Field(description="Canonical content from module")
    actual: str = Field(description="Generated content that deviates")
    similarity: float = Field(description="Similarity score (0.0-1.0)")
    deviation_type: str = Field(description="Type of deviation detected")


class EnforcementResult(BaseModel):
    """Result of fidelity enforcement on generated narration."""
    narration: str = Field(description="Final narration text (possibly corrected)")
    modified: bool = Field(description="Whether corrections were applied")
    violations: list[Deviation] = Field(default_factory=list, description="Violations found")
    corrections_applied: list[str] = Field(default_factory=list, description="Corrections made")


class FidelityWarning(BaseModel):
    """Warning about a fidelity violation."""
    severity: Literal["info", "warning", "critical"] = Field(description="Warning severity")
    element: ElementLock = Field(description="Element involved in violation")
    deviation_type: str = Field(description="Type of deviation")
    expected_content: str = Field(description="Expected canonical content")
    actual_content: str = Field(description="Actual generated content")
    suggestion: str = Field(description="Suggested correction")


class FidelityAuditEntry(BaseModel):
    """Audit log entry for fidelity enforcement events."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event_type: Literal["violation", "warning", "correction", "forced"] = Field(
        description="Type of audit event"
    )
    element_id: str = Field(description="ID of element involved")
    details: dict = Field(default_factory=dict, description="Additional event details")
    session_id: str = Field(description="Session identifier")


def get_applicable_locks(locks: LockConfiguration, context: NarrationContext) -> list[ElementLock]:
    """
    Get locks applicable to the current narration context.

    Returns locked elements relevant to the current scene, including:
    - Location locks for current_location
    - NPC locks for active_npcs
    - Event locks for current_event

    Args:
        locks: Lock configuration to query
        context: Current narration context

    Returns:
        List of applicable locked elements
    """
    applicable = []

    # Check all locked elements
    for lock in locks.get_locked_elements():
        # Include if element matches context
        if lock.element_id == context.current_location:
            applicable.append(lock)
        elif lock.element_id in context.active_npcs:
            applicable.append(lock)
        elif context.current_event and lock.element_id == context.current_event:
            applicable.append(lock)

    return applicable


class DeviationDetector:
    """Detects deviations from canonical module content."""

    def detect_deviations(
        self,
        narration: str,
        locked_elements: list[ElementLock],
        module_content: dict[str, str]
    ) -> list[Deviation]:
        """
        Detect deviations between narration and locked module content.

        Compares generated narration against canonical content for each locked
        element. Uses text similarity to identify significant deviations.

        Args:
            narration: Generated narration text to check
            locked_elements: List of locked elements to validate against
            module_content: Map of element_id to canonical text

        Returns:
            List of detected deviations
        """
        deviations = []

        for lock in locked_elements:
            if lock.element_id not in module_content:
                continue

            canonical = module_content[lock.element_id]
            similarity = self._calculate_similarity(narration, canonical)

            # Determine if this is a significant deviation
            # For locked elements, we expect high similarity (>0.7)
            if similarity < 0.7:
                deviation_type = self._classify_deviation(similarity)
                deviations.append(Deviation(
                    element=lock,
                    expected=canonical,
                    actual=narration,
                    similarity=similarity,
                    deviation_type=deviation_type
                ))

        return deviations

    def _calculate_similarity(self, text_a: str, text_b: str) -> float:
        """
        Calculate Jaccard similarity between two texts at word level.

        Jaccard similarity = |A ∩ B| / |A ∪ B|
        where A and B are sets of words from each text.

        Args:
            text_a: First text
            text_b: Second text

        Returns:
            Similarity score from 0.0 (completely different) to 1.0 (identical)
        """
        # Normalize and tokenize
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())

        if not words_a and not words_b:
            return 1.0
        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b

        return len(intersection) / len(union)

    def _classify_deviation(self, similarity: float) -> str:
        """
        Classify deviation type based on similarity score.

        Args:
            similarity: Similarity score (0.0-1.0)

        Returns:
            Deviation type classification
        """
        if similarity < 0.3:
            return "complete_rewrite"
        elif similarity < 0.5:
            return "major_modification"
        elif similarity < 0.7:
            return "minor_modification"
        else:
            return "acceptable_variation"


class FidelityWarningSystem:
    """Issues and manages fidelity warnings."""

    def __init__(self):
        """Initialize warning system."""
        self._warnings: list[FidelityWarning] = []

    def issue_warning(self, deviation: Deviation) -> FidelityWarning:
        """
        Create a warning from a detected deviation.

        Args:
            deviation: Detected deviation to warn about

        Returns:
            Created fidelity warning
        """
        severity = self._determine_severity(deviation)
        suggestion = self._generate_suggestion(deviation)

        warning = FidelityWarning(
            severity=severity,
            element=deviation.element,
            deviation_type=deviation.deviation_type,
            expected_content=deviation.expected,
            actual_content=deviation.actual,
            suggestion=suggestion
        )

        self._warnings.append(warning)
        return warning

    def _determine_severity(self, deviation: Deviation) -> Literal["info", "warning", "critical"]:
        """
        Determine warning severity based on deviation characteristics.

        Args:
            deviation: Deviation to assess

        Returns:
            Severity level
        """
        # Critical for locked elements with major deviations
        if deviation.element.is_locked and deviation.similarity < 0.3:
            return "critical"

        # Warning for moderate deviations
        if deviation.similarity < 0.5:
            return "warning"

        # Info for minor deviations
        return "info"

    def _generate_suggestion(self, deviation: Deviation) -> str:
        """
        Generate a suggestion for correcting the deviation.

        Args:
            deviation: Deviation to suggest fix for

        Returns:
            Suggested correction text
        """
        # For severe deviations (low similarity), suggest replacement
        if deviation.similarity < 0.3:
            return f"Replace with canonical text: '{deviation.expected[:100]}...'"
        elif deviation.deviation_type == "major_modification":
            return f"Align more closely with module content: '{deviation.expected[:100]}...'"
        else:
            return f"Consider using canonical phrasing: '{deviation.expected[:100]}...'"

    def get_warnings(
        self,
        severity: Optional[Literal["info", "warning", "critical"]] = None
    ) -> list[FidelityWarning]:
        """
        Get recorded warnings, optionally filtered by severity.

        Args:
            severity: Optional severity filter

        Returns:
            List of warnings matching criteria
        """
        if severity is None:
            return self._warnings.copy()

        return [w for w in self._warnings if w.severity == severity]


class ForcedTextInjector:
    """Handles forced injection of canonical boxed text."""

    def __init__(self, module_data: dict[str, str]):
        """
        Initialize text injector.

        Args:
            module_data: Map of element_id to canonical boxed text
        """
        self.module_data = module_data

    def should_force_text(
        self,
        context: NarrationContext,
        locks: LockConfiguration
    ) -> bool:
        """
        Determine if canonical text should be forced for this scene.

        Forced text injection occurs when:
        - Current scene/location/event has a locked element
        - That element has ImprovisationLevel.NONE
        - Canonical text exists in module_data

        Args:
            context: Current narration context
            locks: Lock configuration

        Returns:
            True if text should be forced
        """
        applicable = get_applicable_locks(locks, context)

        for lock in applicable:
            # Check if element requires verbatim text (NONE level)
            effective_level = locks.get_effective_level(lock.element_id, ImprovisationLevel.MEDIUM)

            if effective_level == ImprovisationLevel.NONE and lock.element_id in self.module_data:
                return True

        return False

    def get_forced_text(self, context: NarrationContext) -> Optional[str]:
        """
        Get canonical text to force for this scene.

        Args:
            context: Current narration context

        Returns:
            Canonical text if available, None otherwise
        """
        # Check in priority order: event > location > npc
        if context.current_event and context.current_event in self.module_data:
            return self.module_data[context.current_event]

        if context.current_location in self.module_data:
            return self.module_data[context.current_location]

        # Check for any active NPC with forced text
        for npc_id in context.active_npcs:
            if npc_id in self.module_data:
                return self.module_data[npc_id]

        return None


class FidelityAuditLog:
    """Audit log for fidelity enforcement events."""

    def __init__(self):
        """Initialize audit log."""
        self._entries: list[FidelityAuditEntry] = []

    def add_entry(
        self,
        event_type: Literal["violation", "warning", "correction", "forced"],
        element_id: str,
        details: dict,
        session_id: str
    ) -> FidelityAuditEntry:
        """
        Add an audit log entry.

        Args:
            event_type: Type of event
            element_id: Element involved
            details: Additional event details
            session_id: Session identifier

        Returns:
            Created audit entry
        """
        entry = FidelityAuditEntry(
            event_type=event_type,
            element_id=element_id,
            details=details,
            session_id=session_id
        )
        self._entries.append(entry)
        return entry

    def get_entries(
        self,
        session_id: Optional[str] = None,
        event_type: Optional[Literal["violation", "warning", "correction", "forced"]] = None
    ) -> list[FidelityAuditEntry]:
        """
        Get audit entries, optionally filtered.

        Args:
            session_id: Filter by session ID
            event_type: Filter by event type

        Returns:
            Filtered list of audit entries
        """
        entries = self._entries

        if session_id is not None:
            entries = [e for e in entries if e.session_id == session_id]

        if event_type is not None:
            entries = [e for e in entries if e.event_type == event_type]

        return entries


class NarratorLockEnforcer:
    """Main enforcement engine for narrator fidelity."""

    def __init__(self, locks: LockConfiguration, module_data: dict[str, str]):
        """
        Initialize lock enforcer.

        Args:
            locks: Lock configuration
            module_data: Map of element_id to canonical content
        """
        self.locks = locks
        self.module_data = module_data
        self.detector = DeviationDetector()
        self.warning_system = FidelityWarningSystem()
        self.text_injector = ForcedTextInjector(module_data)
        self.audit_log = FidelityAuditLog()

    def enforce_locks(
        self,
        generated_narration: str,
        context: NarrationContext,
        locks: LockConfiguration
    ) -> EnforcementResult:
        """
        Enforce locks on generated narration.

        Main enforcement workflow:
        1. Check if forced text should be used
        2. Detect violations against locked elements
        3. Apply corrections if needed
        4. Log audit entries

        Args:
            generated_narration: AI-generated narration to check
            context: Current narration context
            locks: Lock configuration to enforce

        Returns:
            Enforcement result with final narration and metadata
        """
        # Check for forced text injection
        if self.text_injector.should_force_text(context, locks):
            forced_text = self.text_injector.get_forced_text(context)
            if forced_text:
                # Log forced injection
                self.audit_log.add_entry(
                    event_type="forced",
                    element_id=context.scene_id,
                    details={"forced_text": forced_text[:100]},
                    session_id=context.session_id
                )
                return EnforcementResult(
                    narration=forced_text,
                    modified=True,
                    violations=[],
                    corrections_applied=["forced_canonical_text"]
                )

        # Detect violations
        violations = self._detect_violations(generated_narration, locks, context)

        # Issue warnings
        for violation in violations:
            self.warning_system.issue_warning(violation)
            self.audit_log.add_entry(
                event_type="violation",
                element_id=violation.element.element_id,
                details={
                    "similarity": violation.similarity,
                    "deviation_type": violation.deviation_type
                },
                session_id=context.session_id
            )

        # Apply corrections if violations found
        if violations:
            return self._apply_corrections(generated_narration, violations)

        # No violations, return original
        return EnforcementResult(
            narration=generated_narration,
            modified=False,
            violations=[],
            corrections_applied=[]
        )

    def _detect_violations(
        self,
        narration: str,
        locks: LockConfiguration,
        context: NarrationContext
    ) -> list[Deviation]:
        """
        Detect violations in narration.

        Args:
            narration: Generated narration
            locks: Lock configuration
            context: Narration context

        Returns:
            List of detected violations
        """
        applicable_locks = get_applicable_locks(locks, context)
        return self.detector.detect_deviations(narration, applicable_locks, self.module_data)

    def _apply_corrections(
        self,
        narration: str,
        violations: list[Deviation]
    ) -> EnforcementResult:
        """
        Apply corrections to narration based on violations.

        For locked elements with significant deviations, replace with canonical text.

        Args:
            narration: Original narration
            violations: Detected violations

        Returns:
            Enforcement result with corrected narration
        """
        corrected = narration
        corrections = []

        for violation in violations:
            # Only correct locked elements with significant deviations
            if violation.element.is_locked and violation.similarity < 0.5:
                # Replace with canonical text
                corrected = violation.expected
                corrections.append(
                    f"Replaced {violation.deviation_type} for {violation.element.element_id}"
                )

                # Log correction
                self.audit_log.add_entry(
                    event_type="correction",
                    element_id=violation.element.element_id,
                    details={
                        "original_similarity": violation.similarity,
                        "deviation_type": violation.deviation_type
                    },
                    session_id="correction_session"
                )

        return EnforcementResult(
            narration=corrected,
            modified=len(corrections) > 0,
            violations=violations,
            corrections_applied=corrections
        )


__all__ = [
    "NarrationContext",
    "Deviation",
    "EnforcementResult",
    "FidelityWarning",
    "FidelityAuditEntry",
    "DeviationDetector",
    "FidelityWarningSystem",
    "ForcedTextInjector",
    "FidelityAuditLog",
    "NarratorLockEnforcer",
    "get_applicable_locks",
]
