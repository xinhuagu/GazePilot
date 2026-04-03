"""Tests for CoordinateTransform: pixel ↔ screen conversion."""

from gazefy.actions.coordinate_transform import CoordinateTransform
from gazefy.config import CaptureRegion
from gazefy.utils.geometry import Point


def test_pixel_to_screen_no_offset():
    t = CoordinateTransform(region=CaptureRegion(top=0, left=0, width=1920, height=1080), retina_scale=2.0)
    result = t.pixel_to_screen(Point(200, 100))
    assert result.x == 100.0  # 200 / 2
    assert result.y == 50.0   # 100 / 2


def test_pixel_to_screen_with_offset():
    t = CoordinateTransform(region=CaptureRegion(top=50, left=100, width=800, height=600), retina_scale=2.0)
    result = t.pixel_to_screen(Point(200, 100))
    assert result.x == 200.0  # 200/2 + 100
    assert result.y == 100.0  # 100/2 + 50


def test_screen_to_pixel_no_offset():
    t = CoordinateTransform(region=CaptureRegion(top=0, left=0, width=1920, height=1080), retina_scale=2.0)
    result = t.screen_to_pixel(Point(100, 50))
    assert result.x == 200.0  # 100 * 2
    assert result.y == 100.0  # 50 * 2


def test_screen_to_pixel_with_offset():
    t = CoordinateTransform(region=CaptureRegion(top=50, left=100, width=800, height=600), retina_scale=2.0)
    result = t.screen_to_pixel(Point(200, 100))
    assert result.x == 200.0  # (200 - 100) * 2
    assert result.y == 100.0  # (100 - 50) * 2


def test_roundtrip():
    t = CoordinateTransform(region=CaptureRegion(top=33, left=0, width=1728, height=1084), retina_scale=2.0)
    pixel = Point(500, 300)
    screen = t.pixel_to_screen(pixel)
    back = t.screen_to_pixel(screen)
    assert abs(back.x - pixel.x) < 0.01
    assert abs(back.y - pixel.y) < 0.01


def test_retina_1x():
    t = CoordinateTransform(region=CaptureRegion(top=0, left=0, width=1920, height=1080), retina_scale=1.0)
    result = t.pixel_to_screen(Point(200, 100))
    assert result.x == 200.0  # No scaling
    assert result.y == 100.0
