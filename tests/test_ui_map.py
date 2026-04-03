"""Tests for UIMap, UIElement, Detection data structures."""

from gazefy.tracker.ui_map import Detection, UIElement, UIMap, UIMapDiff
from gazefy.utils.geometry import Point, Rect


def _el(eid: str, x1: float, y1: float, x2: float, y2: float, cls: str = "button") -> UIElement:
    bbox = Rect(x1, y1, x2, y2)
    return UIElement(
        id=eid, class_id=0, class_name=cls, confidence=0.9,
        bbox=bbox, center=bbox.center,
    )


def test_element_at_returns_smallest():
    dialog = _el("dlg_01", 100, 100, 500, 400, cls="dialog")
    button = _el("btn_01", 200, 200, 300, 240, cls="button")
    uimap = UIMap(elements={"dlg_01": dialog, "btn_01": button})

    hit = uimap.element_at(Point(250, 220))
    assert hit is not None
    assert hit.id == "btn_01"  # Smaller bbox wins


def test_element_at_returns_none_outside():
    btn = _el("btn_01", 10, 10, 50, 50)
    uimap = UIMap(elements={"btn_01": btn})
    assert uimap.element_at(Point(200, 200)) is None


def test_element_at_boundary():
    btn = _el("btn_01", 10, 10, 50, 50)
    uimap = UIMap(elements={"btn_01": btn})
    assert uimap.element_at(Point(10, 10)) is not None
    assert uimap.element_at(Point(50, 50)) is not None


def test_elements_by_class():
    uimap = UIMap(elements={
        "btn_01": _el("btn_01", 100, 10, 200, 40, cls="button"),
        "btn_02": _el("btn_02", 10, 10, 80, 40, cls="button"),
        "inp_01": _el("inp_01", 10, 50, 200, 80, cls="input_field"),
    })

    buttons = uimap.elements_by_class("button")
    assert len(buttons) == 2
    assert buttons[0].id == "btn_02"  # Sorted by position (x1=10 < x1=100)

    inputs = uimap.elements_by_class("input_field")
    assert len(inputs) == 1

    assert uimap.elements_by_class("checkbox") == []


def test_uimap_get():
    btn = _el("btn_01", 10, 10, 50, 50)
    uimap = UIMap(elements={"btn_01": btn})
    assert uimap.get("btn_01") is btn
    assert uimap.get("nonexistent") is None


def test_uimap_properties():
    empty = UIMap()
    assert empty.is_empty
    assert empty.element_count == 0

    uimap = UIMap(elements={"a": _el("a", 0, 0, 10, 10)})
    assert not uimap.is_empty
    assert uimap.element_count == 1


def test_detection_creation():
    det = Detection(class_id=0, class_name="button", confidence=0.95, bbox=Rect(10, 20, 100, 60))
    assert det.class_name == "button"
    assert det.bbox.center == Point(55, 40)


def test_uimap_diff():
    diff = UIMapDiff(added=["btn_01", "btn_02"], removed=["old_01"], generation=5)
    assert len(diff.added) == 2
    assert diff.removed == ["old_01"]
