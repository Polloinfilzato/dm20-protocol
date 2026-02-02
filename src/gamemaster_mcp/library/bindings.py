"""
Library Bindings for Campaign-Specific Content Filtering.

This module provides the binding system that tracks which library content
is enabled for each campaign. It allows campaigns to selectively enable
or disable sources and specific content types from the global library.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from .models import ContentType


@dataclass
class SourceBinding:
    """Binding configuration for a single library source.

    Tracks whether a source is enabled and what content from that
    source should be available to the campaign.

    Attributes:
        source_id: Unique identifier of the library source
        enabled: Whether the source is enabled for this campaign
        content_filter: Per-content-type filter. Maps ContentType to either
            "*" (all content) or a list of specific content names.
            Empty dict means all content is enabled when source is enabled.
    """

    source_id: str
    enabled: bool = True
    content_filter: dict[ContentType, list[str] | Literal["*"]] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        content_filter_serialized = {}
        for content_type, value in self.content_filter.items():
            # Use string key for JSON compatibility
            key = content_type.value if isinstance(content_type, ContentType) else content_type
            content_filter_serialized[key] = value

        return {
            "source_id": self.source_id,
            "enabled": self.enabled,
            "content_filter": content_filter_serialized,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SourceBinding":
        """Create from dictionary."""
        content_filter = {}
        for key, value in data.get("content_filter", {}).items():
            # Convert string key back to ContentType enum
            try:
                content_type = ContentType(key)
            except ValueError:
                # Skip unknown content types for forward compatibility
                continue
            content_filter[content_type] = value

        return cls(
            source_id=data["source_id"],
            enabled=data.get("enabled", True),
            content_filter=content_filter,
        )


@dataclass
class LibraryBindings:
    """Campaign-level bindings for library sources.

    Manages which library sources and content are enabled for a specific
    campaign. This allows each campaign to customize which third-party
    content is available.

    Attributes:
        campaign_id: ID of the campaign these bindings belong to
        updated_at: When the bindings were last modified
        sources: Dictionary mapping source_id to SourceBinding
    """

    campaign_id: str
    updated_at: datetime = field(default_factory=datetime.now)
    sources: dict[str, SourceBinding] = field(default_factory=dict)

    def enable_source(
        self,
        source_id: str,
        content_type: ContentType | None = None,
        content_names: list[str] | None = None,
    ) -> None:
        """Enable a library source or specific content within it.

        Args:
            source_id: The source identifier to enable
            content_type: Optional content type to filter (e.g., ContentType.CLASS)
            content_names: Optional list of specific content names to enable.
                If None and content_type is provided, enables all content of that type.
        """
        # Get or create binding
        if source_id not in self.sources:
            self.sources[source_id] = SourceBinding(source_id=source_id, enabled=True)
        else:
            self.sources[source_id].enabled = True

        binding = self.sources[source_id]

        # Apply content filter if specified
        if content_type is not None:
            if content_names is not None:
                # Enable specific content items
                existing = binding.content_filter.get(content_type, [])
                if existing == "*":
                    # Already allowing all, no change needed
                    pass
                elif isinstance(existing, list):
                    # Merge with existing list
                    merged = list(set(existing) | set(content_names))
                    binding.content_filter[content_type] = merged
                else:
                    binding.content_filter[content_type] = content_names
            else:
                # Enable all content of this type
                binding.content_filter[content_type] = "*"

        self.updated_at = datetime.now()

    def disable_source(self, source_id: str) -> None:
        """Disable a library source entirely.

        Args:
            source_id: The source identifier to disable
        """
        if source_id in self.sources:
            self.sources[source_id].enabled = False
        else:
            # Create a disabled binding
            self.sources[source_id] = SourceBinding(
                source_id=source_id, enabled=False
            )

        self.updated_at = datetime.now()

    def is_content_enabled(
        self,
        source_id: str,
        content_type: ContentType,
        content_name: str,
    ) -> bool:
        """Check if specific content is enabled for this campaign.

        Args:
            source_id: The source identifier
            content_type: The type of content (class, race, spell, etc.)
            content_name: The name of the specific content item

        Returns:
            True if the content is enabled, False otherwise.
            Returns False if the source is not bound or is disabled.
        """
        # Check if source is bound and enabled
        if source_id not in self.sources:
            return False

        binding = self.sources[source_id]
        if not binding.enabled:
            return False

        # If no content filter, all content is enabled
        if not binding.content_filter:
            return True

        # If content type not in filter, it's not enabled
        if content_type not in binding.content_filter:
            return False

        # Check the filter value
        filter_value = binding.content_filter[content_type]
        if filter_value == "*":
            return True

        # Check if content name is in the allowed list
        if isinstance(filter_value, list):
            # Case-insensitive comparison
            return content_name.lower() in [n.lower() for n in filter_value]

        return False

    def get_enabled_sources(self) -> list[str]:
        """Get list of all enabled source IDs.

        Returns:
            List of source_id strings for all enabled sources.
        """
        return [
            source_id
            for source_id, binding in self.sources.items()
            if binding.enabled
        ]

    def get_source_binding(self, source_id: str) -> SourceBinding | None:
        """Get the binding for a specific source.

        Args:
            source_id: The source identifier

        Returns:
            SourceBinding if exists, None otherwise
        """
        return self.sources.get(source_id)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "campaign_id": self.campaign_id,
            "updated_at": self.updated_at.isoformat(),
            "sources": {
                source_id: binding.to_dict()
                for source_id, binding in self.sources.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LibraryBindings":
        """Create from dictionary."""
        sources = {}
        for source_id, binding_data in data.get("sources", {}).items():
            sources[source_id] = SourceBinding.from_dict(binding_data)

        return cls(
            campaign_id=data["campaign_id"],
            updated_at=datetime.fromisoformat(data["updated_at"]),
            sources=sources,
        )
