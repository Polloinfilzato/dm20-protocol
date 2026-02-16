"""
Shared utilities for processing 5etools markup and entry structures.

Extracted from FiveToolsSource so both rulebook and adventure code
can import them without coupling to the full source class.
"""

import re


# Regex for stripping 5etools markup tags
_MARKUP_DC_RE = re.compile(r"\{@dc\s+(\d+)\}")
_MARKUP_HIT_RE = re.compile(r"\{@hit\s+(\d+)\}")
_MARKUP_GENERIC_RE = re.compile(r"\{@\w+\s+([^}|]+?)(?:\|[^}]*)?\}")
_MARKUP_EMPTY_RE = re.compile(r"\{@\w+\}")


def convert_5etools_markup(text: str) -> str:
    """Convert 5etools markup tags to plain text.

    Handles tags like {@dice 1d6}, {@spell fireball}, {@dc 15}, etc.
    """
    if not text:
        return ""
    # Special cases: {@dc 15} → DC 15, {@hit 5} → +5
    text = _MARKUP_DC_RE.sub(r"DC \1", text)
    text = _MARKUP_HIT_RE.sub(r"+\1", text)
    # Generic: {@tag content} or {@tag content|source} → content
    text = _MARKUP_GENERIC_RE.sub(r"\1", text)
    # Empty tags with no content: {@h} → ""
    text = _MARKUP_EMPTY_RE.sub("", text)
    return text


def render_entries(entries: list | None) -> list[str]:
    """Render 5etools entries array to list of plain text paragraphs.

    5etools entries can be strings or nested objects with sub-entries.
    This function recursively flattens them into readable text.
    """
    if not entries:
        return []
    result: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            result.append(convert_5etools_markup(entry))
        elif isinstance(entry, dict):
            entry_type = entry.get("type", "")
            if entry_type in ("entries", "inset", "insetReadaloud"):
                name = entry.get("name", "")
                sub = render_entries(entry.get("entries", []))
                if name and sub:
                    result.append(f"{name}. {sub[0]}")
                    result.extend(sub[1:])
                elif name:
                    result.append(name)
                else:
                    result.extend(sub)
            elif entry_type == "list":
                for item in entry.get("items", []):
                    if isinstance(item, str):
                        result.append(
                            f"- {convert_5etools_markup(item)}"
                        )
                    elif isinstance(item, dict):
                        sub = render_entries([item])
                        for s in sub:
                            result.append(f"- {s}")
            elif entry_type == "table":
                caption = entry.get("caption", "")
                if caption:
                    result.append(f"[Table: {caption}]")
            else:
                # Other types — try to extract nested entries
                sub = render_entries(entry.get("entries", []))
                result.extend(sub)
    return result


__all__ = [
    "convert_5etools_markup",
    "render_entries",
]
