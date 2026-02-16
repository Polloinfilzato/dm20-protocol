"""
Adventure discovery and search system.

Provides keyword search, filtering, and grouping of D&D adventures
from the 5etools index. Includes keyword-to-storyline mapping for
better discoverability and spoiler-free result formatting.
"""

from __future__ import annotations

from .index import AdventureIndex
from .models import (
    AdventureIndexEntry,
    AdventureSearchResult,
    StorylineGroup,
)

# Keyword-to-storyline mapping for improved discoverability
KEYWORD_MAPPING: dict[str, list[str]] = {
    "vampire": ["Ravenloft"],
    "gothic": ["Ravenloft"],
    "horror": ["Ravenloft"],
    "curse": ["Ravenloft"],
    "strahd": ["Ravenloft"],
    "school": ["Strixhaven"],
    "magic school": ["Strixhaven"],
    "university": ["Strixhaven"],
    "college": ["Strixhaven"],
    "dragon": ["Tyranny of Dragons"],
    "cult": ["Tyranny of Dragons"],
    "tiamat": ["Tyranny of Dragons"],
    "heist": ["Keys from the Golden Vault", "Waterdeep"],
    "theft": ["Keys from the Golden Vault"],
    "steal": ["Keys from the Golden Vault"],
    "space": ["Spelljammer"],
    "spelljammer": ["Spelljammer"],
    "wildspace": ["Spelljammer"],
    "undead": ["Ravenloft", "Vecna"],
    "death": ["Ravenloft", "Vecna"],
    "lich": ["Vecna"],
    "vecna": ["Vecna"],
    "underwater": ["Ghosts of Saltmarsh"],
    "sea": ["Ghosts of Saltmarsh"],
    "naval": ["Ghosts of Saltmarsh"],
    "ship": ["Ghosts of Saltmarsh"],
    "baldur": ["Baldur's Gate"],
    "avernus": ["Baldur's Gate"],
    "hell": ["Baldur's Gate"],
    "devil": ["Baldur's Gate"],
    "ice": ["Icewind Dale"],
    "frozen": ["Icewind Dale"],
    "north": ["Icewind Dale"],
    "demon": ["Out of the Abyss"],
    "underdark": ["Out of the Abyss"],
    "drow": ["Out of the Abyss"],
    "giant": ["Storm King's Thunder"],
    "ordning": ["Storm King's Thunder"],
    "yuan-ti": ["Tomb of Annihilation"],
    "jungle": ["Tomb of Annihilation"],
    "chult": ["Tomb of Annihilation"],
    "tomb": ["Tomb of Annihilation"],
    "dungeon": ["Waterdeep"],
    "mad mage": ["Waterdeep"],
}


def expand_keywords(query: str) -> set[str]:
    """Expand search query with mapped storyline keywords.

    Takes a query string and adds any storylines that match
    keyword mappings, improving discoverability.

    Args:
        query: User search query.

    Returns:
        Set of expanded search terms including mapped storylines.
    """
    terms = {query.lower()}

    for keyword, storylines in KEYWORD_MAPPING.items():
        if keyword in query.lower():
            terms.update(s.lower() for s in storylines)

    return terms


def matches_query(entry: AdventureIndexEntry, search_terms: set[str]) -> tuple[bool, int]:
    """Check if an adventure entry matches search terms.

    Returns both a match boolean and a relevance score for sorting.
    Checks all terms and returns the highest relevance score found.

    Args:
        entry: Adventure index entry to check.
        search_terms: Set of search terms (lowercased).

    Returns:
        Tuple of (matches, relevance_score).
        Relevance: 3=exact name, 2=name contains, 1=storyline match, 0=no match.
    """
    name_lower = entry.name.lower()
    storyline_lower = entry.storyline.lower()

    max_score = 0

    for term in search_terms:
        # Exact name match (highest relevance)
        if name_lower == term:
            max_score = max(max_score, 3)
        # Name contains term
        elif term in name_lower:
            max_score = max(max_score, 2)
        # Storyline match
        elif term in storyline_lower:
            max_score = max(max_score, 1)

    return (max_score > 0, max_score)


def search_adventures(
    index: AdventureIndex,
    query: str = "",
    level_min: int | None = None,
    level_max: int | None = None,
    storyline: str | None = None,
    limit: int = 10,
) -> AdventureSearchResult:
    """Search and filter adventures with relevance sorting.

    Searches by keyword (with expansion), filters by level range and
    storyline, then groups results by storyline and sorts by relevance.

    Args:
        index: Loaded AdventureIndex instance.
        query: Keyword search string (searches name and storyline).
        level_min: Minimum character level filter.
        level_max: Maximum character level filter.
        storyline: Filter by exact or partial storyline match.
        limit: Maximum number of adventures to return.

    Returns:
        AdventureSearchResult with grouped, sorted results.
    """
    # Empty query with no filters = return storyline summary
    if not query and level_min is None and level_max is None and storyline is None:
        return _get_storyline_summary(index)

    # Expand query with keyword mapping
    search_terms = expand_keywords(query) if query else set()

    # Filter and score entries
    scored_entries: list[tuple[AdventureIndexEntry, int]] = []

    for entry in index.entries:
        # Level range filter
        if level_min is not None:
            if entry.level_end is not None and entry.level_end < level_min:
                continue
            if entry.level_start is None:
                # "Any" level adventures pass level filters
                pass

        if level_max is not None:
            if entry.level_start is not None and entry.level_start > level_max:
                continue

        # Storyline filter
        if storyline is not None:
            storyline_lower = storyline.lower()
            entry_storyline_lower = entry.storyline.lower()
            if storyline_lower not in entry_storyline_lower:
                continue

        # Query match (or no query = match all that passed filters)
        if search_terms:
            matches, score = matches_query(entry, search_terms)
            if matches:
                scored_entries.append((entry, score))
        else:
            scored_entries.append((entry, 0))

    # Sort by relevance (score desc), then by level_start
    scored_entries.sort(
        key=lambda x: (-x[1], x[0].level_start or 0)
    )

    # Take top N and group by storyline (preserve relevance order)
    top_entries = [e for e, _ in scored_entries[:limit]]
    groups = _group_by_storyline(top_entries, sort_by_level=False)

    return AdventureSearchResult(
        query=query,
        total_matches=len(top_entries),
        groups=groups,
    )


def _group_by_storyline(
    entries: list[AdventureIndexEntry],
    sort_by_level: bool = True
) -> list[StorylineGroup]:
    """Group adventure entries by storyline.

    Creates StorylineGroup instances. By default sorts adventures within
    each group by level (for multi-part series). Can preserve input order
    for relevance-sorted results.

    Args:
        entries: List of adventure entries to group.
        sort_by_level: If True, sort within groups by level_start.
                       If False, preserve input order.

    Returns:
        List of StorylineGroup instances.
    """
    storyline_map: dict[str, list[AdventureIndexEntry]] = {}
    storyline_order: list[str] = []

    for entry in entries:
        storyline = entry.storyline or "Uncategorized"
        if storyline not in storyline_map:
            storyline_map[storyline] = []
            storyline_order.append(storyline)
        storyline_map[storyline].append(entry)

    # Optionally sort each group by level (for multi-part series)
    if sort_by_level:
        for adventures in storyline_map.values():
            adventures.sort(key=lambda a: a.level_start or 0)

    # Build groups in order
    groups = [
        StorylineGroup(storyline=sl, adventures=storyline_map[sl])
        for sl in storyline_order
    ]

    return groups


def _get_storyline_summary(index: AdventureIndex) -> AdventureSearchResult:
    """Get a summary of all storyline categories.

    Returns one adventure per storyline as a representative,
    showing the breadth of available content.

    Args:
        index: Loaded AdventureIndex instance.

    Returns:
        AdventureSearchResult with one entry per storyline.
    """
    storylines = index.get_storylines()
    groups: list[StorylineGroup] = []

    for storyline, adventures in storylines.items():
        # Pick first adventure as representative
        groups.append(
            StorylineGroup(storyline=storyline, adventures=adventures[:1])
        )

    # Sort by storyline name
    groups.sort(key=lambda g: g.storyline)

    return AdventureSearchResult(
        query="",
        total_matches=len(groups),
        groups=groups,
    )


def format_search_results(result: AdventureSearchResult) -> str:
    """Format search results as spoiler-free markdown text.

    Shows adventure name, storyline, level range, and chapter count.
    Groups multi-part adventures with sequential numbering and
    recommendations.

    Args:
        result: AdventureSearchResult to format.

    Returns:
        Formatted markdown string.
    """
    if result.total_matches == 0:
        return "No adventures found matching your criteria."

    lines: list[str] = []

    if result.query:
        lines.append(f"# Search Results: \"{result.query}\"")
    else:
        lines.append("# Available Adventure Storylines")

    lines.append("")
    lines.append(f"Found {result.total_matches} adventure(s) across {result.storyline_count} storyline(s).")
    lines.append("")

    for group in result.groups:
        lines.append(f"## {group.storyline}")
        lines.append("")

        if group.is_multi_part:
            lines.append(f"**Multi-part series** ({len(group.adventures)} adventures, levels {group.level_range})")
            lines.append("**Recommended:** Start with #1")
            lines.append("")

        for i, adventure in enumerate(group.adventures, 1):
            # Multi-part numbering
            if group.is_multi_part:
                prefix = f"{i}. "
            else:
                prefix = ""

            lines.append(f"### {prefix}{adventure.name}")
            lines.append(f"- **Levels:** {adventure.level_range}")
            lines.append(f"- **Chapters:** {adventure.chapter_count}")
            if adventure.published:
                lines.append(f"- **Published:** {adventure.published}")
            lines.append("")

    return "\n".join(lines)


__all__ = [
    "expand_keywords",
    "format_search_results",
    "matches_query",
    "search_adventures",
]
