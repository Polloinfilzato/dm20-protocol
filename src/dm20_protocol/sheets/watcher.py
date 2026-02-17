"""File watcher for character sheet changes.

Uses watchdog to monitor the sheets/ directory for external edits.
Includes debouncing (500ms) and suppression for dm20-initiated writes.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# Default debounce window in seconds
DEBOUNCE_SECONDS = 0.5

# Suppression window for dm20-initiated writes
SUPPRESS_SECONDS = 2.0


class SheetFileWatcher:
    """Watches the sheets/ directory for external modifications.

    Features:
    - Debouncing: coalesces rapid events (500ms window)
    - Suppression: ignores dm20-initiated writes (2s window)
    - Only watches .md files
    - Runs in a daemon thread (dies with main process)
    """

    def __init__(
        self,
        sheets_dir: Path,
        on_change: Callable[[Path], Any],
    ) -> None:
        self._sheets_dir = sheets_dir
        self._on_change = on_change
        self._observer: Observer | None = None
        self._running = False

        # Suppression tracking: path → expiry timestamp
        self._suppressed: dict[str, float] = {}
        self._suppress_lock = threading.Lock()

        # Debounce tracking: path → timer
        self._debounce_timers: dict[str, threading.Timer] = {}
        self._debounce_lock = threading.Lock()

    def start(self) -> None:
        """Start watching the sheets directory."""
        if self._running:
            return

        self._sheets_dir.mkdir(parents=True, exist_ok=True)
        handler = _SheetEventHandler(self)
        self._observer = Observer()
        self._observer.daemon = True
        self._observer.schedule(handler, str(self._sheets_dir), recursive=False)
        self._observer.start()
        self._running = True
        logger.info("Sheet watcher started: %s", self._sheets_dir)

    def stop(self) -> None:
        """Stop watching."""
        if not self._running:
            return

        # Cancel pending debounce timers
        with self._debounce_lock:
            for timer in self._debounce_timers.values():
                timer.cancel()
            self._debounce_timers.clear()

        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

        self._running = False
        self._suppressed.clear()
        logger.info("Sheet watcher stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def suppress_file(self, path: Path, duration: float = SUPPRESS_SECONDS) -> None:
        """Mark a file as suppressed (dm20-initiated write).

        Events for this file within the duration window will be ignored.
        """
        with self._suppress_lock:
            self._suppressed[str(path)] = time.monotonic() + duration

    def _is_suppressed(self, path: str) -> bool:
        """Check if a file is currently suppressed."""
        with self._suppress_lock:
            expiry = self._suppressed.get(path)
            if expiry is None:
                return False
            if time.monotonic() < expiry:
                return True
            # Expired — clean up
            del self._suppressed[path]
            return False

    def _on_file_event(self, path: Path) -> None:
        """Handle a file modification event (called by the event handler)."""
        if not path.suffix == ".md":
            return

        path_str = str(path)

        if self._is_suppressed(path_str):
            logger.debug("Suppressed event for %s", path.name)
            return

        # Debounce: cancel existing timer, set a new one
        with self._debounce_lock:
            existing = self._debounce_timers.get(path_str)
            if existing:
                existing.cancel()

            timer = threading.Timer(
                DEBOUNCE_SECONDS,
                self._fire_change,
                args=(path,),
            )
            timer.daemon = True
            self._debounce_timers[path_str] = timer
            timer.start()

    def _fire_change(self, path: Path) -> None:
        """Fire the on_change callback after debounce window."""
        with self._debounce_lock:
            self._debounce_timers.pop(str(path), None)

        if not path.exists():
            return

        try:
            self._on_change(path)
        except Exception:
            logger.exception("Error processing sheet change: %s", path)


class _SheetEventHandler(FileSystemEventHandler):
    """Watchdog event handler that delegates to SheetFileWatcher."""

    def __init__(self, watcher: SheetFileWatcher) -> None:
        super().__init__()
        self._watcher = watcher

    def on_modified(self, event: FileModifiedEvent) -> None:
        if event.is_directory:
            return
        self._watcher._on_file_event(Path(event.src_path))
