#!/usr/bin/env python3
"""Diagnoses whether key injection is actually layout-independent, by
separating two different things that "what key got pressed" can mean:

  - the raw OS keycode -- this is what Unity's KeyCode reads, and should
    stay exactly the same no matter which input language is active.
  - the translated character -- this is what a text editor displays, and
    is *expected* to change with the active input language (that's simply
    what "switching keyboard layout" means). It changing is not a bug and
    is not something key injection can or should override.

The confusion this script exists to clear up: testing by typing into a
text editor can *look* broken under a non-US layout even when the fix in
src/input/keyboard.py is working correctly, because a text editor only
ever shows you the translated character, never the underlying keycode.

Usage: run this once with a US layout active, note the vk values, then
switch your input source (e.g. to Hebrew) and run it again. The vk column
should be identical both times; only the char column should change.
"""
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.input.keyboard import KeyboardController  # noqa: E402

KEYS_TO_TEST = ["q", "w", "e", "r", "t", "s", "space", "left"]


def main() -> None:
    if platform.system() == "Windows":
        print(
            "This diagnostic is for macOS/Linux (it uses pynput's Listener to observe\n"
            "keys). Windows injection already bypasses character translation entirely\n"
            "via raw SendInput virtual-key codes -- see _WindowsBackend in\n"
            "src/input/keyboard.py -- so there's nothing further to check there."
        )
        return

    from pynput import keyboard as pynput_keyboard

    detected = []

    def on_press(key):
        detected.append((getattr(key, "vk", None), getattr(key, "char", None)))

    listener = pynput_keyboard.Listener(on_press=on_press)
    listener.start()

    controller = KeyboardController()

    print("Click into any text field (Terminal, TextEdit, a browser address bar...)")
    print("so this process can observe the key presses it's about to send itself.")
    for i in range(5, 0, -1):
        print(f"Testing in {i}...")
        time.sleep(1)

    print()
    for key in KEYS_TO_TEST:
        detected.clear()
        controller.tap(key, duration=0.1)
        time.sleep(0.2)
        if detected:
            vk, char = detected[0]
            vk_str = hex(vk) if vk is not None else "n/a"
            print(f"  sent {key!r:>8}  ->  vk={vk_str:<6} char={char!r}")
        else:
            print(f"  sent {key!r:>8}  ->  nothing observed (make sure a window is focused)")

    listener.stop()
    print()
    print("'vk' is the raw keycode -- compare this run's values against a run made")
    print("under a different input language (e.g. Hebrew). They should match exactly.")
    print("'char' is the translated character -- it's expected to differ per layout;")
    print("that difference does not affect Unity, which reads keycodes, not characters.")


if __name__ == "__main__":
    main()
