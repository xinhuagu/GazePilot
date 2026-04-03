#!/usr/bin/env python3
"""Dump macOS Accessibility tree for an application.

Extracts all UI elements with their names, roles, and positions.
This only works for LOCAL applications — VDI apps have no accessibility tree.

Usage:
    python3 scripts/ax_dump.py gimp
"""

from __future__ import annotations

import sys

import AppKit
from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
)


def get_attr(el, attr):
    err, val = AXUIElementCopyAttributeValue(el, attr, None)
    return val if err == 0 else None


def unpack_point(val) -> tuple[int, int]:
    """Unpack AXPosition value to (x, y)."""
    try:
        return int(val.x), int(val.y)
    except AttributeError:
        pass
    # Try string representation parsing as fallback
    s = str(val)
    # Format: "x:123.0 y:456.0" or similar
    try:
        import re

        nums = re.findall(r"[-\d.]+", s)
        if len(nums) >= 2:
            return int(float(nums[0])), int(float(nums[1]))
    except Exception:
        pass
    return 0, 0


def unpack_size(val) -> tuple[int, int]:
    """Unpack AXSize value to (w, h)."""
    try:
        return int(val.width), int(val.height)
    except AttributeError:
        pass
    s = str(val)
    try:
        import re

        nums = re.findall(r"[-\d.]+", s)
        if len(nums) >= 2:
            return int(float(nums[0])), int(float(nums[1]))
    except Exception:
        pass
    return 0, 0


def dump_tree(el, depth=0, max_depth=5, results=None):
    if results is None:
        results = []
    if depth > max_depth:
        return results

    role = get_attr(el, "AXRole") or ""
    title = get_attr(el, "AXTitle") or ""
    desc = get_attr(el, "AXDescription") or ""
    help_text = get_attr(el, "AXHelp") or ""
    pos = get_attr(el, "AXPosition")
    size = get_attr(el, "AXSize")

    label = title or desc or help_text
    x, y = unpack_point(pos) if pos else (0, 0)
    w, h = unpack_size(size) if size else (0, 0)

    if w > 0 and h > 0 and label:
        indent = "  " * depth
        print(f"{indent}{role:20s} [{w:4d}x{h:<4d}] ({x:4d},{y:4d})  \"{label}\"")
        results.append({
            "role": role,
            "label": label,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
        })

    children = get_attr(el, "AXChildren")
    if children:
        for child in children:
            dump_tree(child, depth + 1, max_depth, results)

    return results


def find_pid(app_name: str) -> int | None:
    apps = AppKit.NSWorkspace.sharedWorkspace().runningApplications()
    for app in apps:
        if app_name.lower() in app.localizedName().lower():
            return app.processIdentifier()
    return None


def main():
    app_name = sys.argv[1] if len(sys.argv) > 1 else "gimp"

    pid = find_pid(app_name)
    if pid is None:
        print(f"Application '{app_name}' not found running.")
        sys.exit(1)

    print(f"Application: {app_name} (PID {pid})")
    print(f"{'Role':22s} {'Size':11s} {'Position':12s}  Label")
    print("-" * 80)

    app_ref = AXUIElementCreateApplication(pid)
    results = dump_tree(app_ref)

    print(f"\n{len(results)} labeled elements found.")
    print("\nNOTE: This only works for LOCAL apps. VDI/remote apps need")
    print("CLIP matching or manual icon labeling instead.")


if __name__ == "__main__":
    main()
