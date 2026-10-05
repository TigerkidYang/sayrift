"""Window chrome."""

from __future__ import annotations

import contextlib
import ctypes


def dark_title_bar(hwnd: int, dark: bool) -> None:
    value = ctypes.c_int(1 if dark else 0)
    with contextlib.suppress(OSError):  # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Windows 10 2004+ / 11)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)


def caption_colors(hwnd: int, caption: str, text: str, border: str) -> None:
    """Paint the native title bar (Windows 11): colours as #RRGGBB. Earlier Windows ignores the call."""

    def colorref(hex_rgb: str) -> ctypes.c_uint:
        r, g, b = int(hex_rgb[1:3], 16), int(hex_rgb[3:5], 16), int(hex_rgb[5:7], 16)
        return ctypes.c_uint(r | g << 8 | b << 16)

    for attr, value in ((35, caption), (36, text), (34, border)):  # DWMWA_CAPTION/TEXT/BORDER_COLOR
        ref = colorref(value)
        with contextlib.suppress(OSError):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ref), 4)
