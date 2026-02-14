"""
Model quality profiles for Claudmaster AI DM.

Provides switchable preset configurations so users can trade quality vs
token cost mid-session. Three built-in tiers:

- **quality**  — Opus + effort high, best narrative depth
- **balanced** — Opus + effort medium, matches Sonnet quality with ~76% fewer tokens
- **economy**  — Opus + effort low (Python API), Haiku (CC agents), fastest/cheapest

Each profile sets both the Python-side config (ClaudmasterConfig fields)
and the Claude Code agent file frontmatter (`model:` field).

The effort parameter is only supported on Opus models. It controls output
verbosity: medium effort produces Sonnet-quality output with dramatically
fewer tokens (Anthropic benchmark data: SWE-bench Verified).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import ClaudmasterConfig

# ── Profile Definitions ────────────────────────────────────────────────────

VALID_PROFILES = {"quality", "balanced", "economy", "custom"}

MODEL_PROFILES: dict[str, dict] = {
    "quality": {
        "model_profile": "quality",
        "llm_model": "claude-opus-4-5-20250929",
        "narrator_model": "claude-opus-4-5-20250929",
        "arbiter_model": "claude-opus-4-5-20250929",
        "effort": "high",
        "narrator_effort": "high",
        "arbiter_effort": "high",
        "narrator_max_tokens": 2048,
        "arbiter_max_tokens": 4096,
        "max_tokens": 8192,
        "temperature": 0.8,
        "narrator_temperature": 0.85,
        "arbiter_temperature": 0.4,
    },
    "balanced": {
        "model_profile": "balanced",
        "llm_model": "claude-opus-4-5-20250929",
        "narrator_model": "claude-opus-4-5-20250929",
        "arbiter_model": "claude-opus-4-5-20250929",
        "effort": "medium",
        "narrator_effort": "medium",
        "arbiter_effort": "medium",
        "narrator_max_tokens": 1024,
        "arbiter_max_tokens": 2048,
        "max_tokens": 4096,
        "temperature": 0.7,
        "narrator_temperature": 0.8,
        "arbiter_temperature": 0.3,
    },
    "economy": {
        "model_profile": "economy",
        "llm_model": "claude-opus-4-5-20250929",
        "narrator_model": "claude-opus-4-5-20250929",
        "arbiter_model": "claude-opus-4-5-20250929",
        "effort": "low",
        "narrator_effort": "low",
        "arbiter_effort": "low",
        "narrator_max_tokens": 768,
        "arbiter_max_tokens": 1024,
        "max_tokens": 2048,
        "temperature": 0.7,
        "narrator_temperature": 0.7,
        "arbiter_temperature": 0.2,
    },
}

# Maps profile -> CC agent model alias for writing to agent .md frontmatter.
# CC agents don't support per-agent effort, only model selection.
# rules-lookup is ALWAYS haiku (pure data lookups, speed matters).
AGENT_MODEL_MAP: dict[str, dict[str, str]] = {
    "quality": {
        "narrator": "opus",
        "combat-handler": "opus",
        "rules-lookup": "haiku",
    },
    "balanced": {
        "narrator": "opus",
        "combat-handler": "opus",
        "rules-lookup": "haiku",
    },
    "economy": {
        "narrator": "haiku",
        "combat-handler": "haiku",
        "rules-lookup": "haiku",
    },
}

# Recommended CC main model for display purposes.
CC_RECOMMENDATIONS: dict[str, dict[str, str]] = {
    "quality": {
        "model": "opus",
        "description": "Opus -- best narrative depth, effort high",
    },
    "balanced": {
        "model": "opus",
        "description": "Opus -- effort medium, matches Sonnet quality with fewer tokens",
    },
    "economy": {
        "model": "haiku",
        "description": "Haiku -- fast and token-efficient for CC agents",
    },
}


# ── Core Functions ──────────────────────────────────────────────────────────


def apply_profile(config: "ClaudmasterConfig", profile_name: str) -> "ClaudmasterConfig":
    """Merge a profile preset into the given config, preserving non-model fields.

    Returns a new ClaudmasterConfig instance (does not mutate the original).

    Raises:
        ValueError: If *profile_name* is not a recognised built-in profile.
    """
    if profile_name not in MODEL_PROFILES:
        raise ValueError(
            f"Unknown profile '{profile_name}'. "
            f"Valid profiles: {', '.join(sorted(MODEL_PROFILES))}"
        )

    merged = config.model_dump()
    merged.update(MODEL_PROFILES[profile_name])

    from .config import ClaudmasterConfig as _Cfg
    return _Cfg.model_validate(merged)


def get_profile_summary(profile_name: str) -> str:
    """Return a human-readable summary of a profile's settings."""
    if profile_name not in MODEL_PROFILES:
        return f"Unknown profile: {profile_name}"

    p = MODEL_PROFILES[profile_name]
    rec = CC_RECOMMENDATIONS[profile_name]
    agents = AGENT_MODEL_MAP[profile_name]

    effort_main = p.get("effort", "none")
    effort_narrator = p.get("narrator_effort", "none")
    effort_arbiter = p.get("arbiter_effort", "none")

    lines = [
        f"**Profile: {profile_name.upper()}**",
        "",
        f"  LLM model: {p['llm_model']}",
        f"  Effort (main/narrator/arbiter): {effort_main}/{effort_narrator}/{effort_arbiter}",
        f"  Narrator model: {p['narrator_model']}",
        f"  Arbiter model: {p['arbiter_model']}",
        f"  Max tokens (narrator/arbiter/main): "
        f"{p['narrator_max_tokens']}/{p['arbiter_max_tokens']}/{p['max_tokens']}",
        f"  Temperatures (narrator/arbiter/main): "
        f"{p['narrator_temperature']}/{p['arbiter_temperature']}/{p['temperature']}",
        "",
        "  CC Agent files:",
        f"    narrator.md -> model: {agents['narrator']}",
        f"    combat-handler.md -> model: {agents['combat-handler']}",
        f"    rules-lookup.md -> model: {agents['rules-lookup']}",
        "",
        f"  Recommended CC main model: /model {rec['model']}",
        f"    {rec['description']}",
    ]
    return "\n".join(lines)


# ── Agent File Resolution & Update ──────────────────────────────────────────

# Regex to match the `model:` field inside YAML frontmatter (between --- markers)
_FRONTMATTER_MODEL_RE = re.compile(
    r"(?<=\n)model:\s*\S+",
)


def resolve_agents_dir() -> Path | None:
    """Find the `.claude/agents/` directory using the standard resolution order.

    1. ``DM20_AGENTS_DIR`` env var (explicit override set by installer)
    2. Auto-discover: walk up from this file looking for ``.claude/agents/``
    3. ``DM20_STORAGE_DIR/../.claude/agents/`` (relative to play directory)

    Returns ``None`` if no agents directory can be found.
    """
    # 1. Explicit env var
    env_dir = os.environ.get("DM20_AGENTS_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            return p

    # 2. Walk up from this file
    current = Path(__file__).resolve().parent
    for _ in range(10):  # safety limit
        candidate = current / ".claude" / "agents"
        if candidate.is_dir():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    # 3. Relative to DM20_STORAGE_DIR
    storage_dir = os.environ.get("DM20_STORAGE_DIR")
    if storage_dir:
        candidate = Path(storage_dir).parent / ".claude" / "agents"
        if candidate.is_dir():
            return candidate

    return None


def update_agent_files(profile_name: str, agents_dir: Path | None = None) -> list[str]:
    """Update the ``model:`` field in CC agent .md files for the given profile.

    Args:
        profile_name: One of 'quality', 'balanced', 'economy'.
        agents_dir: Path to the ``.claude/agents/`` directory.
            If ``None``, uses :func:`resolve_agents_dir`.

    Returns:
        List of agent names whose files were successfully updated.
    """
    if profile_name not in AGENT_MODEL_MAP:
        raise ValueError(f"Unknown profile '{profile_name}'")

    if agents_dir is None:
        agents_dir = resolve_agents_dir()
    if agents_dir is None:
        return []

    mapping = AGENT_MODEL_MAP[profile_name]
    updated: list[str] = []

    for agent_name, target_model in mapping.items():
        agent_file = agents_dir / f"{agent_name}.md"
        if not agent_file.is_file():
            continue

        content = agent_file.read_text(encoding="utf-8")

        # Ensure there's a leading newline so the regex works on the first field
        search_content = "\n" + content if not content.startswith("\n") else content
        new_search, count = _FRONTMATTER_MODEL_RE.subn(
            f"model: {target_model}",
            search_content,
            count=1,
        )

        if count > 0:
            # Remove the leading newline we added
            new_content = new_search.lstrip("\n") if not content.startswith("\n") else new_search
            agent_file.write_text(new_content, encoding="utf-8")
            updated.append(agent_name)

    return updated


__all__ = [
    "VALID_PROFILES",
    "MODEL_PROFILES",
    "AGENT_MODEL_MAP",
    "CC_RECOMMENDATIONS",
    "apply_profile",
    "get_profile_summary",
    "resolve_agents_dir",
    "update_agent_files",
]
