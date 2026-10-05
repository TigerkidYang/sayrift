"""Draw the app icon and write src/local_typeless/assets/app.ico (PNG-compressed, 16..256 px) and app.png.

The Glass mark: a luminous violet-to-cyan orb on a deep night squircle with a faint aurora. Below 32 px the
aurora is dropped and the orb grows, so the icon stays a clean, recognisable dot in the taskbar and tray.

Usage: uv run python tools/make_icon.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QRadialGradient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from local_typeless.ui.icons import paint_orb

OUT = Path(__file__).resolve().parents[1] / "src" / "local_typeless" / "assets"
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 256, size / 256)  # draw on a 256 grid

    tile = QPainterPath()
    tile.addRoundedRect(QRectF(8, 8, 240, 240), 60, 60)
    p.fillPath(tile, QColor("#0b0c16"))
    if size >= 32:
        p.setClipPath(tile)
        for (x, y, r), color in (((40, 30, 170), "#6a4dff"), ((230, 230, 170), "#0fb5c6")):
            g = QRadialGradient(QPointF(x, y), r)
            c = QColor(color)
            c.setAlpha(120)
            g.setColorAt(0, c)
            c.setAlpha(0)
            g.setColorAt(1, c)
            p.fillRect(QRectF(0, 0, 256, 256), g)
        p.setClipping(False)
    radius = 70 if size >= 32 else 84
    paint_orb(p, QPointF(128, 128), radius, glow=size >= 32)
    p.end()
    return img


def png(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def main() -> int:
    _app = QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    images = [png(draw(s)) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in zip(SIZES, images, strict=True):
        dim = 0 if size >= 256 else size  # 0 means 256 in ICONDIRENTRY
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset + len(blobs))
        blobs += blob
    (OUT / "app.ico").write_bytes(header + entries + blobs)
    draw(256).save(str(OUT / "app.png"))
    print(OUT / "app.ico")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
