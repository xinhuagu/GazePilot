"""Monitor mode: real-time cursor-to-element tracking with optional recording.

Usage:
    gazefy monitor --window "Citrix"
    gazefy monitor --pack my_erp --window "Citrix" --record
    gazefy replay recordings/session_xxx.jsonl
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from gazefy.config import CaptureRegion, GazefyConfig
from gazefy.core.orchestrator import Orchestrator
from gazefy.utils.timing import FPSCounter

logger = logging.getLogger(__name__)


@dataclass
class RecordedFrame:
    """One frame of recorded cursor trajectory."""

    t: float  # Seconds since recording start
    x: float  # Screen x
    y: float  # Screen y
    element_id: str = ""
    element_class: str = ""
    confidence: float = 0.0


def run_monitor(
    region: CaptureRegion,
    pack_name: str = "",
    packs_dir: str = "packs",
    retina_scale: float = 2.0,
    show_all_interval: float = 5.0,
    record: bool = False,
    record_dir: str = "recordings",
) -> None:
    """Run monitor mode: live cursor-to-element tracking in terminal.

    Args:
        region: Screen region to capture.
        pack_name: Force a specific pack (empty = auto-route or no model).
        packs_dir: Directory containing ApplicationPack artifacts.
        retina_scale: Retina display scale factor.
        show_all_interval: Seconds between full element list dumps.
        record: If True, save cursor trajectory to a JSONL file.
        record_dir: Directory for recording files.
    """
    config = GazefyConfig(
        region=region,
        retina_scale=retina_scale,
        mode="monitor",
    )

    orch = Orchestrator(config)
    registry = _make_registry(packs_dir)
    orch.registry = registry
    orch.router = _make_router(registry)

    # Force pack if specified
    if pack_name:
        orch.registry.scan()
        pack = orch.router.force_pack(pack_name)
        if pack is None:
            print(f"Pack '{pack_name}' not found in {packs_dir}/")
            available = list(orch.registry.packs.keys())
            if available:
                print(f"Available packs: {', '.join(available)}")
            else:
                print("No packs found. Run 'gazefy train' first.")
            sys.exit(1)

    orch.setup()

    ui_map = orch.tracker.current_map
    pack = orch.router.active_pack
    pack_label = pack.metadata.name if pack else "(no pack)"
    has_model = orch.detector is not None and orch.detector.is_loaded

    print("Gazefy Monitor")
    print(f"  Region: ({region.left}, {region.top}) {region.width}x{region.height}")
    print(f"  Pack: {pack_label}")
    print(f"  Model: {'loaded' if has_model else 'none (cursor tracking only)'}")
    print("  Press Ctrl+C to stop.\n")

    fps = FPSCounter()
    last_element_id = ""
    last_full_dump = 0.0
    detect_count = 0
    recording: list[RecordedFrame] = []
    record_start = time.monotonic()
    record_path: Path | None = None

    if record:
        rec_dir = Path(record_dir)
        rec_dir.mkdir(parents=True, exist_ok=True)
        record_path = rec_dir / f"session_{int(time.time())}.jsonl"
        print(f"  Recording to: {record_path}")

    try:
        while True:
            # --- Run one pipeline step ---
            frame = orch.capture.get_latest_frame()
            if frame is not None:
                change = orch.change_detector.check(frame.image)
                if change.changed and has_model:
                    detections = orch.detector.detect(frame.image)
                    h, w = frame.image.shape[:2]
                    orch.tracker.update(detections, change, frame_width=w, frame_height=h)
                    # Bootstrap stability: feed same detections as MINOR to bump to stability=2
                    if detect_count == 0 and detections:
                        from gazefy.capture.change_detector import ChangeLevel, ChangeResult

                        bootstrap = ChangeResult(changed=True, change_level=ChangeLevel.MINOR)
                        orch.tracker.update(detections, bootstrap, frame_width=w, frame_height=h)
                    orch.cursor.set_ui_map(orch.tracker.current_map)
                    detect_count += 1
                fps.tick()

            # --- Read cursor state ---
            state = orch.cursor.state
            ui_map = orch.tracker.current_map
            el = state.current_element

            # --- Record ---
            if record:
                recording.append(
                    RecordedFrame(
                        t=time.monotonic() - record_start,
                        x=state.screen_position.x,
                        y=state.screen_position.y,
                        element_id=el.id if el else "",
                        element_class=el.class_name if el else "",
                        confidence=el.confidence if el else 0.0,
                    )
                )

            # --- Live status line ---
            if el:
                text_part = f' "{el.text}"' if el.text else ""
                line = (
                    f"\r  Cursor: [{el.class_name}]{text_part} "
                    f"id={el.id} conf={el.confidence:.2f} "
                    f"dwell={state.dwell_time_ms:.0f}ms"
                )
                # Notify on element change
                if el.id != last_element_id:
                    last_element_id = el.id
                    # Print on new line when element changes
                    sys.stdout.write(f"\n  → [{el.class_name}]{text_part} id={el.id}")
                    sys.stdout.flush()
            else:
                line = (
                    f"\r  Cursor: (no element) "
                    f"pos=({state.screen_position.x:.0f},{state.screen_position.y:.0f})"
                )
                if last_element_id:
                    last_element_id = ""
                    sys.stdout.write("\n  → (left element)")
                    sys.stdout.flush()

            # Overwrite status line
            sys.stdout.write(f"{line:<80}")
            sys.stdout.flush()

            # --- Periodic full dump ---
            now = time.monotonic()
            if show_all_interval and (now - last_full_dump) >= show_all_interval:
                last_full_dump = now
                n = ui_map.element_count
                sys.stdout.write(
                    f"\n  --- [{n} elements | gen={ui_map.generation} | "
                    f"detections={detect_count} | fps={fps.fps:.1f}] ---\n"
                )
                if n > 0:
                    for e in sorted(ui_map.elements.values(), key=lambda x: (x.bbox.y1, x.bbox.x1)):
                        text = f' "{e.text}"' if e.text else ""
                        sys.stdout.write(
                            f"    {e.id:12s} {e.class_name:15s}{text:20s} "
                            f"({e.bbox.x1:.0f},{e.bbox.y1:.0f})-"
                            f"({e.bbox.x2:.0f},{e.bbox.y2:.0f}) "
                            f"conf={e.confidence:.2f} stab={e.stability}\n"
                        )
                sys.stdout.flush()

            time.sleep(0.05)  # 20Hz display refresh

    except KeyboardInterrupt:
        print("\n\nStopped.")
    finally:
        orch.shutdown()
        print(f"Session: {detect_count} detection cycles, {ui_map.element_count} final elements")
        if record and recording and record_path:
            with open(record_path, "w") as f:
                for frame in recording:
                    f.write(
                        json.dumps(
                            {
                                "t": round(frame.t, 3),
                                "x": round(frame.x),
                                "y": round(frame.y),
                                "element_id": frame.element_id,
                                "element_class": frame.element_class,
                                "confidence": round(frame.confidence, 3),
                            }
                        )
                        + "\n"
                    )
            print(f"Recorded {len(recording)} frames to {record_path}")


def run_replay(recording_path: str, speed: float = 1.0) -> None:
    """Replay a recorded cursor trajectory.

    Args:
        recording_path: Path to a .jsonl recording file.
        speed: Playback speed multiplier (2.0 = double speed).
    """
    try:
        import pyautogui

        pyautogui.FAILSAFE = False
    except ImportError:
        print("pyautogui required: pip install gazefy[platform]")
        sys.exit(1)

    path = Path(recording_path)
    if not path.exists():
        print(f"Recording not found: {path}")
        sys.exit(1)

    with open(path) as f:
        frames = [json.loads(line) for line in f if line.strip()]

    if not frames:
        print("Empty recording.")
        return

    print(f"Replaying {len(frames)} frames from {path}")
    print(f"  Speed: {speed}x")
    print(f"  Duration: {frames[-1]['t']:.1f}s (original)")
    print("  Press Ctrl+C to stop.\n")

    last_element = ""
    try:
        for i, frame in enumerate(frames):
            x, y = int(frame["x"]), int(frame["y"])
            eid = frame.get("element_id", "")
            ecls = frame.get("element_class", "")
            conf = frame.get("confidence", 0)

            # Skip corner positions (pyautogui failsafe)
            if x <= 5 and y <= 5:
                continue
            pyautogui.moveTo(x, y, _pause=False)

            # Print element transitions
            if eid and eid != last_element:
                last_element = eid
                print(f"  → [{ecls}] {eid} conf={conf:.2f} at ({x},{y})")
            elif not eid and last_element:
                last_element = ""
                print(f"  → (left element) at ({x},{y})")

            # Wait for next frame
            if i + 1 < len(frames):
                dt = (frames[i + 1]["t"] - frame["t"]) / speed
                if dt > 0:
                    time.sleep(dt)

    except KeyboardInterrupt:
        print("\n\nReplay stopped.")

    print(f"Replay complete: {len(frames)} frames")


def _make_registry(packs_dir: str):
    from gazefy.core.model_registry import ModelRegistry

    return ModelRegistry(packs_dir=packs_dir)


def _make_router(registry):
    from gazefy.core.app_router import AppRouter

    return AppRouter(registry)
