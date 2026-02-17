"""Sheet Sync Manager — coordinates rendering, parsing, diff, and approvals.

Orchestrates the bidirectional sync between Character JSON and Markdown sheets.
Handles the DM approval queue, auto-applies free changes, and manages the
lifecycle across campaign load/switch/unload.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from dm20_protocol.models import Character
from dm20_protocol.sheets.diff import SheetDiffEngine
from dm20_protocol.sheets.models import (
    ChangeStatus,
    PendingChange,
    SheetDiff,
    SyncState,
)
from dm20_protocol.sheets.parser import CharacterSheetParser, ParseError
from dm20_protocol.sheets.renderer import CharacterSheetRenderer
from dm20_protocol.sheets.schema import SheetSchema

logger = logging.getLogger(__name__)


class SheetSyncManager:
    """Coordinates bidirectional character sheet sync.

    Manages:
    - Rendering sheets when characters change
    - Processing player edits from MD files
    - DM approval queue for player_approval changes
    - Auto-applying player_free changes
    """

    def __init__(self, sheets_dir: Path | None = None) -> None:
        self._sheets_dir = sheets_dir
        self._renderer: CharacterSheetRenderer | None = None
        self._sync_states: dict[str, SyncState] = {}  # character_id → SyncState
        self._storage: Any = None  # Set by wire_storage()
        self._watcher: Any = None  # SheetFileWatcher, lazy import
        self._active = False

    def wire_storage(self, storage: Any) -> None:
        """Connect to the storage layer for applying approved changes."""
        self._storage = storage

    def start(self, sheets_dir: Path, *, enable_watcher: bool = True) -> None:
        """Start the sync manager for a campaign's sheets directory."""
        # Stop existing watcher if running (campaign switch)
        self.stop()

        self._sheets_dir = sheets_dir
        self._renderer = CharacterSheetRenderer(sheets_dir)
        self._sync_states.clear()
        self._active = True

        # Start file watcher
        if enable_watcher:
            try:
                from dm20_protocol.sheets.watcher import SheetFileWatcher
                self._watcher = SheetFileWatcher(sheets_dir, self.process_file_change)
                self._watcher.start()
            except ImportError:
                logger.warning("watchdog not installed, file watching disabled")
            except Exception:
                logger.exception("Failed to start file watcher")

        logger.info("SheetSyncManager started: %s", sheets_dir)

    def stop(self) -> None:
        """Stop the sync manager (e.g., on campaign switch)."""
        if self._watcher is not None:
            try:
                self._watcher.stop()
            except Exception:
                logger.exception("Error stopping file watcher")
            self._watcher = None

        self._active = False
        self._sync_states.clear()
        self._renderer = None
        logger.info("SheetSyncManager stopped")

    @property
    def is_active(self) -> bool:
        return self._active and self._renderer is not None

    # --- Rendering (JSON → MD) ---

    def render_character(self, character: Character) -> Path | None:
        """Render a single character sheet to disk.

        Returns the path to the written file, or None if not active.
        """
        if not self.is_active or self._renderer is None:
            return None

        state = self._get_or_create_state(character)
        state.dm20_version += 1
        state.last_sync = datetime.now()

        # Suppress watcher for this write to prevent feedback loop
        expected_path = self._renderer.sheet_path(character.name)
        if self._watcher is not None:
            self._watcher.suppress_file(expected_path)

        path, fm_hash = self._renderer.write(
            character,
            sync_version=state.dm20_version,
            sync_time=state.last_sync.isoformat(timespec="seconds"),
        )
        state.md_path = str(path)
        state.last_md_hash = fm_hash
        return path

    def render_all(self, characters: dict[str, Character]) -> list[Path]:
        """Render all character sheets. Returns list of written paths."""
        paths = []
        for character in characters.values():
            path = self.render_character(character)
            if path:
                paths.append(path)
        return paths

    def delete_sheet(self, character_name: str, character_id: str = "") -> None:
        """Remove a character sheet file and sync state."""
        if self._renderer:
            self._renderer.delete(character_name)
        # Clean up sync state
        if character_id:
            self._sync_states.pop(character_id, None)
        else:
            # Find by name
            to_remove = [
                cid for cid, state in self._sync_states.items()
                if state.character_name == character_name
            ]
            for cid in to_remove:
                self._sync_states.pop(cid, None)

    def handle_rename(
        self, old_name: str, new_name: str, character: Character
    ) -> Path | None:
        """Handle character rename: delete old sheet, render new one."""
        if self._renderer:
            self._renderer.delete(old_name)
        return self.render_character(character)

    # --- Parsing (MD → JSON) ---

    def process_file_change(self, md_path: Path) -> SheetDiff | None:
        """Process an externally modified MD file.

        1. Parse the YAML frontmatter
        2. Find the matching character by dm20_id
        3. Compute diff
        4. Auto-apply free changes
        5. Queue approval changes
        6. Drop dm_only changes

        Returns the SheetDiff, or None if no valid changes found.
        """
        if not self.is_active or self._storage is None:
            return None

        # Parse the file
        try:
            frontmatter = CharacterSheetParser.parse_file(md_path)
        except ParseError as e:
            logger.warning("Failed to parse %s: %s", md_path, e)
            return None

        # Validate
        warnings = CharacterSheetParser.validate_frontmatter(frontmatter)
        if warnings:
            logger.warning("Validation warnings for %s: %s", md_path, warnings)

        # Find character by dm20_id
        dm20_id, version, _ = CharacterSheetParser.extract_sync_metadata(frontmatter)
        if not dm20_id:
            logger.warning("No dm20_id in %s, cannot link to character", md_path)
            return None

        character = self._find_character_by_id(dm20_id)
        if character is None:
            logger.warning("Character with id %s not found", dm20_id)
            return None

        # Check feedback loop: is this our own write?
        state = self._sync_states.get(dm20_id)
        if state:
            content = md_path.read_text(encoding="utf-8")
            current_hash = CharacterSheetParser.frontmatter_hash(content)
            if current_hash == state.last_md_hash:
                logger.debug("Ignoring dm20-initiated write for %s", character.name)
                return None

        # Compute diff
        diff = SheetDiffEngine.compute_diff(character, frontmatter)
        if not diff.has_changes:
            return diff

        # Auto-apply free changes
        if diff.free_changes:
            free_updates = {}
            for change in diff.free_changes:
                mapping = SheetSchema.get_mapping(change.field)
                if mapping:
                    free_updates[mapping.model_path] = change.new_value

            changed = SheetSchema.apply_updates_to_character(character, free_updates)
            if changed:
                character.updated_at = datetime.now()
                self._storage.save()
                self.render_character(character)
                logger.info(
                    "Auto-applied %d free changes for %s: %s",
                    len(changed), character.name, changed,
                )

        # Queue approval changes
        if diff.approval_changes:
            pending = PendingChange(
                character_name=character.name,
                character_id=character.id,
                diff=diff,
            )
            state = self._get_or_create_state(character)
            state.pending_changes.append(pending)
            logger.info(
                "Queued %d changes for DM approval (%s): %s",
                len(diff.approval_changes),
                character.name,
                [c.field for c in diff.approval_changes],
            )

        return diff

    # --- DM Approval ---

    def get_pending_changes(self) -> list[PendingChange]:
        """Return all pending changes across all characters."""
        pending: list[PendingChange] = []
        for state in self._sync_states.values():
            pending.extend(
                p for p in state.pending_changes
                if p.status == ChangeStatus.PENDING
            )
        return pending

    def get_pending_for_character(self, character_name: str) -> list[PendingChange]:
        """Return pending changes for a specific character."""
        for state in self._sync_states.values():
            if state.character_name == character_name:
                return [
                    p for p in state.pending_changes
                    if p.status == ChangeStatus.PENDING
                ]
        return []

    def approve_changes(self, character_name: str) -> str:
        """Approve all pending changes for a character.

        Applies the changes to the Character model and regenerates the sheet.
        """
        if not self._storage:
            return "No storage connected"

        pending = self.get_pending_for_character(character_name)
        if not pending:
            return f"No pending changes for {character_name}"

        character = self._find_character_by_name(character_name)
        if not character:
            return f"Character {character_name} not found"

        total_applied = 0
        for p in pending:
            updates = {}
            for change in p.diff.approval_changes:
                mapping = SheetSchema.get_mapping(change.field)
                if mapping:
                    updates[mapping.model_path] = change.new_value

            changed = SheetSchema.apply_updates_to_character(character, updates)
            total_applied += len(changed)
            p.status = ChangeStatus.APPROVED
            p.resolved_at = datetime.now()

        if total_applied:
            character.updated_at = datetime.now()
            self._storage.save()
            self.render_character(character)

        return f"Approved {total_applied} changes for {character_name}"

    def reject_changes(self, character_name: str) -> str:
        """Reject all pending changes for a character.

        Regenerates the sheet from current JSON, overwriting player edits.
        """
        pending = self.get_pending_for_character(character_name)
        if not pending:
            return f"No pending changes for {character_name}"

        for p in pending:
            p.status = ChangeStatus.REJECTED
            p.resolved_at = datetime.now()

        # Regenerate sheet to overwrite player edits
        character = self._find_character_by_name(character_name)
        if character:
            self.render_character(character)

        return f"Rejected changes for {character_name}, sheet regenerated from server data"

    # --- Storage Callback ---

    def on_event(self, action: str, *args: Any) -> None:
        """Handle storage events (called by the storage callback system).

        Actions:
            - "saved": Campaign was saved → regenerate changed sheets
            - "deleted": Character was deleted → remove sheet
            - "renamed": Character was renamed → rename sheet
        """
        if not self.is_active:
            return

        try:
            if action == "saved" and self._storage:
                campaign = self._storage.get_current_campaign()
                if campaign:
                    self.render_all(campaign.characters)
            elif action == "deleted" and len(args) >= 1:
                self.delete_sheet(str(args[0]))
            elif action == "renamed" and len(args) >= 3:
                old_name, new_name, character = args[0], args[1], args[2]
                self.handle_rename(str(old_name), str(new_name), character)
        except Exception:
            logger.exception("Error in sheet sync callback (action=%s)", action)

    # --- Internal ---

    def _get_or_create_state(self, character: Character) -> SyncState:
        """Get or create a SyncState for a character."""
        if character.id not in self._sync_states:
            self._sync_states[character.id] = SyncState(
                character_id=character.id,
                character_name=character.name,
            )
        state = self._sync_states[character.id]
        state.character_name = character.name  # Keep in sync
        return state

    def _find_character_by_id(self, char_id: str) -> Character | None:
        """Find a character by ID through the storage layer."""
        if not self._storage:
            return None
        try:
            return self._storage.find_character(char_id)
        except (ValueError, AttributeError):
            return None

    def _find_character_by_name(self, name: str) -> Character | None:
        """Find a character by name through the storage layer."""
        if not self._storage:
            return None
        try:
            return self._storage.find_character(name)
        except (ValueError, AttributeError):
            return None
