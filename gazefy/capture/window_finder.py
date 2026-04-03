"""Find and track macOS windows by name or process using Quartz CGWindowList."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import Quartz

from gazefy.config import CaptureRegion

logger = logging.getLogger(__name__)


@dataclass
class WindowInfo:
    window_id: int
    owner_name: str
    window_name: str
    region: CaptureRegion


def list_windows(*, include_offscreen: bool = False) -> list[WindowInfo]:
    """List all visible on-screen windows."""
    options = Quartz.kCGWindowListOptionOnScreenOnly
    if include_offscreen:
        options = Quartz.kCGWindowListOptionAll

    window_list = Quartz.CGWindowListCopyWindowInfo(
        options | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID,
    )
    results = []
    for w in window_list or []:
        bounds = w.get(Quartz.kCGWindowBounds, {})
        if not bounds:
            continue
        # Skip tiny/invisible windows
        width = int(bounds.get("Width", 0))
        height = int(bounds.get("Height", 0))
        if width < 50 or height < 50:
            continue

        results.append(
            WindowInfo(
                window_id=int(w.get(Quartz.kCGWindowNumber, 0)),
                owner_name=str(w.get(Quartz.kCGWindowOwnerName, "")),
                window_name=str(w.get(Quartz.kCGWindowName, "")),
                region=CaptureRegion(
                    top=int(bounds.get("Y", 0)),
                    left=int(bounds.get("X", 0)),
                    width=width,
                    height=height,
                ),
            )
        )
    return results


def find_window(name: str) -> WindowInfo | None:
    """Find the best window matching name substring.

    Prefers owner_name matches (actual application) over window_name matches
    (could be a browser tab showing the same name). Among matches, picks largest.
    """
    name_lower = name.lower()
    all_windows = list_windows()

    # Prefer owner_name match (e.g. process "gimp" not Chrome tab titled "GIMP")
    owner_matches = [w for w in all_windows if name_lower in w.owner_name.lower()]
    title_matches = [
        w for w in all_windows if name_lower in w.window_name.lower() and w not in owner_matches
    ]
    matches = owner_matches or title_matches
    if not matches:
        return None
    # Pick the largest window (by area) — avoids grabbing tiny tab bars or toolbars
    best = max(matches, key=lambda w: w.region.width * w.region.height)
    logger.info(
        "Found window: '%s' (%s) at (%d, %d) %dx%d [%d matches, picked largest]",
        best.window_name,
        best.owner_name,
        best.region.left,
        best.region.top,
        best.region.width,
        best.region.height,
        len(matches),
    )
    return best


def print_windows() -> None:
    """Print all visible windows for debugging."""
    for w in list_windows():
        print(
            f"  [{w.window_id:5d}] {w.owner_name:30s} | {w.window_name:40s} | "
            f"({w.region.left}, {w.region.top}) {w.region.width}x{w.region.height}"
        )
