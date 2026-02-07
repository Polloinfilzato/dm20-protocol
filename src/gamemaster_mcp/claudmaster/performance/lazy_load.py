"""
Lazy loading manager for Claudmaster module content.

This module provides lazy loading and preloading capabilities for module
sections, deferring expensive operations until they are needed and
preloading content based on predicted player actions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class LoadableSection:
    """
    Represents a section that can be lazy loaded.

    Tracks the loading state and priority of a module section,
    supporting both synchronous and asynchronous loading.
    """
    name: str
    loader: Callable[[], Any] | None = None  # Callable to load the data
    data: Any = None
    loaded: bool = False
    loading: bool = False
    priority: int = 0  # Higher = load first


class LazyLoadManager:
    """
    Manages lazy loading of non-critical data.

    This manager handles deferred loading of module sections, with support
    for action-based preloading to improve response times for anticipated
    player actions.

    Features:
    - Lazy loading: Load sections only when needed
    - Background preloading: Load anticipated sections asynchronously
    - Action-based priorities: Preload sections based on action type
    - Memory management: Unload sections to free memory

    Usage:
        manager = LazyLoadManager()

        # Register sections with loaders
        manager.register_section("encounters", load_encounters_func, priority=10)
        manager.register_section("lore", load_lore_func, priority=5)

        # Ensure sections are loaded (synchronous)
        manager.ensure_loaded("encounters")

        # Preload for anticipated action (async)
        await manager.preload_for_action("combat")

        # Access loaded data
        if manager.is_loaded("encounters"):
            data = manager.sections["encounters"].data
    """

    # Priority mapping: action type -> sections to preload
    PRELOAD_PRIORITIES = {
        "combat": ["encounters", "monsters", "rules"],
        "exploration": ["locations", "traps", "treasures"],
        "roleplay": ["npcs", "dialogue", "lore"],
        "rest": ["rules", "items", "spells"],
    }

    def __init__(self):
        """Initialize the lazy load manager."""
        self.sections: dict[str, LoadableSection] = {}
        self._background_tasks: list[asyncio.Task] = []

    def register_section(self, name: str, loader: Callable, priority: int = 0) -> None:
        """
        Register a section with its loader function.

        Args:
            name: Section name
            loader: Callable that loads the section data
            priority: Loading priority (higher loads first)
        """
        self.sections[name] = LoadableSection(
            name=name,
            loader=loader,
            priority=priority,
        )

    def is_loaded(self, section: str) -> bool:
        """
        Check if a section is loaded.

        Args:
            section: Section name

        Returns:
            True if section is loaded, False otherwise
        """
        return section in self.sections and self.sections[section].loaded

    def ensure_loaded(self, *section_names: str) -> None:
        """
        Synchronously ensure sections are loaded.

        Calls the loader if not already loaded. This is a blocking operation.

        Args:
            section_names: Names of sections to load
        """
        for section_name in section_names:
            if section_name not in self.sections:
                continue

            section = self.sections[section_name]

            # Skip if already loaded or currently loading
            if section.loaded or section.loading:
                continue

            # Load synchronously
            if section.loader is not None:
                section.loading = True
                try:
                    section.data = section.loader()
                    section.loaded = True
                finally:
                    section.loading = False

    async def load_background(self, section: str) -> None:
        """
        Load a section in the background without blocking.

        Args:
            section: Section name to load
        """
        if section not in self.sections:
            return

        section_obj = self.sections[section]

        # Skip if already loaded or currently loading
        if section_obj.loaded or section_obj.loading:
            return

        # Load asynchronously
        if section_obj.loader is not None:
            section_obj.loading = True
            try:
                # If loader is async, await it; otherwise run in executor
                if asyncio.iscoroutinefunction(section_obj.loader):
                    section_obj.data = await section_obj.loader()
                else:
                    # Run sync loader in executor to avoid blocking
                    loop = asyncio.get_event_loop()
                    section_obj.data = await loop.run_in_executor(None, section_obj.loader)
                section_obj.loaded = True
            finally:
                section_obj.loading = False

    async def preload_for_action(self, action_type: str) -> None:
        """
        Preload sections relevant to the given action type.

        Args:
            action_type: Type of player action (combat, exploration, roleplay, rest)
        """
        # Get priority list for this action type
        section_names = self.PRELOAD_PRIORITIES.get(action_type, [])

        # Filter to registered and unloaded sections
        sections_to_load = [
            name for name in section_names
            if name in self.sections and not self.is_loaded(name)
        ]

        # Sort by priority (higher first)
        sections_to_load.sort(
            key=lambda name: self.sections[name].priority,
            reverse=True
        )

        # Launch background loads
        tasks = [self.load_background(section) for section in sections_to_load]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_load_priority(self, action_type: str) -> list[str]:
        """
        Return section names to preload for action type, ordered by priority.

        Args:
            action_type: Type of player action

        Returns:
            List of section names in priority order (highest first)
        """
        section_names = self.PRELOAD_PRIORITIES.get(action_type, [])

        # Filter to registered sections only
        registered = [name for name in section_names if name in self.sections]

        # Sort by priority
        registered.sort(
            key=lambda name: self.sections[name].priority,
            reverse=True
        )

        return registered

    def get_loaded_sections(self) -> list[str]:
        """
        Return names of all loaded sections.

        Returns:
            List of loaded section names
        """
        return [name for name, section in self.sections.items() if section.loaded]

    def unload_section(self, section: str) -> None:
        """
        Unload a section to free memory.

        Args:
            section: Section name to unload
        """
        if section in self.sections:
            section_obj = self.sections[section]
            section_obj.data = None
            section_obj.loaded = False

    def unload_all(self) -> None:
        """Unload all sections."""
        for section in self.sections.values():
            section.data = None
            section.loaded = False


__all__ = [
    "LazyLoadManager",
    "LoadableSection",
]
