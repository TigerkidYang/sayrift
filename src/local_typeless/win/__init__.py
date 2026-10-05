"""Windows-only integration: keyboard hook, foreground window, clipboard, input injection.

Everything here talks to Win32 through ctypes (see `_api.py`). Keep business logic out of
this package so it stays testable elsewhere.
"""
