"""Tests for UIMap → text serialization."""

from gazefy.cursor.cursor_monitor import CursorState
from gazefy.llm.formatters import format_state
from gazefy.tracker.ui_map import UIElement, UIMap
from gazefy.utils.geometry import Point, Rect


def _make_map() -> UIMap:
    btn = UIElement(
        id="btn_01", class_id=0, class_name="button", confidence=0.95,
        bbox=Rect(100, 50, 200, 80), center=Point(150, 65), text="Save",
    )
    inp = UIElement(
        id="inp_01", class_id=2, class_name="input_field", confidence=0.88,
        bbox=Rect(100, 100, 400, 130), center=Point(250, 115),
    )
    return UIMap(
        elements={"btn_01": btn, "inp_01": inp},
        frame_width=800, frame_height=600, generation=5,
    )


def test_format_basic():
    text = format_state(_make_map())
    assert "SCREEN STATE" in text
    assert "generation=5" in text
    assert "elements=2" in text
    assert "btn_01" in text
    assert '"Save"' in text
    assert "input_field" in text


def test_format_empty_map():
    text = format_state(UIMap())
    assert "ELEMENTS:" in text
    assert "(none detected)" in text


def test_format_with_cursor_on_element():
    uimap = _make_map()
    cursor = CursorState(
        screen_position=Point(150, 65),
        frame_position=Point(300, 130),
        current_element=uimap.elements["btn_01"],
        dwell_time_ms=500,
    )
    text = format_state(uimap, cursor=cursor)
    assert "**CURSOR**" in text
    assert "Save" in text


def test_format_with_cursor_no_element():
    cursor = CursorState(
        screen_position=Point(500, 500),
        frame_position=Point(1000, 1000),
    )
    text = format_state(UIMap(), cursor=cursor)
    assert "not on any element" in text


def test_format_with_context():
    text = format_state(_make_map(), screen_context="Export Dialog")
    assert "Context: Export Dialog" in text


def test_format_resolution():
    uimap = UIMap(frame_width=1920, frame_height=1080)
    text = format_state(uimap)
    assert "1920x1080" in text
