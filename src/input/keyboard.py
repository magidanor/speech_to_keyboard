"""Cross-platform key press injection aimed at games, not text fields.

Unity's `KeyCode` (both the legacy Input Manager and the new Input System)
identifies a key by a fixed virtual-key/keycode value tied to a physical
position on a reference US QWERTY keyboard - not by "whatever character is
currently printed on that key." That identity does not change when the
user's active input language changes.

Character-based injection does not have that property: asking the OS to
"produce the character 'q'" (or injecting the scan code of the physical Q
position and letting the OS translate it) is resolved through the OS's
*currently active keyboard layout*. On a US layout that happens to agree
with what we want, but it silently breaks under other layouts - e.g. the
standard Hebrew layout maps that same physical position to "/", so a config
key of "q" would show up in the game as "/" whenever Hebrew input is active.

To avoid that, this module injects the raw virtual-key code (Windows) or
virtual keycode (macOS) directly, bypassing character/layout translation
entirely, so a given canonical key always maps to the same Unity KeyCode
no matter what input language is active elsewhere on the machine.

Linux/X11 is the exception: pynput's X11 backend only exposes character-
based key synthesis, so `key_l`-style layout independence isn't available
there. That's an acceptable gap since Windows and macOS are this project's
supported platforms.

Canonical key names used throughout this project (and in config.yaml):
  left, right, up, down, space, enter, esc, tab,
  shift_l, shift_r, ctrl_l, ctrl_r, alt_l, alt_r,
  single letters (a-z), digits (0-9), f1-f12.
"""
import platform
import time

_SYSTEM = platform.system()

# Windows virtual-key codes for the non-alphanumeric canonical keys.
# Letters/digits are handled separately below: on Windows, VK_A-VK_Z and
# VK_0-VK_9 conveniently equal the ASCII codes of the uppercase letter/digit.
_WINDOWS_VK = {
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "space": 0x20,
    "enter": 0x0D,
    "esc": 0x1B,
    "tab": 0x09,
    "shift_l": 0xA0,
    "shift_r": 0xA1,
    "ctrl_l": 0xA2,
    "ctrl_r": 0xA3,
    "alt_l": 0xA4,
    "alt_r": 0xA5,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}

# macOS virtual keycodes (the standard Carbon/HIToolbox table), covering
# every canonical key including letters/digits, since macOS doesn't have a
# tidy ASCII-aligned range like Windows does.
_MAC_VK = {
    "a": 0x00, "b": 0x0B, "c": 0x08, "d": 0x02, "e": 0x0E, "f": 0x03, "g": 0x05,
    "h": 0x04, "i": 0x22, "j": 0x26, "k": 0x28, "l": 0x25, "m": 0x2E, "n": 0x2D,
    "o": 0x1F, "p": 0x23, "q": 0x0C, "r": 0x0F, "s": 0x01, "t": 0x11, "u": 0x20,
    "v": 0x09, "w": 0x0D, "x": 0x07, "y": 0x10, "z": 0x06,
    "0": 0x1D, "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "5": 0x17,
    "6": 0x16, "7": 0x1A, "8": 0x1C, "9": 0x19,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
    "space": 0x31, "enter": 0x24, "esc": 0x35, "tab": 0x30,
    "shift_l": 0x38, "shift_r": 0x3C,
    "ctrl_l": 0x3B, "ctrl_r": 0x3E,
    "alt_l": 0x3A, "alt_r": 0x3D,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60, "f6": 0x61,
    "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
}  # fmt: skip


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


def _windows_vk_for(key: str) -> int:
    name = key.lower()
    if name in _WINDOWS_VK:
        return _WINDOWS_VK[name]
    if len(name) == 1 and (name.isalpha() or name.isdigit()):
        return ord(name.upper())
    raise ValueError(f"Unrecognized key name: {key!r}")


class _WindowsBackend:
    """Injects key events by explicit virtual-key code via SendInput
    (dwFlags=0, no KEYEVENTF_SCANCODE), so the OS delivers exactly the VK we
    specify without re-translating it through the active keyboard layout.
    """

    _INPUT_KEYBOARD = 1
    _KEYEVENTF_KEYUP = 0x0002

    def __init__(self):
        import ctypes

        self._ctypes = ctypes
        user32 = ctypes.windll.user32

        class _KeyBdInput(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class _InputUnion(ctypes.Union):
            _fields_ = [("ki", _KeyBdInput)]

        class _Input(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("ii", _InputUnion)]

        self._KeyBdInput = _KeyBdInput
        self._InputUnion = _InputUnion
        self._Input = _Input
        self._user32 = user32

    def _send(self, vk: int, key_up: bool) -> None:
        ctypes = self._ctypes
        extra = ctypes.c_ulong(0)
        flags = self._KEYEVENTF_KEYUP if key_up else 0
        ki = self._KeyBdInput(vk, 0, flags, 0, ctypes.pointer(extra))
        packet = self._Input(self._INPUT_KEYBOARD, self._InputUnion(ki=ki))
        self._user32.SendInput(1, ctypes.pointer(packet), ctypes.sizeof(packet))

    def press(self, key: str) -> None:
        self._send(_windows_vk_for(key), key_up=False)

    def release(self, key: str) -> None:
        self._send(_windows_vk_for(key), key_up=True)


class _PynputBackend:
    """macOS: injects by explicit virtual keycode (layout-independent, see
    module docstring). Linux/X11: falls back to pynput's character-based
    resolution, since its X11 backend has no layout-independent primitive.
    """

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
        self._is_mac = _SYSTEM == "Darwin"

    def _resolve(self, key: str):
        name = key.lower()

        if self._is_mac:
            if name in _MAC_VK:
                return self._KeyCode.from_vk(_MAC_VK[name])
            raise ValueError(f"Unrecognized key name: {key!r}")

        # Linux/X11 character-based fallback.
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
