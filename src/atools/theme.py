from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .paths import asset_path


DEFAULT_THEME_MODE = "dark"


def normalize_theme_mode(theme_mode: str | None) -> str:
    if theme_mode == "light":
        return "light"
    return DEFAULT_THEME_MODE


def _qss_asset_path(name: str) -> str:
    return asset_path(name).as_posix()


def _theme_tokens(theme_mode: str) -> dict[str, str]:
    mode = normalize_theme_mode(theme_mode)
    if mode == "light":
        return {
            "CHARCOAL": "#f4efe7",
            "SURFACE": "#fffdfa",
            "SURFACE_LIGHT": "#f7f2ea",
            "SURFACE_RAISED": "#ffffff",
            "WINDOW_TEXT": "#1f2832",
            "SECONDARY": "#51606f",
            "MUTED": "#7f7d77",
            "TABLE_TEXT": "#1f2832",
            "ACCENT": "#58697d",
            "ACCENT_SOFT": "rgba(88, 105, 125, 0.12)",
            "ACCENT_LINE": "rgba(88, 105, 125, 0.20)",
            "ACCENT_STRONG": "#445465",
            "AMBER": "#b88856",
            "CYAN": "#6d9197",
            "DANGER": "#b45d55",
            "EMERALD": "#6d8d72",
            "SKY": "#6f89a5",
            "WINDOW_BG": """
                qradialgradient(cx:0.08, cy:0.00, radius:0.40, fx:0.08, fy:0.00,
                    stop:0 rgba(184, 136, 86, 0.12),
                    stop:1 transparent),
                qradialgradient(cx:0.94, cy:0.06, radius:0.32, fx:0.94, fy:0.06,
                    stop:0 rgba(111, 137, 165, 0.10),
                    stop:1 transparent),
                qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #faf6ef,
                    stop:0.48 #f5efe7,
                    stop:1 #f1ebe3)
            """,
            "TITLEBAR_BG": "rgba(255, 251, 246, 0.78)",
            "TITLEBAR_BORDER": "rgba(31, 40, 50, 0.10)",
            "NAV_BG": "rgba(255, 255, 255, 0.58)",
            "NAV_BORDER": "rgba(31, 40, 50, 0.08)",
            "NAV_TEXT": "#556273",
            "NAV_HOVER_BG": "rgba(31, 40, 50, 0.05)",
            "NAV_ACTIVE_BG": "rgba(31, 40, 50, 0.08)",
            "NAV_ACTIVE_BORDER": "rgba(31, 40, 50, 0.12)",
            "NAV_BADGE_BG": "rgba(180, 93, 85, 0.13)",
            "NAV_BADGE_BORDER": "rgba(180, 93, 85, 0.20)",
            "CONTROL_BG": "rgba(255, 255, 255, 0.92)",
            "CONTROL_HOVER_BG": "rgba(245, 240, 233, 1)",
            "CONTROL_BORDER": "rgba(31, 40, 50, 0.10)",
            "CONTROL_CLOSE_BG": "rgba(180, 93, 85, 0.14)",
            "HERO_BG": """
                qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(255, 252, 247, 0.98),
                    stop:1 rgba(248, 242, 234, 0.98))
            """,
            "HERO_BORDER": "rgba(31, 40, 50, 0.08)",
            "CARD_BG": "rgba(255, 255, 255, 0.90)",
            "CARD_BG_HOVER": "rgba(255, 255, 255, 0.98)",
            "CARD_RAISED": "rgba(250, 245, 237, 0.98)",
            "CARD_BORDER": "rgba(31, 40, 50, 0.08)",
            "CARD_BORDER_STRONG": "rgba(31, 40, 50, 0.12)",
            "CARD_BORDER_GLOW": "rgba(88, 105, 125, 0.18)",
            "INPUT_BG": "rgba(255, 255, 255, 0.96)",
            "INPUT_BG_SOFT": "rgba(250, 245, 237, 0.98)",
            "INPUT_BORDER": "rgba(31, 40, 50, 0.10)",
            "INPUT_FOCUS": "rgba(88, 105, 125, 0.24)",
            "INPUT_SELECTION": "rgba(88, 105, 125, 0.18)",
            "BUTTON_BG": "rgba(255, 255, 255, 0.94)",
            "BUTTON_HOVER_BG": "rgba(245, 240, 233, 1)",
            "BUTTON_BORDER": "rgba(31, 40, 50, 0.10)",
            "BUTTON_TEXT": "#33404d",
            "PRIMARY_BG_TOP": "#5c6e83",
            "PRIMARY_BG_BOTTOM": "#4a5a6d",
            "PRIMARY_BORDER": "rgba(74, 90, 109, 0.40)",
            "PRIMARY_HOVER_TOP": "#677b91",
            "PRIMARY_HOVER_BOTTOM": "#536476",
            "PRIMARY_TEXT": "#ffffff",
            "SECONDARY_BG": "rgba(255, 255, 255, 0.92)",
            "SECONDARY_HOVER_BG": "rgba(245, 240, 233, 1)",
            "SECONDARY_TEXT": "#1f2832",
            "DANGER_BG": "rgba(180, 93, 85, 0.08)",
            "DANGER_HOVER_BG": "rgba(180, 93, 85, 0.12)",
            "DANGER_BORDER": "rgba(180, 93, 85, 0.15)",
            "CHECK_BG": "rgba(255, 255, 255, 1)",
            "CHECK_BORDER": "rgba(31, 40, 50, 0.15)",
            "CHECK_ACTIVE_BG": "#58697d",
            "CHECK_ACTIVE_BORDER": "rgba(88, 105, 125, 0.28)",
            "RADIO_ACTIVE_BG": "#b45d55",
            "RADIO_ACTIVE_BORDER": "rgba(180, 93, 85, 0.26)",
            "TABLE_BG": "rgba(255, 255, 255, 0.98)",
            "TABLE_ALT_BG": "rgba(247, 242, 234, 0.78)",
            "TABLE_HEADER_BG": "rgba(249, 244, 236, 0.98)",
            "TABLE_HEADER_TEXT": "#536171",
            "SPLITTER": "rgba(88, 105, 125, 0.12)",
            "SPLITTER_HOVER": "rgba(88, 105, 125, 0.18)",
            "STATUSBAR_BG": "rgba(255, 251, 246, 0.84)",
            "STATUSBAR_BORDER": "rgba(31, 40, 50, 0.08)",
            "SCROLL_HANDLE": "rgba(88, 105, 125, 0.20)",
            "SCROLL_HANDLE_HOVER": "rgba(88, 105, 125, 0.30)",
            "COMBO_BG": "rgba(255, 255, 255, 0.96)",
            "COMBO_HOVER_BG": "rgba(250, 245, 237, 0.98)",
            "COMBO_POPUP_BG": "rgba(255, 255, 255, 0.98)",
            "COMBO_POPUP_HOVER": "rgba(88, 105, 125, 0.08)",
            "COMBO_POPUP_SELECTED": "rgba(88, 105, 125, 0.14)",
            "CHECK_ICON": _qss_asset_path("ui/check-light.svg"),
            "RADIO_ICON": _qss_asset_path("ui/dot-light.svg"),
            "CHEVRON_ICON": _qss_asset_path("ui/chevron-light.svg"),
        }
    elif mode == "blueprint":
        return {
            "CHARCOAL": "#0b0f14",
            "SURFACE": "#10151b",
            "SURFACE_LIGHT": "#141a21",
            "SURFACE_RAISED": "#171e26",

            "WINDOW_TEXT": "#e7edf3",
            "SECONDARY": "#aeb8c2",
            "MUTED": "#6f7a84",
            "TABLE_TEXT": "#dce4ec",

            "ACCENT": "#dce4ec",
            "ACCENT_SOFT": "rgba(220, 228, 236, 0.055)",
            "ACCENT_LINE": "rgba(220, 228, 236, 0.16)",
            "ACCENT_STRONG": "#ffffff",

            "AMBER": "#d9b46f",
            "CYAN": "#cfd8e2",
            "DANGER": "#d86c6c",
            "EMERALD": "#8fc79a",
            "SKY": "#9db8d6",

            "WINDOW_BG": """
                qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #10151b,
                    stop:0.50 #0b0f14,
                    stop:1 #070a0e)
            """,

            "TITLEBAR_BG": "rgba(12, 16, 22, 0.96)",
            "TITLEBAR_BORDER": "rgba(220, 228, 236, 0.13)",

            "NAV_BG": "rgba(10, 14, 19, 0.90)",
            "NAV_BORDER": "rgba(220, 228, 236, 0.15)",
            "NAV_TEXT": "#aeb8c2",
            "NAV_HOVER_BG": "rgba(220, 228, 236, 0.055)",
            "NAV_ACTIVE_BG": "rgba(220, 228, 236, 0.085)",
            "NAV_ACTIVE_BORDER": "rgba(220, 228, 236, 0.28)",

            "NAV_BADGE_BG": "rgba(216, 108, 108, 0.10)",
            "NAV_BADGE_BORDER": "rgba(216, 108, 108, 0.22)",

            "CONTROL_BG": "rgba(13, 18, 24, 0.92)",
            "CONTROL_HOVER_BG": "rgba(220, 228, 236, 0.075)",
            "CONTROL_BORDER": "rgba(220, 228, 236, 0.16)",
            "CONTROL_CLOSE_BG": "rgba(216, 108, 108, 0.13)",

            "HERO_BG": "rgba(12, 16, 22, 0.86)",
            "HERO_BORDER": "rgba(220, 228, 236, 0.18)",

            "CARD_BG": "rgba(11, 15, 20, 0.82)",
            "CARD_BG_HOVER": "rgba(16, 21, 27, 0.92)",
            "CARD_RAISED": "rgba(18, 24, 31, 0.88)",
            "CARD_BORDER": "rgba(220, 228, 236, 0.15)",
            "CARD_BORDER_STRONG": "rgba(220, 228, 236, 0.24)",
            "CARD_BORDER_GLOW": "rgba(220, 228, 236, 0.34)",

            "INPUT_BG": "rgba(5, 8, 12, 0.74)",
            "INPUT_BG_SOFT": "rgba(10, 14, 19, 0.82)",
            "INPUT_BORDER": "rgba(220, 228, 236, 0.15)",
            "INPUT_FOCUS": "rgba(220, 228, 236, 0.38)",
            "INPUT_SELECTION": "rgba(220, 228, 236, 0.18)",

            "BUTTON_BG": "rgba(12, 16, 22, 0.82)",
            "BUTTON_HOVER_BG": "rgba(220, 228, 236, 0.075)",
            "BUTTON_BORDER": "rgba(220, 228, 236, 0.18)",
            "BUTTON_TEXT": "#dce4ec",

            "PRIMARY_BG_TOP": "#e7edf3",
            "PRIMARY_BG_BOTTOM": "#c7d1dc",
            "PRIMARY_BORDER": "rgba(255, 255, 255, 0.36)",
            "PRIMARY_HOVER_TOP": "#ffffff",
            "PRIMARY_HOVER_BOTTOM": "#dce4ec",
            "PRIMARY_TEXT": "#080c11",

            "SECONDARY_BG": "rgba(12, 16, 22, 0.72)",
            "SECONDARY_HOVER_BG": "rgba(220, 228, 236, 0.07)",
            "SECONDARY_TEXT": "#dce4ec",

            "DANGER_BG": "rgba(216, 108, 108, 0.08)",
            "DANGER_HOVER_BG": "rgba(216, 108, 108, 0.14)",
            "DANGER_BORDER": "rgba(216, 108, 108, 0.24)",

            "CHECK_BG": "rgba(5, 8, 12, 0.95)",
            "CHECK_BORDER": "rgba(220, 228, 236, 0.24)",
            "CHECK_ACTIVE_BG": "#dce4ec",
            "CHECK_ACTIVE_BORDER": "rgba(255, 255, 255, 0.42)",

            "RADIO_ACTIVE_BG": "#dce4ec",
            "RADIO_ACTIVE_BORDER": "rgba(255, 255, 255, 0.42)",

            "TABLE_BG": "rgba(5, 8, 12, 0.72)",
            "TABLE_ALT_BG": "rgba(220, 228, 236, 0.035)",
            "TABLE_HEADER_BG": "rgba(220, 228, 236, 0.065)",
            "TABLE_HEADER_TEXT": "#b8c3ce",

            "SPLITTER": "rgba(220, 228, 236, 0.14)",
            "SPLITTER_HOVER": "rgba(220, 228, 236, 0.28)",

            "STATUSBAR_BG": "rgba(8, 12, 17, 0.94)",
            "STATUSBAR_BORDER": "rgba(220, 228, 236, 0.15)",

            "SCROLL_HANDLE": "rgba(220, 228, 236, 0.18)",
            "SCROLL_HANDLE_HOVER": "rgba(220, 228, 236, 0.34)",

            "COMBO_BG": "rgba(5, 8, 12, 0.86)",
            "COMBO_HOVER_BG": "rgba(220, 228, 236, 0.055)",
            "COMBO_POPUP_BG": "rgba(8, 12, 17, 0.98)",
            "COMBO_POPUP_HOVER": "rgba(220, 228, 236, 0.08)",
            "COMBO_POPUP_SELECTED": "rgba(220, 228, 236, 0.14)",

            "CHECK_ICON": _qss_asset_path("ui/check-blueprint.svg"),
            "RADIO_ICON": _qss_asset_path("ui/dot-blueprint.svg"),
            "CHEVRON_ICON": _qss_asset_path("ui/chevron-blueprint.svg"),
        }
    return {
        "CHARCOAL": "#14171c",
        "SURFACE": "#1a1f26",
        "SURFACE_LIGHT": "#20262e",
        "SURFACE_RAISED": "#252d36",
        "WINDOW_TEXT": "#eef2f6",
        "SECONDARY": "#c5d0db",
        "MUTED": "#8c98a3",
        "TABLE_TEXT": "#eef2f6",
        "ACCENT": "#93a6bb",
        "ACCENT_SOFT": "rgba(147, 166, 187, 0.14)",
        "ACCENT_LINE": "rgba(147, 166, 187, 0.24)",
        "ACCENT_STRONG": "#71859c",
        "AMBER": "#d2a16d",
        "CYAN": "#8ab4bd",
        "DANGER": "#d07a72",
        "EMERALD": "#87ad91",
        "SKY": "#8ca8c7",
        "WINDOW_BG": """
            qradialgradient(cx:0.10, cy:0.02, radius:0.42, fx:0.10, fy:0.02,
                stop:0 rgba(210, 161, 109, 0.14),
                stop:1 transparent),
            qradialgradient(cx:0.94, cy:0.06, radius:0.34, fx:0.94, fy:0.06,
                stop:0 rgba(140, 168, 199, 0.10),
                stop:1 transparent),
            qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #1a1d23,
                stop:0.48 #161a20,
                stop:1 #12151a)
        """,
        "TITLEBAR_BG": "rgba(19, 22, 28, 0.86)",
        "TITLEBAR_BORDER": "rgba(255, 255, 255, 0.08)",
        "NAV_BG": "rgba(28, 33, 40, 0.92)",
        "NAV_BORDER": "rgba(255, 255, 255, 0.07)",
        "NAV_TEXT": "#a8b6c4",
        "NAV_HOVER_BG": "rgba(255, 255, 255, 0.05)",
        "NAV_ACTIVE_BG": "rgba(147, 166, 187, 0.16)",
        "NAV_ACTIVE_BORDER": "rgba(147, 166, 187, 0.22)",
        "NAV_BADGE_BG": "rgba(208, 122, 114, 0.16)",
        "NAV_BADGE_BORDER": "rgba(208, 122, 114, 0.24)",
        "CONTROL_BG": "rgba(30, 35, 42, 0.96)",
        "CONTROL_HOVER_BG": "rgba(36, 42, 50, 1)",
        "CONTROL_BORDER": "rgba(255, 255, 255, 0.08)",
        "CONTROL_CLOSE_BG": "rgba(208, 122, 114, 0.20)",
        "HERO_BG": """
            qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(32, 38, 46, 0.98),
                stop:1 rgba(28, 33, 40, 0.98))
        """,
        "HERO_BORDER": "rgba(255, 255, 255, 0.08)",
        "CARD_BG": "rgba(26, 31, 38, 0.94)",
        "CARD_BG_HOVER": "rgba(29, 35, 43, 0.98)",
        "CARD_RAISED": "rgba(32, 38, 46, 0.98)",
        "CARD_BORDER": "rgba(255, 255, 255, 0.08)",
        "CARD_BORDER_STRONG": "rgba(255, 255, 255, 0.12)",
        "CARD_BORDER_GLOW": "rgba(147, 166, 187, 0.20)",
        "INPUT_BG": "rgba(19, 23, 29, 0.96)",
        "INPUT_BG_SOFT": "rgba(24, 29, 35, 0.98)",
        "INPUT_BORDER": "rgba(255, 255, 255, 0.09)",
        "INPUT_FOCUS": "rgba(147, 166, 187, 0.28)",
        "INPUT_SELECTION": "rgba(147, 166, 187, 0.26)",
        "BUTTON_BG": "rgba(34, 40, 48, 0.98)",
        "BUTTON_HOVER_BG": "rgba(39, 46, 55, 1)",
        "BUTTON_BORDER": "rgba(255, 255, 255, 0.08)",
        "BUTTON_TEXT": "#d6dee7",
        "PRIMARY_BG_TOP": "#9cb0c5",
        "PRIMARY_BG_BOTTOM": "#8094aa",
        "PRIMARY_BORDER": "rgba(128, 148, 170, 0.44)",
        "PRIMARY_HOVER_TOP": "#a8bdd2",
        "PRIMARY_HOVER_BOTTOM": "#8a9fb6",
        "PRIMARY_TEXT": "#101318",
        "SECONDARY_BG": "rgba(34, 40, 48, 0.98)",
        "SECONDARY_HOVER_BG": "rgba(39, 46, 55, 1)",
        "SECONDARY_TEXT": "#eef2f6",
        "DANGER_BG": "rgba(208, 122, 114, 0.10)",
        "DANGER_HOVER_BG": "rgba(208, 122, 114, 0.14)",
        "DANGER_BORDER": "rgba(208, 122, 114, 0.18)",
        "CHECK_BG": "rgba(19, 23, 29, 1)",
        "CHECK_BORDER": "rgba(255, 255, 255, 0.16)",
        "CHECK_ACTIVE_BG": "#93a6bb",
        "CHECK_ACTIVE_BORDER": "rgba(147, 166, 187, 0.30)",
        "RADIO_ACTIVE_BG": "#d07a72",
        "RADIO_ACTIVE_BORDER": "rgba(208, 122, 114, 0.28)",
        "TABLE_BG": "rgba(20, 24, 30, 0.98)",
        "TABLE_ALT_BG": "rgba(28, 33, 40, 0.74)",
        "TABLE_HEADER_BG": "rgba(28, 33, 40, 0.98)",
        "TABLE_HEADER_TEXT": "#aab8c5",
        "SPLITTER": "rgba(147, 166, 187, 0.16)",
        "SPLITTER_HOVER": "rgba(147, 166, 187, 0.24)",
        "STATUSBAR_BG": "rgba(17, 20, 26, 0.92)",
        "STATUSBAR_BORDER": "rgba(255, 255, 255, 0.08)",
        "SCROLL_HANDLE": "rgba(147, 166, 187, 0.24)",
        "SCROLL_HANDLE_HOVER": "rgba(147, 166, 187, 0.34)",
        "COMBO_BG": "rgba(19, 23, 29, 0.98)",
        "COMBO_HOVER_BG": "rgba(24, 29, 35, 1)",
        "COMBO_POPUP_BG": "rgba(26, 31, 38, 0.99)",
        "COMBO_POPUP_HOVER": "rgba(147, 166, 187, 0.10)",
        "COMBO_POPUP_SELECTED": "rgba(147, 166, 187, 0.18)",
        "CHECK_ICON": _qss_asset_path("ui/check-dark.svg"),
        "RADIO_ICON": _qss_asset_path("ui/dot-dark.svg"),
        "CHEVRON_ICON": _qss_asset_path("ui/chevron-dark.svg"),
    }


_DEFAULT_TOKENS = _theme_tokens(DEFAULT_THEME_MODE)

CHARCOAL = _DEFAULT_TOKENS["CHARCOAL"]
SURFACE = _DEFAULT_TOKENS["SURFACE"]
SURFACE_LIGHT = _DEFAULT_TOKENS["SURFACE_LIGHT"]
SURFACE_RAISED = _DEFAULT_TOKENS["SURFACE_RAISED"]
VIOLET = _DEFAULT_TOKENS["ACCENT"]
VIOLET_GLOW = _DEFAULT_TOKENS["ACCENT_SOFT"]
AMBER = _DEFAULT_TOKENS["AMBER"]
AMBER_GLOW = "rgba(210, 161, 109, 0.18)"
CYAN = _DEFAULT_TOKENS["CYAN"]
CYAN_GLOW = "rgba(138, 180, 189, 0.18)"
DANGER = _DEFAULT_TOKENS["DANGER"]
EMERALD = _DEFAULT_TOKENS["EMERALD"]
EMERALD_GLOW = "rgba(135, 173, 145, 0.18)"
SKY = _DEFAULT_TOKENS["SKY"]
SKY_GLOW = "rgba(140, 168, 199, 0.18)"
INK = _DEFAULT_TOKENS["WINDOW_TEXT"]
SECONDARY = _DEFAULT_TOKENS["SECONDARY"]
MUTED = _DEFAULT_TOKENS["MUTED"]
TABLE_TEXT = _DEFAULT_TOKENS["TABLE_TEXT"]
GLASS_BG = _DEFAULT_TOKENS["CARD_BG"]
GLASS_BG_HOVER = _DEFAULT_TOKENS["CARD_BG_HOVER"]
GLASS_BG_RAISED = _DEFAULT_TOKENS["CARD_RAISED"]
GLASS_BORDER = _DEFAULT_TOKENS["CARD_BORDER"]
GLASS_BORDER_STRONG = _DEFAULT_TOKENS["CARD_BORDER_STRONG"]
GLASS_BORDER_GLOW = _DEFAULT_TOKENS["CARD_BORDER_GLOW"]


def palette(theme_mode: str = DEFAULT_THEME_MODE) -> QPalette:
    t = _theme_tokens(theme_mode)
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(t["CHARCOAL"]))
    pal.setColor(QPalette.WindowText, QColor(t["WINDOW_TEXT"]))
    pal.setColor(QPalette.Base, QColor(t["SURFACE"]))
    pal.setColor(QPalette.AlternateBase, QColor(t["SURFACE_LIGHT"]))
    pal.setColor(QPalette.Text, QColor(t["WINDOW_TEXT"]))
    pal.setColor(QPalette.Button, QColor(t["SURFACE_RAISED"]))
    pal.setColor(QPalette.ButtonText, QColor(t["WINDOW_TEXT"]))
    pal.setColor(QPalette.Highlight, QColor(t["ACCENT"]))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff" if normalize_theme_mode(theme_mode) == "light" else "#101318"))
    pal.setColor(QPalette.ToolTipBase, QColor(t["SURFACE_RAISED"]))
    pal.setColor(QPalette.ToolTipText, QColor(t["WINDOW_TEXT"]))
    pal.setColor(QPalette.Link, QColor(t["SKY"]))
    return pal


def apply_theme(app: QApplication, theme_mode: str = DEFAULT_THEME_MODE) -> str:
    mode = normalize_theme_mode(theme_mode)
    app.setProperty("theme_mode", mode)
    app.setPalette(palette(mode))
    app.setStyleSheet(stylesheet(mode))
    return mode


def stylesheet(theme_mode: str = DEFAULT_THEME_MODE) -> str:
    mode = normalize_theme_mode(theme_mode)
    t = _theme_tokens(mode)
    return f"""
    QWidget {{
        background: transparent;
        color: {t["WINDOW_TEXT"]};
        font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif;
        font-size: 10pt;
        font-weight: 500;
        letter-spacing: 0px;
        outline: 0;
    }}

    QMainWindow, QDialog {{
        background: {t["WINDOW_BG"]};
    }}

    QToolTip {{
        background: {t["CARD_RAISED"]};
        color: {t["WINDOW_TEXT"]};
        border: 1px solid {t["CARD_BORDER"]};
        padding: 6px 8px;
    }}

    QWidget#titleBar {{
        background: {t["TITLEBAR_BG"]};
        border-bottom: 1px solid {t["TITLEBAR_BORDER"]};
    }}

    QLabel#appTitle {{
        color: {t["WINDOW_TEXT"]};
        font-size: 11.8pt;
        font-weight: 700;
        letter-spacing: 0.6px;
    }}

    QFrame#navigationBar {{
        background: {t["NAV_BG"]};
        border: 1px solid {t["NAV_BORDER"]};
        border-radius: 18px;
    }}

    QFrame#windowControls {{
        background: {t["NAV_BG"]};
        border: 1px solid {t["NAV_BORDER"]};
        border-radius: 14px;
    }}

    QWidget[navItem="true"] {{
        background: transparent;
        border-radius: 14px;
    }}

    QPushButton#navButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 12px;
        padding: 0 16px;
        color: {t["NAV_TEXT"]};
        font-size: 9.3pt;
        font-weight: 600;
        min-height: 24px;
    }}

    QPushButton#navButton:hover {{
        background: {t["NAV_HOVER_BG"]};
        color: {t["WINDOW_TEXT"]};
    }}

    QPushButton#navButton[active="true"] {{
        background: {t["NAV_ACTIVE_BG"]};
        border-color: {t["NAV_ACTIVE_BORDER"]};
        color: {t["WINDOW_TEXT"]};
    }}

    QLabel#navAlertBadge {{
        background: {t["NAV_BADGE_BG"]};
        border: 1px solid {t["NAV_BADGE_BORDER"]};
        border-radius: 10px;
        color: {t["DANGER"]};
        font-size: 7.2pt;
        font-weight: 800;
        padding: 0 4px;
    }}

    QPushButton#winControl,
    QPushButton#winControl_close {{
        background: {t["CONTROL_BG"]};
        border: 1px solid {t["CONTROL_BORDER"]};
        border-radius: 11px;
        color: {t["SECONDARY"]};
        font-size: 1pt;
        font-weight: 700;
        padding: 0;
        min-width: 30px;
        max-width: 30px;
        min-height: 30px;
        max-height: 30px;
    }}

    QPushButton#winControl:hover {{
        background: {t["CONTROL_HOVER_BG"]};
        border-color: {t["NAV_ACTIVE_BORDER"]};
        color: {t["WINDOW_TEXT"]};
    }}

    QPushButton#winControl_close:hover {{
        background: {t["CONTROL_CLOSE_BG"]};
        border-color: {t["NAV_BADGE_BORDER"]};
        color: {t["DANGER"]};
    }}

    QPushButton#winControl:pressed,
    QPushButton#winControl_close:pressed {{
        background: {t["CARD_RAISED"]};
    }}

    QTabWidget#mainTabs::pane {{
        border: none;
    }}

    QTabBar::tab {{
        width: 0;
        height: 0;
        padding: 0;
        margin: 0;
        border: none;
    }}

    QFrame#heroBanner {{
        background: {t["HERO_BG"]};
        border: 1px solid {t["HERO_BORDER"]};
        border-top: 1px solid {t["CARD_BORDER_STRONG"]};
        border-radius: 24px;
    }}

    QLabel[class="heroTitle"] {{
        font-size: 12pt;
        font-weight: 700;
        color: {t["WINDOW_TEXT"]};
        letter-spacing: 0.2px;
        {"letter-spacing: 0px;" if mode == "blueprint" else ""}
    }}

    QLabel[class="heroChip"], QLabel#heroTargetChip {{
        border-radius: 13px;
        padding: 4px 11px;
        font-size: 8pt;
        font-weight: 700;
        letter-spacing: 0.2px;
    }}

    QLabel[class="heroChip"] {{
        background: rgba(138, 180, 189, 0.12);
        border: 1px solid rgba(138, 180, 189, 0.18);
        color: {t["CYAN"]};
    }}

    QLabel#heroTargetChip[variant="neutral"] {{
        background: {t["ACCENT_SOFT"]};
        border: 1px solid {t["ACCENT_LINE"]};
        color: {t["SECONDARY"]};
    }}

    QLabel#heroTargetChip[variant="status_new"] {{
        background: rgba(208, 122, 114, 0.12);
        border: 1px solid rgba(208, 122, 114, 0.18);
        color: {t["DANGER"]};
    }}

    QLabel#heroTargetChip[variant="status_progress"] {{
        background: rgba(210, 161, 109, 0.12);
        border: 1px solid rgba(210, 161, 109, 0.18);
        color: {t["AMBER"]};
    }}

    QLabel#heroTargetChip[variant="status_answered_me"] {{
        background: rgba(135, 173, 145, 0.12);
        border: 1px solid rgba(135, 173, 145, 0.18);
        color: {t["EMERALD"]};
    }}

    QLabel#heroTargetChip[variant="status_answered_other"] {{
        background: rgba(140, 168, 199, 0.12);
        border: 1px solid rgba(140, 168, 199, 0.18);
        color: {t["SKY"]};
    }}

    QFrame[class="glassPanel"], QFrame#card, QGroupBox,
    QFrame[contentCard="true"] {{
        background: {t["CARD_BG"]};
        border: 1px solid {t["CARD_BORDER"]};
        border-top: 1px solid {t["CARD_BORDER_STRONG"]};
        border-radius: 18px;
    }}
    QFrame[class="glassPanel"]:hover, QFrame#card:hover, QGroupBox:hover,
    QFrame[contentCard="true"]:hover {{
        background: {t["CARD_BG_HOVER"]};
        border-color: {t["CARD_BORDER_GLOW"]};
    }}

    QScrollArea#embeddedScrollArea {{
        background: {t["ACCENT_SOFT"]};
        border: 1px solid {t["CARD_BORDER"]};
        border-radius: 24px;
    }}

    QWidget#embeddedScrollViewport,
    QWidget#settingsScrollAreaViewport,
    QWidget#embeddedScrollHost,
    QWidget#settingsScrollAreaHost {{
        background: transparent;
        border: none;
    }}

    QScrollArea#settingsScrollArea {{
        background: transparent;
        border: none;
    }}

    QFrame[class="statsCard"] {{
        background: {t["CARD_RAISED"]};
        border: 1px solid {t["CARD_BORDER"]};
        border-radius: 18px;
        min-width: 136px;
    }}

    QLabel[class="statsValue"] {{
        font-size: 18pt;
        font-weight: 700;
        color: {t["WINDOW_TEXT"]};
        {"letter-spacing: 0px;" if mode == "blueprint" else ""}
    }}

    QLabel[class="statsLabel"] {{
        color: {t["MUTED"]};
        font-size: 8.2pt;
        font-weight: 700;
        {"letter-spacing: 0px;" if mode == "blueprint" else ""}
    }}

    QFrame[class="kpiCard"] {{
        background: {t["CARD_RAISED"]};
        border: 1px solid {t["CARD_BORDER"]};
        border-radius: 18px;
        min-width: 144px;
        padding: 4px;
    }}

    QLabel[class="kpiLabel"] {{
        color: {t["MUTED"]};
        font-size: 8.8pt;
        font-weight: 600;
    }}

    QLabel[class="kpiValue"] {{
        color: {t["WINDOW_TEXT"]};
        font-size: 22pt;
        font-weight: 700;
        {"letter-spacing: 0px;" if mode == "blueprint" else ""}
    }}

    QLabel[class="sectionTitle"] {{
        font-size: 15.8pt;
        font-weight: 700;
        color: {t["WINDOW_TEXT"]};
        letter-spacing: 0.1px;
        {"letter-spacing: 0px;" if mode == "blueprint" else ""}
    }}

    QLabel[formLabel="true"] {{
        color: {t["MUTED"]};
        font-size: 8.1pt;
        font-weight: 700;
        letter-spacing: 0.3px;
        padding-right: 8px;
    }}

    QLabel[class="muted"] {{
        color: {t["MUTED"]};
    }}

    QLabel[class="status_new"],
    QLabel[class="status_progress"],
    QLabel[class="status_answered_me"],
    QLabel[class="status_answered_other"],
    QLabel#reportCountBadge {{
        border-radius: 13px;
        padding: 5px 12px;
        font-weight: 700;
        letter-spacing: 0.1px;
    }}

    QLabel#reportCountBadge {{
        font-size: 8.3pt;
    }}

    QLabel#reportCountBadge[variant="warning"] {{
        background: rgba(210, 161, 109, 0.12);
        border: 1px solid rgba(210, 161, 109, 0.18);
        color: {t["AMBER"]};
    }}

    QLabel#reportCountBadge[variant="success"] {{
        background: rgba(135, 173, 145, 0.12);
        border: 1px solid rgba(135, 173, 145, 0.18);
        color: {t["EMERALD"]};
    }}

    QLabel#reportCountBadge[variant="empty"] {{
        background: {t["ACCENT_SOFT"]};
        border: 1px solid {t["ACCENT_LINE"]};
        color: {t["SECONDARY"]};
    }}

    QLabel[class="status_new"] {{
        background: rgba(208, 122, 114, 0.12);
        border: 1px solid rgba(208, 122, 114, 0.18);
        color: {t["DANGER"]};
    }}

    QLabel[class="status_progress"] {{
        background: rgba(210, 161, 109, 0.12);
        border: 1px solid rgba(210, 161, 109, 0.18);
        color: {t["AMBER"]};
    }}

    QLabel[class="status_answered_me"] {{
        background: rgba(135, 173, 145, 0.12);
        border: 1px solid rgba(135, 173, 145, 0.18);
        color: {t["EMERALD"]};
    }}

    QLabel[class="status_answered_other"] {{
        background: rgba(140, 168, 199, 0.12);
        border: 1px solid rgba(140, 168, 199, 0.18);
        color: {t["SKY"]};
    }}

    QLabel#statusBadge {{
        border-radius: 12px;
        padding: 0 10px;
        font-size: 7.5pt;
        font-weight: 700;
        letter-spacing: 0.2px;
    }}

    QLabel#statusBadge[variant="status_new"] {{
        background: rgba(208, 122, 114, 0.12);
        border: 1px solid rgba(208, 122, 114, 0.18);
        color: {t["DANGER"]};
    }}

    QLabel#statusBadge[variant="status_progress"] {{
        background: rgba(210, 161, 109, 0.12);
        border: 1px solid rgba(210, 161, 109, 0.18);
        color: {t["AMBER"]};
    }}

    QLabel#statusBadge[variant="status_answered_me"] {{
        background: rgba(135, 173, 145, 0.12);
        border: 1px solid rgba(135, 173, 145, 0.18);
        color: {t["EMERALD"]};
    }}

    QLabel#statusBadge[variant="status_answered_other"] {{
        background: rgba(140, 168, 199, 0.12);
        border: 1px solid rgba(140, 168, 199, 0.18);
        color: {t["SKY"]};
    }}

    QFrame#playerInfoCard {{
        background: {t["CARD_RAISED"]};
        border: 1px solid {t["CARD_BORDER"]};
        border-radius: 20px;
    }}

    QFrame#playerInfoCard[variant="status_new"] {{
        border-color: rgba(208, 122, 114, 0.18);
    }}

    QFrame#playerInfoCard[variant="status_progress"] {{
        border-color: rgba(210, 161, 109, 0.18);
    }}

    QFrame#playerInfoCard[variant="status_answered_me"] {{
        border-color: rgba(135, 173, 145, 0.18);
    }}

    QFrame#playerInfoCard[variant="status_answered_other"] {{
        border-color: rgba(140, 168, 199, 0.18);
    }}

    QLabel#playerAvatar {{
        background: rgba(210, 161, 109, 0.16);
        border-radius: 18px;
        border: 1px solid rgba(210, 161, 109, 0.14);
        font-size: 13pt;
        font-weight: 700;
    }}

    QLabel#playerNameLabel {{
        font-weight: 700;
        font-size: 11pt;
        letter-spacing: 0.2px;
    }}

    QLabel#playerIdLabel {{
        font-size: 8.9pt;
        font-weight: 600;
        color: {t["MUTED"]};
    }}

    QPushButton {{
        background: {t["BUTTON_BG"]};
        border: 1px solid {t["BUTTON_BORDER"]};
        border-radius: 12px;
        padding: 0 14px;
        color: {t["BUTTON_TEXT"]};
        font-size: 8.9pt;
        font-weight: 600;
        min-height: 34px;
        {"letter-spacing: 0px;" if mode == "blueprint" else ""}
    }}

    QPushButton:hover {{
        background: {t["BUTTON_HOVER_BG"]};
        border-color: {t["NAV_ACTIVE_BORDER"]};
        color: {t["WINDOW_TEXT"]};
    }}

    QPushButton:pressed {{
        background: {t["CARD_RAISED"]};
    }}

    QPushButton:focus {{
        border-color: {t["BUTTON_BORDER"]};
    }}

    QPushButton:disabled {{
        color: {t["MUTED"]};
        background: {t["CARD_RAISED"]};
    }}

    QPushButton[class="primaryAction"] {{
        background:
            qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {t["PRIMARY_BG_TOP"]},
                stop:1 {t["PRIMARY_BG_BOTTOM"]});
        border: 1px solid {t["PRIMARY_BORDER"]};
        color: {t["PRIMARY_TEXT"]};
    }}

    QPushButton[class="primaryAction"]:hover {{
        background:
            qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {t["PRIMARY_HOVER_TOP"]},
                stop:1 {t["PRIMARY_HOVER_BOTTOM"]});
    }}

    QPushButton[class="secondaryAction"] {{
        background: {t["SECONDARY_BG"]};
        border: 1px solid {t["BUTTON_BORDER"]};
        color: {t["SECONDARY_TEXT"]};
    }}

    QPushButton[class="secondaryAction"]:hover {{
        background: {t["SECONDARY_HOVER_BG"]};
    }}

    QPushButton[class="dangerGhost"] {{
        background: {t["DANGER_BG"]};
        border: 1px solid {t["DANGER_BORDER"]};
        color: {t["DANGER"]};
    }}

    QPushButton[class="dangerGhost"]:hover {{
        background: {t["DANGER_HOVER_BG"]};
        border-color: {t["NAV_BADGE_BORDER"]};
    }}

    QPushButton[chipAction="true"],
    QPushButton#quickReplyButton {{
        background: transparent;
        border: 1px solid {t["ACCENT_LINE"]};
        border-radius: 14px;
        padding: 0 12px;
        min-height: 30px;
        color: {t["SECONDARY"]};
        font-size: 8.5pt;
        font-weight: 600;
        {"letter-spacing: 0px;" if mode == "blueprint" else ""}
    }}

    QPushButton[chipAction="true"]:hover,
    QPushButton#quickReplyButton:hover {{
        background: {t["ACCENT_SOFT"]};
        border-color: {t["CARD_BORDER_GLOW"]};
        color: {t["WINDOW_TEXT"]};
    }}

    QPushButton[chipAction="true"]:pressed,
    QPushButton#quickReplyButton:pressed {{
        background: {t["COMBO_POPUP_SELECTED"]};
    }}

    QLineEdit, QPlainTextEdit, QTableWidget, QComboBox {{
        background: {t["INPUT_BG"]};
        border: 1px solid {t["INPUT_BORDER"]};
        border-radius: 12px;
        padding: 8px 12px;
        selection-background-color: {t["INPUT_SELECTION"]};
        selection-color: {t["WINDOW_TEXT"]};
        {"letter-spacing: 0px;" if mode == "blueprint" else ""}
    }}

    QLineEdit, QComboBox {{
        min-height: 26px;
    }}

    QLineEdit:focus, QPlainTextEdit:focus, QTableWidget:focus, QComboBox:focus {{
        border: 2px solid {t["INPUT_FOCUS"]};
    }}

    QComboBox {{
        padding-right: 32px;
    }}

    QComboBox:hover {{
        background: {t["COMBO_HOVER_BG"]};
    }}

    QComboBox::drop-down {{
        width: 30px;
        border: none;
        border-left: 1px solid {t["ACCENT_LINE"]};
        background: transparent;
    }}

    QComboBox::down-arrow {{
        image: url({t["CHEVRON_ICON"]});
        width: 12px;
        height: 12px;
    }}

    QComboBox QAbstractItemView {{
        background: {t["COMBO_POPUP_BG"]};
        border: 1px solid {t["INPUT_BORDER"]};
        selection-background-color: {t["COMBO_POPUP_SELECTED"]};
        selection-color: {t["WINDOW_TEXT"]};
        outline: 0;
        padding: 4px;
    }}

    QComboBox QAbstractItemView::item {{
        min-height: 26px;
        padding: 4px 8px;
        border-radius: 8px;
    }}

    QComboBox QAbstractItemView::item:hover {{
        background: {t["COMBO_POPUP_HOVER"]};
    }}

    QPlainTextEdit#reportPreview,
    QPlainTextEdit#vipAdPreview,
    QPlainTextEdit#aiReplyPreview {{
        background: {t["INPUT_BG"]};
        border: 1px solid {t["INPUT_BORDER"]};
        border-radius: 18px;
        font-size: 10.6pt;
        padding: 12px;
    }}

    QPlainTextEdit#replyComposer {{
        background: {t["INPUT_BG"]};
        border: 1px solid {t["ACCENT_LINE"]};
        border-radius: 18px;
        font-size: 11pt;
    }}

    QLineEdit#vipCommandPreview {{
        background: {t["INPUT_BG_SOFT"]};
        border: 1px solid rgba(210, 161, 109, 0.16);
        font-weight: 600;
        color: {t["WINDOW_TEXT"]};
    }}

    QTableWidget#reportTable,
    QTableWidget#vipAdTable,
    QTableWidget#bindTable {{
        background: {t["TABLE_BG"]};
        alternate-background-color: {t["TABLE_ALT_BG"]};
        gridline-color: {t["CARD_BORDER"]};
        border: 1px solid {t["CARD_BORDER"]};
        border-radius: 14px;
    }}

    QTableWidget::item {{
        padding: 8px 6px;
        color: {t["TABLE_TEXT"]};
        border: none;
        border-bottom: 1px solid {t["CARD_BORDER"]};
    }}

    QTableWidget::item:selected {{
        background: transparent;
        color: {t["WINDOW_TEXT"]};
    }}

    QHeaderView::section {{
        background: {t["TABLE_HEADER_BG"]};
        border: none;
        border-bottom: 2px solid {t["INPUT_BORDER"]};
        padding: 12px 10px;
        color: {t["TABLE_HEADER_TEXT"]};
        font-size: 9pt;
        font-weight: 600;
        {"letter-spacing: 0px;" if mode == "blueprint" else ""}
    }}

    QTableCornerButton::section {{
        background: {t["TABLE_HEADER_BG"]};
        border: none;
        border-bottom: 2px solid {t["INPUT_BORDER"]};
    }}

    QSplitter#reportSplitter::handle {{
        background: {t["SPLITTER"]};
        border-radius: 4px;
        margin: 86px 3px;
        border: 2px solid {t["SPLITTER_HOVER"]};
    }}

    QSplitter#reportSplitter::handle:hover {{
        background: {t["SPLITTER_HOVER"]};
    }}

    QGroupBox {{
        margin-top: 14px;
        padding: 18px;
        font-weight: 700;
        color: {t["WINDOW_TEXT"]};
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 8px;
        color: {t["SECONDARY"]};
    }}

    QCheckBox {{
        spacing: 10px;
        min-height: 24px;
        padding: 2px 0;
        color: {t["WINDOW_TEXT"]};
        font-weight: 600;
    }}

    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 6px;
        border: 1px solid {t["CHECK_BORDER"]};
        background: {t["CHECK_BG"]};
    }}

    QCheckBox::indicator:hover {{
        border-color: {t["INPUT_FOCUS"]};
    }}

    QCheckBox::indicator:checked {{
        background: {t["CHECK_ACTIVE_BG"]};
        border-color: {t["CHECK_ACTIVE_BORDER"]};
        image: url({t["CHECK_ICON"]});
    }}

    QRadioButton {{
        spacing: 8px;
        color: {t["WINDOW_TEXT"]};
        font-weight: 600;
    }}

    QRadioButton::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 9px;
        border: 1px solid {t["CHECK_BORDER"]};
        background: {t["CHECK_BG"]};
    }}

    QRadioButton::indicator:hover {{
        border-color: {t["INPUT_FOCUS"]};
    }}

    QRadioButton::indicator:checked {{
        background: {t["RADIO_ACTIVE_BG"]};
        border-color: {t["RADIO_ACTIVE_BORDER"]};
        image: url({t["RADIO_ICON"]});
    }}

    QStatusBar {{
        background: {t["STATUSBAR_BG"]};
        border-top: 3px solid {t["STATUSBAR_BORDER"]};
        color: {t["MUTED"]};
        {"letter-spacing: 0px;" if mode == "blueprint" else ""}
    }}

    QStatusBar::item {{
        border: none;
    }}

    QScrollBar:vertical, QScrollBar:horizontal {{
        background: transparent;
        margin: 6px;
    }}

    QScrollBar:vertical {{
        width: 12px;
    }}

    QScrollBar:horizontal {{
        height: 12px;
    }}

    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {t["SCROLL_HANDLE"]};
        border-radius: 5px;
        min-height: 32px;
        min-width: 32px;
        border: 2px solid {t["SCROLL_HANDLE_HOVER"]};
    }}

    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
        background: {t["SCROLL_HANDLE_HOVER"]};
        border: 3px solid {t["SCROLL_HANDLE"]};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
        height: 0;
    }}
    """
