"""Floating recorder control widget: small always-on-top window for record/replay.

┌─────────────────────────────────┐
│ Gazefy Recorder        ● REC   │
│ [Start] [Stop] [Replay] [Open] │
│ Frames: 0    00:00              │
└─────────────────────────────────┘
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class RecorderWidget(QMainWindow):
    """Compact floating window to control monitor recording."""

    _frame_update = Signal(int, str)  # (count, element_desc)

    def __init__(self):
        super().__init__()
        self._recording = False
        self._replaying = False
        self._frames: list[dict] = []
        self._record_start = 0.0
        self._record_path: Path | None = None
        self._worker_thread: threading.Thread | None = None

        self._init_ui()
        self._frame_update.connect(self._on_frame_update)

        # Timer for elapsed time display
        self._elapsed_timer = QTimer()
        self._elapsed_timer.timeout.connect(self._update_elapsed)

    def _init_ui(self) -> None:
        self.setWindowTitle("Gazefy Recorder")
        self.setFixedSize(320, 100)
        # Always on top
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        # Controls row
        ctrl = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.replay_btn = QPushButton("Replay")
        self.open_btn = QPushButton("Open")
        self.stop_btn.setEnabled(False)
        self.replay_btn.setEnabled(False)
        for btn in [self.start_btn, self.stop_btn, self.replay_btn, self.open_btn]:
            btn.setFixedHeight(28)
            ctrl.addWidget(btn)
        layout.addLayout(ctrl)

        # Status row
        status = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-weight: bold;")
        self.frame_label = QLabel("Frames: 0")
        self.time_label = QLabel("00:00")
        self.element_label = QLabel("")
        self.element_label.setStyleSheet("color: #4CAF50;")
        status.addWidget(self.status_label)
        status.addWidget(self.frame_label)
        status.addWidget(self.time_label)
        status.addStretch()
        layout.addWidget(self.element_label)
        layout.addLayout(status)

        # Signals
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.replay_btn.clicked.connect(self._on_replay)
        self.open_btn.clicked.connect(self._on_open)

    def _on_start(self) -> None:
        if self._recording:
            return
        self._recording = True
        self._frames = []
        self._record_start = time.monotonic()
        rec_dir = Path("recordings")
        rec_dir.mkdir(exist_ok=True)
        self._record_path = rec_dir / f"session_{int(time.time())}.jsonl"

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.replay_btn.setEnabled(False)
        self.status_label.setText("● REC")
        self.status_label.setStyleSheet("font-weight: bold; color: red;")
        self._elapsed_timer.start(200)

        # Start cursor polling in background
        self._worker_thread = threading.Thread(target=self._record_loop, daemon=True)
        self._worker_thread.start()

    def _on_stop(self) -> None:
        if not self._recording:
            return
        self._recording = False
        self._elapsed_timer.stop()

        # Save
        if self._record_path and self._frames:
            with open(self._record_path, "w") as f:
                for frame in self._frames:
                    f.write(json.dumps(frame) + "\n")

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.replay_btn.setEnabled(bool(self._frames))
        self.status_label.setText(f"Saved ({len(self._frames)} frames)")
        self.status_label.setStyleSheet("font-weight: bold; color: #333;")
        self.element_label.setText(f"→ {self._record_path}")

    def _on_replay(self) -> None:
        if self._replaying or not self._frames:
            return

        # Ask for speed? Just use 1x for now
        self._replaying = True
        self.replay_btn.setEnabled(False)
        self.status_label.setText("▶ Replaying...")
        self.status_label.setStyleSheet("font-weight: bold; color: blue;")

        t = threading.Thread(target=self._replay_loop, daemon=True)
        t.start()

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Recording", "recordings", "JSONL (*.jsonl)"
        )
        if path:
            with open(path) as f:
                self._frames = [json.loads(line) for line in f if line.strip()]
            self._record_path = Path(path)
            self.replay_btn.setEnabled(bool(self._frames))
            self.status_label.setText(f"Loaded ({len(self._frames)} frames)")
            self.frame_label.setText(f"Frames: {len(self._frames)}")
            if self._frames:
                dur = self._frames[-1].get("t", 0)
                m, s = divmod(int(dur), 60)
                self.time_label.setText(f"{m:02d}:{s:02d}")

    def _record_loop(self) -> None:
        try:
            import pyautogui

            pyautogui.FAILSAFE = False
            from pynput import mouse
        except ImportError:
            return

        # Click listener runs in its own thread via pynput
        def on_click(x, y, button, pressed):
            if not self._recording:
                return False
            if pressed:
                t = time.monotonic() - self._record_start
                btn = "left" if button == mouse.Button.left else "right"
                self._frames.append(
                    {
                        "t": round(t, 3),
                        "x": int(x),
                        "y": int(y),
                        "click": btn,
                    }
                )
                self._frame_update.emit(len(self._frames), f"CLICK {btn} ({int(x)}, {int(y)})")

        listener = mouse.Listener(on_click=on_click)
        listener.start()

        while self._recording:
            x, y = pyautogui.position()
            t = time.monotonic() - self._record_start
            frame = {"t": round(t, 3), "x": x, "y": y}
            self._frames.append(frame)
            self._frame_update.emit(len(self._frames), f"({x}, {y})")
            time.sleep(0.05)

        listener.stop()

    def _replay_loop(self) -> None:
        try:
            import pyautogui

            pyautogui.FAILSAFE = False
        except ImportError:
            return

        for i, frame in enumerate(self._frames):
            if not self._replaying:
                break
            x, y = int(frame["x"]), int(frame["y"])
            if x <= 5 and y <= 5:
                continue

            click = frame.get("click", "")
            if click:
                if click == "right":
                    pyautogui.rightClick(x, y, _pause=False)
                else:
                    pyautogui.click(x, y, _pause=False)
                self._frame_update.emit(i + 1, f"CLICK {click} ({x}, {y})")
            else:
                pyautogui.moveTo(x, y, _pause=False)
                self._frame_update.emit(i + 1, f"({x}, {y})")

            if i + 1 < len(self._frames):
                dt = self._frames[i + 1]["t"] - frame["t"]
                if dt > 0:
                    time.sleep(dt)

        self._replaying = False
        self._frame_update.emit(len(self._frames), "done")

    def _on_frame_update(self, count: int, desc: str) -> None:
        self.frame_label.setText(f"Frames: {count}")
        if desc != "done":
            self.element_label.setText(desc)
        else:
            self.status_label.setText("Replay done")
            self.status_label.setStyleSheet("font-weight: bold; color: #333;")
            self.replay_btn.setEnabled(True)

    def _update_elapsed(self) -> None:
        if self._recording:
            elapsed = time.monotonic() - self._record_start
            m, s = divmod(int(elapsed), 60)
            self.time_label.setText(f"{m:02d}:{s:02d}")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Gazefy Recorder")
    w = RecorderWidget()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
