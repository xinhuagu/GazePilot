"""Gazefy Collector UI: compact PySide6 window for training data collection.

Layout:
┌──────────────────────────────────────────────────┐
│ Gazefy Collector                      ● Status   │
├──────────────────────────────────────────────────┤
│ Window: [dropdown ▼]  [Refresh]                  │
│ Pack:   [__________]  Session: [__________]      │
│ Interval: [500] ms                               │
├──────────────────────────────────────────────────┤
│ [Start]  [Pause]  [Stop]  [Open Output]          │
├──────────────────────────────────────────────────┤
│ Frames: 0                                        │
│ ┌──────────────────────────────────────────────┐ │
│ │              preview thumbnail               │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import cv2
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gazefy.collector_ui.view_model import CollectorViewModel


class CollectorWindow(QMainWindow):
    """Main collector window."""

    def __init__(self):
        super().__init__()
        self.vm = CollectorViewModel()
        self._last_preview_path: Path | None = None
        self._init_ui()
        self._bind_signals()
        self.vm.refresh_windows()

    def _init_ui(self) -> None:
        self.setWindowTitle("Gazefy Collector")
        self.setMinimumWidth(480)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Window selection ---
        win_group = QGroupBox("Target Window")
        win_layout = QHBoxLayout(win_group)
        self.window_combo = QComboBox()
        self.window_combo.setMinimumWidth(280)
        self.refresh_btn = QPushButton("Refresh")
        win_layout.addWidget(self.window_combo, 1)
        win_layout.addWidget(self.refresh_btn)
        layout.addWidget(win_group)

        # --- Pack / Session ---
        names_group = QGroupBox("Session")
        names_layout = QHBoxLayout(names_group)
        names_layout.addWidget(QLabel("Pack:"))
        self.pack_input = QLineEdit("my_app")
        names_layout.addWidget(self.pack_input)
        names_layout.addWidget(QLabel("Session:"))
        self.session_input = QLineEdit("")
        self.session_input.setPlaceholderText("auto")
        names_layout.addWidget(self.session_input)
        names_layout.addWidget(QLabel("Interval:"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(100, 5000)
        self.interval_spin.setValue(500)
        self.interval_spin.setSuffix(" ms")
        names_layout.addWidget(self.interval_spin)
        layout.addWidget(names_group)

        # --- Controls ---
        ctrl_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.pause_btn = QPushButton("Pause")
        self.stop_btn = QPushButton("Stop")
        self.open_btn = QPushButton("Open Output")
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        for btn in [self.start_btn, self.pause_btn, self.stop_btn, self.open_btn]:
            ctrl_layout.addWidget(btn)
        layout.addLayout(ctrl_layout)

        # --- Status + count ---
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-weight: bold;")
        self.frame_count_label = QLabel("Frames: 0")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.frame_count_label)
        layout.addLayout(status_layout)

        # --- Preview ---
        self.preview_label = QLabel("No preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setStyleSheet(
            "background-color: #1a1a1a; color: #666; border-radius: 4px;"
        )
        layout.addWidget(self.preview_label)

    def _bind_signals(self) -> None:
        # UI → ViewModel
        self.refresh_btn.clicked.connect(self.vm.refresh_windows)
        self.window_combo.currentIndexChanged.connect(self.vm.select_window)
        self.start_btn.clicked.connect(self._on_start)
        self.pause_btn.clicked.connect(self._on_pause)
        self.stop_btn.clicked.connect(self.vm.stop_recording)
        self.open_btn.clicked.connect(self._on_open_output)

        # ViewModel → UI
        self.vm.windows_updated.connect(self._update_window_list)
        self.vm.recording_started.connect(self._on_recording_started)
        self.vm.recording_stopped.connect(self._on_recording_stopped)
        self.vm.frame_captured.connect(self._on_frame_captured)
        self.vm.status_changed.connect(self._on_status_changed)
        self.vm.error_occurred.connect(self._on_error)

    # --- UI actions ---

    def _on_start(self) -> None:
        if self.vm.selected_window is None:
            QMessageBox.warning(self, "No window", "Select a target window first.")
            return
        self.vm.start_recording(
            pack_name=self.pack_input.text(),
            session_name=self.session_input.text(),
            interval_ms=self.interval_spin.value(),
        )

    def _on_pause(self) -> None:
        if self.pause_btn.text() == "Pause":
            self.vm.pause_recording()
            self.pause_btn.setText("Resume")
        else:
            self.vm.resume_recording()
            self.pause_btn.setText("Pause")

    def _on_open_output(self) -> None:
        d = self.vm.session_dir
        if d and d.exists():
            subprocess.Popen(["open", str(d)])

    # --- Signal handlers ---

    def _update_window_list(self, windows: list) -> None:
        self.window_combo.clear()
        for w in windows:
            label = f"{w.owner_name} — {w.window_name} ({w.region.width}x{w.region.height})"
            self.window_combo.addItem(label)

    def _on_recording_started(self, session_dir: str) -> None:
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        self.pack_input.setEnabled(False)
        self.session_input.setEnabled(False)
        self.window_combo.setEnabled(False)
        self.refresh_btn.setEnabled(False)

    def _on_recording_stopped(self, summary: dict) -> None:
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setText("Pause")
        self.stop_btn.setEnabled(False)
        self.pack_input.setEnabled(True)
        self.session_input.setEnabled(True)
        self.window_combo.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        frames = summary.get("frames", 0)
        QMessageBox.information(
            self,
            "Collection Complete",
            f"Saved {frames} frames to:\n{summary.get('output_dir', '')}",
        )

    def _on_frame_captured(self, filename: str, count: int) -> None:
        self.frame_count_label.setText(f"Frames: {count}")
        # Update preview from the last saved file
        if self.vm.session_dir:
            img_path = self.vm.session_dir / "images" / filename
            self._show_preview(img_path)

    def _on_status_changed(self, status: str) -> None:
        self.status_label.setText(status)

    def _on_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Error", msg)

    def _show_preview(self, path: Path) -> None:
        if not path.exists():
            return
        img = cv2.imread(str(path))
        if img is None:
            return
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        # Scale to fit preview label
        label_w = self.preview_label.width()
        label_h = self.preview_label.height()
        h, w = img.shape[:2]
        scale = min(label_w / w, label_h / h, 1.0)
        if scale < 1.0:
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h))
            h, w = new_h, new_w
        qimg = QImage(img.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self.preview_label.setPixmap(QPixmap.fromImage(qimg))


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Gazefy Collector")
    window = CollectorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
