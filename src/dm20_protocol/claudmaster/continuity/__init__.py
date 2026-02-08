"""
Session continuity module for the Claudmaster AI DM system.

This module provides tools for session persistence and narrative continuity:
- AutoSaveManager: Automatic session state preservation with interval-based saving
- SessionRecapGenerator: Generate narrative recaps for session resumption
- Data models for recaps, quest summaries, and story threads
"""

from __future__ import annotations

from .auto_save import AutoSaveManager
from .recap_generator import (
    QuestSummary,
    SessionRecap,
    SessionRecapGenerator,
    StoryThread,
)

__all__ = [
    "AutoSaveManager",
    "SessionRecapGenerator",
    "SessionRecap",
    "StoryThread",
    "QuestSummary",
]
