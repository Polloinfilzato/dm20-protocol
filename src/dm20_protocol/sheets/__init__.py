"""Bidirectional character sheet sync (Markdown ↔ JSON).

Generates beautiful Markdown character sheets from Character data,
and detects player edits in YAML frontmatter for DM approval.
"""

from dm20_protocol.sheets.models import FieldChange, PendingChange, SheetDiff, SyncState
from dm20_protocol.sheets.renderer import CharacterSheetRenderer
from dm20_protocol.sheets.schema import EditTier, FieldMapping, SheetSchema

__all__ = [
    "CharacterSheetRenderer",
    "SheetSchema",
    "FieldMapping",
    "EditTier",
    "FieldChange",
    "SheetDiff",
    "PendingChange",
    "SyncState",
]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    """Lazy imports for modules created in later phases."""
    if name == "CharacterSheetParser":
        from dm20_protocol.sheets.parser import CharacterSheetParser
        return CharacterSheetParser
    if name == "SheetDiffEngine":
        from dm20_protocol.sheets.diff import SheetDiffEngine
        return SheetDiffEngine
    if name == "SheetSyncManager":
        from dm20_protocol.sheets.sync import SheetSyncManager
        return SheetSyncManager
    if name == "SheetFileWatcher":
        from dm20_protocol.sheets.watcher import SheetFileWatcher
        return SheetFileWatcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
