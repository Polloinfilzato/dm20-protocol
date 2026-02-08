"""
Module binding system for campaigns.

Connects adventure modules to campaigns and tracks progression state
including chapters, locations, encounters, revealed NPC info, and plot flags.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from shortuuid import random

logger = logging.getLogger("dm20-protocol")


class ModuleBinding(BaseModel):
    """Binding between campaign and module."""

    module_id: str
    source_id: str
    bound_at: datetime
    is_active: bool = False


class ModuleProgress(BaseModel):
    """Progress state for a bound module."""

    module_id: str
    current_chapter: str | None = None
    current_location: str | None = None
    visited_locations: list[str] = Field(default_factory=list)
    completed_encounters: list[str] = Field(default_factory=list)
    revealed_npcs: dict[str, list[str]] = Field(default_factory=dict)
    key_items_found: list[str] = Field(default_factory=list)
    plot_flags: dict[str, bool] = Field(default_factory=dict)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BindingResult(BaseModel):
    """Result of binding operation."""

    success: bool
    module_id: str
    message: str


class UnbindingResult(BaseModel):
    """Result of unbinding operation."""

    success: bool
    module_id: str
    message: str
    progress_preserved: bool = False


class CampaignModuleManager:
    """Manages module bindings and progress for a campaign."""

    def __init__(self, campaign_path: Path) -> None:
        """Initialize with campaign directory path.

        Args:
            campaign_path: Path to campaign directory where module_binding.json will be stored.
        """
        self.campaign_path = Path(campaign_path)
        self.binding_file = self.campaign_path / "module_binding.json"

        self._bindings: dict[str, ModuleBinding] = {}
        self._progress: dict[str, ModuleProgress] = {}
        self._active_module_id: str | None = None
        self._version: str = "1.0"

        # Load existing data if available
        self.load()

    def bind_module(
        self, module_id: str, source_id: str, set_active: bool = True
    ) -> BindingResult:
        """Bind a module to the campaign.

        Args:
            module_id: Unique identifier for the module.
            source_id: Source library ID for the module.
            set_active: Whether to set this module as active immediately.

        Returns:
            BindingResult indicating success or failure.
        """
        # Check if already bound
        if module_id in self._bindings:
            logger.warning(f"Module {module_id} is already bound to this campaign")
            return BindingResult(
                success=False,
                module_id=module_id,
                message=f"Module '{module_id}' is already bound to this campaign",
            )

        # Create binding
        binding = ModuleBinding(
            module_id=module_id,
            source_id=source_id,
            bound_at=datetime.now(timezone.utc),
            is_active=set_active,
        )

        self._bindings[module_id] = binding

        # Initialize progress
        progress = ModuleProgress(module_id=module_id)
        self._progress[module_id] = progress

        # Set as active if requested
        if set_active:
            # Deactivate other modules
            for bid in self._bindings:
                if bid != module_id:
                    self._bindings[bid].is_active = False
            self._active_module_id = module_id

        self.save()

        logger.info(
            f"Bound module '{module_id}' from source '{source_id}'"
            + (" (set as active)" if set_active else "")
        )

        return BindingResult(
            success=True,
            module_id=module_id,
            message=f"Successfully bound module '{module_id}'"
            + (" and set as active" if set_active else ""),
        )

    def unbind_module(
        self, module_id: str, preserve_progress: bool = True
    ) -> UnbindingResult:
        """Unbind a module from the campaign.

        Args:
            module_id: ID of the module to unbind.
            preserve_progress: Whether to keep progress data after unbinding.

        Returns:
            UnbindingResult indicating success or failure.
        """
        # Check if bound
        if module_id not in self._bindings:
            logger.warning(f"Module {module_id} is not bound to this campaign")
            return UnbindingResult(
                success=False,
                module_id=module_id,
                message=f"Module '{module_id}' is not bound to this campaign",
                progress_preserved=False,
            )

        # Remove binding
        del self._bindings[module_id]

        # Clear active module if this was it
        if self._active_module_id == module_id:
            self._active_module_id = None

        # Handle progress
        progress_preserved = False
        if not preserve_progress and module_id in self._progress:
            del self._progress[module_id]
        elif preserve_progress and module_id in self._progress:
            progress_preserved = True

        self.save()

        logger.info(
            f"Unbound module '{module_id}'"
            + (
                " (progress preserved)" if progress_preserved else " (progress deleted)"
            )
        )

        return UnbindingResult(
            success=True,
            module_id=module_id,
            message=f"Successfully unbound module '{module_id}'",
            progress_preserved=progress_preserved,
        )

    def set_active_module(self, module_id: str) -> None:
        """Set a module as the active module.

        Args:
            module_id: ID of the module to set as active.

        Raises:
            ValueError: If the module is not bound to this campaign.
        """
        if module_id not in self._bindings:
            raise ValueError(
                f"Cannot set '{module_id}' as active - module is not bound to this campaign"
            )

        # Deactivate all modules
        for bid in self._bindings:
            self._bindings[bid].is_active = False

        # Activate the requested module
        self._bindings[module_id].is_active = True
        self._active_module_id = module_id

        self.save()
        logger.info(f"Set module '{module_id}' as active")

    def get_active_module(self) -> str | None:
        """Get the ID of the currently active module.

        Returns:
            Module ID if one is active, None otherwise.
        """
        return self._active_module_id

    def get_binding(self, module_id: str) -> ModuleBinding | None:
        """Get binding information for a specific module.

        Args:
            module_id: ID of the module.

        Returns:
            ModuleBinding if the module is bound, None otherwise.
        """
        return self._bindings.get(module_id)

    def list_bindings(self) -> list[ModuleBinding]:
        """Get all module bindings for this campaign.

        Returns:
            List of all ModuleBinding objects.
        """
        return list(self._bindings.values())

    def update_progress(
        self,
        module_id: str,
        current_chapter: str | None = None,
        current_location: str | None = None,
        visited_location: str | None = None,
        completed_encounter: str | None = None,
        revealed_npc: tuple[str, str] | None = None,
        key_item_found: str | None = None,
        plot_flag: tuple[str, bool] | None = None,
    ) -> ModuleProgress:
        """Update progress for a module.

        Args:
            module_id: ID of the module to update.
            current_chapter: Set current chapter (optional).
            current_location: Set current location (optional).
            visited_location: Add a visited location (optional).
            completed_encounter: Add a completed encounter (optional).
            revealed_npc: Tuple of (npc_id, info) to add revealed info (optional).
            key_item_found: Add a key item found (optional).
            plot_flag: Tuple of (flag_name, value) to set a plot flag (optional).

        Returns:
            Updated ModuleProgress object.

        Raises:
            ValueError: If the module is not bound to this campaign.
        """
        if module_id not in self._bindings:
            raise ValueError(
                f"Cannot update progress for '{module_id}' - module is not bound to this campaign"
            )

        # Get or create progress
        if module_id not in self._progress:
            self._progress[module_id] = ModuleProgress(module_id=module_id)

        progress = self._progress[module_id]

        # Update fields
        if current_chapter is not None:
            progress.current_chapter = current_chapter

        if current_location is not None:
            progress.current_location = current_location

        if visited_location is not None:
            if visited_location not in progress.visited_locations:
                progress.visited_locations.append(visited_location)

        if completed_encounter is not None:
            if completed_encounter not in progress.completed_encounters:
                progress.completed_encounters.append(completed_encounter)

        if revealed_npc is not None:
            npc_id, info = revealed_npc
            if npc_id not in progress.revealed_npcs:
                progress.revealed_npcs[npc_id] = []
            if info not in progress.revealed_npcs[npc_id]:
                progress.revealed_npcs[npc_id].append(info)

        if key_item_found is not None:
            if key_item_found not in progress.key_items_found:
                progress.key_items_found.append(key_item_found)

        if plot_flag is not None:
            flag_name, value = plot_flag
            progress.plot_flags[flag_name] = value

        # Update timestamp
        progress.last_updated = datetime.now(timezone.utc)

        self.save()
        logger.debug(f"Updated progress for module '{module_id}'")

        return progress

    def get_progress(self, module_id: str | None = None) -> ModuleProgress | None:
        """Get progress for a module.

        Args:
            module_id: ID of the module. If None, returns progress for active module.

        Returns:
            ModuleProgress if found, None otherwise.
        """
        # Use active module if none specified
        if module_id is None:
            module_id = self._active_module_id

        if module_id is None:
            return None

        return self._progress.get(module_id)

    def save(self) -> None:
        """Persist bindings and progress to module_binding.json."""
        data = {
            "version": self._version,
            "active_module_id": self._active_module_id,
            "bindings": [binding.model_dump() for binding in self._bindings.values()],
            "progress": {
                mid: progress.model_dump() for mid, progress in self._progress.items()
            },
            "metadata": {"last_updated": datetime.now(timezone.utc).isoformat()},
        }

        # Ensure directory exists
        self.campaign_path.mkdir(parents=True, exist_ok=True)

        with open(self.binding_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        logger.debug(f"Saved module bindings to {self.binding_file}")

    def load(self) -> None:
        """Load bindings and progress from module_binding.json."""
        if not self.binding_file.exists():
            logger.debug(
                f"No existing binding file at {self.binding_file}, starting fresh"
            )
            return

        try:
            with open(self.binding_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._version = data.get("version", "1.0")
            self._active_module_id = data.get("active_module_id")

            # Load bindings
            bindings_list = data.get("bindings", [])
            self._bindings = {
                binding["module_id"]: ModuleBinding(**binding)
                for binding in bindings_list
            }

            # Load progress
            progress_dict = data.get("progress", {})
            self._progress = {
                mid: ModuleProgress(**prog_data)
                for mid, prog_data in progress_dict.items()
            }

            logger.debug(
                f"Loaded {len(self._bindings)} module bindings from {self.binding_file}"
            )

        except Exception as e:
            logger.error(f"Error loading module bindings from {self.binding_file}: {e}")
            # Start fresh on error
            self._bindings = {}
            self._progress = {}
            self._active_module_id = None
