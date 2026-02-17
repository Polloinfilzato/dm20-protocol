"""
Character import from external platforms.

Currently supports:
- D&D Beyond (public characters via URL, or local JSON file)
"""

# Public API — actual implementations provided by submodules.
# Stubs here for discoverability; wired in task #163.

__all__ = ["import_from_dndbeyond", "import_from_file"]


async def import_from_dndbeyond(url_or_id: str, player_name: str | None = None):
    """Import a public D&D Beyond character by URL or numeric ID."""
    raise NotImplementedError("Wired in task #163 (MCP tool integration)")


def import_from_file(file_path: str, source_format: str | None = None, player_name: str | None = None):
    """Import a character from a local JSON file."""
    raise NotImplementedError("Wired in task #163 (MCP tool integration)")
