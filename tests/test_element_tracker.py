"""Tests for ElementTracker: IoU matching, stability, rebuild."""

from gazefy.capture.change_detector import ChangeLevel, ChangeResult
from gazefy.tracker.element_tracker import ElementTracker
from gazefy.tracker.ui_map import Detection
from gazefy.utils.geometry import Rect


def _det(cls: str, x1: float, y1: float, x2: float, y2: float, conf: float = 0.9) -> Detection:
    return Detection(class_id=0, class_name=cls, confidence=conf, bbox=Rect(x1, y1, x2, y2))


def _major():
    return ChangeResult(changed=True, change_level=ChangeLevel.MAJOR)


def _minor():
    return ChangeResult(changed=True, change_level=ChangeLevel.MINOR)


def test_first_detection_creates_elements():
    tracker = ElementTracker(min_stability=1)
    dets = [_det("button", 10, 10, 100, 50), _det("input", 10, 60, 200, 90)]
    diff = tracker.update(dets, _major(), frame_width=800, frame_height=600)

    assert len(diff.added) == 2
    assert tracker.current_map.element_count == 2


def test_stability_filtering():
    tracker = ElementTracker(min_stability=2)
    dets = [_det("button", 10, 10, 100, 50)]

    # First frame: element exists but not yet stable
    tracker.update(dets, _major(), frame_width=800, frame_height=600)
    assert tracker.current_map.element_count == 0  # Not stable yet

    # Second frame: same detection → stability=2 → published
    tracker.update(dets, _minor(), frame_width=800, frame_height=600)
    assert tracker.current_map.element_count == 1


def test_iou_matching_preserves_id():
    tracker = ElementTracker(min_stability=1, iou_threshold=0.3)
    dets1 = [_det("button", 10, 10, 100, 50)]
    tracker.update(dets1, _major(), frame_width=800, frame_height=600)
    first_id = list(tracker.current_map.elements.keys())[0]

    # Slightly moved detection — should match by IoU
    dets2 = [_det("button", 12, 12, 102, 52)]
    tracker.update(dets2, _minor(), frame_width=800, frame_height=600)

    assert first_id in tracker.current_map.elements
    assert tracker.current_map.elements[first_id].stability == 2


def test_major_change_rebuilds():
    tracker = ElementTracker(min_stability=1)

    dets1 = [_det("button", 10, 10, 100, 50)]
    tracker.update(dets1, _major(), frame_width=800, frame_height=600)
    old_ids = set(tracker.current_map.elements.keys())

    # Major change with completely different detections
    dets2 = [_det("dialog", 200, 200, 600, 400)]
    diff = tracker.update(dets2, _major(), frame_width=800, frame_height=600)

    new_ids = set(tracker.current_map.elements.keys())
    assert old_ids != new_ids
    assert len(diff.removed) > 0
    assert len(diff.added) > 0


def test_stale_elements_removed():
    tracker = ElementTracker(min_stability=1, stale_after_frames=2)

    dets = [_det("button", 10, 10, 100, 50)]
    tracker.update(dets, _major(), frame_width=800, frame_height=600)

    # 3 frames with no matching detection → stale → removed
    for _ in range(3):
        tracker.update([], _minor(), frame_width=800, frame_height=600)

    assert tracker.current_map.element_count == 0


def test_different_classes_not_matched():
    tracker = ElementTracker(min_stability=1, iou_threshold=0.3)

    dets1 = [_det("button", 10, 10, 100, 50)]
    tracker.update(dets1, _major(), frame_width=800, frame_height=600)
    first_id = list(tracker.current_map.elements.keys())[0]

    # Same bbox but different class → new element, not matched
    dets2 = [_det("input", 10, 10, 100, 50)]
    tracker.update(dets2, _minor(), frame_width=800, frame_height=600)

    # Should have the new element (input) and possibly the old one (stale)
    classes = {e.class_name for e in tracker.current_map.elements.values()}
    assert "input" in classes


def test_multiple_elements_tracked():
    tracker = ElementTracker(min_stability=1)
    dets = [
        _det("button", 10, 10, 100, 40),
        _det("button", 110, 10, 200, 40),
        _det("input", 10, 50, 300, 80),
    ]
    tracker.update(dets, _major(), frame_width=800, frame_height=600)
    assert tracker.current_map.element_count == 3
