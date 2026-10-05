"""Lucide/Feather SVG icons (ISC/MIT); attribution and texts are in THIRD_PARTY_NOTICES.md and licenses/."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

APP_ICON = Path(__file__).resolve().parents[1] / "assets" / "app.ico"

_PATHS = {
    "home": '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    "history": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>'
    '<path d="M12 7v5l4 2"/>',
    "book": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>'
    '<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "settings": '<path d="M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4"/>',
    "mic": '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/>'
    '<path d="M12 19v3"/>',
    "copy": '<rect width="14" height="14" x="8" y="8" rx="2"/>'
    '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "retry": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>'
    '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>'
    '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "translate": '<path d="m5 8 6 6"/><path d="m4 14 6-6 2-3"/><path d="M2 5h12"/><path d="M7 2h1"/>'
    '<path d="m22 22-5-10-5 10"/><path d="M14 18h6"/>',
    "sparkles": '<path d="M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2z"/><path d="M19 3v4M21 5h-4"/>',
    "up": '<path d="m18 15-6-6-6 6"/>',
    "down": '<path d="m6 9 6 6 6-6"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "folder": '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4'
    'a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>',
    "flame": '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5'
    ' 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
    "zap": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "type": '<path d="M4 7V4h16v3"/><path d="M9 20h6"/><path d="M12 4v16"/>',
    "timer": '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2"/><path d="M9 2h6"/>',
    "keyboard": '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="M6 8h.01M10 8h.01M14 8h.01M18 8h.01'
    'M8 12h.01M12 12h.01M16 12h.01M7 16h10"/>',
    "volume": '<path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>'
    '<path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
    "palette": '<circle cx="13.5" cy="6.5" r=".5"/><circle cx="17.5" cy="10.5" r=".5"/>'
    '<circle cx="8.5" cy="7.5" r=".5"/><circle cx="6.5" cy="12.5" r=".5"/>'
    '<path d="M12 2a10 10 0 0 0 0 20c.9 0 1.6-.7 1.6-1.6 0-.4-.2-.8-.4-1.1-.3-.3-.4-.6-.4-1.1'
    ' 0-.9.7-1.6 1.6-1.6H16a6 6 0 0 0 6-6c0-4.9-4.5-8.6-10-8.6z"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
    "arrow_right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "wallet": '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2'
    'a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "trend": '<path d="M22 7 13.5 15.5 8.5 10.5 2 17"/><path d="M16 7h6v6"/>',
    "coins": '<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/>',
}


@cache
def pixmap(name: str, color: str, size: int = 18, ratio: float = 2.0, stroke: float = 2.0) -> QPixmap:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{_PATHS[name]}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, size * ratio, size * ratio))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str, size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))


def paint_orb(p: QPainter, c, r: float, *, glow: bool = True, dim: float = 1.0, ring: bool = False) -> None:
    """The Glass mark: a lit violet-to-cyan sphere. Shared by the app icon, tray icons and the orb widget's look.

    `dim` < 1 fades the sphere (processing), `ring` adds a bright outline (listening)."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QPen, QRadialGradient

    violet, cyan = QColor("#9b82ff"), QColor("#2fd3e0")
    p.setPen(Qt.PenStyle.NoPen)
    if glow:
        halo = QRadialGradient(c, r * 1.7)
        for stop, color, alpha in ((0.5, violet, 110), (0.75, cyan, 40), (1.0, cyan, 0)):
            col = QColor(color)
            col.setAlpha(int(alpha * dim))
            halo.setColorAt(stop, col)
        p.setBrush(halo)
        p.drawEllipse(c, r * 1.7, r * 1.7)
    sphere = QRadialGradient(QPointF(c.x() - r * 0.32, c.y() - r * 0.4), r * 1.55)
    stops = ((0.0, QColor("#ffffff")), (0.14, QColor("#d9ceff")), (0.44, violet), (0.8, cyan), (1.0, QColor("#0b3b52")))
    for stop, color in stops:
        color.setAlphaF(dim)
        sphere.setColorAt(stop, color)
    p.setBrush(sphere)
    p.drawEllipse(c, r, r)
    if ring:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#ffffff"), max(1.0, r * 0.14)))
        p.drawEllipse(c, r * 1.22, r * 1.22)
