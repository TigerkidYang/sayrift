"""One app per user: launching again (Start menu, desktop icon) just shows the running instance's window.

Two instances would each install a keyboard hook and both react to Right Alt.
"""

from __future__ import annotations

import getpass
import hashlib
from collections.abc import Callable

from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .. import config


def _server_name() -> str:
    # Keyed by config path too, so test runs with a redirected LOCAL_TYPELESS_CONFIG stay independent.
    digest = hashlib.sha1(str(config.config_path()).lower().encode()).hexdigest()[:10]
    return f"local-typeless-{getpass.getuser()}-{digest}"


def notify_running(message: bytes) -> bool:
    """True if another instance is running (and got `message`)."""
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(500):
        return False
    sock.write(message)
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def listen(on_message: Callable[[bytes], None]) -> QLocalServer:
    """Become the running instance. Keep the returned server alive."""
    name = _server_name()
    server = QLocalServer()
    QLocalServer.removeServer(name)  # a crashed instance can leave a stale endpoint behind
    server.listen(name)

    def accept() -> None:
        while (conn := server.nextPendingConnection()) is not None:
            conn.waitForReadyRead(500)
            on_message(bytes(conn.readAll()))
            conn.deleteLater()

    server.newConnection.connect(accept)
    return server


def quit_running(timeout_s: float = 8.0) -> bool:
    """Ask a running instance to quit and wait until it has (setup / uninstall). False if it is still there."""
    import time

    if not notify_running(b"quit"):
        return True
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        sock = QLocalSocket()
        sock.connectToServer(_server_name())
        if not sock.waitForConnected(200):
            time.sleep(0.5)  # endpoint gone; give the process a moment to release its files
            return True
        sock.disconnectFromServer()
        time.sleep(0.2)
    return False
