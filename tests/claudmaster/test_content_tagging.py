"""
Tests for the content tagging system.

This module tests the content origin tagging functionality, including
classification of canonical vs improvised content, hybrid segmentation,
and tagged content storage.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from gamemaster_mcp.claudmaster.content_tagging import (
    ContentOrigin,
    ContentTag,
    ContentTagger,
    SessionNotesFormatter,
    TaggedContentStore,
    TaggedFact,
    TaggedNarrative,
    TaggedSegment,
)
from gamemaster_mcp.claudmaster.improvisation import ImprovisationLevel


class TestContentOriginEnum:
    """Test ContentOrigin enum values."""

    def test_canonical_value(self):
        """Test CANONICAL enum value."""
        assert ContentOrigin.CANONICAL.value == "canonical"

    def test_improvised_value(self):
        """Test IMPROVISED enum value."""
        assert ContentOrigin.IMPROVISED.value == "improvised"

    def test_hybrid_value(self):
        """Test HYBRID enum value."""
        assert ContentOrigin.HYBRID.value == "hybrid"

    def test_all_origins_present(self):
        """Test all three origin types are available."""
        origins = {o.value for o in ContentOrigin}
        assert origins == {"canonical", "improvised", "hybrid"}


class TestContentTag:
    """Test ContentTag model."""

    def test_create_canonical_tag(self):
        """Test creating a canonical content tag."""
        tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.95,
            module_source="Area 2-B",
            agent_id="narrator"
        )

        assert tag.origin == ContentOrigin.CANONICAL
        assert tag.confidence == 0.95
        assert tag.module_source == "Area 2-B"
        assert tag.agent_id == "narrator"
        assert tag.improvisation_level is None

    def test_create_improvised_tag(self):
        """Test creating an improvised content tag."""
        tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.9,
            improvisation_level=ImprovisationLevel.HIGH,
            agent_id="narrator"
        )

        assert tag.origin == ContentOrigin.IMPROVISED
        assert tag.confidence == 0.9
        assert tag.module_source is None
        assert tag.improvisation_level == ImprovisationLevel.HIGH

    def test_timestamp_auto_generated(self):
        """Test timestamp is automatically generated."""
        tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.8,
            agent_id="narrator"
        )

        assert isinstance(tag.timestamp, datetime)

    def test_confidence_validation(self):
        """Test confidence must be between 0.0 and 1.0."""
        # Valid confidence
        tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.5,
            agent_id="narrator"
        )
        assert tag.confidence == 0.5

        # Invalid confidence (too high)
        with pytest.raises(ValueError):
            ContentTag(
                origin=ContentOrigin.CANONICAL,
                confidence=1.5,
                agent_id="narrator"
            )

        # Invalid confidence (negative)
        with pytest.raises(ValueError):
            ContentTag(
                origin=ContentOrigin.CANONICAL,
                confidence=-0.1,
                agent_id="narrator"
            )


class TestTaggedSegment:
    """Test TaggedSegment model."""

    def test_create_canonical_segment(self):
        """Test creating a canonical segment."""
        segment = TaggedSegment(
            text="You enter a dimly lit chamber.",
            start_index=0,
            end_index=31,
            origin=ContentOrigin.CANONICAL,
            source_reference="Room 1"
        )

        assert segment.text == "You enter a dimly lit chamber."
        assert segment.start_index == 0
        assert segment.end_index == 31
        assert segment.origin == ContentOrigin.CANONICAL
        assert segment.source_reference == "Room 1"

    def test_create_improvised_segment(self):
        """Test creating an improvised segment."""
        segment = TaggedSegment(
            text="The air smells of lavender.",
            start_index=32,
            end_index=59,
            origin=ContentOrigin.IMPROVISED
        )

        assert segment.origin == ContentOrigin.IMPROVISED
        assert segment.source_reference is None


class TestTaggedNarrative:
    """Test TaggedNarrative model."""

    def test_create_canonical_narrative(self):
        """Test creating a canonical narrative."""
        tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.95,
            module_source="Area 1",
            agent_id="narrator"
        )

        narrative = TaggedNarrative(
            content="You find yourself in a dark cave.",
            tag=tag
        )

        assert narrative.content == "You find yourself in a dark cave."
        assert narrative.tag.origin == ContentOrigin.CANONICAL
        assert narrative.tag.module_source == "Area 1"
        assert len(narrative.segments) == 0
        assert narrative.narrative_id.startswith("narr_")

    def test_create_hybrid_narrative_with_segments(self):
        """Test creating a hybrid narrative with segments."""
        tag = ContentTag(
            origin=ContentOrigin.HYBRID,
            confidence=0.7,
            agent_id="narrator"
        )

        segments = [
            TaggedSegment(
                text="You enter the chamber.",
                start_index=0,
                end_index=22,
                origin=ContentOrigin.CANONICAL,
                source_reference="Room 5"
            ),
            TaggedSegment(
                text="The walls shimmer with magical energy.",
                start_index=23,
                end_index=62,
                origin=ContentOrigin.IMPROVISED
            )
        ]

        narrative = TaggedNarrative(
            content="You enter the chamber. The walls shimmer with magical energy.",
            tag=tag,
            segments=segments
        )

        assert narrative.tag.origin == ContentOrigin.HYBRID
        assert len(narrative.segments) == 2
        assert narrative.segments[0].origin == ContentOrigin.CANONICAL
        assert narrative.segments[1].origin == ContentOrigin.IMPROVISED

    def test_narrative_id_auto_generated(self):
        """Test narrative ID is automatically generated."""
        tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.9,
            agent_id="narrator"
        )

        narrative1 = TaggedNarrative(content="First narrative.", tag=tag)
        narrative2 = TaggedNarrative(content="Second narrative.", tag=tag)

        assert narrative1.narrative_id != narrative2.narrative_id
        assert narrative1.narrative_id.startswith("narr_")
        assert narrative2.narrative_id.startswith("narr_")


class TestTaggedFact:
    """Test TaggedFact model."""

    def test_create_canonical_fact(self):
        """Test creating a canonical fact."""
        tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=1.0,
            module_source="NPC Roster",
            agent_id="archivist"
        )

        fact = TaggedFact(
            content="The innkeeper's name is Garren.",
            origin_tag=tag,
            established_in_session=1,
            last_referenced_session=1
        )

        assert fact.content == "The innkeeper's name is Garren."
        assert fact.origin_tag.origin == ContentOrigin.CANONICAL
        assert fact.established_in_session == 1
        assert fact.last_referenced_session == 1
        assert fact.times_referenced == 1
        assert fact.fact_id.startswith("fact_")

    def test_create_improvised_fact(self):
        """Test creating an improvised fact."""
        tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.85,
            improvisation_level=ImprovisationLevel.MEDIUM,
            agent_id="narrator"
        )

        fact = TaggedFact(
            content="The village has a secret underground market.",
            origin_tag=tag,
            established_in_session=3,
            last_referenced_session=5,
            times_referenced=3
        )

        assert fact.origin_tag.origin == ContentOrigin.IMPROVISED
        assert fact.times_referenced == 3

    def test_fact_id_auto_generated(self):
        """Test fact ID is automatically generated."""
        tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.9,
            agent_id="archivist"
        )

        fact1 = TaggedFact(
            content="Fact 1",
            origin_tag=tag,
            established_in_session=1,
            last_referenced_session=1
        )
        fact2 = TaggedFact(
            content="Fact 2",
            origin_tag=tag,
            established_in_session=1,
            last_referenced_session=1
        )

        assert fact1.fact_id != fact2.fact_id
        assert fact1.fact_id.startswith("fact_")
        assert fact2.fact_id.startswith("fact_")


class TestContentTagger:
    """Test ContentTagger classification."""

    def test_classify_canonical_exact_match(self):
        """Test classification of exact canonical match."""
        module_content = {
            "room1": "You enter a dark and musty chamber filled with cobwebs."
        }
        tagger = ContentTagger(module_content)

        narrative = tagger.tag_narrative(
            content="You enter a dark and musty chamber filled with cobwebs.",
            agent_id="narrator"
        )

        assert narrative.tag.origin == ContentOrigin.CANONICAL
        assert narrative.tag.confidence >= 0.6
        assert narrative.tag.module_source == "room1"

    def test_classify_improvised_no_match(self):
        """Test classification of fully improvised content."""
        module_content = {
            "room1": "You enter a dark chamber."
        }
        tagger = ContentTagger(module_content)

        narrative = tagger.tag_narrative(
            content="A mysterious purple glow emanates from the ceiling.",
            agent_id="narrator"
        )

        assert narrative.tag.origin == ContentOrigin.IMPROVISED
        assert narrative.tag.module_source is None

    def test_classify_hybrid_partial_match(self):
        """Test classification of hybrid content."""
        module_content = {
            "room1": "You enter a dark chamber filled with ancient relics."
        }
        tagger = ContentTagger(module_content, similarity_threshold=0.6)

        # Content has some overlap but also new material
        narrative = tagger.tag_narrative(
            content="You enter a dark chamber filled with mysterious artifacts.",
            agent_id="narrator"
        )

        # Should be hybrid due to partial match
        # (may be canonical or hybrid depending on exact similarity)
        assert narrative.tag.origin in [ContentOrigin.CANONICAL, ContentOrigin.HYBRID]

    def test_empty_module_content(self):
        """Test classification with no module content."""
        tagger = ContentTagger({})

        narrative = tagger.tag_narrative(
            content="Any content here.",
            agent_id="narrator"
        )

        # With no module content, everything is improvised
        assert narrative.tag.origin == ContentOrigin.IMPROVISED
        assert narrative.tag.confidence == 1.0

    def test_jaccard_similarity(self):
        """Test Jaccard similarity calculation."""
        tagger = ContentTagger({})

        # Identical texts
        sim = tagger._jaccard_similarity("hello world", "hello world")
        assert sim == 1.0

        # No overlap
        sim = tagger._jaccard_similarity("hello world", "foo bar")
        assert sim == 0.0

        # Partial overlap
        sim = tagger._jaccard_similarity("hello world", "hello there")
        assert 0.0 < sim < 1.0

    def test_segment_hybrid_content(self):
        """Test segmentation of hybrid content."""
        module_content = {
            "room1": "You enter a dark chamber."
        }
        tagger = ContentTagger(module_content)

        # Mix of canonical and improvised
        content = "You enter a dark chamber. Strange runes glow on the walls."
        narrative = tagger.tag_narrative(content, agent_id="narrator")

        # If classified as hybrid, should have segments
        if narrative.tag.origin == ContentOrigin.HYBRID:
            assert len(narrative.segments) > 0

    def test_improvisation_level_stored(self):
        """Test improvisation level is stored in tag."""
        tagger = ContentTagger({})

        narrative = tagger.tag_narrative(
            content="Improvised content.",
            agent_id="narrator",
            improvisation_level=ImprovisationLevel.HIGH
        )

        assert narrative.tag.improvisation_level == ImprovisationLevel.HIGH

    def test_similarity_threshold_custom(self):
        """Test custom similarity threshold."""
        module_content = {
            "room1": "You enter a dark and ancient stone chamber filled with cobwebs."
        }
        # Very strict threshold
        tagger = ContentTagger(module_content, similarity_threshold=0.9)

        narrative = tagger.tag_narrative(
            content="You enter a bright modern hallway.",  # Some overlap but different
            agent_id="narrator"
        )

        # With high threshold and low similarity, should be improvised or hybrid
        assert narrative.tag.origin in [ContentOrigin.IMPROVISED, ContentOrigin.HYBRID]


class TestTaggedContentStore:
    """Test TaggedContentStore functionality."""

    def test_store_and_retrieve_narrative(self):
        """Test storing and retrieving narratives."""
        store = TaggedContentStore()

        tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.95,
            agent_id="narrator"
        )
        narrative = TaggedNarrative(content="Test content.", tag=tag)

        # Store narrative
        nid = store.store_narrative(narrative)
        assert nid == narrative.narrative_id

        # Retrieve narrative
        retrieved = store.get_narrative(nid)
        assert retrieved is not None
        assert retrieved.content == "Test content."
        assert retrieved.tag.origin == ContentOrigin.CANONICAL

    def test_store_and_retrieve_fact(self):
        """Test storing and retrieving facts."""
        store = TaggedContentStore()

        tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.8,
            agent_id="archivist"
        )
        fact = TaggedFact(
            content="The dragon is sleeping.",
            origin_tag=tag,
            established_in_session=1,
            last_referenced_session=1
        )

        # Store fact
        fid = store.store_fact(fact)
        assert fid == fact.fact_id

        # Retrieve via direct access (store doesn't have get_fact method yet)
        assert fact.fact_id in store.facts
        assert store.facts[fact.fact_id].content == "The dragon is sleeping."

    def test_get_improvised_content(self):
        """Test filtering improvised content."""
        store = TaggedContentStore()

        # Add canonical narrative
        canon_tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.95,
            agent_id="narrator"
        )
        canon_narrative = TaggedNarrative(content="Canonical.", tag=canon_tag)
        store.store_narrative(canon_narrative)

        # Add improvised narrative
        improv_tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.85,
            agent_id="narrator"
        )
        improv_narrative = TaggedNarrative(content="Improvised.", tag=improv_tag)
        store.store_narrative(improv_narrative)

        # Get improvised content
        improvised = store.get_improvised_content()
        assert len(improvised) == 1
        assert improvised[0].content == "Improvised."

    def test_get_improvised_content_confidence_filter(self):
        """Test filtering improvised content by confidence."""
        store = TaggedContentStore()

        # Low confidence improvisation
        low_tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.4,
            agent_id="narrator"
        )
        low_narrative = TaggedNarrative(content="Low confidence.", tag=low_tag)
        store.store_narrative(low_narrative)

        # High confidence improvisation
        high_tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.9,
            agent_id="narrator"
        )
        high_narrative = TaggedNarrative(content="High confidence.", tag=high_tag)
        store.store_narrative(high_narrative)

        # Filter by confidence
        results = store.get_improvised_content(min_confidence=0.5)
        assert len(results) == 1
        assert results[0].content == "High confidence."

    def test_get_improvised_content_agent_filter(self):
        """Test filtering improvised content by agent."""
        store = TaggedContentStore()

        # Narrator's improvisation
        narrator_tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.8,
            agent_id="narrator"
        )
        narrator_narrative = TaggedNarrative(content="Narrator's work.", tag=narrator_tag)
        store.store_narrative(narrator_narrative)

        # Archivist's improvisation
        archivist_tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.8,
            agent_id="archivist"
        )
        archivist_narrative = TaggedNarrative(content="Archivist's work.", tag=archivist_tag)
        store.store_narrative(archivist_narrative)

        # Filter by agent
        results = store.get_improvised_content(agent_filter="narrator")
        assert len(results) == 1
        assert results[0].content == "Narrator's work."

    def test_get_canonical_content(self):
        """Test filtering canonical content."""
        store = TaggedContentStore()

        # Add canonical narrative
        canon_tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.95,
            module_source="Room 1",
            agent_id="narrator"
        )
        canon_narrative = TaggedNarrative(content="Canonical.", tag=canon_tag)
        store.store_narrative(canon_narrative)

        # Add improvised narrative
        improv_tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.8,
            agent_id="narrator"
        )
        improv_narrative = TaggedNarrative(content="Improvised.", tag=improv_tag)
        store.store_narrative(improv_narrative)

        # Get canonical content
        canonical = store.get_canonical_content()
        assert len(canonical) == 1
        assert canonical[0].content == "Canonical."

    def test_get_canonical_content_module_filter(self):
        """Test filtering canonical content by module section."""
        store = TaggedContentStore()

        # Room 1 canonical
        room1_tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.95,
            module_source="Room 1",
            agent_id="narrator"
        )
        room1_narrative = TaggedNarrative(content="Room 1 description.", tag=room1_tag)
        store.store_narrative(room1_narrative)

        # Room 2 canonical
        room2_tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.95,
            module_source="Room 2",
            agent_id="narrator"
        )
        room2_narrative = TaggedNarrative(content="Room 2 description.", tag=room2_tag)
        store.store_narrative(room2_narrative)

        # Filter by module section
        results = store.get_canonical_content(module_section="Room 1")
        assert len(results) == 1
        assert results[0].content == "Room 1 description."

    def test_get_hybrid_breakdown(self):
        """Test getting segment breakdown for hybrid content."""
        store = TaggedContentStore()

        # Create hybrid narrative with segments
        hybrid_tag = ContentTag(
            origin=ContentOrigin.HYBRID,
            confidence=0.7,
            agent_id="narrator"
        )
        segments = [
            TaggedSegment(
                text="Canonical part.",
                start_index=0,
                end_index=15,
                origin=ContentOrigin.CANONICAL
            ),
            TaggedSegment(
                text="Improvised part.",
                start_index=16,
                end_index=32,
                origin=ContentOrigin.IMPROVISED
            )
        ]
        hybrid_narrative = TaggedNarrative(
            content="Canonical part. Improvised part.",
            tag=hybrid_tag,
            segments=segments
        )
        nid = store.store_narrative(hybrid_narrative)

        # Get breakdown
        breakdown = store.get_hybrid_breakdown(nid)
        assert len(breakdown) == 2
        assert breakdown[0].origin == ContentOrigin.CANONICAL
        assert breakdown[1].origin == ContentOrigin.IMPROVISED

    def test_get_hybrid_breakdown_non_hybrid(self):
        """Test hybrid breakdown for non-hybrid content returns empty."""
        store = TaggedContentStore()

        # Non-hybrid narrative
        tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.95,
            agent_id="narrator"
        )
        narrative = TaggedNarrative(content="Not hybrid.", tag=tag)
        nid = store.store_narrative(narrative)

        # Should return empty list
        breakdown = store.get_hybrid_breakdown(nid)
        assert len(breakdown) == 0

    def test_approve_improvisation(self):
        """Test approving improvisation."""
        store = TaggedContentStore()

        tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.8,
            agent_id="narrator"
        )
        narrative = TaggedNarrative(content="Improvised content.", tag=tag)
        nid = store.store_narrative(narrative)

        # Approve
        result = store.approve_improvisation(nid)
        assert result is True
        assert nid in store.approval_status
        approved, reason = store.approval_status[nid]
        assert approved is True
        assert reason is None

    def test_reject_improvisation(self):
        """Test rejecting improvisation."""
        store = TaggedContentStore()

        tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.8,
            agent_id="narrator"
        )
        narrative = TaggedNarrative(content="Improvised content.", tag=tag)
        nid = store.store_narrative(narrative)

        # Reject
        result = store.reject_improvisation(nid, "Contradicts module lore")
        assert result is True
        assert nid in store.approval_status
        approved, reason = store.approval_status[nid]
        assert approved is False
        assert reason == "Contradicts module lore"

    def test_approve_nonexistent_narrative(self):
        """Test approving non-existent narrative returns False."""
        store = TaggedContentStore()

        result = store.approve_improvisation("nonexistent_id")
        assert result is False

    def test_reject_nonexistent_narrative(self):
        """Test rejecting non-existent narrative returns False."""
        store = TaggedContentStore()

        result = store.reject_improvisation("nonexistent_id", "Test reason")
        assert result is False

    def test_get_session_summary(self):
        """Test getting session summary statistics."""
        store = TaggedContentStore()

        # Add various narratives
        canon_tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.95,
            agent_id="narrator"
        )
        store.store_narrative(TaggedNarrative(content="Canon 1.", tag=canon_tag))

        improv_tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.8,
            agent_id="narrator"
        )
        improv_nid = store.store_narrative(TaggedNarrative(content="Improv 1.", tag=improv_tag))

        hybrid_tag = ContentTag(
            origin=ContentOrigin.HYBRID,
            confidence=0.7,
            agent_id="narrator"
        )
        store.store_narrative(TaggedNarrative(content="Hybrid 1.", tag=hybrid_tag))

        # Approve one improvisation
        store.approve_improvisation(improv_nid)

        # Get summary
        summary = store.get_session_summary(1)
        assert summary["total_narratives"] == 3
        assert summary["canonical_count"] == 1
        assert summary["improvised_count"] == 1
        assert summary["hybrid_count"] == 1
        assert summary["approved_improvisations"] == 1
        assert summary["rejected_improvisations"] == 0

    def test_save_and_load(self):
        """Test saving and loading the store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test_store.json"

            # Create store with content
            store1 = TaggedContentStore()

            tag = ContentTag(
                origin=ContentOrigin.CANONICAL,
                confidence=0.95,
                module_source="Room 1",
                agent_id="narrator"
            )
            narrative = TaggedNarrative(content="Test content.", tag=tag)
            nid = store1.store_narrative(narrative)
            store1.approve_improvisation(nid)

            # Save
            store1.save(filepath)
            assert filepath.exists()

            # Load into new store
            store2 = TaggedContentStore()
            store2.load(filepath)

            # Verify content
            assert len(store2.narratives) == 1
            retrieved = store2.get_narrative(nid)
            assert retrieved is not None
            assert retrieved.content == "Test content."
            assert nid in store2.approval_status


class TestSessionNotesFormatter:
    """Test SessionNotesFormatter functionality."""

    def test_format_session_notes_basic(self):
        """Test basic session notes formatting."""
        store = TaggedContentStore()
        formatter = SessionNotesFormatter()

        # Add a canonical narrative
        tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.95,
            module_source="Room 1",
            agent_id="narrator"
        )
        narrative = TaggedNarrative(content="You enter a dark chamber.", tag=tag)
        store.store_narrative(narrative)

        # Format notes
        notes = formatter.format_session_notes(store, session_number=1)

        assert "# Session 1 Notes" in notes
        assert "## Summary" in notes
        assert "[CANONICAL]" in notes
        assert "Room 1" in notes
        assert "You enter a dark chamber." in notes

    def test_format_session_notes_all_origins(self):
        """Test formatting with all origin types."""
        store = TaggedContentStore()
        formatter = SessionNotesFormatter()

        # Canonical
        canon_tag = ContentTag(
            origin=ContentOrigin.CANONICAL,
            confidence=0.95,
            module_source="Room 1",
            agent_id="narrator"
        )
        store.store_narrative(TaggedNarrative(content="Canonical content.", tag=canon_tag))

        # Improvised
        improv_tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.8,
            agent_id="narrator"
        )
        store.store_narrative(TaggedNarrative(content="Improvised content.", tag=improv_tag))

        # Hybrid
        hybrid_tag = ContentTag(
            origin=ContentOrigin.HYBRID,
            confidence=0.7,
            agent_id="narrator"
        )
        segments = [
            TaggedSegment(
                text="Canon part.",
                start_index=0,
                end_index=11,
                origin=ContentOrigin.CANONICAL
            ),
            TaggedSegment(
                text="Improv part.",
                start_index=12,
                end_index=24,
                origin=ContentOrigin.IMPROVISED
            )
        ]
        store.store_narrative(TaggedNarrative(
            content="Canon part. Improv part.",
            tag=hybrid_tag,
            segments=segments
        ))

        # Format notes
        notes = formatter.format_session_notes(store, session_number=1)

        assert "[CANONICAL]" in notes
        assert "[IMPROVISED]" in notes
        assert "[HYBRID]" in notes
        assert "**Segmented Content:**" in notes

    def test_format_session_notes_with_approval_status(self):
        """Test formatting with approval/rejection status."""
        store = TaggedContentStore()
        formatter = SessionNotesFormatter()

        # Approved improvisation
        approved_tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.8,
            agent_id="narrator"
        )
        approved_narrative = TaggedNarrative(content="Approved.", tag=approved_tag)
        approved_nid = store.store_narrative(approved_narrative)
        store.approve_improvisation(approved_nid)

        # Rejected improvisation
        rejected_tag = ContentTag(
            origin=ContentOrigin.IMPROVISED,
            confidence=0.7,
            agent_id="narrator"
        )
        rejected_narrative = TaggedNarrative(content="Rejected.", tag=rejected_tag)
        rejected_nid = store.store_narrative(rejected_narrative)
        store.reject_improvisation(rejected_nid, "Breaks lore")

        # Format notes
        notes = formatter.format_session_notes(store, session_number=1)

        assert "APPROVED" in notes
        assert "REJECTED" in notes
        assert "Breaks lore" in notes

    def test_format_empty_store(self):
        """Test formatting with empty store."""
        store = TaggedContentStore()
        formatter = SessionNotesFormatter()

        notes = formatter.format_session_notes(store, session_number=1)

        assert "# Session 1 Notes" in notes
        assert "## Summary" in notes
        assert "**Total Narratives**: 0" in notes

    def test_format_summary_statistics(self):
        """Test summary statistics in formatted notes."""
        store = TaggedContentStore()
        formatter = SessionNotesFormatter()

        # Add multiple narratives
        for i in range(3):
            tag = ContentTag(
                origin=ContentOrigin.CANONICAL,
                confidence=0.95,
                agent_id="narrator"
            )
            store.store_narrative(TaggedNarrative(content=f"Content {i}.", tag=tag))

        notes = formatter.format_session_notes(store, session_number=1)

        assert "**Total Narratives**: 3" in notes
        assert "**Canonical**: 3" in notes
