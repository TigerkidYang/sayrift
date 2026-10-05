"""ctypes declarations for the Win32 APIs the app uses.

Every function gets explicit argtypes/restype: without them ctypes passes handles and
LPARAMs as 32-bit C ints, which works until a pointer happens not to fit.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes as w

from ..keys import VK_LCONTROL, VK_LMENU, VK_LSHIFT, VK_LWIN, VK_RCONTROL, VK_RMENU, VK_RSHIFT, VK_RWIN

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, w.WPARAM, w.LPARAM)

# Marks input we inject ourselves (KEYBDINPUT.dwExtraInfo) so our own hook lets it through.
INJECT_TAG = 0x4C54_5950  # "LTYP"

# --- constants -------------------------------------------------------------------------------

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_QUIT = 0x0012
WM_TIMER = 0x0113
WM_APP = 0x8000
WM_SYSCOMMAND = 0x0112
WM_PASTE = 0x0302
LLKHF_EXTENDED = 0x01
LLKHF_INJECTED = 0x10

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
MAPVK_VK_TO_VSC = 0

VK_SHIFT, VK_CONTROL, VK_MENU, VK_INSERT, VK_V = 0x10, 0x11, 0x12, 0x2D, 0x56

MODIFIER_VKS = (VK_LSHIFT, VK_RSHIFT, VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU, VK_LWIN, VK_RWIN)
# Right-hand modifiers and the Windows keys are "extended" keys for SendInput.
EXTENDED_VKS = frozenset({VK_RCONTROL, VK_RMENU, VK_LWIN, VK_RWIN, VK_INSERT})

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TokenElevation = 20

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# --- structures ------------------------------------------------------------------------------


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", w.DWORD),
        ("scanCode", w.DWORD),
        ("flags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", w.WORD),
        ("wScan", w.WORD),
        ("dwFlags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", w.LONG),
        ("dy", w.LONG),
        ("mouseData", w.DWORD),
        ("dwFlags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", w.DWORD), ("u", _INPUTUNION)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD),
        ("flags", w.DWORD),
        ("hwndActive", w.HWND),
        ("hwndFocus", w.HWND),
        ("hwndCapture", w.HWND),
        ("hwndMenuOwner", w.HWND),
        ("hwndMoveSize", w.HWND),
        ("hwndCaret", w.HWND),
        ("rcCaret", w.RECT),
    ]


class TOKEN_ELEVATION(ctypes.Structure):
    _fields_ = [("TokenIsElevated", w.DWORD)]


# --- prototypes ------------------------------------------------------------------------------


def _proto(dll: ctypes.WinDLL, name: str, restype, *argtypes) -> None:
    fn = getattr(dll, name)
    fn.restype = restype
    fn.argtypes = argtypes


_proto(user32, "SetWindowsHookExW", w.HHOOK, ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD)
_proto(user32, "UnhookWindowsHookEx", w.BOOL, w.HHOOK)
_proto(user32, "CallNextHookEx", LRESULT, w.HHOOK, ctypes.c_int, w.WPARAM, w.LPARAM)
_proto(user32, "GetMessageW", w.BOOL, ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
_proto(user32, "TranslateMessage", w.BOOL, ctypes.POINTER(w.MSG))
_proto(user32, "DispatchMessageW", LRESULT, ctypes.POINTER(w.MSG))
_proto(user32, "PostThreadMessageW", w.BOOL, w.DWORD, w.UINT, w.WPARAM, w.LPARAM)
_proto(user32, "SetTimer", ctypes.c_size_t, w.HWND, ctypes.c_size_t, w.UINT, ctypes.c_void_p)
_proto(user32, "KillTimer", w.BOOL, w.HWND, ctypes.c_size_t)
_proto(user32, "SendInput", w.UINT, w.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_proto(user32, "MapVirtualKeyW", w.UINT, w.UINT, w.UINT)
_proto(user32, "GetAsyncKeyState", w.SHORT, ctypes.c_int)
_proto(user32, "GetForegroundWindow", w.HWND)
_proto(user32, "FindWindowW", w.HWND, w.LPCWSTR, w.LPCWSTR)
_proto(user32, "SetForegroundWindow", w.BOOL, w.HWND)
_proto(user32, "IsWindow", w.BOOL, w.HWND)
_proto(user32, "GetWindowThreadProcessId", w.DWORD, w.HWND, ctypes.POINTER(w.DWORD))
_proto(user32, "GetWindowTextLengthW", ctypes.c_int, w.HWND)
_proto(user32, "GetWindowTextW", ctypes.c_int, w.HWND, w.LPWSTR, ctypes.c_int)
_proto(user32, "GetClassNameW", ctypes.c_int, w.HWND, w.LPWSTR, ctypes.c_int)
_proto(user32, "GetGUIThreadInfo", w.BOOL, w.DWORD, ctypes.POINTER(GUITHREADINFO))
_proto(user32, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_proto(user32, "SendMessageW", LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_proto(
    user32,
    "CreateWindowExW",
    w.HWND,
    w.DWORD,
    w.LPCWSTR,
    w.LPCWSTR,
    w.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    w.HWND,
    w.HMENU,
    w.HINSTANCE,
    w.LPVOID,
)
_proto(user32, "DestroyWindow", w.BOOL, w.HWND)
_proto(user32, "GetWindowLongPtrW", ctypes.c_ssize_t, w.HWND, ctypes.c_int)
_proto(user32, "SetWindowLongPtrW", ctypes.c_ssize_t, w.HWND, ctypes.c_int, ctypes.c_ssize_t)
_proto(user32, "GetWindowRect", w.BOOL, w.HWND, ctypes.POINTER(w.RECT))

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


def make_window_non_activating(hwnd: int, *, click_through: bool) -> None:
    """Belt and braces on top of Qt's flags: never take focus (and optionally ignore the mouse)."""
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
    if click_through:
        style |= WS_EX_TRANSPARENT
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)


_proto(user32, "OpenClipboard", w.BOOL, w.HWND)
_proto(user32, "CloseClipboard", w.BOOL)
_proto(user32, "EmptyClipboard", w.BOOL)
_proto(user32, "GetClipboardData", w.HANDLE, w.UINT)
_proto(user32, "SetClipboardData", w.HANDLE, w.UINT, w.HANDLE)
_proto(user32, "EnumClipboardFormats", w.UINT, w.UINT)
_proto(user32, "IsClipboardFormatAvailable", w.BOOL, w.UINT)
_proto(user32, "GetClipboardSequenceNumber", w.DWORD)
_proto(user32, "RegisterClipboardFormatW", w.UINT, w.LPCWSTR)

_proto(kernel32, "GetCurrentThreadId", w.DWORD)
_proto(kernel32, "GetModuleHandleW", w.HMODULE, w.LPCWSTR)
_proto(kernel32, "OpenProcess", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
_proto(kernel32, "CloseHandle", w.BOOL, w.HANDLE)
_proto(kernel32, "GetCurrentProcess", w.HANDLE)
_proto(kernel32, "QueryFullProcessImageNameW", w.BOOL, w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD))
_proto(kernel32, "GlobalAlloc", w.HGLOBAL, w.UINT, ctypes.c_size_t)
_proto(kernel32, "GlobalLock", w.LPVOID, w.HGLOBAL)
_proto(kernel32, "GlobalUnlock", w.BOOL, w.HGLOBAL)
_proto(kernel32, "GlobalSize", ctypes.c_size_t, w.HGLOBAL)
_proto(kernel32, "GlobalFree", w.HGLOBAL, w.HGLOBAL)

_proto(advapi32, "OpenProcessToken", w.BOOL, w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE))
_proto(advapi32, "GetTokenInformation", w.BOOL, w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD))


def key_is_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)
