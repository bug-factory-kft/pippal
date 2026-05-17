"""Small reusable Qt widgets that recreate the Tk UI's building blocks.

The Tk frontend leans on one helper, ``theme.make_card``. The Qt side
needs the same notion (a titled rounded panel) plus a couple of label
flavours so cards read identically. Keeping them here means the window
modules stay focused on layout, exactly like the Tk split between
``settings_window.py`` and ``settings_cards.py``."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme_qt import UI


def make_card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    """Return ``(card_frame, content_layout)``.

    Mirrors ``pippal.ui.theme.make_card``: a rounded ``bg_card`` panel
    with an optional uppercase section title. Put widgets into the
    returned layout."""
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(0)
    if title:
        section = QLabel(title.upper())
        section.setObjectName("SectionTitle")
        layout.addWidget(section)
        layout.addSpacing(12)
    return card, layout


def section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("SectionTitle")
    return lbl


def title_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("TitleLabel")
    lbl.setWordWrap(True)
    return lbl


def sub_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("SubLabel")
    lbl.setWordWrap(True)
    return lbl


def hint_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("CardHint")
    lbl.setWordWrap(True)
    return lbl


def card_label(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    return lbl


def link_label(text: str, url: str) -> QLabel:
    """A clickable underlined accent label that opens ``url`` — same
    affordance the Tk About card builds by hand."""
    lbl = QLabel(f'<a href="{url}" style="color:{UI["accent"]};'
                 f'text-decoration:underline;">{text}</a>')
    lbl.setObjectName("LinkLabel")
    lbl.setOpenExternalLinks(False)
    lbl.setTextInteractionFlags(Qt.TextBrowserInteraction)
    lbl.setCursor(Qt.PointingHandCursor)
    return lbl


def primary_button(text: str, on_click: Callable[[], None] | None = None) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Primary")
    btn.setCursor(Qt.PointingHandCursor)
    if on_click is not None:
        btn.clicked.connect(on_click)
    return btn


def button(text: str, on_click: Callable[[], None] | None = None) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    if on_click is not None:
        btn.clicked.connect(on_click)
    return btn


def danger_button(text: str, on_click: Callable[[], None] | None = None) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("Danger")
    btn.setCursor(Qt.PointingHandCursor)
    if on_click is not None:
        btn.clicked.connect(on_click)
    return btn


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName("Separator")
    line.setFixedHeight(1)
    return line


def labeled_row(label_text: str, control: QWidget, label_width: int = 110) -> QWidget:
    """A horizontal `label : control` row matching the Tk card rows."""
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    lbl = QLabel(label_text)
    lbl.setFixedWidth(label_width)
    h.addWidget(lbl)
    h.addWidget(control, 1)
    return row
