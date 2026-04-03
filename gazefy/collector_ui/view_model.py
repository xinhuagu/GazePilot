"""ViewModel: mediates between the UI and the collection backend.

Owns all mutable state. The UI binds to signals; the backend runs in a worker thread.
"""

from __future__ import annotations

import time
from pathlib import Path

import mss
import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from gazefy.capture.window_finder import WindowInfo, list_windows
from gazefy.config import CaptureRegion
from gazefy.training.collector import CollectorConfig, DataCollector


class CollectorWorker(QObject):
    """Runs in a background thread: captures frames at interval."""

    frame_saved = Signal(str, int)  # (filename, total_count)
    finished = Signal(dict)  # session summary
    error = Signal(str)

    def __init__(self, collector: DataCollector, region: CaptureRegion, interval_ms: int):
        super().__init__()
        self._collector = collector
        self._region = region
        self._interval = interval_ms / 1000.0
        self._running = False
        self._paused = False

    def run(self) -> None:
        monitor = {
            "top": self._region.top,
            "left": self._region.left,
            "width": self._region.width,
            "height": self._region.height,
        }
        self._running = True
        try:
            with mss.mss() as sct:
                while self._running:
                    if not self._paused:
                        frame = np.array(sct.grab(monitor))
                        path = self._collector.save_frame(frame)
                        self.frame_saved.emit(path.name, self._collector.frame_count)
                    time.sleep(self._interval)
        except Exception as e:
            self.error.emit(str(e))

        summary = self._collector.finish_session()
        self.finished.emit(summary)

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def stop(self) -> None:
        self._running = False


class CollectorViewModel(QObject):
    """Owns collection state, exposes signals for the UI to bind to."""

    # Signals for UI binding
    windows_updated = Signal(list)  # list[WindowInfo]
    recording_started = Signal(str)  # session dir
    recording_stopped = Signal(dict)  # summary
    frame_captured = Signal(str, int)  # (filename, count)
    status_changed = Signal(str)  # status text
    error_occurred = Signal(str)

    def __init__(self):
        super().__init__()
        self._windows: list[WindowInfo] = []
        self._selected_window: WindowInfo | None = None
        self._worker: CollectorWorker | None = None
        self._thread: QThread | None = None
        self._recording = False
        self._session_dir: Path | None = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def selected_window(self) -> WindowInfo | None:
        return self._selected_window

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    def refresh_windows(self) -> None:
        self._windows = list_windows()
        self.windows_updated.emit(self._windows)

    def select_window(self, index: int) -> None:
        if 0 <= index < len(self._windows):
            self._selected_window = self._windows[index]

    def start_recording(self, pack_name: str, session_name: str, interval_ms: int = 500) -> None:
        if self._recording or self._selected_window is None:
            return

        region = self._selected_window.region
        config = CollectorConfig(
            output_dir="datasets",
            pack_name=pack_name or "default",
            capture_interval_ms=interval_ms,
        )
        collector = DataCollector(config)
        self._session_dir = collector.start_session(session_name or "")

        self._worker = CollectorWorker(collector, region, interval_ms)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.frame_saved.connect(self._on_frame_saved)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)

        self._recording = True
        self._thread.start()
        self.recording_started.emit(str(self._session_dir))
        self.status_changed.emit("Recording")

    def pause_recording(self) -> None:
        if self._worker:
            self._worker.pause()
            self.status_changed.emit("Paused")

    def resume_recording(self) -> None:
        if self._worker:
            self._worker.resume()
            self.status_changed.emit("Recording")

    def stop_recording(self) -> None:
        if self._worker:
            self._worker.stop()

    def _on_frame_saved(self, filename: str, count: int) -> None:
        self.frame_captured.emit(filename, count)

    def _on_finished(self, summary: dict) -> None:
        self._recording = False
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
        self._worker = None
        self.recording_stopped.emit(summary)
        self.status_changed.emit("Stopped")

    def _on_error(self, msg: str) -> None:
        self.error_occurred.emit(msg)
        self.status_changed.emit(f"Error: {msg}")
