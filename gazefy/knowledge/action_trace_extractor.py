"""ActionTraceExtractor: events.jsonl + video -> grounded action trace.

Turns a recorded user demonstration into a structured, element-grounded
action trace by aligning mouse events to video frames and detecting
which UI element each action targeted.

Output: recordings/<session>/action_trace.json
"""

from __future__ import annotations

import bisect
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class ActionStep:
    """A single grounded action in the trace."""

    timestamp: float
    action: str  # click, double_click, scroll, type, drag
    target_class: str = ""
    target_text: str = ""
    target_semantic_id: str = ""
    target_bbox: list[float] = field(default_factory=list)  # [x1,y1,x2,y2] normalized
    screen_x: int = 0
    screen_y: int = 0
    frame_index: int = -1
    details: dict = field(default_factory=dict)  # scroll_dy, typed_text, etc.
    screen_changed: bool = False
    diff_score: float = 0.0


def extract_action_trace(
    session_dir: Path,
    pack_dir: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> list[ActionStep]:
    """Extract grounded action trace from a recording session.

    Args:
        session_dir: Path to recordings/<session>/ containing events.jsonl + video.mp4
        pack_dir: Pack directory (for model + ontology). If None, inferred from session_dir.
        on_progress: Progress callback

    Returns:
        List of ActionStep, also written to session_dir/action_trace.json
    """
    import cv2

    def log(msg: str) -> None:
        if on_progress:
            on_progress(msg)
        logger.info(msg)

    # Validate inputs
    events_path = session_dir / "events.jsonl"
    video_path = session_dir / "video.mp4"
    if not events_path.exists():
        log(f"No events.jsonl in {session_dir}")
        return []
    if not video_path.exists():
        log(f"No video.mp4 in {session_dir}")
        return []

    # Load events
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line.strip()]
    log(f"Step 1: Loaded {len(events)} events")

    # Load frame times
    frame_times_path = session_dir / "frame_times.json"
    frame_windows_path = session_dir / "frame_windows.json"
    frame_times = json.loads(frame_times_path.read_text()) if frame_times_path.exists() else []
    frame_windows = (
        json.loads(frame_windows_path.read_text()) if frame_windows_path.exists() else []
    )

    # Extract actionable events (clicks + scrolls, ignore moves)
    actions_raw = _extract_actions(events)
    log(f"Step 2: {len(actions_raw)} actionable events (clicks + scrolls)")

    if not actions_raw:
        log("No actionable events found")
        return []

    # Infer pack_dir
    if pack_dir is None:
        # session_dir is packs/<app>/recordings/<session>
        pack_dir = session_dir.parent.parent

    # Load detector if model available
    detector = None
    if (pack_dir / "model.pt").exists():
        from gazefy.core.application_pack import ApplicationPack
        from gazefy.detection.detector import UIDetector

        pack = ApplicationPack.load(pack_dir)
        detector = UIDetector(pack)
        detector.load_model()
        log("  Loaded YOLO model for element grounding")

    # Load ontology resolver if available
    resolver = None
    ontology_path = pack_dir / "ontology.yaml"
    if ontology_path.exists():
        from gazefy.knowledge.ontology_resolver import OntologyResolver

        resolver = OntologyResolver.load(ontology_path)
        log(f"  Loaded ontology ({len(resolver)} entries)")

    # Load OCR for text extraction
    from gazefy.detection.ocr import ElementOCR

    ocr = ElementOCR()

    # Open video
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 10
    log(f"Step 3: Processing video ({total_frames} frames, {fps:.1f} fps)")

    # Process each action
    trace: list[ActionStep] = []
    prev_frame = None

    for i, action in enumerate(actions_raw):
        t = action["t"]

        # Find nearest frame
        if frame_times:
            frame_idx = bisect.bisect_left(frame_times, t)
            frame_idx = min(frame_idx, len(frame_times) - 1)
        else:
            frame_idx = int(t * fps)

        # Read frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue

        h, w = frame.shape[:2]

        # Convert screen coords to frame coords
        win = frame_windows[frame_idx] if frame_idx < len(frame_windows) else {}
        win_left = win.get("left", 0)
        win_top = win.get("top", 0)
        fx = action["x"] - win_left
        fy = action["y"] - win_top

        # Detect elements in this frame
        target_class = ""
        target_text = ""
        target_semantic_id = ""
        target_bbox: list[float] = []

        if detector:
            frame_bgra = cv2.cvtColor(frame, cv2.COLOR_BGR2BGRA)
            detections = detector.detect(frame_bgra)

            # Find element at click position
            best_det = None
            best_area = float("inf")
            for det in detections:
                bx1, by1, bx2, by2 = det.bbox.x1, det.bbox.y1, det.bbox.x2, det.bbox.y2
                if bx1 <= fx <= bx2 and by1 <= fy <= by2:
                    area = (bx2 - bx1) * (by2 - by1)
                    if area < best_area:
                        best_area = area
                        best_det = det

            if best_det:
                target_class = best_det.class_name
                bx1, by1 = best_det.bbox.x1, best_det.bbox.y1
                bx2, by2 = best_det.bbox.x2, best_det.bbox.y2
                target_bbox = [
                    round(bx1 / w, 4),
                    round(by1 / h, 4),
                    round(bx2 / w, 4),
                    round(by2 / h, 4),
                ]

                # OCR the element
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                text = ocr.read_element_text(frame_rgb, (bx1, by1, bx2, by2))
                if text:
                    target_text = text

                # Resolve semantic ID
                if resolver and target_text:
                    from gazefy.tracker.ui_map import UIElement
                    from gazefy.utils.geometry import Point, Rect

                    el = UIElement(
                        id="tmp",
                        class_id=best_det.class_id,
                        class_name=best_det.class_name,
                        confidence=best_det.confidence,
                        bbox=Rect(bx1, by1, bx2, by2),
                        center=Point((bx1 + bx2) / 2, (by1 + by2) / 2),
                        text=target_text,
                    )
                    entry = resolver.resolve(el)
                    if entry:
                        target_semantic_id = entry.semantic_id

        # Detect screen change (compare with next frame)
        screen_changed = False
        diff_score = 0.0
        if prev_frame is not None:
            diff_score = _frame_diff(prev_frame, frame)
            screen_changed = diff_score > 0.05
        prev_frame = frame.copy()

        step = ActionStep(
            timestamp=round(t, 3),
            action=action["action_type"],
            target_class=target_class,
            target_text=target_text,
            target_semantic_id=target_semantic_id,
            target_bbox=target_bbox,
            screen_x=action["x"],
            screen_y=action["y"],
            frame_index=frame_idx,
            details=action.get("details", {}),
            screen_changed=screen_changed,
            diff_score=round(diff_score, 4),
        )
        trace.append(step)

        semantic_str = f" [{target_semantic_id}]" if target_semantic_id else ""
        log(
            f"  [{i + 1}/{len(actions_raw)}] t={t:.1f}s {action['action_type']} "
            f'-> {target_class} "{target_text}"{semantic_str}'
        )

    cap.release()

    # Write output
    output_path = session_dir / "action_trace.json"
    output_data = [asdict(step) for step in trace]
    output_path.write_text(json.dumps(output_data, indent=2))
    log(f"Step 4: Written {len(trace)} actions to {output_path.name}")

    return trace


def _extract_actions(events: list[dict]) -> list[dict]:
    """Extract actionable events from raw event stream.

    Collapses press+release into click, detects double clicks, etc.
    """
    actions = []
    i = 0
    while i < len(events):
        ev = events[i]

        if ev.get("click") and ev.get("action") == "press":
            # Scan forward for matching release (no fixed window limit)
            release = None
            release_idx = -1
            for j in range(i + 1, len(events)):
                if events[j].get("click") == ev["click"] and events[j].get("action") == "release":
                    release = events[j]
                    release_idx = j
                    break
                # Give up after 2 seconds
                if events[j]["t"] - ev["t"] > 2.0:
                    break

            if release:
                dt = release["t"] - ev["t"]
                if dt < 0.5:
                    action_type = "click"
                    # Check for double click: another press within 0.5s after release
                    for k in range(release_idx + 1, len(events)):
                        nxt = events[k]
                        if nxt["t"] - ev["t"] > 0.5:
                            break
                        if nxt.get("click") == ev["click"] and nxt.get("action") == "press":
                            action_type = "double_click"
                            # Consume the second press+release pair
                            for m in range(k + 1, len(events)):
                                if (
                                    events[m].get("click") == ev["click"]
                                    and events[m].get("action") == "release"
                                ):
                                    i = m  # Skip past second release
                                    break
                            break
                else:
                    action_type = "drag"

                actions.append(
                    {
                        "t": ev["t"],
                        "x": ev["x"],
                        "y": ev["y"],
                        "action_type": action_type,
                        "details": {"button": ev["click"]},
                    }
                )

        elif ev.get("scroll"):
            dy = ev.get("dy", 0)
            if dy:
                actions.append(
                    {
                        "t": ev["t"],
                        "x": ev["x"],
                        "y": ev["y"],
                        "action_type": "scroll",
                        "details": {"dy": dy},
                    }
                )

        i += 1

    return actions


def _frame_diff(frame_a, frame_b) -> float:
    """Compute normalized frame difference (0-1)."""
    import cv2
    import numpy as np

    a_gray = cv2.cvtColor(frame_a, cv2.COLOR_BGR2GRAY)
    b_gray = cv2.cvtColor(frame_b, cv2.COLOR_BGR2GRAY)
    # Resize for speed
    a_small = cv2.resize(a_gray, (160, 120))
    b_small = cv2.resize(b_gray, (160, 120))
    diff = np.abs(a_small.astype(float) - b_small.astype(float))
    return float(diff.mean() / 255.0)
