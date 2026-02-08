"""
Error recovery subsystem for the Claudmaster AI DM.

This package provides comprehensive error recovery capabilities including:
- Agent failure recovery with retry and fallback strategies
- Graceful degradation of system capabilities
- State rollback to previous snapshots
- Crash recovery for unexpected termination
- User-friendly error message formatting
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dm20_protocol.claudmaster.base import AgentResponse


@dataclass
class RecoveryResult:
    """Result of a recovery operation.

    Attributes:
        success: Whether the recovery was successful
        strategy_used: The recovery strategy that was applied
            ("retry", "fallback", "degradation", "user_intervention")
        message: Human-readable description of the recovery outcome
        response: Optional agent response if recovery produced output
        degradation_level: Optional degradation level if degradation was applied
    """

    success: bool
    strategy_used: str
    message: str
    response: AgentResponse | None = None
    degradation_level: str | None = None


__all__ = [
    "RecoveryResult",
]
