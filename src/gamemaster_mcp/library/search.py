"""
Natural language search for the PDF Library System.

Provides semantic search across the library using keyword expansion
and TF-IDF style scoring. Works without embedding models by leveraging
D&D-specific concept synonyms and term frequency analysis.
"""

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import LibraryManager
    from .models import TOCEntry


@dataclass
class SearchResult:
    """A single search result from the library.

    Attributes:
        title: Display name of the content
        source_id: Identifier of the source (e.g., 'tome-of-heroes')
        source_name: Filename of the source
        page: Page number where content starts (1-indexed)
        content_type: Type of content (class, race, spell, etc.)
        score: Relevance score (higher is better)
        is_extracted: Whether content has been extracted to JSON
    """

    title: str
    source_id: str
    source_name: str
    page: int | None
    content_type: str | None
    score: float
    is_extracted: bool


class LibrarySearch:
    """Natural language search across the library.

    Uses keyword expansion with D&D concept synonyms and TF-IDF style
    scoring to provide relevant search results. Does not require
    embedding models or external APIs.

    Attributes:
        library_manager: Reference to the LibraryManager for accessing indexes
    """

    # D&D concept synonyms for query expansion
    # Maps common D&D concepts to related terms for broader matching
    CONCEPT_SYNONYMS: dict[str, list[str]] = {
        # Combat roles
        "tanky": ["tank", "defensive", "high hp", "high ac", "durable", "tough", "frontline"],
        "tank": ["tanky", "defensive", "high hp", "durable", "tough", "frontline", "protector"],
        "dps": ["damage", "striker", "offense", "offensive", "attacker"],
        "support": ["healer", "buffer", "utility", "aid", "assist"],
        # Class archetypes
        "spellcaster": ["caster", "magic", "spells", "arcane", "divine", "mage", "sorcerer", "wizard"],
        "caster": ["spellcaster", "magic", "spells", "arcane", "divine", "mage"],
        "melee": ["martial", "fighter", "warrior", "close combat", "weapon", "frontline"],
        "martial": ["melee", "fighter", "warrior", "weapon", "combat", "physical"],
        "healer": ["healing", "support", "restoration", "cure", "cleric", "life"],
        "rogue": ["stealthy", "sneaky", "thief", "assassin", "cunning"],
        "ranger": ["nature", "hunter", "archer", "wilderness", "animal"],
        "druid": ["nature", "wild", "animal", "shapeshifter", "natural"],
        "paladin": ["holy", "divine", "knight", "oath", "smite"],
        "warlock": ["pact", "patron", "eldritch", "invocation"],
        "bard": ["music", "performance", "inspiration", "jack of all trades"],
        "monk": ["martial arts", "ki", "unarmed", "fist", "agile"],
        "barbarian": ["rage", "primal", "berserker", "savage", "fury"],
        "cleric": ["divine", "holy", "healer", "priest", "domain"],
        "sorcerer": ["innate magic", "bloodline", "metamagic", "charisma caster"],
        "wizard": ["arcane", "spellbook", "learned magic", "intelligence caster"],
        "artificer": ["inventor", "infusion", "magic item", "construct"],
        # Creature types
        "dragon": ["draconic", "wyrm", "drake", "dragonborn", "kobold"],
        "draconic": ["dragon", "wyrm", "drake", "dragonborn"],
        "undead": ["zombie", "skeleton", "vampire", "lich", "ghost", "necromancy"],
        "demon": ["fiend", "devil", "infernal", "abyssal", "evil outsider"],
        "devil": ["fiend", "demon", "infernal", "baatezu", "evil outsider"],
        "fiend": ["demon", "devil", "infernal", "abyssal"],
        "celestial": ["angel", "divine", "holy", "good outsider"],
        "fey": ["fairy", "pixie", "sprite", "feywild", "nature spirit"],
        "elemental": ["fire", "water", "earth", "air", "primordial"],
        # Playstyles
        "stealthy": ["stealth", "rogue", "sneaky", "shadow", "invisible", "hidden"],
        "sneaky": ["stealthy", "stealth", "rogue", "shadow", "cunning"],
        "nature": ["druid", "ranger", "natural", "wild", "animal", "beast"],
        "wild": ["nature", "feral", "savage", "primal", "beast"],
        "holy": ["divine", "sacred", "celestial", "paladin", "cleric", "radiant"],
        "divine": ["holy", "sacred", "celestial", "god", "deity", "cleric"],
        "arcane": ["wizard", "sorcerer", "magic", "spellcaster", "mystical"],
        "dark": ["shadow", "evil", "necromancy", "warlock", "curse"],
        "shadow": ["dark", "stealth", "rogue", "assassin", "darkness"],
        # Abilities
        "teleport": ["blink", "misty step", "dimension door", "teleportation"],
        "fly": ["flight", "wings", "levitate", "airborne"],
        "healing": ["cure", "restore", "heal", "recovery", "life"],
        "buff": ["enhance", "boost", "strengthen", "empower", "support"],
        "debuff": ["weaken", "curse", "slow", "hinder", "disable"],
        "summon": ["conjure", "call", "create", "familiar", "minion"],
        "shapeshifting": ["polymorph", "wild shape", "transform", "metamorphosis"],
        # Damage types
        "fire": ["flame", "burn", "heat", "pyro", "ignite"],
        "ice": ["cold", "frost", "freeze", "chill", "winter"],
        "cold": ["ice", "frost", "freeze", "chill", "winter"],
        "lightning": ["electric", "thunder", "storm", "shock"],
        "thunder": ["sonic", "lightning", "storm", "shatter"],
        "poison": ["toxic", "venom", "acid", "disease"],
        "necrotic": ["death", "undead", "decay", "wither", "necromancy"],
        "radiant": ["holy", "light", "divine", "celestial", "sacred"],
        "psychic": ["mind", "mental", "psionic", "telepathy"],
        "force": ["magic missile", "eldritch blast", "pure magic"],
    }

    # Inverse document frequency approximations for common D&D terms
    # Lower values = more common terms (less weight in scoring)
    # Higher values = rarer terms (more weight in scoring)
    TERM_RARITY: dict[str, float] = {
        # Very common terms (low IDF)
        "the": 0.1, "and": 0.1, "of": 0.1, "a": 0.1, "to": 0.1,
        "class": 0.3, "spell": 0.3, "race": 0.3, "feat": 0.3,
        "attack": 0.4, "damage": 0.4, "level": 0.4, "hit": 0.4,
        "action": 0.4, "bonus": 0.4, "saving": 0.4, "throw": 0.4,
        # Moderately common
        "fighter": 0.6, "wizard": 0.6, "rogue": 0.6, "cleric": 0.6,
        "elf": 0.6, "dwarf": 0.6, "human": 0.6, "halfling": 0.6,
        "fire": 0.6, "lightning": 0.6, "cold": 0.6, "poison": 0.6,
        # Less common
        "dragon": 0.8, "draconic": 0.8, "dragonborn": 0.8,
        "paladin": 0.7, "warlock": 0.7, "barbarian": 0.7,
        "necromancy": 0.8, "conjuration": 0.8, "transmutation": 0.8,
        # Rare/specific terms (high IDF)
        "bladesinger": 1.0, "hexblade": 1.0, "battlemaster": 1.0,
        "eldritch": 0.9, "metamagic": 0.9, "wild shape": 0.9,
    }

    # Default IDF for unknown terms
    DEFAULT_TERM_RARITY = 0.7

    def __init__(self, library_manager: "LibraryManager"):
        """Initialize LibrarySearch.

        Args:
            library_manager: The LibraryManager instance to search
        """
        self.library_manager = library_manager

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search across all indexed library content using natural language.

        Expands the query with D&D concept synonyms and scores results
        using TF-IDF style weighting.

        Args:
            query: Natural language search query
            limit: Maximum number of results to return

        Returns:
            List of SearchResult objects sorted by relevance score
        """
        if not query or not query.strip():
            return []

        # Expand query with synonyms
        keywords = self._expand_query(query)

        results: list[SearchResult] = []

        # Search across all indexed sources
        for source_id, index in self.library_manager._index_cache.items():
            # Check if extracted content exists
            extracted_dir = self.library_manager.extracted_dir / source_id
            has_extracted = extracted_dir.exists() and any(extracted_dir.glob("*.json"))

            for entry in self._flatten_toc(index.toc):
                score = self._score_entry(entry, keywords)
                if score > 0:
                    results.append(
                        SearchResult(
                            title=entry.title,
                            source_id=source_id,
                            source_name=index.filename,
                            page=entry.page,
                            content_type=entry.content_type.value if entry.content_type else None,
                            score=score,
                            is_extracted=has_extracted,
                        )
                    )

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        return results[:limit]

    def _expand_query(self, query: str) -> list[str]:
        """Expand query with D&D concept synonyms.

        Takes the original query and adds related terms based on
        the CONCEPT_SYNONYMS dictionary.

        Args:
            query: Original search query

        Returns:
            List of keywords including original terms and synonyms
        """
        # Tokenize query
        query_lower = query.lower()
        # Split on non-alphanumeric characters
        original_tokens = re.findall(r"[a-z0-9]+", query_lower)

        # Start with original tokens (weighted higher)
        keywords: list[str] = list(original_tokens)

        # Add synonyms for each token
        for token in original_tokens:
            if token in self.CONCEPT_SYNONYMS:
                # Add synonyms (they'll have lower weight via TF-IDF)
                for synonym in self.CONCEPT_SYNONYMS[token]:
                    # Synonyms can be multi-word phrases
                    synonym_tokens = re.findall(r"[a-z0-9]+", synonym.lower())
                    keywords.extend(synonym_tokens)

        # Also check for multi-word phrases in the original query
        for concept, synonyms in self.CONCEPT_SYNONYMS.items():
            if concept in query_lower and concept not in original_tokens:
                keywords.append(concept)
                for synonym in synonyms:
                    synonym_tokens = re.findall(r"[a-z0-9]+", synonym.lower())
                    keywords.extend(synonym_tokens)

        # Remove duplicates while preserving order
        seen: set[str] = set()
        unique_keywords: list[str] = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique_keywords.append(kw)

        return unique_keywords

    def _score_entry(self, entry: "TOCEntry", keywords: list[str]) -> float:
        """Score a TOC entry against expanded keywords using TF-IDF style scoring.

        Args:
            entry: The TOC entry to score
            keywords: Expanded list of search keywords

        Returns:
            Relevance score (0.0 if no match)
        """
        title_lower = entry.title.lower()
        title_tokens = set(re.findall(r"[a-z0-9]+", title_lower))

        score = 0.0

        # Track which original keywords (first few in list) matched
        original_keyword_matches = 0
        original_keyword_count = 0

        for i, keyword in enumerate(keywords):
            # Determine if this is an original keyword (before synonyms)
            # Original keywords are at the start of the list
            is_original = i < 5  # First 5 keywords are likely original

            # Check if keyword is in title
            if keyword in title_lower:
                # Get term rarity (IDF approximation)
                idf = self.TERM_RARITY.get(keyword, self.DEFAULT_TERM_RARITY)

                # Position weight: earlier keywords in the expanded list
                # are from the original query (more important)
                # Keywords from synonyms are added later (less important)
                position_weight = 1.0 / (1.0 + i * 0.1)

                # Exact token match bonus (word boundary match)
                exact_match_bonus = 1.5 if keyword in title_tokens else 1.0

                # Calculate term contribution
                term_score = idf * position_weight * exact_match_bonus
                score += term_score

                if is_original:
                    original_keyword_matches += 1

            if is_original:
                original_keyword_count += 1

        # Title length penalty (longer titles dilute relevance)
        # Use stronger penalty for longer titles
        if score > 0 and len(title_tokens) > 0:
            # Shorter titles get higher scores
            # 1 token = no penalty, 2 tokens = small penalty, etc.
            length_penalty = 1.0 + (len(title_tokens) - 1) * 0.15
            score = score / length_penalty

        # Exact title match bonus (title is exactly or nearly the keyword)
        # This heavily favors entries where title matches the search term
        if len(title_tokens) == 1 and title_tokens.intersection(set(keywords)):
            score *= 2.0
        elif len(title_tokens) <= 2 and len(title_tokens.intersection(set(keywords))) == len(title_tokens):
            score *= 1.5

        # Content type bonus for specific content types
        if entry.content_type:
            content_type_value = entry.content_type.value
            if content_type_value != "unknown":
                # Boost results that have identified content types
                score *= 1.2

        return score

    def _flatten_toc(self, entries: list["TOCEntry"]) -> list["TOCEntry"]:
        """Recursively flatten hierarchical TOC entries.

        Args:
            entries: List of TOCEntry objects (may have children)

        Returns:
            Flat list of all TOCEntry objects including nested children
        """
        flat: list["TOCEntry"] = []
        for entry in entries:
            flat.append(entry)
            if entry.children:
                flat.extend(self._flatten_toc(entry.children))
        return flat
