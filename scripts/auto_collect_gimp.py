#!/usr/bin/env python3
"""Auto-collect GIMP screenshots by scripting menu interactions via AppleScript.

Brings GIMP to front, walks through menus/dialogs, captures each state.
No manual operation needed.

Usage:
    python3 scripts/auto_collect_gimp.py
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import mss
import numpy as np
import cv2


def applescript(script: str) -> str:
    """Run an AppleScript and return stdout."""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    return r.stdout.strip()


def activate_gimp() -> None:
    applescript('tell application "GIMP" to activate')
    time.sleep(1)


def capture_screen(region: dict, path: Path) -> None:
    with mss.mss() as sct:
        img = np.array(sct.grab(region))
        bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        cv2.imwrite(str(path), bgr)


def click_menu(menu_name: str, item_name: str | None = None) -> None:
    """Click a GIMP menu, optionally a menu item."""
    if item_name:
        script = f'''
        tell application "System Events"
            tell process "gimp"
                click menu bar item "{menu_name}" of menu bar 1
                delay 0.5
                click menu item "{item_name}" of menu 1 of menu bar item "{menu_name}" of menu bar 1
            end tell
        end tell
        '''
    else:
        script = f'''
        tell application "System Events"
            tell process "gimp"
                click menu bar item "{menu_name}" of menu bar 1
            end tell
        end tell
        '''
    try:
        applescript(script)
    except Exception as e:
        print(f"  Menu click failed: {e}")


def press_escape() -> None:
    applescript('''
    tell application "System Events"
        key code 53
    end tell
    ''')


def main() -> None:
    output_dir = Path("datasets/gimp_demo/auto_collect/images")
    output_dir.mkdir(parents=True, exist_ok=True)

    frame_count = 0

    def snap(label: str) -> None:
        nonlocal frame_count
        # Get GIMP window bounds
        result = applescript('''
        tell application "System Events"
            tell process "gimp"
                set w to front window
                set p to position of w
                set s to size of w
                return (item 1 of p) & "," & (item 2 of p) & "," & (item 1 of s) & "," & (item 2 of s)
            end tell
        end tell
        ''')
        if not result:
            print(f"  [{frame_count}] SKIP {label} — no window bounds")
            return

        parts = [int(x.strip()) for x in result.split(",") if x.strip()]
        # mss uses pixel coords on Retina
        region = {
            "left": parts[0], "top": parts[1],
            "width": parts[2], "height": parts[3],
        }
        name = f"frame_{frame_count:04d}_{label}.png"
        capture_screen(region, output_dir / name)
        print(f"  [{frame_count}] {name}")
        frame_count += 1

    print("Auto-collecting GIMP screenshots...")
    print(f"Output: {output_dir}\n")

    # --- Bring GIMP to front ---
    activate_gimp()
    time.sleep(2)
    snap("main_window")

    # --- Walk through menus ---
    menus = ["File", "Edit", "Select", "View", "Image", "Layer", "Colors",
             "Tools", "Filters", "Windows", "Help"]

    for menu in menus:
        click_menu(menu)
        time.sleep(0.8)
        snap(f"menu_{menu.lower()}")
        press_escape()
        time.sleep(0.3)

    # --- Open some dialogs ---
    dialogs = [
        ("Edit", "Preferences"),
        ("Image", "Canvas Size..."),
        ("Image", "Scale Image..."),
        ("File", "New..."),
    ]
    for menu, item in dialogs:
        click_menu(menu, item)
        time.sleep(1.5)
        snap(f"dialog_{item.lower().replace(' ', '_').replace('.', '')}")
        press_escape()
        time.sleep(0.5)

    # --- Capture tool options by clicking different tools ---
    tool_shortcuts = {
        "paintbrush": "p",
        "eraser": "e",
        "text": "t",
        "selection_rect": "r",
        "selection_ellipse": "e",
        "bucket_fill": "shift+b",
        "gradient": "g",
        "move": "m",
        "crop": "shift+c",
    }
    for tool_name, key in tool_shortcuts.items():
        applescript(f'''
        tell application "System Events"
            keystroke "{key}"
        end tell
        ''')
        time.sleep(0.5)
        snap(f"tool_{tool_name}")

    print(f"\nDone: {frame_count} screenshots saved to {output_dir}")
    print(f"Next: annotate in Label Studio, then run gazefy prep + train")


if __name__ == "__main__":
    main()
