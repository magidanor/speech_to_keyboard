#!/usr/bin/env python3
"""Standalone sanity check for keyboard injection, independent of speech recognition.

Focus your Unity game (or a text editor, to start) and run this script --
it presses a few keys after a short countdown so you can confirm the target
window actually registers them before wiring up speech recognition.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.input.keyboard import KeyboardController  # noqa: E402


def main() -> None:
    controller = KeyboardController()
    keys_to_test = ["left", "right", "space"]

    print("Click into the target window (game / text editor).")
    for i in range(5, 0, -1):
        print(f"Testing in {i}...")
        time.sleep(1)

    for key in keys_to_test:
        print(f"Pressing {key!r}")
        controller.tap(key, duration=0.1)
        time.sleep(0.5)

    print("Done. Did the target window register left / right / space?")


if __name__ == "__main__":
    main()
