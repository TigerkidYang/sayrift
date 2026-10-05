"""Virtual-key codes and the key names accepted in config.toml ([hotkeys] section).

Kept free of Win32 imports so the hotkey logic and config parsing are testable anywhere.
"""

from __future__ import annotations

VK_BACK, VK_TAB, VK_RETURN = 0x08, 0x09, 0x0D
VK_CAPITAL, VK_ESCAPE, VK_SPACE = 0x14, 0x1B, 0x20
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_LSHIFT, VK_RSHIFT, VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU = 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5

KEY_NAMES: dict[str, int] = {
    "rightalt": VK_RMENU,
    "leftalt": VK_LMENU,
    "rightctrl": VK_RCONTROL,
    "leftctrl": VK_LCONTROL,
    "rightshift": VK_RSHIFT,
    "leftshift": VK_LSHIFT,
    "leftwin": VK_LWIN,
    "rightwin": VK_RWIN,
    "space": VK_SPACE,
    "capslock": VK_CAPITAL,
    "escape": VK_ESCAPE,
    "esc": VK_ESCAPE,
    "tab": VK_TAB,
    "enter": VK_RETURN,
    "backspace": VK_BACK,
    **{f"f{n}": 0x70 + n - 1 for n in range(1, 25)},  # F1..F24
}


def parse_key(name: str) -> int:
    """'RightAlt' / 'right_alt' / 'F13' -> virtual-key code."""
    key = name.strip().lower().replace("_", "").replace("-", "").replace(" ", "")
    if key in KEY_NAMES:
        return KEY_NAMES[key]
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())  # VK codes for 0-9 and A-Z are their ASCII codes
    raise ValueError(f"unknown key name {name!r}; known: {sorted(KEY_NAMES)} or a single letter/digit")


# Canonical config names for keys the settings page can record, and how they are shown.
_CANONICAL = {
    VK_RMENU: "RightAlt", VK_LMENU: "LeftAlt", VK_RCONTROL: "RightCtrl", VK_LCONTROL: "LeftCtrl",
    VK_RSHIFT: "RightShift", VK_LSHIFT: "LeftShift", VK_LWIN: "LeftWin", VK_RWIN: "RightWin",
    VK_SPACE: "Space", VK_CAPITAL: "CapsLock", VK_ESCAPE: "Escape", VK_TAB: "Tab", VK_RETURN: "Enter",
    VK_BACK: "Backspace", **{0x70 + n - 1: f"F{n}" for n in range(1, 25)},
}  # fmt: skip


def name_for(vk: int) -> str | None:
    """Virtual-key code -> config name ('RightAlt', 'F13', 'A'); None for keys we don't bind."""
    if vk in _CANONICAL:
        return _CANONICAL[vk]
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    return None


def display(name: str) -> str:
    """Config name -> label for a key cap: 'RightAlt' -> 'Right Alt'."""
    vk = parse_key(name)
    canonical = name_for(vk) or name
    for side in ("Right", "Left"):
        if canonical.startswith(side) and len(canonical) > len(side):
            return f"{side} {canonical[len(side) :]}"
    return canonical
