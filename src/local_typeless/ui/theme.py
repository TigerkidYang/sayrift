"""Design tokens and the Qt stylesheet — the "Glass" language.

Frosted, translucent layers over a slowly drifting aurora (glass.Aurora paints it), one glowing orb, and a
violet-to-cyan gradient as the only accent. Dark is the primary look; light is a pale, airy variant.
Translucent colours are #AARRGGBB, which both QColor and Qt stylesheets accept.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from ..brand import APP_NAME as APP_NAME

FONT = '"Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI"'
DISPLAY = '"Segoe UI Variable Display", "Segoe UI", "Microsoft YaHei UI"'


@dataclass(frozen=True)
class Palette:
    dark: bool
    base: str  # the canvas under the aurora
    aurora: tuple[str, str, str]  # the three light blobs
    bg: str  # opaque fallback for areas without the aurora
    surface: str  # frosted card
    surface2: str  # inputs, hover, tracks
    border: str  # hairline around glass
    text: str
    muted: str
    faint: str
    accent: str  # violet end of the gradient
    accent2: str  # cyan end of the gradient
    accent_hover: str
    accent_soft: str
    on_accent: str
    pill: str  # the selected nav pill / primary button (white on dark, ink on light)
    on_pill: str
    danger: str
    success: str
    warning: str


DARK = Palette(
    dark=True,
    base="#07080d",
    aurora=("#4a35c9", "#0e7f8f", "#8a2f7a"),
    bg="#0c0d14",
    surface="#12ffffff",
    surface2="#1cffffff",
    border="#24ffffff",
    text="#f3f4f8",
    muted="#a4a7b8",
    faint="#6d7082",
    accent="#9b82ff",
    accent2="#2fd3e0",
    accent_hover="#b3a1ff",
    accent_soft="#2e9b82ff",
    on_accent="#0b0c12",
    pill="#eef0f6",
    on_pill="#0b0c12",
    danger="#ff7a8a",
    success="#4ee3b0",
    warning="#ffc46b",
)

LIGHT = Palette(
    dark=False,
    base="#eef0f8",
    aurora=("#b9a6ff", "#8fe0ea", "#f5b8dc"),
    bg="#f6f7fb",
    surface="#9effffff",
    surface2="#c8ffffff",
    border="#1a141a3c",
    text="#0d0e16",
    muted="#4d5166",
    faint="#8a8ea3",
    accent="#6a4dff",
    accent2="#0fb5c6",
    accent_hover="#5a3cf0",
    accent_soft="#226a4dff",
    on_accent="#ffffff",
    pill="#0d0e16",
    on_pill="#ffffff",
    danger="#e0364f",
    success="#0f9f73",
    warning="#c77a00",
)


def palette_for(setting: str) -> Palette:
    if setting == "dark":
        return DARK
    if setting == "light":
        return LIGHT
    return DARK if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else LIGHT


def stylesheet(p: Palette) -> str:
    return f"""
* {{ font-family: {FONT}; font-size: 13px; color: {p.text}; }}
QMainWindow {{ background: {p.base}; }}
#Content, #Page {{ background: transparent; }}

#Brand {{ font-family: {DISPLAY}; font-size: 15px; font-weight: 600; }}
#Status {{ color: {p.muted}; font-size: 12px; }}
#NavPill {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 19px; }}
QPushButton#NavItem {{
    background: transparent; border: none; border-radius: 15px; padding: 7px 16px;
    color: {p.muted}; font-size: 13px; font-weight: 500;
}}
QPushButton#NavItem:hover {{ color: {p.text}; }}
QPushButton#NavItem:checked {{ background: {p.pill}; color: {p.on_pill}; font-weight: 600; }}

#HeroTitle {{ font-family: {DISPLAY}; font-size: 30px; font-weight: 600; }}
#PageTitle {{ font-family: {DISPLAY}; font-size: 26px; font-weight: 600; }}
#PageSub {{ color: {p.muted}; font-size: 13px; }}
#SectionTitle {{ font-family: {DISPLAY}; font-size: 15px; font-weight: 600; }}
#Eyebrow {{ color: {p.faint}; font-size: 12px; font-weight: 500; }}
#Muted {{ color: {p.muted}; }}
#Faint {{ color: {p.faint}; font-size: 12px; }}
#Danger {{ color: {p.danger}; }}
#BigNumber {{ font-family: {DISPLAY}; font-size: 34px; font-weight: 600; }}

#Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 18px; }}
#StatValue {{ font-family: {DISPLAY}; font-size: 26px; font-weight: 600; }}
#StatLabel {{ color: {p.muted}; font-size: 12px; }}
#KeyCap {{
    background: {p.surface2}; border: 1px solid {p.border}; border-radius: 8px;
    padding: 3px 9px; font-size: 12px; font-weight: 600;
}}
#KeyCapBig {{
    background: {p.surface2}; border: 1px solid {p.border}; border-radius: 10px;
    padding: 2px 10px; font-family: {DISPLAY}; font-size: 22px; font-weight: 600;
}}
#Badge {{ background: {p.accent_soft}; color: {p.accent}; border-radius: 9px; padding: 2px 8px; font-size: 11px; }}
#BadgeMuted {{ background: {p.surface2}; color: {p.muted}; border-radius: 9px; padding: 2px 8px; font-size: 11px; }}
#DayHeader {{ color: {p.faint}; font-size: 12px; font-weight: 600; padding-top: 8px; }}
#Row {{ background: transparent; border-radius: 12px; }}
#Row:hover {{ background: {p.surface}; }}
#RowText {{ font-size: 14px; }}

QPushButton {{
    background: {p.surface2}; border: 1px solid {p.border}; border-radius: 10px; padding: 7px 15px;
}}
QPushButton:hover {{ background: {p.border}; }}
QPushButton:disabled {{ color: {p.faint}; }}
QPushButton#Primary {{ background: {p.pill}; color: {p.on_pill}; border: none; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {p.accent_hover}; color: {p.on_accent}; }}
QPushButton#Ghost {{ background: transparent; border: none; padding: 6px 8px; border-radius: 8px; color: {p.muted}; }}
QPushButton#Ghost:hover {{ background: {p.surface2}; color: {p.text}; }}
QPushButton#Seg {{ background: transparent; border: none; border-radius: 13px; padding: 6px 14px; color: {p.muted}; }}
QPushButton#Seg:hover {{ color: {p.text}; }}
QPushButton#Seg:checked {{ background: {p.surface2}; color: {p.text}; font-weight: 600; }}
#SegBox {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 17px; }}
QPushButton#Chip {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 15px; padding: 6px 14px;
}}
QPushButton#Chip:hover {{ border-color: {p.danger}; color: {p.danger}; }}

QLineEdit, QComboBox, QSpinBox {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; padding: 8px 12px;
    selection-background-color: {p.accent};
}}
QPlainTextEdit, QTextEdit {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 14px; padding: 10px 12px;
    selection-background-color: {p.accent}; font-size: 14px;
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {p.accent}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {p.bg}; border: 1px solid {p.border}; selection-background-color: {p.accent_soft};
    selection-color: {p.text}; outline: none; padding: 4px; border-radius: 10px;
}}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ padding: 8px 10px; border-radius: 8px; }}
QListWidget::item:selected {{ background: {p.accent_soft}; color: {p.text}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.faint}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QToolTip {{ background: {p.bg}; color: {p.text}; border: 1px solid {p.border}; padding: 5px 9px; border-radius: 8px; }}
QMenu {{ background: {p.bg}; border: 1px solid {p.border}; padding: 6px; border-radius: 12px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 8px; }}
QMenu::item:selected {{ background: {p.surface2}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}
"""
