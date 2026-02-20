"""
Per-campaign voice registry for mapping speakers to TTS configurations.

The VoiceRegistry loads a ``voice_registry.yaml`` from the campaign
directory and resolves speaker identifiers to concrete VoiceConfig
objects.  Resolution follows a cascade:

  1. Exact NPC override (``npc_overrides.<npc_name>``)
  2. Exact archetype (``npc_defaults.<gender>_<race>``)
  3. Gender wildcard (``npc_defaults.<gender>_*``)
  4. Race wildcard  (``npc_defaults.*_<race>``)
  5. Role default   (``dm_voice`` or ``combat_voice``)

This allows a campaign to define a few archetypes and specific
overrides for named NPCs while every other NPC gracefully falls
back through the cascade.
"""

import logging
import time
from pathlib import Path
from typing import Optional

import yaml

from .engines.base import AudioFormat, VoiceConfig

logger = logging.getLogger("dm20-protocol.voice.registry")

# --- YAML Schema Version ---
_SCHEMA_VERSION = 1

# --- Default registry template (written when none exists) ---
_DEFAULT_REGISTRY: dict = {
    "version": _SCHEMA_VERSION,
    "default_language": "en",
    "dm_voice": {
        "engine": "edge-tts",
        "voice_id": "default",
        "voice_design": "A warm, deep voice with authority",
    },
    "combat_voice": {
        "engine": "edge-tts",
        "voice_id": "default",
        "voice_design": "A tense, urgent narrator voice",
    },
    "npc_defaults": {
        "male_human": {
            "engine": "edge-tts",
            "voice_design": "A middle-aged male voice, neutral and calm",
        },
        "female_human": {
            "engine": "edge-tts",
            "voice_design": "A young female voice, clear and friendly",
        },
    },
    "npc_overrides": {},
}


def _raw_to_voice_config(
    raw: dict,
    default_language: str = "en",
) -> VoiceConfig:
    """Convert a raw YAML dict into a ``VoiceConfig``.

    Engine-specific keys (``voice_design``, ``engine``, and any unknown
    keys) are placed into ``VoiceConfig.extra``.

    Args:
        raw: Dictionary from the YAML registry entry.
        default_language: Fallback language if not specified.

    Returns:
        A populated VoiceConfig instance.
    """
    # Standard fields
    voice_id = raw.get("voice_id", raw.get("voice", "default"))
    language = raw.get("language", default_language)
    speed = float(raw.get("speed", 1.0))
    pitch = float(raw.get("pitch", 0.0))

    fmt_str = raw.get("output_format", "wav")
    try:
        output_format = AudioFormat(fmt_str)
    except ValueError:
        output_format = AudioFormat.WAV

    # Everything else → extra (engine, voice_design, etc.)
    _standard_keys = {"voice_id", "voice", "language", "speed", "pitch", "output_format"}
    extra: dict[str, object] = {
        k: v for k, v in raw.items() if k not in _standard_keys
    }

    return VoiceConfig(
        voice_id=voice_id,
        language=language,
        speed=speed,
        pitch=pitch,
        output_format=output_format,
        extra=extra,
    )


class VoiceRegistry:
    """Per-campaign voice configuration registry.

    Loads (or creates) a ``voice_registry.yaml`` inside the campaign
    directory and provides lookup methods that cascade through
    overrides, archetype defaults, and role defaults.

    Attributes:
        config: The raw parsed YAML dictionary.
        path: Path to the voice_registry.yaml file.
    """

    def __init__(self, campaign_dir: Path) -> None:
        self.path = campaign_dir / "voice_registry.yaml"
        self.config: dict = {}
        self._load_start = time.monotonic()
        self.config = self._load_or_create()
        load_ms = (time.monotonic() - self._load_start) * 1000
        logger.info("Voice registry loaded in %.0fms from %s", load_ms, self.path)

    # ------------------------------------------------------------------
    # Loading / saving
    # ------------------------------------------------------------------

    def _load_or_create(self) -> dict:
        """Load the registry YAML, or write the default template."""
        if self.path.exists():
            with open(self.path) as fh:
                data = yaml.safe_load(fh)
            if not isinstance(data, dict):
                logger.warning("Invalid voice registry, using defaults")
                return dict(_DEFAULT_REGISTRY)
            return data

        # First run — create the default registry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as fh:
            yaml.safe_dump(
                _DEFAULT_REGISTRY,
                fh,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        logger.info("Created default voice registry at %s", self.path)
        return dict(_DEFAULT_REGISTRY)

    def save(self) -> None:
        """Persist the current config back to YAML."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as fh:
            yaml.safe_dump(
                self.config,
                fh,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        logger.debug("Voice registry saved to %s", self.path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def default_language(self) -> str:
        return self.config.get("default_language", "en")

    def get_dm_voice(self) -> VoiceConfig:
        """Get the DM narrator voice configuration."""
        raw = self.config.get("dm_voice", {})
        return _raw_to_voice_config(raw, self.default_language)

    def get_combat_voice(self) -> VoiceConfig:
        """Get the combat narrator voice configuration."""
        raw = self.config.get("combat_voice", {})
        return _raw_to_voice_config(raw, self.default_language)

    def get_voice_config(self, speaker: str) -> VoiceConfig:
        """Resolve a speaker identifier to a VoiceConfig.

        ``speaker`` may be one of the reserved names ``"dm"`` /
        ``"combat"``, or a specific NPC name.  NPC names are looked up
        through the cascade described in the module docstring.

        Args:
            speaker: Speaker identifier (e.g. ``"dm"``, ``"combat"``,
                     ``"giuseppe_barkeep"``).

        Returns:
            Resolved VoiceConfig.
        """
        lower = speaker.lower().strip()

        if lower == "dm":
            return self.get_dm_voice()
        if lower == "combat":
            return self.get_combat_voice()

        # 1. Exact NPC override
        overrides = self.config.get("npc_overrides", {})
        if lower in overrides:
            return _raw_to_voice_config(overrides[lower], self.default_language)

        # 2–4. Archetype cascade (needs race/gender — fall to DM default)
        return self.get_dm_voice()

    def get_npc_voice(
        self,
        npc_name: str,
        *,
        race: Optional[str] = None,
        gender: Optional[str] = None,
    ) -> VoiceConfig:
        """Resolve an NPC to a VoiceConfig using the full cascade.

        Args:
            npc_name: Unique NPC identifier (slug / lowercase).
            race: NPC race (e.g. ``"human"``, ``"elf"``).
            gender: NPC gender (e.g. ``"male"``, ``"female"``).

        Returns:
            Best-match VoiceConfig for the NPC.
        """
        name = npc_name.lower().strip()

        # 1. Exact NPC override
        overrides = self.config.get("npc_overrides", {})
        if name in overrides:
            return _raw_to_voice_config(overrides[name], self.default_language)

        defaults = self.config.get("npc_defaults", {})
        g = (gender or "").lower().strip()
        r = (race or "").lower().strip()

        # 2. Exact archetype  e.g. male_human
        if g and r:
            key = f"{g}_{r}"
            if key in defaults:
                return _raw_to_voice_config(defaults[key], self.default_language)

        # 3. Gender wildcard  e.g. male_*
        if g:
            wildcard_key = f"{g}_*"
            if wildcard_key in defaults:
                return _raw_to_voice_config(defaults[wildcard_key], self.default_language)
            # Also try gender_default as convenience alias
            default_key = f"{g}_default"
            if default_key in defaults:
                return _raw_to_voice_config(defaults[default_key], self.default_language)

        # 4. Race wildcard  e.g. *_elf
        if r:
            wildcard_key = f"*_{r}"
            if wildcard_key in defaults:
                return _raw_to_voice_config(defaults[wildcard_key], self.default_language)

        # 5. Role default → DM voice
        return self.get_dm_voice()

    def set_npc_voice(self, npc_name: str, config: dict) -> None:
        """Set or update a specific NPC voice override.

        Args:
            npc_name: NPC identifier (slug / lowercase).
            config: Raw config dict (engine, voice_design, etc.).
        """
        overrides = self.config.setdefault("npc_overrides", {})
        overrides[npc_name.lower().strip()] = config
        self.save()
        logger.info("Updated voice override for NPC '%s'", npc_name)

    def remove_npc_voice(self, npc_name: str) -> bool:
        """Remove an NPC voice override.

        Args:
            npc_name: NPC identifier.

        Returns:
            True if the override existed and was removed.
        """
        overrides = self.config.get("npc_overrides", {})
        key = npc_name.lower().strip()
        if key in overrides:
            del overrides[key]
            self.save()
            return True
        return False

    def set_archetype_default(self, archetype_key: str, config: dict) -> None:
        """Set or update an archetype default (e.g. ``male_human``).

        Args:
            archetype_key: Archetype key like ``"male_elf"`` or ``"female_*"``.
            config: Raw config dict.
        """
        defaults = self.config.setdefault("npc_defaults", {})
        defaults[archetype_key.lower().strip()] = config
        self.save()

    def list_overrides(self) -> dict[str, dict]:
        """Return all NPC-specific voice overrides."""
        return dict(self.config.get("npc_overrides", {}))

    def list_archetypes(self) -> dict[str, dict]:
        """Return all archetype default entries."""
        return dict(self.config.get("npc_defaults", {}))
