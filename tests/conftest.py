import socket

import pytest


@pytest.fixture(autouse=True)
def _no_real_api_key(request, monkeypatch):
    """Unit tests must never reach the paid API: hide the key unless the test is marked `network`."""
    if request.node.get_closest_marker("network"):
        return
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("local_typeless.config.api_key", lambda: None)
    monkeypatch.setattr("local_typeless.app.api_key", lambda: None)

    def blocked(*args, **kwargs):
        raise AssertionError("Network access is disabled in unit tests; use a mock transport")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
