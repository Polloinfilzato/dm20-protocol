"""Tests for sheets/watcher.py — file watching, debouncing, suppression."""

import time
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dm20_protocol.sheets.watcher import SheetFileWatcher, DEBOUNCE_SECONDS


@pytest.fixture
def sheets_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sheets"
    d.mkdir()
    return d


@pytest.fixture
def callback() -> MagicMock:
    return MagicMock()


class TestWatcherLifecycle:

    def test_start_stop(self, sheets_dir: Path, callback: MagicMock) -> None:
        watcher = SheetFileWatcher(sheets_dir, callback)
        assert not watcher.is_running
        watcher.start()
        assert watcher.is_running
        watcher.stop()
        assert not watcher.is_running

    def test_double_start(self, sheets_dir: Path, callback: MagicMock) -> None:
        watcher = SheetFileWatcher(sheets_dir, callback)
        watcher.start()
        watcher.start()  # Should be idempotent
        assert watcher.is_running
        watcher.stop()

    def test_stop_without_start(self, sheets_dir: Path, callback: MagicMock) -> None:
        watcher = SheetFileWatcher(sheets_dir, callback)
        watcher.stop()  # Should not raise
        assert not watcher.is_running


class TestSuppression:

    def test_suppress_file(self, sheets_dir: Path, callback: MagicMock) -> None:
        watcher = SheetFileWatcher(sheets_dir, callback)
        test_file = sheets_dir / "test.md"
        watcher.suppress_file(test_file, duration=1.0)
        assert watcher._is_suppressed(str(test_file))

    def test_suppression_expires(self, sheets_dir: Path, callback: MagicMock) -> None:
        watcher = SheetFileWatcher(sheets_dir, callback)
        test_file = sheets_dir / "test.md"
        watcher.suppress_file(test_file, duration=0.1)
        time.sleep(0.15)
        assert not watcher._is_suppressed(str(test_file))

    def test_non_suppressed_file(self, sheets_dir: Path, callback: MagicMock) -> None:
        watcher = SheetFileWatcher(sheets_dir, callback)
        assert not watcher._is_suppressed(str(sheets_dir / "other.md"))


class TestDebouncing:

    def test_debounce_coalesces_events(self, sheets_dir: Path, callback: MagicMock) -> None:
        """Multiple rapid events for the same file should result in one callback."""
        watcher = SheetFileWatcher(sheets_dir, callback)
        test_file = sheets_dir / "test.md"
        test_file.write_text("---\nname: Test\n---\nBody")

        # Simulate multiple rapid events
        for _ in range(5):
            watcher._on_file_event(test_file)
            time.sleep(0.05)

        # Wait for debounce to fire
        time.sleep(DEBOUNCE_SECONDS + 0.2)
        # Should have been called exactly once
        assert callback.call_count == 1
        callback.assert_called_once_with(test_file)

    def test_different_files_not_coalesced(self, sheets_dir: Path, callback: MagicMock) -> None:
        """Events for different files should not be coalesced."""
        watcher = SheetFileWatcher(sheets_dir, callback)
        file_a = sheets_dir / "a.md"
        file_b = sheets_dir / "b.md"
        file_a.write_text("---\nname: A\n---\n")
        file_b.write_text("---\nname: B\n---\n")

        watcher._on_file_event(file_a)
        watcher._on_file_event(file_b)

        time.sleep(DEBOUNCE_SECONDS + 0.2)
        assert callback.call_count == 2

    def test_non_md_files_ignored(self, sheets_dir: Path, callback: MagicMock) -> None:
        watcher = SheetFileWatcher(sheets_dir, callback)
        watcher._on_file_event(sheets_dir / "test.txt")
        time.sleep(DEBOUNCE_SECONDS + 0.2)
        callback.assert_not_called()

    def test_suppressed_events_not_fired(self, sheets_dir: Path, callback: MagicMock) -> None:
        watcher = SheetFileWatcher(sheets_dir, callback)
        test_file = sheets_dir / "test.md"
        test_file.write_text("content")
        watcher.suppress_file(test_file, duration=5.0)
        watcher._on_file_event(test_file)
        time.sleep(DEBOUNCE_SECONDS + 0.2)
        callback.assert_not_called()


class TestFileWatchIntegration:
    """Test actual file system events (slower, uses real watchdog observer)."""

    @pytest.mark.slow
    def test_detects_file_modification(self, sheets_dir: Path) -> None:
        """Write a file and verify the watcher detects the change."""
        detected = threading.Event()
        detected_path = [None]

        def on_change(path: Path) -> None:
            detected_path[0] = path
            detected.set()

        watcher = SheetFileWatcher(sheets_dir, on_change)
        watcher.start()

        try:
            # Create initial file
            test_file = sheets_dir / "char.md"
            test_file.write_text("---\nname: Test\n---\nBody")
            time.sleep(1)  # Let watchdog settle

            # Modify the file
            test_file.write_text("---\nname: Modified\n---\nBody")

            # Wait for detection
            assert detected.wait(timeout=5), "File change not detected within 5s"
            assert detected_path[0] == test_file
        finally:
            watcher.stop()
