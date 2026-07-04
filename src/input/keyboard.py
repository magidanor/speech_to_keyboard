"""Cross-platform key press injection aimed at games, not just text fields.

On Windows we use `pydirectinput`, which injects scan-code-based SendInput
events. Many games -- including Unity's newer Input System, which reads raw
input rather than the classic WM_KEYDOWN message queue -- only respond
reliably to that style of injection; higher-level virtual-key events that
some other libraries send are silently ignored by those games.

On macOS/Linux we use `pynput`, which drives the OS-level Quartz/X11 event
APIs that Unity's input backends do listen to on those platforms.

Canonical key names used throughout this project (and in config.yaml):
  left, right, up, down, space, enter, esc, tab,
  shift_l, shift_r, ctrl_l, ctrl_r, alt_l, alt_r,
  single letters (a-z), digits (0-9), f1-f12.
"""
import platform
import time

_SYSTEM = platform.system()


class KeyboardController:
    def __init__(self):
        self._backend = _WindowsBackend() if _SYSTEM == "Windows" else _PynputBackend()

    def press(self, key: str) -> None:
        self._backend.press(key)

    def release(self, key: str) -> None:
        self._backend.release(key)

    def tap(self, key: str, duration: float = 0.05) -> None:
        self.press(key)
        time.sleep(duration)
        self.release(key)


class _WindowsBackend:
    _KEY_MAP = {
        "shift_l": "shiftleft",
        "shift_r": "shiftright",
        "ctrl_l": "ctrlleft",
        "ctrl_r": "ctrlright",
        "alt_l": "altleft",
        "alt_r": "altright",
    }

    def __init__(self):
        import pydirectinput

        pydirectinput.FAILSAFE = False
        # pydirectinput defaults to a 0.1s pause after every call, inherited
        # from pyautogui -- that alone would blow most of our latency budget.
        pydirectinput.PAUSE = 0
        self._lib = pydirectinput

    def _resolve(self, key: str) -> str:
        name = key.lower()
        return self._KEY_MAP.get(name, name)

    def press(self, key: str) -> None:
        self._lib.keyDown(self._resolve(key))

    def release(self, key: str) -> None:
        self._lib.keyUp(self._resolve(key))


class _PynputBackend:
    _SPECIAL = {
        "left": "left",
        "right": "right",
        "up": "up",
        "down": "down",
        "space": "space",
        "enter": "enter",
        "esc": "esc",
        "escape": "esc",
        "tab": "tab",
        "shift_l": "shift_l",
        "shift_r": "shift_r",
        "ctrl_l": "ctrl_l",
        "ctrl_r": "ctrl_r",
        "alt_l": "alt_l",
        "alt_r": "alt_r",
    }

    def __init__(self):
        from pynput.keyboard import Controller, Key, KeyCode

        self._Key = Key
        self._KeyCode = KeyCode
        self._controller = Controller()

    def _resolve(self, key: str):
        name = key.lower()
        if name in self._SPECIAL:
            return getattr(self._Key, self._SPECIAL[name])
        if len(name) == 1:
            return self._KeyCode.from_char(name)
        if hasattr(self._Key, name):  # f1..f12, etc.
            return getattr(self._Key, name)
        raise ValueError(f"Unrecognized key name: {key!r}")

    def press(self, key: str) -> None:
        self._controller.press(self._resolve(key))

    def release(self, key: str) -> None:
        self._controller.release(self._resolve(key))
