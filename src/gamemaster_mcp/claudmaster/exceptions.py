"""
Custom exception hierarchy for the Claudmaster AI DM system.

This module defines a comprehensive exception hierarchy for error handling
across all Claudmaster components, enabling precise error classification
and recovery strategies.
"""

from __future__ import annotations

from typing import Any


class ClaudmasterError(Exception):
    """Base exception for all Claudmaster errors.

    All custom exceptions in the Claudmaster system inherit from this base class,
    allowing for generic error handling when needed.

    Attributes:
        message: Human-readable error message
        details: Optional dictionary of additional error context
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        """Initialize the error.

        Args:
            message: Human-readable error message
            details: Optional dictionary of additional error context
        """
        super().__init__(message)
        self.details = details or {}


class AgentError(ClaudmasterError):
    """Agent-specific failures.

    Raised when an agent encounters an error during execution.
    Includes information about recoverability to guide recovery strategies.

    Attributes:
        agent_name: Name of the agent that encountered the error
        recoverable: Whether this error can potentially be recovered from
    """

    def __init__(
        self,
        message: str,
        agent_name: str,
        recoverable: bool = True,
        details: dict[str, Any] | None = None,
    ):
        """Initialize the agent error.

        Args:
            message: Human-readable error message
            agent_name: Name of the agent that encountered the error
            recoverable: Whether this error can potentially be recovered from
            details: Optional dictionary of additional error context
        """
        super().__init__(message, details)
        self.agent_name = agent_name
        self.recoverable = recoverable


class StateError(ClaudmasterError):
    """Game state corruption or inconsistency.

    Raised when the game state becomes corrupted or contains
    inconsistent data that cannot be reconciled.
    """
    pass


class SessionError(ClaudmasterError):
    """Session management errors.

    Raised when session lifecycle operations fail, such as
    starting, ending, or persisting sessions.
    """
    pass


class ClaudmasterTimeoutError(ClaudmasterError):
    """Operation timeout.

    Raised when an operation exceeds its allowed execution time.
    Uses a custom name to avoid shadowing Python's builtin TimeoutError.

    Attributes:
        operation: Name of the operation that timed out
        timeout_seconds: The timeout threshold that was exceeded
    """

    def __init__(
        self,
        message: str,
        operation: str,
        timeout_seconds: float,
        details: dict[str, Any] | None = None,
    ):
        """Initialize the timeout error.

        Args:
            message: Human-readable error message
            operation: Name of the operation that timed out
            timeout_seconds: The timeout threshold that was exceeded
            details: Optional dictionary of additional error context
        """
        super().__init__(message, details)
        self.operation = operation
        self.timeout_seconds = timeout_seconds


class RecoveryError(ClaudmasterError):
    """Recovery operation itself failed.

    Raised when an error recovery attempt fails, indicating that
    the recovery mechanism itself encountered a problem.
    """
    pass


class RollbackError(ClaudmasterError):
    """State rollback failed.

    Raised when attempting to rollback to a previous state snapshot fails,
    possibly due to missing snapshots or corrupted snapshot data.
    """
    pass


__all__ = [
    "ClaudmasterError",
    "AgentError",
    "StateError",
    "SessionError",
    "ClaudmasterTimeoutError",
    "RecoveryError",
    "RollbackError",
]
