from __future__ import annotations

from importlib.machinery import SourcelessFileLoader
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import logging
import re
import threading
import time
import warnings
from functools import partial

try:
    import winsound
except ImportError:
    winsound = None

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRect, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..ai_responder import AIReportResponder, GeneratedAIReply, SharedAIService
from ..appointments import (
    ACTION_APPOINT,
    ACTION_REMOVE,
    AppointmentActionResult,
    AppointmentConfig,
    AppointmentRecord,
    AppointmentService,
    ROLE_DEPUTY,
    ROLE_LEADER,
    ROLE_WATCHER,
    load_appointment_config,
    project_number_for_record,
    save_appointment_config,
)
from ..game import BackgroundSender
from ..hotkeys import GlobalHotkeyManager
from ..log_watcher import ConsoleLogWatcher
from ..models import BindConfig, Report, VipAdAlert, VipChatMessage
from ..optimization import OptimizationManager, OptimizationSnapshot, OptimizationState
from ..parser import parse_line
from ..paths import asset_path
from ..player_lookup import PlayerLookupError, PlayerLookupResult, lookup_player
from ..report_store import ReportStore
from ..settings import load_settings, save_settings
from ..state import load_dismissed_signatures, load_dismissed_vip_signatures, save_dismissed_signatures
from ..supabase_sync import SupabaseSync
from ..telegram_notifier import (
    REPORT_THRESHOLD,
    REPORT_THRESHOLD_THREAD_ID,
    VIP_CLEAN_THREAD_ID,
    VIP_FALSE_POSITIVE_THREAD_ID,
    VIP_PUNISHMENT_THREAD_ID,
    TelegramForumNotifier,
    format_report_threshold_message,
    format_vip_clean_message,
    format_vip_false_positive_message,
    format_vip_punishment_message,
)
from ..theme import AMBER, CYAN, DANGER, EMERALD, INK, MUTED, SECONDARY, SKY, VIOLET, apply_theme, normalize_theme_mode
from ..vip_ad_store import VipAdStore
from ..vip_ads import VipAdDetector
from .bind_dialog import BindDialog, HotkeyLineEdit
from .composition import apply_blur
from .icon_pack import make_icon, window_control_icon


def _load_recovered_module():
    module_name = "atools.ui._main_window_full"
    pyc_path = Path(__file__).with_name("main_window_full.pyc")
    if not pyc_path.exists():
        # Fallback: define dummy classes
        from PySide6.QtGui import QPainter, QPen, QBrush, QFont
        
        class AIReplyThread(QThread):
            finished = Signal(str)
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
        
        class MainWindow(QMainWindow):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.SETTINGS_TAB_INDEX = 4
                self.settings = type('Settings', (), {'vip_ad_punish_mode': 'admin'})()  # dummy settings object
                # Add basic UI
                self.setWindowTitle("RichCore V12")
                self.setGeometry(100, 100, 800, 600)
                central_widget = QWidget()
                self.setCentralWidget(central_widget)
                layout = QVBoxLayout(central_widget)
                label = QLabel("RichCore V12 - Basic UI")
                layout.addWidget(label)
                self.show()
            # Add dummy methods
            def _build_general_settings_group(self, *args, **kwargs): pass
            def _load_settings_into_ui(self, *args, **kwargs): pass
            def _save_settings_from_ui(self, *args, **kwargs): pass
            def _on_nav_clicked(self, *args, **kwargs): pass
        
        return type('DummyModule', (), {
            'AIReplyThread': AIReplyThread, 
            'MainWindow': MainWindow,
            'QLineEdit': QLineEdit,
            'QFrame': QFrame,
            'QLabel': QLabel,
            'QPushButton': QPushButton,
            'QVBoxLayout': QVBoxLayout,
            'QHBoxLayout': QHBoxLayout,
            'QGridLayout': QGridLayout,
            'QScrollArea': QScrollArea,
            'QSplitter': QSplitter,
            'QTabWidget': QTabWidget,
            'QTableWidget': QTableWidget,
            'QTableWidgetItem': QTableWidgetItem,
            'QCheckBox': QCheckBox,
            'QComboBox': QComboBox,
            'QPlainTextEdit': QPlainTextEdit,
            'QGroupBox': QGroupBox,
            'QFormLayout': QFormLayout,
            'QSizePolicy': QSizePolicy,
            'QGraphicsDropShadowEffect': QGraphicsDropShadowEffect,
            'QGraphicsOpacityEffect': QGraphicsOpacityEffect,
            'QMouseEvent': QMouseEvent,
            'QEvent': QEvent,
            'QPoint': QPoint,
            'QSize': QSize,
            'QRect': QRect,
            'QPropertyAnimation': QPropertyAnimation,
            'QEasingCurve': QEasingCurve,
            'QCursor': QCursor,
            'QPainter': QPainter,
            'QPen': QPen,
            'QBrush': QBrush,
            'QColor': QColor,
            'QPixmap': QPixmap,
            'QPainter': QPainter,
            'QPen': QPen,
            'QBrush': QBrush,
            'QFont': QFont,
            'QMainWindow': QMainWindow,
            'QWidget': QWidget,
            'QThread': QThread,
            'QTimer': QTimer,
            'Signal': Signal,
            'Qt': Qt,
        })()

    loader = SourcelessFileLoader(module_name, str(pyc_path))
    spec = spec_from_file_location(module_name, pyc_path, loader=loader)
    if spec is None:
        raise ImportError(f"Failed to create import spec for {pyc_path}")

    module = module_from_spec(spec)
    if module is None:
        raise ImportError(f"Failed to create import spec for {pyc_path}")
    module.__package__ = "atools.ui"
    try:
        loader.exec_module(module)
    except ImportError as exc:
        if "bad magic number" in str(exc).lower():
            raise ImportError(
                "The UI bytecode main_window_full.pyc was compiled for a different Python version. "
                "Run this application with Python 3.14."
            ) from exc
        raise
    return module


_RECOVERED = _load_recovered_module()
AIReplyThread = _RECOVERED.AIReplyThread
MainWindow = _RECOVERED.MainWindow
_LOGGER = logging.getLogger(__name__)

_REPORTS_TAB_INDEX = 0
_VIP_TAB_INDEX = 1
_BINDS_TAB_INDEX = 2
_OPTIMIZATION_TAB_INDEX = 3
_SETTINGS_TAB_INDEX = 4
_PLAYERS_TAB_FALLBACK_INDEX = 5
_APPOINTMENTS_TAB_FALLBACK_INDEX = 6
_REMOVALS_TAB_FALLBACK_INDEX = 7
_TEST_TAB_FALLBACK_INDEX = 8

_OFFLINE_MARKERS = (
    "не в мережі",
    "немає в мережі",
    "гравця немає",
    "гравець не знайдений",
    "гравця не знайдено",
    "не знайдено гравця",
    "not online",
    "offline",
    "not found",
)

_TEST_ACTIONS = (
    ("pm", "Відповідь на репорт"),
    ("warn", "Warn"),
    ("pban", "Бан"),
    ("mute", "Mute"),
    ("pmute", "PMute"),
    ("jail", "Деморган"),
    ("pkick", "Кік"),
    ("pwarp", "pwarp"),
    ("sp", "sp"),
    ("custom", "Своя команда"),
)

_FACTION_OPTIONS = (
    "1 - ЗСУ",
    "2 - СБУ",
    "3 - НПУ",
    "4 - МОЗ",
    "7 - ВРУ",
    "9 - ДКВС",
    "10 - ДСНС",
    "11 - ЗМІ",
    "12 - УЗ",
)

_SECTION_CONTEXT = {
    _REPORTS_TAB_INDEX: (
        "Репорти",
        "Операторська черга",
        "Швидкі відповіді, AI-чернетка та контроль активних звернень в одному робочому просторі.",
    ),
    _VIP_TAB_INDEX: (
        "VIP чат",
        "Модерація VIP-оголошень",
        "Перегляд спрацювань, готова команда покарання та акуратна ручна перевірка.",
    ),
    _BINDS_TAB_INDEX: (
        "Бінди",
        "Готові команди",
        "Шаблони відповідей і службові бінди, зібрані в два чисті робочі блоки.",
    ),
    _OPTIMIZATION_TAB_INDEX: (
        "Оптимізація",
        "FPS workstation",
        "Стан системи, швидкі дії та пакет твіків без візуального шуму.",
    ),
    _SETTINGS_TAB_INDEX: (
        "Налаштування",
        "Профіль та гарячі клавіші",
        "Основні параметри програми, шляхи та глобальні комбінації для щоденної роботи.",
    ),
    _PLAYERS_TAB_FALLBACK_INDEX: (
        "Гравці",
        "Керування гравцем",
        "Пошук ID, покарання, зняття та фракції з offline fallback для консольних команд.",
    ),
    _APPOINTMENTS_TAB_FALLBACK_INDEX: (
        "Призначення",
        "Лідери, заступники, слідкуючі",
        "Черга Google Forms, GitHub Projects, Telegram-нагадування та готові службові оголошення.",
    ),
    _REMOVALS_TAB_FALLBACK_INDEX: (
        "Зняття",
        "Пошук активних призначених",
        "Пошук у GitHub Projects, причина зняття, Telegram-нагадування та оновлення карток.",
    ),
    _TEST_TAB_FALLBACK_INDEX: (
        "Тест",
        "Перевірка команд",
        "Безпечна тестова відправка в консоль через say перед PM або покаранням.",
    ),
}


def _repolish(widget: QWidget | None) -> None:
    if widget is None:
        return
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


def _detach_widget(widget: QWidget | None) -> None:
    if widget is None:
        return
    parent = widget.parentWidget()
    if parent is not None and parent.layout() is not None:
        parent.layout().removeWidget(widget)
    widget.hide()
    widget.setParent(None)
    widget.deleteLater()


def _remove_labels_by_text(root: QWidget, texts: set[str]) -> None:
    for label in root.findChildren(QLabel):
        if label.text().strip() in texts:
            _detach_widget(label)


def _find_parent_form_layout(widget: QWidget | None) -> QFormLayout | None:
    if widget is None:
        return None
    try:
        current = widget.parentWidget()
    except RuntimeError:
        return None
    while current is not None:
        layout = current.layout()
        if isinstance(layout, QFormLayout):
            return layout
        current = current.parentWidget()
    return None


def _hide_form_row(widget: QWidget | None) -> None:
    if widget is None:
        return
    layout = _find_parent_form_layout(widget)
    label = None
    if layout is not None:
        try:
            label = layout.labelForField(widget)
        except Exception:
            label = None

    for candidate in (label, widget):
        if candidate is None:
            continue
        try:
            candidate.hide()
            candidate.setMaximumHeight(0)
            candidate.setMinimumHeight(0)
            candidate.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        except RuntimeError:
            continue


def _set_radio_checked(radio: QRadioButton | None, checked: bool) -> None:
    if radio is None:
        return
    was_blocked = radio.blockSignals(True)
    radio.setChecked(checked)
    radio.blockSignals(was_blocked)


def _strip_slash_command(command: str) -> str:
    normalized = command.strip()
    if normalized.startswith("/"):
        return normalized[1:]
    return normalized


def _direct_children(parent: QWidget, widget_type: type[QWidget]) -> list[QWidget]:
    return parent.findChildren(widget_type, options=Qt.FindChildOption.FindDirectChildrenOnly)


def _first_label_by_text(root: QWidget, text: str) -> QLabel | None:
    for label in root.findChildren(QLabel):
        if label.text().strip() == text:
            return label
    return None


def _first_button_by_text(root: QWidget, text: str) -> QPushButton | None:
    for button in root.findChildren(QPushButton):
        if button.text().strip() == text:
            return button
    return None


def _rename_label(root: QWidget, old_text: str, new_text: str) -> None:
    label = _first_label_by_text(root, old_text)
    if label is not None:
        label.setText(new_text)


def _rename_button(root: QWidget, old_text: str, new_text: str) -> None:
    button = _first_button_by_text(root, old_text)
    if button is not None:
        button.setText(new_text)


def _set_panel_style(widget: QWidget | None, *, object_name: str | None = None) -> None:
    if widget is None:
        return
    if object_name:
        widget.setObjectName(object_name)
    widget.setProperty("workspacePanel", True)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    _repolish(widget)


def _ensure_button_class(button: QPushButton | None, class_name: str) -> None:
    if button is None:
        return
    button.setProperty("class", class_name)
    _repolish(button)


def _normalized_button_text(button: QPushButton | None) -> str:
    if button is None:
        return ""
    return button.text().strip().replace("  ", " ").casefold()


def _apply_action_button_classes(self: MainWindow) -> None:
    primary_texts = {
        "зберегти",
        "зберегти всі налаштування",
        "відправити відповідь",
        "зберегти всі налаштування",
        "додати",
        "застосувати fps-пакет",
        "видати покарання",
    }
    secondary_texts = {
        "огляд",
        "редагувати",
        "відповідь колеги",
        "вставити текст ai",
        "телепорт",
        "на форум",
        "оновити аналіз",
        "підняти пріоритет gta зараз",
        "відкинути спрацювання",
        "скасувати",
    }
    danger_texts = {
        "видалити",
        "очистити весь список",
        "повернути стандарт",
    }

    for button in self.findChildren(QPushButton):
        if button.objectName() in {"navButton", "winControl", "winControl_close"}:
            continue
        text = _normalized_button_text(button)
        if not text:
            continue
        if text in primary_texts or text.startswith("застосувати"):
            _ensure_button_class(button, "primaryAction")
        elif text in danger_texts:
            _ensure_button_class(button, "dangerGhost")
        elif text in secondary_texts:
            _ensure_button_class(button, "secondaryAction")


def _settings_form_container(group: QWidget | None) -> QWidget | None:
    if group is None:
        return None
    for child in group.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        if isinstance(child.layout(), QFormLayout):
            return child
    return None


def _theme_combo_index(combo: QComboBox, theme_mode: str) -> int:
    index = combo.findData(normalize_theme_mode(theme_mode))
    return index if index >= 0 else 0


_LIGHT_INLINE_STYLE_REPLACEMENTS = {
    "#eef2f6": "#1f2832",
    "#c5d0db": "#51606f",
    "#8c98a3": "#7f7d77",
    "#93a6bb": "#58697d",
    "#d2a16d": "#b88856",
    "#8ab4bd": "#6d9197",
    "rgba(255, 255, 255, 0.03)": "rgba(88, 105, 125, 0.06)",
    "rgba(255, 255, 255, 0.05)": "rgba(31, 40, 50, 0.10)",
    "rgba(255, 255, 255, 0.07)": "rgba(88, 105, 125, 0.12)",
    "rgba(255, 255, 255, 0.12)": "rgba(31, 40, 50, 0.10)",
}


def _retint_inline_stylesheet(style_sheet: str, theme_mode: str) -> str:
    if not style_sheet:
        return ""
    if normalize_theme_mode(theme_mode) != "light":
        return style_sheet

    retinted = style_sheet
    for old_value, new_value in _LIGHT_INLINE_STYLE_REPLACEMENTS.items():
        retinted = retinted.replace(old_value, new_value)
    return retinted


def _sync_inline_widget_styles(self: MainWindow, theme_mode: str) -> None:
    for widget in self.findChildren(QWidget):
        if not isinstance(widget, (QLabel, QPushButton)):
            continue

        current_style = widget.styleSheet()
        base_style = widget.property("_baseInlineStyle")
        if base_style is None:
            base_style = current_style
            widget.setProperty("_baseInlineStyle", base_style)

        if not isinstance(base_style, str):
            base_style = current_style

        if isinstance(widget, QPushButton) and widget.property("chipAction"):
            target_style = ""
        else:
            target_style = _retint_inline_stylesheet(base_style, theme_mode)

        if current_style != target_style:
            widget.setStyleSheet(target_style)
            _repolish(widget)


def _apply_selected_theme(self: MainWindow, theme_mode: str) -> None:
    app = QApplication.instance()
    if app is None:
        return
    mode = apply_theme(app, theme_mode)
    _sync_inline_widget_styles(self, mode)
    _sync_window_control_icons(self, mode)
    for widget in (self, self.centralWidget(), self.statusBar()):
        _repolish(widget)


def _preview_theme_mode(self: MainWindow) -> None:
    combo = getattr(self, "theme_mode_combo", None)
    if combo is None:
        return
    _apply_selected_theme(self, combo.currentData())


def _attach_theme_selector(self: MainWindow, group: QWidget | None) -> None:
    if getattr(self, "theme_mode_combo", None) is not None:
        return
    form_host = _settings_form_container(group)
    if form_host is None:
        return
    form = form_host.layout()
    if not isinstance(form, QFormLayout):
        return

    combo = QComboBox(form_host)
    combo.setObjectName("themeModeCombo")
    combo.addItem("Темна", "dark")
    combo.addItem("Світла", "light")
    combo.currentIndexChanged.connect(lambda _index: _preview_theme_mode(self))

    insert_row = max(form.rowCount() - 1, 0)
    form.insertRow(insert_row, "ТЕМА ІНТЕРФЕЙСУ", combo)
    self.theme_mode_combo = combo


def _sync_theme_selector(self: MainWindow) -> None:
    combo = getattr(self, "theme_mode_combo", None)
    if combo is None:
        return
    blocked = combo.blockSignals(True)
    combo.setCurrentIndex(_theme_combo_index(combo, getattr(self.settings, "theme_mode", "dark")))
    combo.blockSignals(blocked)


def _mark_chip_button(button: QPushButton | None) -> None:
    if button is None:
        return
    button.setObjectName("quickReplyButton")
    button.setProperty("class", "quickReply")
    button.setProperty("chipAction", "true")
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    _repolish(button)
    button.setMinimumHeight(30)
    button.setMaximumHeight(32)
    button.setFixedHeight(32)
    button.updateGeometry()


def _set_layout_spacing(widget: QWidget | None, *, margins: tuple[int, int, int, int], spacing: int) -> None:
    if widget is None or widget.layout() is None:
        return
    widget.layout().setContentsMargins(*margins)
    widget.layout().setSpacing(spacing)


def _drain_layout(layout) -> list[QWidget]:
    widgets: list[QWidget] = []
    while layout is not None and layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widgets.append(widget)
    return widgets


def _detail_frame_from_embedded_scroll(scroll: QWidget | None) -> QFrame | None:
    if not isinstance(scroll, QScrollArea):
        return None
    host = scroll.widget()
    if host is None:
        return None
    frames = _direct_children(host, QFrame)
    return frames[0] if frames else None


def _reorder_splitter_for_table_first(splitter: QSplitter | None, table_name: str) -> tuple[QWidget | None, QWidget | None]:
    if splitter is None or splitter.count() < 2:
        return (None, None)

    first = splitter.widget(0)
    second = splitter.widget(1)
    first_has_table = first.findChild(QTableWidget, table_name) is not None if first is not None else False
    second_has_table = second.findChild(QTableWidget, table_name) is not None if second is not None else False

    list_panel = first if first_has_table else second if second_has_table else first
    detail_panel = second if list_panel is first else first
    if list_panel is not None:
        splitter.insertWidget(0, list_panel)
    return (list_panel, detail_panel)


def _tune_table(table: QTableWidget | None) -> None:
    if table is None:
        return
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(42)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setStretchLastSection(True)
    _repolish(table)


def _set_header_text(table: QTableWidget, column: int, text: str) -> None:
    item = table.horizontalHeaderItem(column)
    if item is None:
        item = QTableWidgetItem(text)
        table.setHorizontalHeaderItem(column, item)
    else:
        item.setText(text)


def _configure_report_queue_table(table: QTableWidget | None) -> None:
    if table is None or table.columnCount() < 5:
        return

    visible_columns = {2, 4}
    for column in range(table.columnCount()):
        table.setColumnHidden(column, column not in visible_columns)

    _set_header_text(table, 2, "Нік")
    _set_header_text(table, 4, "Статус")

    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(4, 166)
    table.setMinimumWidth(330)
    for label in table.findChildren(QLabel, "statusBadge"):
        label.setMinimumWidth(132)
        label.setMaximumWidth(154)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        _repolish(label)
    _repolish(table)


def _normalize_count_badge(label: QLabel | None) -> None:
    if label is None:
        return
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    label.setMinimumHeight(28)
    label.setMaximumHeight(28)
    width = min(148, max(96, label.sizeHint().width() + 4))
    label.setMinimumWidth(width)
    label.setMaximumWidth(width)
    _repolish(label)


def _find_count_badge(panel: QWidget | None, *, active_only: bool = False) -> QLabel | None:
    if panel is None:
        return None
    direct = panel.findChild(QLabel, "reportCountBadge", options=Qt.FindChildOption.FindDirectChildrenOnly)
    if direct is not None and (not active_only or "актив" in direct.text().casefold()):
        return direct
    for label in panel.findChildren(QLabel, "reportCountBadge"):
        if active_only and "актив" not in label.text().casefold():
            continue
        return label
    return None


def _active_count_text(count: int) -> str:
    if count == 1:
        return "1 активне"
    last_two = count % 100
    last = count % 10
    if 11 <= last_two <= 14:
        return f"{count} активних"
    if 2 <= last <= 4:
        return f"{count} активні"
    return f"{count} активних"


def _sync_vip_active_badge(self: MainWindow) -> None:
    badge = getattr(self, "vip_alert_count_badge", None)
    if not isinstance(badge, QLabel):
        return
    store = getattr(self, "vip_store", None)
    rows = getattr(store, "rows", [])
    count = len(rows) if rows is not None else 0
    badge.setText(_active_count_text(count))
    badge.setProperty("variant", "warning" if count else "empty")
    _normalize_count_badge(badge)


def _build_queue_header(parent: QWidget, object_name: str, title: QLabel | None, badge: QLabel | None) -> QWidget | None:
    if title is None and badge is None:
        return None
    row, layout = _ensure_row_widget(parent, object_name, 10)
    row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    row.setMinimumHeight(30)
    row.setMaximumHeight(34)
    if title is not None:
        title.setWordWrap(False)
        title.setMinimumWidth(min(max(150, title.sizeHint().width() + 8), 260))
        title.setMaximumWidth(16777215)
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(title, 1, Qt.AlignmentFlag.AlignVCenter)
    else:
        layout.addStretch(1)
    if badge is not None:
        _normalize_count_badge(badge)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return row


def _apply_queue_table_fixups(self: MainWindow) -> None:
    _configure_report_queue_table(self.findChild(QTableWidget, "reportTable"))


def _update_shell_context(self: MainWindow, index: int) -> None:
    eyebrow, title, subtitle = _SECTION_CONTEXT.get(index, _SECTION_CONTEXT[_REPORTS_TAB_INDEX])
    eyebrow_label = getattr(self, "_section_eyebrow_label", None)
    title_label = getattr(self, "_section_title_label", None)
    subtitle_label = getattr(self, "_section_subtitle_label", None)
    if eyebrow_label is not None:
        eyebrow_label.setText(eyebrow)
    if title_label is not None:
        title_label.setText(title)
    if subtitle_label is not None:
        subtitle_label.setText(subtitle)


def _rebuild_shell(self: MainWindow) -> None:
    if getattr(self, "_shell_rebuilt", False):
        return

    central = self.centralWidget()
    root_layout = central.layout() if central is not None else None
    title_bar = self.findChild(QWidget, "titleBar")
    nav_frame = self.findChild(QFrame, "navigationBar")
    window_controls = self.findChild(QFrame, "windowControls")
    tabs = getattr(self, "tabs", None)
    if central is None or root_layout is None or title_bar is None or nav_frame is None or window_controls is None or tabs is None:
        return

    app_title = self.findChild(QLabel, "appTitle")
    logo_label = None
    for label in title_bar.findChildren(QLabel, options=Qt.FindChildOption.FindDirectChildrenOnly):
        if label is not app_title:
            logo_label = label
            break

    root_layout.removeWidget(title_bar)
    root_layout.removeWidget(tabs)

    shell = QFrame(central)
    shell.setObjectName("appShell")
    shell.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    shell_layout = QHBoxLayout(shell)
    shell_layout.setContentsMargins(18, 16, 18, 10)
    shell_layout.setSpacing(18)

    side_rail = QFrame(shell)
    side_rail.setObjectName("sideRail")
    side_rail.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    side_rail.setFixedWidth(232)
    side_layout = QVBoxLayout(side_rail)
    side_layout.setContentsMargins(16, 16, 16, 16)
    side_layout.setSpacing(16)

    brand_card = QFrame(side_rail)
    brand_card.setObjectName("brandCard")
    brand_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    brand_layout = QHBoxLayout(brand_card)
    brand_layout.setContentsMargins(14, 14, 14, 14)
    brand_layout.setSpacing(12)

    if logo_label is not None:
        title_bar.layout().removeWidget(logo_label)
        logo_label.setParent(brand_card)
        logo_label.setFixedSize(30, 30)
        logo_label.show()
        brand_layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignTop)
    else:
        brand_mark = QLabel("RC", brand_card)
        brand_mark.setObjectName("brandMark")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setFixedSize(30, 30)
        brand_layout.addWidget(brand_mark, 0, Qt.AlignmentFlag.AlignTop)

    brand_text = QWidget(brand_card)
    brand_text_layout = QVBoxLayout(brand_text)
    brand_text_layout.setContentsMargins(0, 0, 0, 0)
    brand_text_layout.setSpacing(2)
    brand_kicker = QLabel("RichCore", brand_text)
    brand_kicker.setObjectName("brandTitle")
    brand_meta = QLabel("Operator workspace", brand_text)
    brand_meta.setObjectName("brandSubtitle")
    brand_text_layout.addWidget(brand_kicker)
    brand_text_layout.addWidget(brand_meta)
    brand_layout.addWidget(brand_text, 1)

    side_layout.addWidget(brand_card)

    title_layout = title_bar.layout()
    if title_layout is not None:
        for widget in _drain_layout(title_layout):
            if widget in {window_controls, nav_frame}:
                continue
            widget.hide()

    nav_layout = nav_frame.layout()
    if isinstance(nav_layout, QBoxLayout):
        nav_layout.setDirection(QBoxLayout.Direction.TopToBottom)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(8)
    nav_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    nav_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    side_layout.addWidget(nav_frame)

    for item_host in _direct_children(nav_frame, QWidget):
        item_host.setProperty("navItem", True)
        item_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        item_host.setFixedHeight(44)
        item_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button = item_host.findChild(QPushButton, "navButton")
        if button is not None:
            button.setFixedHeight(38)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if button.text().strip() == "AD VIP":
                button.setText("VIP чат")
            _repolish(button)
        _repolish(item_host)

    side_meta = QLabel("Швидкий доступ до черги, VIP-модерації, біндів, оптимізації та параметрів.", side_rail)
    side_meta.setObjectName("sideMeta")
    side_meta.setWordWrap(True)
    side_layout.addStretch(1)
    side_layout.addWidget(side_meta)

    content_shell = QWidget(shell)
    content_shell.setObjectName("contentShell")
    content_layout = QVBoxLayout(content_shell)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(14)

    section_header = QFrame(title_bar)
    section_header.setObjectName("sectionHeaderBar")
    section_header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    section_header_layout = QVBoxLayout(section_header)
    section_header_layout.setContentsMargins(0, 0, 0, 0)
    section_header_layout.setSpacing(2)
    section_eyebrow = QLabel(section_header)
    section_eyebrow.setObjectName("sectionEyebrow")
    section_title = QLabel(section_header)
    section_title.setObjectName("sectionHeaderTitle")
    section_subtitle = QLabel(section_header)
    section_subtitle.setObjectName("sectionHeaderSubtitle")
    section_subtitle.setWordWrap(True)
    section_header_layout.addWidget(section_eyebrow)
    section_header_layout.addWidget(section_title)
    section_header_layout.addWidget(section_subtitle)

    if title_layout is not None:
        title_layout.setContentsMargins(4, 0, 2, 0)
        title_layout.setSpacing(12)
        title_layout.addWidget(section_header, 1)
        title_layout.addStretch(1)
        title_layout.addWidget(window_controls, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
    title_bar.setFixedHeight(76)
    title_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    workspace_surface = QFrame(content_shell)
    workspace_surface.setObjectName("workspaceSurface")
    workspace_surface.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    workspace_layout = QVBoxLayout(workspace_surface)
    workspace_layout.setContentsMargins(18, 18, 18, 18)
    workspace_layout.setSpacing(0)
    workspace_layout.addWidget(tabs)

    content_layout.addWidget(title_bar)
    content_layout.addWidget(workspace_surface, 1)

    shell_layout.addWidget(side_rail)
    shell_layout.addWidget(content_shell, 1)
    root_layout.addWidget(shell)

    self._section_eyebrow_label = section_eyebrow
    self._section_title_label = section_title
    self._section_subtitle_label = section_subtitle
    self._shell_rebuilt = True

    for widget in (shell, side_rail, brand_card, nav_frame, title_bar, section_header, workspace_surface, content_shell):
        _repolish(widget)
    _update_shell_context(self, tabs.currentIndex())


def _rebuild_reports_tab(self: MainWindow) -> None:
    page = getattr(self, "tabs", None).widget(_REPORTS_TAB_INDEX) if getattr(self, "tabs", None) is not None else None
    if page is None or page.property("redesignApplied"):
        return

    layout = page.layout()
    hero = page.findChild(QFrame, "heroBanner")
    splitter = page.findChild(QSplitter, "reportSplitter")
    stat_frames = [frame for frame in _direct_children(page, QFrame) if frame is not hero]
    if layout is not None and hero is not None and stat_frames:
        overview = QWidget(page)
        overview.setObjectName("overviewStrip")
        overview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        overview_layout = QHBoxLayout(overview)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(14)

        metric_host = QWidget(overview)
        metric_host.setObjectName("metricHost")
        metric_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        metric_layout = QHBoxLayout(metric_host)
        metric_layout.setContentsMargins(0, 0, 0, 0)
        metric_layout.setSpacing(12)

        for frame in stat_frames:
            frame.setProperty("metricCard", True)
            frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            frame.setFixedHeight(92)
            _set_layout_spacing(frame, margins=(14, 12, 14, 12), spacing=4)
            metric_layout.addWidget(frame)
            _repolish(frame)

        _set_layout_spacing(hero, margins=(20, 18, 20, 18), spacing=6)
        hero.setMinimumHeight(96)
        overview_layout.addWidget(hero, 5)
        overview_layout.addWidget(metric_host, 4)

        while layout.count():
            layout.takeAt(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(overview)
        if splitter is not None:
            splitter.setParent(page)
            splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(splitter, 1)

    queue_panel, detail_panel = _reorder_splitter_for_table_first(splitter, "reportTable")
    detail_frame = _detail_frame_from_embedded_scroll(detail_panel)
    _set_panel_style(queue_panel, object_name="listPanel")
    _set_panel_style(detail_panel, object_name="detailScrollPanel")
    _set_panel_style(detail_frame, object_name="detailPanel")
    if splitter is not None:
        splitter.setSizes([360, 760])
        splitter.setChildrenCollapsible(False)

    report_table = page.findChild(QTableWidget, "reportTable")
    _tune_table(report_table)

    _rename_label(page, "RICHCORE V12", "Репорти")
    _rename_label(page, "СИСТЕМА: МОНІТОРИНГ АКТИВНОСТІ", "Операційна черга онлайн")
    _rename_label(page, "ЧЕРГА", "У черзі")
    _rename_label(page, "ОЧІКУЮТЬ", "Очікують")
    _rename_label(page, "ВИКОНАНО", "Виконано")
    _rename_label(page, "ЧЕРГА РЕПОРТІВ", "Черга репортів")
    _rename_label(page, "AI-ЧЕРНЕТКА", "AI-чернетка")

    if detail_frame is not None:
        quick_strip = None
        for child in _direct_children(detail_frame, QWidget):
            buttons = child.findChildren(QPushButton, options=Qt.FindChildOption.FindDirectChildrenOnly)
            if len(buttons) >= 4:
                quick_strip = child
                break
        if quick_strip is not None:
            quick_strip.setObjectName("quickReplyStrip")
            quick_strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            if quick_strip.layout() is not None:
                quick_strip.layout().setContentsMargins(0, 2, 0, 2)
                quick_strip.layout().setSpacing(8)
            for button in quick_strip.findChildren(QPushButton, options=Qt.FindChildOption.FindDirectChildrenOnly):
                _mark_chip_button(button)

    _rename_button(page, "ВСТАВИТИ ТЕКСТ AI", "Вставити AI-текст")
    _rename_button(page, "ВІДПОВІДЬ КОЛЕГИ", "Відповідь колеги")
    _rename_button(page, "ВІДПРАВИТИ ВІДПОВІДЬ", "Відправити")
    _rename_button(page, "ТЕЛЕПОРТ", "Телепорт")
    _rename_button(page, "НА ФОРУМ", "На форум")

    _ensure_button_class(_first_button_by_text(page, "Вставити AI-текст"), "secondaryAction")
    _ensure_button_class(_first_button_by_text(page, "Відповідь колеги"), "secondaryAction")
    _ensure_button_class(_first_button_by_text(page, "Відправити"), "primaryAction")
    _ensure_button_class(_first_button_by_text(page, "Очистити весь список"), "dangerGhost")

    page.setProperty("redesignApplied", True)


def _rebuild_vip_tab(self: MainWindow) -> None:
    page = getattr(self, "tabs", None).widget(_VIP_TAB_INDEX) if getattr(self, "tabs", None) is not None else None
    if page is None or page.property("redesignApplied"):
        return

    hero = page.findChild(QFrame, "heroBanner")
    if hero is not None:
        _set_layout_spacing(hero, margins=(20, 18, 20, 18), spacing=6)

    splitter = page.findChild(QSplitter, "reportSplitter")
    queue_panel, detail_panel = _reorder_splitter_for_table_first(splitter, "vipAdTable")
    detail_frame = _detail_frame_from_embedded_scroll(detail_panel)
    _set_panel_style(queue_panel, object_name="listPanel")
    _set_panel_style(detail_panel, object_name="detailScrollPanel")
    _set_panel_style(detail_frame, object_name="detailPanel")
    if splitter is not None:
        splitter.setSizes([380, 740])
        splitter.setChildrenCollapsible(False)

    vip_table = page.findChild(QTableWidget, "vipAdTable")
    _tune_table(vip_table)

    _rename_label(page, "AD VIP", "VIP чат")
    _rename_label(page, "СПРАЦЮВАННЯ VIP ЧАТУ", "Черга VIP-порушень")
    _rename_label(page, "КОМАНДА", "Команда")
    _rename_button(page, "Відкинути спрацювання", "Позначити як чисте")

    _ensure_button_class(_first_button_by_text(page, "Позначити як чисте"), "secondaryAction")
    _ensure_button_class(_first_button_by_text(page, "Видати покарання"), "primaryAction")
    _ensure_button_class(_first_button_by_text(page, "Очистити весь список"), "dangerGhost")

    page.setProperty("redesignApplied", True)


def _rebuild_binds_tab(self: MainWindow) -> None:
    page = getattr(self, "tabs", None).widget(_BINDS_TAB_INDEX) if getattr(self, "tabs", None) is not None else None
    if page is None or page.property("redesignApplied"):
        return

    layout = page.layout()
    if layout is not None:
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

    for frame in _direct_children(page, QFrame):
        _set_panel_style(frame)
        _set_layout_spacing(frame, margins=(18, 18, 18, 18), spacing=12)

    for table in page.findChildren(QTableWidget, "bindTable"):
        _tune_table(table)

    _rename_label(page, "БІНДИ НА ВІДПОВІДЬ", "Швидкі відповіді")
    _rename_label(page, "КОМАНДНІ БІНДИ", "Командні бінди")
    for old, new in (("ДОДАТИ", "Додати"), ("РЕДАГУВАТИ", "Редагувати"), ("ВИДАЛИТИ", "Видалити")):
        for button in page.findChildren(QPushButton):
            if button.text().strip() == old:
                button.setText(new)

    for button in page.findChildren(QPushButton):
        text = button.text().strip()
        if text == "Додати":
            _ensure_button_class(button, "primaryAction")
        elif text == "Редагувати":
            _ensure_button_class(button, "secondaryAction")
        elif text == "Видалити":
            _ensure_button_class(button, "dangerGhost")

    page.setProperty("redesignApplied", True)


def _rebuild_optimization_tab(self: MainWindow) -> None:
    page = getattr(self, "tabs", None).widget(_OPTIMIZATION_TAB_INDEX) if getattr(self, "tabs", None) is not None else None
    if page is None or page.property("redesignApplied"):
        return

    scroll = page.findChild(QScrollArea)
    host = scroll.widget() if scroll is not None else None
    layout = host.layout() if host is not None else None
    frames = _direct_children(host, QFrame) if host is not None else []
    if layout is None or len(frames) < 5:
        return

    hero, state_frame, actions_frame, package_frame, log_frame = frames[:5]
    for frame in (hero, state_frame, actions_frame, package_frame, log_frame):
        layout.removeWidget(frame)

    top_row = QWidget(host)
    top_row.setObjectName("optTopRow")
    top_row_layout = QHBoxLayout(top_row)
    top_row_layout.setContentsMargins(0, 0, 0, 0)
    top_row_layout.setSpacing(16)
    top_row_layout.addWidget(hero, 5)
    top_row_layout.addWidget(actions_frame, 4)

    middle_row = QWidget(host)
    middle_row.setObjectName("optMidRow")
    middle_row_layout = QHBoxLayout(middle_row)
    middle_row_layout.setContentsMargins(0, 0, 0, 0)
    middle_row_layout.setSpacing(16)
    middle_row_layout.addWidget(state_frame, 4)
    middle_row_layout.addWidget(package_frame, 7)

    layout.insertWidget(0, top_row)
    layout.insertWidget(1, middle_row)
    layout.insertWidget(2, log_frame)
    layout.setSpacing(16)

    for frame, name in (
        (actions_frame, "actionsPanel"),
        (state_frame, "statePanel"),
        (package_frame, "packagePanel"),
        (log_frame, "logPanel"),
    ):
        _set_panel_style(frame, object_name=name)
        _set_layout_spacing(frame, margins=(18, 18, 18, 18), spacing=12)
    _set_layout_spacing(hero, margins=(20, 18, 20, 18), spacing=6)

    _rename_label(page, "GTA FPS OPTIMIZER", "Оптимізація")
    _rename_label(page, "Швидкі дії", "Панель керування")
    _rename_label(page, "Рекомендований FPS-пакет", "Сценарії оптимізації")
    _rename_label(page, "Журнал оптимізації", "Журнал")

    _ensure_button_class(_first_button_by_text(page, "Застосувати FPS-пакет"), "primaryAction")
    _ensure_button_class(_first_button_by_text(page, "Підняти пріоритет GTA зараз"), "secondaryAction")
    _ensure_button_class(_first_button_by_text(page, "Оновити аналіз"), "secondaryAction")
    _ensure_button_class(_first_button_by_text(page, "Повернути стандарт"), "dangerGhost")

    page.setProperty("redesignApplied", True)


def _rebuild_settings_tab(self: MainWindow) -> None:
    tabs = getattr(self, "tabs", None)
    page = tabs.widget(_SETTINGS_TAB_INDEX) if tabs is not None else None
    if page is None or page.property("redesignApplied"):
        return

    host = page.widget() if isinstance(page, QScrollArea) else None
    if host is None:
        return

    for frame in host.findChildren(QFrame, options=Qt.FindChildOption.FindDirectChildrenOnly):
        _set_panel_style(frame)
        _set_layout_spacing(frame, margins=(20, 20, 20, 20), spacing=14)

    _rename_label(host, "ADMIN IDENTITY", "Профіль адміністратора")
    _rename_label(host, "GLOBAL HOTKEYS", "Гарячі клавіші")
    _rename_button(host, "ЗБЕРЕГТИ ВСІ НАЛАШТУВАННЯ", "Зберегти всі налаштування")
    _ensure_button_class(_first_button_by_text(host, "Зберегти всі налаштування"), "primaryAction")

    for button in host.findChildren(QPushButton):
        if button.text().strip() == "ОГЛЯД":
            button.setText("Огляд")
            _ensure_button_class(button, "secondaryAction")

    page.setProperty("redesignApplied", True)


def _apply_radical_redesign(self: MainWindow) -> None:
    if getattr(self, "_radical_redesign_applied", False):
        return
    try:
        _rebuild_shell(self)
        _rebuild_reports_tab(self)
        _rebuild_vip_tab(self)
        _rebuild_binds_tab(self)
        _rebuild_optimization_tab(self)
        _rebuild_settings_tab(self)
        _update_shell_context(self, getattr(self, "tabs", None).currentIndex() if getattr(self, "tabs", None) is not None else 0)
        self._radical_redesign_applied = True
    except Exception:
        _LOGGER.exception("Radical UI redesign failed")


def _force_admin_vip_mode(self: MainWindow) -> None:
    self.settings.vip_ad_punish_mode = "admin"
    _set_radio_checked(getattr(self, "vip_mode_assistant_radio", None), False)
    _set_radio_checked(getattr(self, "vip_mode_admin_radio", None), True)

    assistant_radio = getattr(self, "vip_mode_assistant_radio", None)
    if assistant_radio is not None:
        assistant_radio.setEnabled(False)
        assistant_radio.hide()

    admin_radio = getattr(self, "vip_mode_admin_radio", None)
    if admin_radio is not None:
        admin_radio.setEnabled(False)
        admin_radio.hide()

    _hide_form_row(getattr(self, "vip_helper_signature_edit", None))
    _remove_labels_by_text(
        self,
        {
            "РЕЖИМ ПОКАРАННЯ",
            "Режим змінює команду покарання: для адміністратора використовується /pmute, а для ігрового помічника /a pmute ... | by ...",
            "Підпис після `| by` береться з налаштувань програми.",
        },
    )

    if hasattr(self, "_update_vip_command_preview"):
        self._update_vip_command_preview()


def _wrap_in_scroll_area(widget: QWidget) -> None:
    parent = widget.parentWidget()
    if parent is None or not isinstance(parent, _RECOVERED.QSplitter):
        return
    if isinstance(parent, QScrollArea):
        return

    scroll = QScrollArea(parent)
    scroll.setObjectName("embeddedScrollArea")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.viewport().setObjectName("embeddedScrollViewport")
    scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    index = parent.indexOf(widget)
    widget.setParent(None)
    widget.setProperty("contentCard", True)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    widget.setMinimumHeight(max(widget.minimumHeight(), widget.sizeHint().height()))
    host = QWidget()
    host.setObjectName("embeddedScrollHost")
    host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    host_layout = QVBoxLayout(host)
    host_layout.setContentsMargins(8, 8, 10, 8)
    host_layout.setSpacing(0)
    host_layout.addWidget(widget)
    widget.show()
    host.show()
    scroll.setWidget(host)
    parent.insertWidget(index, scroll)
    parent.setStretchFactor(index, 5)
    _repolish(widget)
    _repolish(host)
    _repolish(scroll.viewport())
    _repolish(scroll)


def _find_parent_splitter(widget: QWidget | None) -> QSplitter | None:
    current = widget
    while current is not None:
        parent = current.parentWidget()
        if isinstance(parent, QSplitter):
            return parent
        current = parent
    return None


def _find_splitter_panel(widget: QWidget | None) -> QWidget | None:
    current = widget
    while current is not None:
        parent = current.parentWidget()
        if isinstance(parent, QScrollArea):
            return None
        if isinstance(parent, QSplitter):
            return current
        current = parent
    return None


def _rebalance_splitter(splitter: QSplitter | None, left_ratio: float) -> None:
    if splitter is None or splitter.count() < 2:
        return
    total = splitter.size().width()
    if total <= 0:
        return
    left = max(260, int(total * left_ratio))
    right = max(320, total - left)
    splitter.setSizes([left, right])


def _wrap_tab_page_in_scroll(self: MainWindow, index: int, object_name: str) -> None:
    tabs = getattr(self, "tabs", None)
    if tabs is None:
        return
    page = tabs.widget(index)
    if page is None or isinstance(page, QScrollArea):
        return

    scroll = QScrollArea()
    scroll.setObjectName(object_name)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.viewport().setObjectName(f"{object_name}Viewport")
    scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    page.setParent(None)
    page.setMinimumHeight(max(page.minimumHeight(), page.sizeHint().height()))
    host = QWidget()
    host.setObjectName(f"{object_name}Host")
    host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    host_layout = QVBoxLayout(host)
    host_layout.setContentsMargins(18, 14, 18, 18)
    host_layout.setSpacing(0)
    host_layout.addWidget(page)
    page.show()
    host.show()
    scroll.setWidget(host)
    tabs.removeTab(index)
    tabs.insertTab(index, scroll, "")
    _repolish(page)
    _repolish(host)
    _repolish(scroll.viewport())
    _repolish(scroll)


def _restore_previous_design(self: MainWindow) -> None:
    subtitle = self.findChild(QLabel, "appSubtitle")
    _detach_widget(subtitle)

    _remove_labels_by_text(
        self,
        {
            "Операційна панель для репортів, VIP-модерації та швидких дій.",
            "Актуальні звернення, статус відповіді та остання дія по кожному репорту.",
            "Автоматичний моніторинг VIP-чату через AI: нейронка визначає намір повідомлення і відділяє рекламу або торгівлю від звичайних інформаційних питань.",
        },
    )

    for button in self.findChildren(QPushButton):
        if button.objectName() not in {"winControl", "winControl_close"}:
            button.setIcon(QIcon())
        if button.objectName() == "navButton":
            button.setFlat(True)
            button.setFixedHeight(24)
            parent = button.parentWidget()
            if parent is not None and parent.layout() is not None:
                parent.setProperty("navItem", True)
                parent.setProperty("navActive", button.property("active") == "true")
                parent.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                parent.setFixedHeight(28)
                parent.layout().setContentsMargins(5, 2, 5, 2)
                parent.layout().setSpacing(0)
                _repolish(parent)

    for checkbox in self.findChildren(QCheckBox):
        checkbox.setMinimumHeight(max(24, checkbox.sizeHint().height() + 6))
        checkbox.setContentsMargins(0, 2, 0, 2)
        form_container = checkbox.parentWidget()
        if form_container is not None and isinstance(form_container.layout(), QFormLayout):
            layout_hint = form_container.layout().sizeHint().height()
            form_container.setMinimumHeight(max(form_container.minimumHeight(), layout_hint))
            form_frame = form_container.parentWidget()
            if isinstance(form_frame, QFrame):
                form_frame.setMinimumHeight(max(form_frame.minimumHeight(), form_frame.sizeHint().height()))

    nav_frame = self.findChild(QFrame, "navigationBar")
    if nav_frame is not None and nav_frame.layout() is not None:
        nav_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        nav_frame.setFixedHeight(42)
        nav_frame.layout().setContentsMargins(10, 6, 10, 6)
        nav_frame.layout().setSpacing(4)
        _repolish(nav_frame)

    for frame in self.findChildren(QFrame):
        if frame.property("class") == "glassPanel":
            frame.setProperty("contentCard", True)
            frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            _repolish(frame)

    for frame in self.findChildren(QFrame, "heroBanner"):
        texts = {label.text().strip() for label in frame.findChildren(QLabel)}
        layout = frame.layout()
        if layout is None:
            continue
        if "RICHCORE V12" in texts:
            frame.setFixedHeight(74)
            layout.setContentsMargins(20, 12, 20, 12)
            layout.setSpacing(4)
        elif "AD VIP" in texts:
            frame.setFixedHeight(88)
            layout.setContentsMargins(22, 14, 22, 14)
            layout.setSpacing(5)

    reply_input = self.findChild(QPlainTextEdit, "replyComposer")
    if reply_input is not None:
        reply_frame = reply_input.parentWidget()
        if isinstance(reply_frame, QFrame):
            reply_frame.setMinimumHeight(max(reply_frame.minimumHeight(), reply_frame.sizeHint().height()))
            for child in reply_frame.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
                if isinstance(child, QWidget) and child.layout() is not None and child.sizeHint().height() > child.height():
                    child.setMinimumHeight(child.sizeHint().height())
            if reply_frame.sizeHint().height() > reply_frame.height():
                _wrap_in_scroll_area(reply_frame)

    vip_command = self.findChild(_RECOVERED.QLineEdit, "vipCommandPreview")
    if vip_command is not None:
        vip_frame = vip_command.parentWidget()
        while vip_frame is not None and not isinstance(vip_frame.parentWidget(), _RECOVERED.QSplitter):
            vip_frame = vip_frame.parentWidget()
        if isinstance(vip_frame, QFrame) and vip_frame.sizeHint().height() > vip_frame.height():
            vip_frame.setMinimumHeight(max(vip_frame.minimumHeight(), vip_frame.sizeHint().height()))
            _wrap_in_scroll_area(vip_frame)

    _wrap_tab_page_in_scroll(self, self.SETTINGS_TAB_INDEX, "settingsScrollArea")


def _post_layout_fixups(self: MainWindow) -> None:
    _wrap_tab_page_in_scroll(self, self.SETTINGS_TAB_INDEX, "settingsScrollArea")

    reply_input = self.findChild(QPlainTextEdit, "replyComposer")
    if reply_input is not None:
        reply_panel = _find_splitter_panel(reply_input)
        if isinstance(reply_panel, QFrame):
            reply_panel.setMinimumHeight(max(reply_panel.minimumHeight(), reply_panel.sizeHint().height()))
            _wrap_in_scroll_area(reply_panel)
        _rebalance_splitter(_find_parent_splitter(reply_input), 0.34)

    vip_command = self.findChild(_RECOVERED.QLineEdit, "vipCommandPreview")
    if vip_command is not None:
        vip_panel = _find_splitter_panel(vip_command)
        if isinstance(vip_panel, QFrame):
            vip_panel.setMinimumHeight(max(vip_panel.minimumHeight(), vip_panel.sizeHint().height()))
            _wrap_in_scroll_area(vip_panel)
        _rebalance_splitter(_find_parent_splitter(vip_command), 0.56)

    for checkbox in self.findChildren(QCheckBox):
        checkbox.setMinimumHeight(max(24, checkbox.sizeHint().height() + 6))
        form_container = checkbox.parentWidget()
        if form_container is not None and isinstance(form_container.layout(), QFormLayout):
            layout_hint = form_container.layout().sizeHint().height()
            form_container.setMinimumHeight(max(form_container.minimumHeight(), layout_hint))
            form_frame = form_container.parentWidget()
            if isinstance(form_frame, QFrame):
                form_frame.setMinimumHeight(max(form_frame.minimumHeight(), form_frame.sizeHint().height()))

    for frame in self.findChildren(QFrame):
        if frame.property("class") == "glassPanel":
            frame.setProperty("contentCard", True)
            _repolish(frame)

    self.updateGeometry()


def _safe_post_layout_fixups(self: MainWindow) -> None:
    try:
        _post_layout_fixups(self)
    except Exception:
        _LOGGER.exception("Post-layout UI fixups failed")


def _apply_nav_button_icon(self: MainWindow, button: QPushButton, *, active: bool) -> None:
    button.setIcon(QIcon())


def _format_pm_command(self: MainWindow, player_id: str, text: str) -> str:
    return _strip_slash_command(f"pm {player_id} {text}")


def _format_vip_punishment_command(self: MainWindow, alert: VipAdAlert) -> str:
    self.settings.vip_ad_punish_mode = "admin"
    _set_radio_checked(getattr(self, "vip_mode_assistant_radio", None), False)
    _set_radio_checked(getattr(self, "vip_mode_admin_radio", None), True)
    return _strip_slash_command(f"pmute {alert.player_id} 30 Реклама у VIP чаті")


def _on_vip_mode_changed(self: MainWindow, _checked: bool) -> None:
    _force_admin_vip_mode(self)


def _reply_from_other_admin_for_report(self: MainWindow, report: Report):
    resolver = getattr(self.store, "latest_other_reply_for_report", None)
    if callable(resolver):
        return resolver(report, self.settings.admin_nickname)
    return self.store.latest_other_reply_for_player(report.player_id, self.settings.admin_nickname)


def _report_status_info_patched(self: MainWindow, report: Report) -> tuple[str, str]:
    if report.answered_by_me:
        return ("ВІДПОВІВ Я", "status_answered_me")
    if report.answered_by_other:
        return ("ВІДПОВІВ", "status_answered_other")
    if report.handled_by_me and report.handled_by_other:
        return ("В РОБОТІ", "status_progress")
    if report.handled_by_me:
        return ("В РОБОТІ Я", "status_progress")
    if report.handled_by_other:
        return ("В РОБОТІ", "status_progress")
    if report.unanswered:
        return ("БЕЗ ВІДП.", "status_new")
    return ("НОВИЙ", "status_new")


def _send_reply_patched(self: MainWindow) -> None:
    report = self._target_report()
    text = self.reply_input.toPlainText().strip()
    if report is None or not text:
        self._set_status("Потрібно обрати репорт і ввести текст")
        return

    command = self._format_pm_command(report.player_id, text)
    try:
        self.sender.send_reply_command(
            command,
            open_chat=True,
            submit=True,
            dismiss_ui=False,
        )
        marker = getattr(self.store, "mark_report_answered_by_me", None)
        if callable(marker):
            marker(report, text)
        else:
            self.store.mark_answered_by_me(report.player_id, text)
        self.reply_input.clear()
        self._refresh_table()
        self._set_status(f"Відправлено для {report.player_name}[{report.player_id}]")
    except Exception as exc:
        self._logger.exception("Failed to send reply")
        self._set_status(f"Помилка відправки: {exc}")


def _hotkey_last_report_pm_patched(self: MainWindow) -> None:
    resolver = getattr(self.store, "latest_received_report", None)
    report = resolver() if callable(resolver) else self.store.latest_report()
    if report is None:
        self._set_status("Останній репорт не знайдено")
        return
    self._send_ahk_like(f"/pm {report.player_id} ", open_chat=True, submit=False, dismiss_ui=False)
    self._set_status(f"PM відкрито для {report.player_name}[{report.player_id}]")


def _hotkey_last_reply_id_patched(self: MainWindow) -> None:
    player_id = self.store.last_answered_by_me_player_id
    if not player_id:
        self._set_status("Немає ID з останньої відповіді")
        return
    status_text = f"ID {player_id} з останньої відповіді вставлено"

    self._send_ahk_like(player_id, open_chat=False, submit=False, dismiss_ui=False)
    self._set_status(status_text)


def _hotkey_other_reply_patched(self: MainWindow) -> None:
    report = self._target_report()
    if report is None:
        self._set_status("Репорт не знайдено")
        return

    reply = _reply_from_other_admin_for_report(self, report)
    if reply is None:
        self._set_status("Не знайдено відповіді іншого адміністратора")
        return

    self._send_ahk_like(
        f"/pm {report.player_id} {reply.text}",
        open_chat=True,
        submit=False,
        dismiss_ui=False,
    )
    self._set_status(f"Останню відповідь для {report.player_name}[{report.player_id}] вставлено в чат")


def _insert_other_admin_reply_patched(self: MainWindow) -> None:
    report = self._target_report()
    if report is None:
        self._set_status("Репорт не знайдено")
        return

    reply = _reply_from_other_admin_for_report(self, report)
    if reply is None:
        self._set_status("Не знайдено відповіді іншого адміністратора")
        return

    self.reply_input.setPlainText(reply.text)
    self.reply_input.setFocus()
    self._set_status(f"Останню відповідь для {report.player_name}[{report.player_id}] вставлено")


def _settings_form_layout(self: MainWindow, group: QWidget | None = None) -> QFormLayout | None:
    if group is not None:
        form_host = _settings_form_container(group)
        if form_host is not None and isinstance(form_host.layout(), QFormLayout):
            return form_host.layout()

    for attr_name in (
        "chat_open_box",
        "admin_name_edit",
        "vip_helper_signature_edit",
        "game_path_edit",
        "console_path_edit",
    ):
        layout = _find_parent_form_layout(getattr(self, attr_name, None))
        if layout is not None:
            return layout

    settings_host = self.findChild(QWidget, "settingsScrollAreaHost")
    if settings_host is None:
        return None
    for host in settings_host.findChildren(QWidget):
        layout = host.layout()
        if isinstance(layout, QFormLayout):
            return layout
    return None


def _style_form_labels(form: QFormLayout | None) -> None:
    if form is None:
        return
    for row in range(form.rowCount()):
        item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        if item is None:
            continue
        label = item.widget()
        if isinstance(label, QLabel):
            label.setProperty("formLabel", True)
            _repolish(label)


def _apply_action_button_classes(self: MainWindow) -> None:
    primary_texts = {
        "зберегти",
        "зберегти всі налаштування",
        "відправити відповідь",
        "відправити",
        "відправити say",
        "перевірити",
        "додати",
        "видати",
        "посадити",
        "кікнути",
        "поставити",
        "змінити ранг",
        "застосувати fps-пакет",
        "видати покарання",
    }
    secondary_texts = {
        "огляд",
        "редагувати",
        "з репорту",
        "розбан",
        "зняти мут",
        "випустити",
        "зняти warn",
        "відповідь колеги",
        "вставити текст ai",
        "вставити ai-текст",
        "телепорт",
        "оновити аналіз",
        "підняти пріоритет gta зараз",
        "відкинути спрацювання",
        "позначити як чисте",
        "скасувати",
    }
    danger_texts = {
        "видалити",
        "звільнити",
        "очистити весь список",
        "повернути стандарт",
    }
    chip_texts = {
        "вітаю",
        "очікуйте",
        "не виконуємо",
        "уточніть",
        "предам",
        "на форум",
    }

    for button in self.findChildren(QPushButton):
        if button.objectName() in {"navButton", "winControl", "winControl_close"}:
            continue
        text = _normalized_button_text(button)
        if not text:
            continue

        button.setProperty("chipAction", False)
        if text in primary_texts or text.startswith("застосувати"):
            _ensure_button_class(button, "primaryAction")
        elif text in danger_texts:
            _ensure_button_class(button, "dangerGhost")
        elif text in secondary_texts:
            _ensure_button_class(button, "secondaryAction")
        elif text in chip_texts:
            button.setProperty("class", "")
            _mark_chip_button(button)
        else:
            button.setProperty("class", "")
            _repolish(button)


def _normalize_runtime_texts(self: MainWindow) -> None:
    label_map = {
        "RICHCORE V12": "Репорти",
        "Операційна панель для репортів, VIP-модерації та швидких дій.": "Черга репортів, відповіді та швидкі дії в одному місці.",
        "СИСТЕМА: МОНІТОРИНГ АКТИВНОСТІ": "Черга онлайн",
        "ЧЕРГА": "У черзі",
        "ОЧІКУЮТЬ": "Очікують",
        "ВИКОНАНО": "Виконано",
        "ЧЕРГА РЕПОРТІВ": "Черга репортів",
        "AI-ЧЕРНЕТКА": "AI-чернетка",
        "AD VIP": "VIP чат",
        "Автоматичний моніторинг VIP-чату через AI: нейронка визначає намір повідомлення і відділяє рекламу або торгівлю від звичайних інформаційних питань.": "Моніторинг VIP-чату: перевірка спрацювань і дії без зайвого шуму.",
        "VIP CHAT: нових спрацювань немає": "Нових спрацювань немає",
        "СПРАЦЮВАННЯ VIP ЧАТУ": "Черга VIP-порушень",
        "КОМАНДА": "Команда",
        "БІНДИ НА ВІДПОВІДЬ": "Швидкі відповіді",
        "КОМАНДНІ БІНДИ": "Командні бінди",
        "ADMIN IDENTITY": "Профіль адміністратора",
        "GLOBAL HOTKEYS": "Гарячі клавіші",
    }
    button_map = {
        "AD VIP": "VIP чат",
        "ВСТАВИТИ ТЕКСТ AI": "Вставити AI-текст",
        "ВІДПОВІДЬ КОЛЕГИ": "Відповідь колеги",
        "ВІДПРАВИТИ ВІДПОВІДЬ": "Відправити",
        "ТЕЛЕПОРТ": "Телепорт",
        "НА ФОРУМ": "На форум",
        "ДОДАТИ": "Додати",
        "РЕДАГУВАТИ": "Редагувати",
        "ВИДАЛИТИ": "Видалити",
        "ОГЛЯД": "Огляд",
        "ЗБЕРЕГТИ ВСІ НАЛАШТУВАННЯ": "Зберегти всі налаштування",
        "Відкинути спрацювання": "Позначити як чисте",
    }

    for label in self.findChildren(QLabel):
        text = label.text().strip()
        new_text = label_map.get(text)
        if new_text and text != new_text:
            label.setText(new_text)
            _repolish(label)

    for button in self.findChildren(QPushButton):
        text = button.text().strip()
        new_text = button_map.get(text)
        if new_text and text != new_text:
            button.setText(new_text)
            _repolish(button)


def _attach_theme_selector(self: MainWindow, group: QWidget | None) -> None:
    if getattr(self, "theme_mode_combo", None) is not None:
        return

    form = _settings_form_layout(self, group)
    if form is None:
        return
    form_host = form.parentWidget()
    if form_host is None:
        return

    combo = QComboBox(form_host)
    combo.setObjectName("themeModeCombo")
    combo.addItem("Темна", "dark")
    combo.addItem("Світла", "light")
    combo.setToolTip("Перемикає нову темну або світлу тему інтерфейсу.")
    combo.currentIndexChanged.connect(lambda _index: _preview_theme_mode(self))

    insert_row = form.rowCount()
    chat_open_box = getattr(self, "chat_open_box", None)
    if chat_open_box is not None:
        row, _role = form.getWidgetPosition(chat_open_box)
        if row >= 0:
            insert_row = row

    form.insertRow(insert_row, "ТЕМА ІНТЕРФЕЙСУ", combo)
    _style_form_labels(form)
    self.theme_mode_combo = combo


def _sync_theme_selector(self: MainWindow) -> None:
    combo = getattr(self, "theme_mode_combo", None)
    if combo is None:
        _attach_theme_selector(self, None)
        combo = getattr(self, "theme_mode_combo", None)
    if combo is None:
        return

    _style_form_labels(_settings_form_layout(self))
    blocked = combo.blockSignals(True)
    combo.setCurrentIndex(_theme_combo_index(combo, getattr(self.settings, "theme_mode", "dark")))
    combo.blockSignals(blocked)


def _find_embedded_scroll_area(widget: QWidget | None) -> QScrollArea | None:
    current = widget
    while current is not None:
        parent = current.parentWidget()
        if isinstance(parent, QScrollArea) and parent.objectName() == "embeddedScrollArea":
            return parent
        current = parent
    return None


def _unwrap_embedded_scroll_area(scroll: QScrollArea | None) -> QWidget | None:
    if scroll is None or scroll.objectName() != "embeddedScrollArea":
        return None
    splitter = scroll.parentWidget()
    if splitter is None or not isinstance(splitter, _RECOVERED.QSplitter):
        return None

    index = splitter.indexOf(scroll)
    host = scroll.takeWidget()
    panel = None
    if host is not None and host.layout() is not None and host.layout().count():
        item = host.layout().takeAt(0)
        panel = item.widget()
        if panel is not None:
            panel.setParent(None)
            panel.setMinimumHeight(0)
            panel.show()
    if host is not None:
        host.deleteLater()
    scroll.deleteLater()
    if panel is None:
        return None

    splitter.insertWidget(index, panel)
    splitter.setStretchFactor(index, 5)
    _repolish(panel)
    return panel


def _set_button_height(button: QPushButton | None, minimum: int, maximum: int | None = None) -> None:
    if button is None:
        return
    height = maximum if maximum is not None else minimum
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    _repolish(button)
    button.setMinimumHeight(minimum)
    button.setMaximumHeight(height)
    button.setFixedHeight(height)
    button.updateGeometry()


def _set_editor_height(widget: QWidget | None, minimum: int, maximum: int) -> None:
    if widget is None:
        return
    widget.setMinimumHeight(minimum)
    widget.setMaximumHeight(maximum)
    widget.updateGeometry()


def _window_control_buttons(self: MainWindow) -> dict[str, QPushButton]:
    frame = self.findChild(QFrame, "windowControls")
    if frame is None:
        return {}
    buttons = sorted(
        frame.findChildren(QPushButton, options=Qt.FindChildOption.FindDirectChildrenOnly),
        key=lambda button: button.geometry().x(),
    )
    roles = ("minimize", "maximize", "close")
    resolved: dict[str, QPushButton] = {}
    for role, button in zip(roles, buttons):
        button.setProperty("windowRole", role)
        resolved[role] = button
    return resolved


def _sync_window_control_icons(self: MainWindow, theme_mode: str | None = None) -> None:
    app = QApplication.instance()
    mode = normalize_theme_mode(theme_mode or (app.property("theme_mode") if app is not None else "dark"))
    controls = _window_control_buttons(self)
    frame = self.findChild(QFrame, "windowControls")
    if frame is not None and frame.layout() is not None:
        frame.layout().setContentsMargins(6, 6, 6, 6)
        frame.layout().setSpacing(6)
        _repolish(frame)
    for role, button in controls.items():
        icon_role = role
        if role == "maximize" and self.isMaximized():
            icon_role = "restore"
        button.setText("")
        button.setIcon(window_control_icon(icon_role, mode))
        button.setIconSize(QSize(16, 16))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(30, 30)
        button.setToolTip(
            {
                "minimize": "Згорнути",
                "maximize": "Розгорнути" if not self.isMaximized() else "Відновити",
                "close": "Закрити",
            }[role]
        )
        _repolish(button)


def _first_label_by_normalized_text(root: QWidget, text: str) -> QLabel | None:
    target = text.strip().casefold()
    for label in root.findChildren(QLabel):
        if label.text().strip().casefold() == target:
            return label
    return None


def _find_table_panel(root: QWidget, table_name: str) -> QFrame | None:
    table = root.findChild(QTableWidget, table_name)
    current = table.parentWidget() if table is not None else None
    while current is not None:
        if isinstance(current, QFrame):
            return current
        current = current.parentWidget()
    return None


def _direct_label_by_text(root: QWidget, texts: tuple[str, ...]) -> QLabel | None:
    for label in root.findChildren(QLabel, options=Qt.FindChildOption.FindDirectChildrenOnly):
        if label.text().strip() in texts:
            return label
    return None


def _first_button_by_normalized_text(root: QWidget, text: str) -> QPushButton | None:
    target = text.strip().casefold()
    for button in root.findChildren(QPushButton):
        if _normalized_button_text(button) == target:
            return button
    return None


def _clear_layout_items(layout) -> None:
    if layout is None:
        return
    while layout.count():
        layout.takeAt(0)


def _ensure_row_widget(parent: QWidget, object_name: str, spacing: int) -> tuple[QWidget, QHBoxLayout]:
    row = parent.findChild(QWidget, object_name, options=Qt.FindChildOption.FindDirectChildrenOnly)
    if row is None:
        row = QWidget(parent)
        row.setObjectName(object_name)
        row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(row)
    else:
        layout = row.layout()
        if not isinstance(layout, QHBoxLayout):
            layout = QHBoxLayout(row)
    _clear_layout_items(layout)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    return row, layout


def _rebuild_quick_reply_grid(panel: QWidget) -> QWidget | None:
    for button in panel.findChildren(QPushButton):
        text = button.text().casefold()
        if "перевір" in text:
            _detach_widget(button)

    preferred_rows = (
        ("Вітаю", "Очікуйте", "Уточніть"),
        ("Не виконуємо", "Предам", "На форум"),
    )
    ordered_buttons: list[QPushButton] = []
    for row in preferred_rows:
        for label in row:
            button = _first_button_by_normalized_text(panel, label)
            if button is not None and button not in ordered_buttons:
                ordered_buttons.append(button)

    if not ordered_buttons:
        return None

    grid = ordered_buttons[0].parentWidget()
    if grid is None:
        return None

    layout = grid.layout()
    if not isinstance(layout, QGridLayout):
        layout = QGridLayout(grid)

    _clear_layout_items(layout)
    grid.setObjectName("quickReplyGrid")
    grid.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setHorizontalSpacing(8)
    layout.setVerticalSpacing(6)

    arranged: list[QPushButton] = []
    for row_index, row in enumerate(preferred_rows):
        for column_index, label in enumerate(row):
            button = _first_button_by_normalized_text(panel, label)
            if button is None:
                continue
            _set_button_height(button, 30, 32)
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            layout.addWidget(button, row_index, column_index)
            arranged.append(button)

    next_index = len(arranged)
    for button in ordered_buttons:
        if button in arranged:
            continue
        row_index = next_index // 3
        column_index = next_index % 3
        _set_button_height(button, 30, 32)
        button.setMinimumWidth(0)
        button.setMaximumWidth(16777215)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(button, row_index, column_index)
        next_index += 1

    row_count = max(2, (max(next_index, 1) + 2) // 3)
    for column_index in range(3):
        layout.setColumnStretch(column_index, 1)
    for row_index in range(row_count):
        layout.setRowStretch(row_index, 0)
        layout.setRowMinimumHeight(row_index, 32)

    grid.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    grid.setMinimumHeight(70)
    grid.setMaximumHeight(70)
    grid.setFixedHeight(70)
    return grid


def _rebuild_report_queue_panel(self: MainWindow) -> None:
    report_table = self.findChild(QTableWidget, "reportTable")
    queue_panel = _find_splitter_panel(report_table)
    if not isinstance(queue_panel, QFrame) or report_table is None:
        return
    queue_panel.setMinimumWidth(390)

    title = _direct_label_by_text(queue_panel, ("Черга репортів", "ЧЕРГА РЕПОРТІВ"))
    subtitle = None
    for label in queue_panel.findChildren(QLabel, options=Qt.FindChildOption.FindDirectChildrenOnly):
        text = label.text().strip()
        if "Актуальні звернення" in text:
            subtitle = label
            break
    count_badge = _find_count_badge(queue_panel)
    clear_button = _first_button_by_text(queue_panel, "Очистити весь список")
    _configure_report_queue_table(report_table)
    if count_badge is not None:
        _detach_widget(count_badge)
    header_row = _build_queue_header(queue_panel, "reportQueueHeaderRow", title, None)
    layout = queue_panel.layout()
    if layout is None:
        layout = QVBoxLayout(queue_panel)

    _clear_layout_items(layout)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)
    if header_row is not None:
        layout.addWidget(header_row)
    if subtitle is not None:
        subtitle.hide()
    layout.addWidget(report_table, 1)
    if clear_button is not None:
        _set_button_height(clear_button, 32, 34)
        clear_button.setMaximumWidth(220)
        clear_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(clear_button, 0, Qt.AlignmentFlag.AlignLeft)


def _rebuild_report_detail_panel(self: MainWindow) -> None:
    reply_input = self.findChild(QPlainTextEdit, "replyComposer")
    if reply_input is None:
        return

    panel = _find_splitter_panel(reply_input)
    if not isinstance(panel, QFrame):
        panel = reply_input.parentWidget()
    if not isinstance(panel, QFrame):
        return

    player_card = panel.findChild(QFrame, "playerInfoCard")
    report_preview = panel.findChild(QPlainTextEdit, "reportPreview")
    ai_reply_preview = panel.findChild(QPlainTextEdit, "aiReplyPreview")
    insert_ai_button = _first_button_by_text(panel, "Вставити AI-текст") or _first_button_by_text(panel, "ВСТАВИТИ ТЕКСТ AI")
    quick_reply_grid = _rebuild_quick_reply_grid(panel)
    teleport_button = _first_button_by_text(panel, "Телепорт") or _first_button_by_text(panel, "ТЕЛЕПОРТ")
    colleague_button = _first_button_by_text(panel, "Відповідь колеги") or _first_button_by_text(panel, "ВІДПОВІДЬ КОЛЕГИ")
    send_button = _first_button_by_text(panel, "Відправити") or _first_button_by_text(panel, "ВІДПРАВИТИ ВІДПОВІДЬ")
    ai_title = _first_label_by_text(panel, "AI-чернетка") or _first_label_by_text(panel, "AI-ЧЕРНЕТКА")
    ai_status = None
    for label in panel.findChildren(QLabel):
        if label.text().strip().startswith("AI:"):
            ai_status = label
            break

    layout = panel.layout()
    if layout is None:
        layout = QVBoxLayout(panel)

    ai_header_row, ai_header_layout = _ensure_row_widget(panel, "reportAiHeaderRow", 10)
    if ai_title is not None:
        ai_header_layout.addWidget(ai_title)
    ai_header_layout.addStretch(1)
    if ai_status is not None:
        ai_header_layout.addWidget(ai_status, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    ai_header_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    ai_header_row.setFixedHeight(22)

    action_row, action_layout = _ensure_row_widget(panel, "reportActionRow", 8)
    if teleport_button is not None:
        teleport_button.setMinimumWidth(118)
        teleport_button.setMaximumWidth(118)
        teleport_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        action_layout.addWidget(teleport_button)
    if colleague_button is not None:
        colleague_button.setMinimumWidth(176)
        colleague_button.setMaximumWidth(176)
        colleague_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        action_layout.addWidget(colleague_button)
    if send_button is not None:
        send_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        action_layout.addWidget(send_button, 1)
    action_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    action_row.setFixedHeight(34)

    _clear_layout_items(layout)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(6)
    if player_card is not None:
        layout.addWidget(player_card)
    if report_preview is not None:
        layout.addWidget(report_preview)
    layout.addWidget(ai_header_row)
    if ai_reply_preview is not None:
        layout.addWidget(ai_reply_preview)
    if insert_ai_button is not None:
        layout.addWidget(insert_ai_button)
    layout.addWidget(reply_input)
    if quick_reply_grid is not None:
        layout.addWidget(quick_reply_grid)
    layout.addWidget(action_row)


def _rebuild_vip_queue_panel(self: MainWindow) -> None:
    vip_table = self.findChild(QTableWidget, "vipAdTable")
    queue_panel = _find_splitter_panel(vip_table)
    if not isinstance(queue_panel, QFrame) or vip_table is None:
        return

    title = _first_label_by_normalized_text(queue_panel, "Черга VIP-порушень")
    subtitle = None
    for label in queue_panel.findChildren(QLabel, options=Qt.FindChildOption.FindDirectChildrenOnly):
        text = label.text().strip()
        if "VIP" in text and "детектор" in text.casefold():
            subtitle = label
            break
    count_badge = _find_count_badge(queue_panel, active_only=True)
    clear_button = _first_button_by_normalized_text(queue_panel, "Очистити весь список")
    _sync_vip_active_badge(self)
    header_row = _build_queue_header(queue_panel, "vipQueueHeaderRow", title, count_badge)
    layout = queue_panel.layout()
    if layout is None:
        layout = QVBoxLayout(queue_panel)

    _clear_layout_items(layout)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(8)
    if header_row is not None:
        layout.addWidget(header_row)
    if subtitle is not None:
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
    layout.addWidget(vip_table, 1)
    if clear_button is not None:
        _set_button_height(clear_button, 32, 34)
        clear_button.setMaximumWidth(220)
        clear_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(clear_button, 0, Qt.AlignmentFlag.AlignLeft)


def _rebuild_vip_detail_panel(self: MainWindow) -> None:
    preview = self.findChild(QPlainTextEdit, "vipAdPreview")
    if preview is None:
        return

    scroll = _find_embedded_scroll_area(preview)
    panel = _unwrap_embedded_scroll_area(scroll) if scroll is not None else _find_splitter_panel(preview)
    if not isinstance(panel, QFrame):
        panel = preview.parentWidget()
    if not isinstance(panel, QFrame):
        return

    player_card = panel.findChild(QFrame, "playerInfoCard")
    command_label = _first_label_by_normalized_text(panel, "Команда")
    command_preview = self.findChild(_RECOVERED.QLineEdit, "vipCommandPreview")
    clean_button = _first_button_by_normalized_text(panel, "Позначити як чисте")
    punish_button = _first_button_by_normalized_text(panel, "Видати покарання")

    action_row, action_layout = _ensure_row_widget(panel, "vipActionRow", 10)
    if clean_button is not None:
        clean_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        action_layout.addWidget(clean_button, 1)
    if punish_button is not None:
        punish_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        action_layout.addWidget(punish_button, 1)
    action_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    action_row.setMinimumHeight(34)
    action_row.setMaximumHeight(34)
    action_row.setFixedHeight(34)

    layout = panel.layout()
    if layout is None:
        layout = QVBoxLayout(panel)

    _clear_layout_items(layout)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)
    if player_card is not None:
        layout.addWidget(player_card)
    if preview is not None:
        preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(preview, 1)
    if command_label is not None:
        layout.addWidget(command_label)
    if command_preview is not None:
        command_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(command_preview)
    layout.addWidget(action_row)


def _rebuild_bind_panel(panel: QFrame) -> None:
    title = None
    table = None
    buttons: dict[str, QPushButton] = {}
    for child in panel.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        if isinstance(child, QLabel) and title is None:
            title = child
        elif isinstance(child, QTableWidget) and child.objectName() == "bindTable":
            table = child
        elif isinstance(child, QPushButton):
            text = _normalized_button_text(child)
            if text in {"додати", "редагувати", "видалити"}:
                buttons[text] = child

    if title is None or table is None or len(buttons) < 3:
        return

    footer_row, footer_layout = _ensure_row_widget(panel, "bindFooterRow", 10)
    for text in ("додати", "редагувати", "видалити"):
        button = buttons.get(text)
        if button is None:
            continue
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        footer_layout.addWidget(button, 1)
    footer_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    footer_row.setMinimumHeight(34)
    footer_row.setMaximumHeight(34)
    footer_row.setFixedHeight(34)

    layout = panel.layout()
    if layout is None:
        layout = QVBoxLayout(panel)

    _clear_layout_items(layout)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(14)
    layout.addWidget(title)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    layout.addWidget(table, 1)
    layout.addWidget(footer_row)


def _rebuild_binds_layout(self: MainWindow) -> None:
    page = getattr(self, "tabs", None).widget(_BINDS_TAB_INDEX) if getattr(self, "tabs", None) is not None else None
    if page is None:
        return
    for table in page.findChildren(QTableWidget, "bindTable"):
        current = table.parentWidget()
        while current is not None and not isinstance(current, QFrame):
            current = current.parentWidget()
        if isinstance(current, QFrame):
            _rebuild_bind_panel(current)


def _compact_button_metrics(self: MainWindow) -> None:
    chip_texts = {
        "вітаю",
        "очікуйте",
        "не виконуємо",
        "уточніть",
        "предам",
        "на форум",
    }
    compact_texts = {
        "огляд",
        "зберегти",
        "зберегти всі налаштування",
        "додати",
        "редагувати",
        "видалити",
        "застосувати",
        "скасувати",
        "оновити аналіз",
        "очистити весь список",
        "повернути стандарт",
        "відкинути спрацювання",
        "позначити як чисте",
        "видати покарання",
        "застосувати fps-пакет",
        "підняти пріоритет gta зараз",
    }
    report_action_texts = {
        "вставити текст ai",
        "вставити ai-текст",
        "телепорт",
        "відповідь колеги",
        "відправити відповідь",
        "відправити",
    }

    for button in self.findChildren(QPushButton):
        if button.objectName() in {"navButton", "winControl", "winControl_close"}:
            continue
        text = _normalized_button_text(button)
        if not text:
            continue
        if button.property("chipAction") or text in chip_texts:
            _set_button_height(button, 30, 32)
        elif text in report_action_texts:
            _set_button_height(button, 34, 34)
        elif text in compact_texts or button.property("class") in {"primaryAction", "secondaryAction", "dangerGhost"}:
            _set_button_height(button, 32, 34)


def _compact_report_reply_panel(self: MainWindow) -> None:
    _rebuild_report_queue_panel(self)
    _rebuild_report_detail_panel(self)
    _rebuild_vip_queue_panel(self)
    _rebuild_vip_detail_panel(self)
    _rebuild_binds_layout(self)
    _apply_queue_table_fixups(self)

    reply_input = self.findChild(QPlainTextEdit, "replyComposer")
    if reply_input is None:
        _sync_window_control_icons(self)
        return

    scroll = _find_embedded_scroll_area(reply_input)
    panel = _unwrap_embedded_scroll_area(scroll) if scroll is not None else _find_splitter_panel(reply_input)
    if not isinstance(panel, QFrame):
        panel = reply_input.parentWidget()
    if not isinstance(panel, QFrame):
        return

    dense_mode = self.height() <= 660
    panel_margins = (10, 10, 10, 10) if dense_mode else (12, 12, 12, 12)
    panel_spacing = 4 if dense_mode else 6
    player_min, player_max = ((48, 50) if dense_mode else (52, 54))
    report_min, report_max = ((60, 64) if dense_mode else (68, 140))
    ai_min, ai_max = ((44, 48) if dense_mode else (52, 96))
    reply_min, reply_max = ((60, 64) if dense_mode else (70, 280))
    quick_min, quick_max = ((28, 30) if dense_mode else (30, 32))
    quick_grid_height = 64 if dense_mode else 70
    action_height = 32 if dense_mode else 34
    ai_header_height = 20 if dense_mode else 22
    insert_height = 34

    panel.setMinimumHeight(0)
    layout = panel.layout()
    if layout is not None:
        layout.setContentsMargins(*panel_margins)
        layout.setSpacing(panel_spacing)

    player_card = panel.findChild(QFrame, "playerInfoCard")
    if player_card is not None and player_card.layout() is not None:
        if dense_mode:
            player_card.layout().setContentsMargins(8, 6, 8, 6)
            player_card.layout().setSpacing(6)
        else:
            player_card.layout().setContentsMargins(10, 8, 10, 8)
            player_card.layout().setSpacing(8)
        player_card.setMinimumHeight(player_min)
        player_card.setMaximumHeight(player_max)

    available_editor_height = max(
        0,
        panel.height()
        - panel_margins[1]
        - panel_margins[3]
        - panel_spacing * 7
        - player_max
        - ai_header_height
        - insert_height
        - quick_grid_height
        - action_height,
    )
    report_target = report_min
    ai_target = ai_min
    reply_target = reply_min
    baseline_editor_total = report_target + ai_target + reply_target
    extra_editor_height = max(0, available_editor_height - baseline_editor_total)
    if not dense_mode and extra_editor_height:
        report_growth = min(report_max - report_min, extra_editor_height // 5)
        ai_growth = min(ai_max - ai_min, extra_editor_height // 7)
        report_target += report_growth
        ai_target += ai_growth
        reply_target += max(0, extra_editor_height - report_growth - ai_growth)
    reply_target = min(reply_max, reply_target)

    _set_editor_height(panel.findChild(QPlainTextEdit, "reportPreview"), report_target, report_target)
    _set_editor_height(panel.findChild(QPlainTextEdit, "aiReplyPreview"), ai_target, ai_target)
    _set_editor_height(reply_input, reply_target, reply_target)

    ai_header_row = panel.findChild(QWidget, "reportAiHeaderRow")
    if ai_header_row is not None:
        ai_header_row.setMinimumHeight(ai_header_height)
        ai_header_row.setMaximumHeight(ai_header_height)
        ai_header_row.setFixedHeight(ai_header_height)

    action_row = panel.findChild(QWidget, "reportActionRow")
    if action_row is not None:
        action_row.setMinimumHeight(action_height)
        action_row.setMaximumHeight(action_height)
        action_row.setFixedHeight(action_height)

    quick_reply_grid = _rebuild_quick_reply_grid(panel)

    if quick_reply_grid is not None and quick_reply_grid.layout() is not None:
        quick_reply_grid.layout().setContentsMargins(0, 0, 0, 0)
        quick_reply_grid.layout().setSpacing(4 if dense_mode else 6)
        if isinstance(quick_reply_grid.layout(), QGridLayout):
            quick_reply_grid.layout().setRowMinimumHeight(0, quick_max)
            quick_reply_grid.layout().setRowMinimumHeight(1, quick_max)
            quick_reply_grid.layout().setRowStretch(0, 0)
            quick_reply_grid.layout().setRowStretch(1, 0)
        quick_reply_grid.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        quick_reply_grid.setMinimumHeight(quick_grid_height)
        quick_reply_grid.setMaximumHeight(quick_grid_height)
        quick_reply_grid.setFixedHeight(quick_grid_height)

    for text in (
        "Вітаю",
        "Очікуйте",
        "Не виконуємо",
        "Уточніть",
        "Предам",
        "На форум",
        "НА ФОРУМ",
    ):
        _set_button_height(_first_button_by_text(panel, text), quick_min, quick_max)

    for text in (
        "Вставити AI-текст",
        "ВСТАВИТИ ТЕКСТ AI",
        "Телепорт",
        "ТЕЛЕПОРТ",
        "Відповідь колеги",
        "ВІДПОВІДЬ КОЛЕГИ",
        "Відправити",
        "ВІДПРАВИТИ ВІДПОВІДЬ",
    ):
        _set_button_height(_first_button_by_text(panel, text), action_height, action_height)

    reports_page = getattr(self, "tabs", None).widget(_REPORTS_TAB_INDEX) if getattr(self, "tabs", None) is not None else None
    if reports_page is not None and reports_page.layout() is not None:
        reports_page.layout().setSpacing(8 if dense_mode else 10)
        hero = reports_page.findChild(QFrame, "heroBanner")
        if hero is not None and hero.layout() is not None:
            hero.setFixedHeight(76 if dense_mode else 82)
            hero.layout().setContentsMargins(16, 12, 16, 12) if dense_mode else hero.layout().setContentsMargins(18, 14, 18, 14)
            hero.layout().setSpacing(3 if dense_mode else 4)
        metric_host = reports_page.findChild(QWidget, "metricHost")
        if metric_host is not None and metric_host.layout() is not None:
            metric_host.layout().setSpacing(10)
            for index in range(metric_host.layout().count()):
                item = metric_host.layout().itemAt(index)
                card = item.widget()
                if isinstance(card, QFrame):
                    card.setFixedHeight(82)
                    if card.layout() is not None:
                        card.layout().setContentsMargins(14, 10, 14, 10)
                        card.layout().setSpacing(3)

    vip_preview = self.findChild(QPlainTextEdit, "vipAdPreview")
    if vip_preview is not None:
        vip_panel = _find_splitter_panel(vip_preview)
        if not isinstance(vip_panel, QFrame):
            vip_panel = vip_preview.parentWidget()
        if isinstance(vip_panel, QFrame):
            vip_layout = vip_panel.layout()
            if vip_layout is not None:
                vip_layout.setContentsMargins(16, 16, 16, 16)
                vip_layout.setSpacing(10)
            vip_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            preview_height = max(188, vip_panel.height() - 230)
            _set_editor_height(vip_preview, preview_height, preview_height)
            vip_command = self.findChild(_RECOVERED.QLineEdit, "vipCommandPreview")
            if vip_command is not None:
                vip_command.setMinimumHeight(42)
                vip_command.setMaximumHeight(42)
            vip_action_row = vip_panel.findChild(QWidget, "vipActionRow")
            if vip_action_row is not None:
                vip_action_row.setFixedHeight(34)
                vip_action_row.setMinimumHeight(34)
                vip_action_row.setMaximumHeight(34)
            _rebalance_splitter(_find_parent_splitter(vip_panel), 0.52)

    if quick_reply_grid is not None and quick_reply_grid.layout() is not None:
        quick_reply_grid.layout().invalidate()
        quick_reply_grid.layout().activate()
    if layout is not None:
        layout.invalidate()
        layout.activate()

    splitter = _find_parent_splitter(panel)
    _rebalance_splitter(splitter, 0.40)
    _sync_window_control_icons(self)
    panel.updateGeometry()


class _PlayerLookupThread(QThread):
    completed = Signal(object, str)

    def __init__(self, identifier: str) -> None:
        super().__init__()
        self._identifier = identifier

    def run(self) -> None:
        try:
            self.completed.emit(lookup_player(self._identifier), "")
        except PlayerLookupError as exc:
            self.completed.emit(None, str(exc))
        except Exception as exc:  # noqa: BLE001
            self.completed.emit(None, f"Не вдалося знайти ID: {exc}")


class _ConsoleCommandThread(QThread):
    completed = Signal(bool, str, str)

    def __init__(self, sender: object, command: str) -> None:
        super().__init__()
        self._sender = sender
        self._command = command

    def run(self) -> None:
        if self._sender is None:
            self.completed.emit(False, "Модуль відправки команд не готовий", self._command)
            return
        try:
            self._sender.send_reply_command(
                self._command,
                open_chat=True,
                submit=True,
                dismiss_ui=False,
            )
        except Exception as exc:  # noqa: BLE001
            self.completed.emit(False, f"Не вдалося відправити команду: {exc}", self._command)
        else:
            self.completed.emit(True, f"Команду відправлено у MTA: {self._command}", self._command)


class _AppointmentFetchThread(QThread):
    completed = Signal(object, str)

    def __init__(self, config: AppointmentConfig) -> None:
        super().__init__()
        self._config = config

    def run(self) -> None:
        try:
            self.completed.emit(AppointmentService(self._config).fetch_form_queue(), "")
        except Exception as exc:  # noqa: BLE001
            self.completed.emit([], str(exc))


class _AppointmentActiveFetchThread(QThread):
    completed = Signal(object, str)

    def __init__(self, config: AppointmentConfig) -> None:
        super().__init__()
        self._config = config

    def run(self) -> None:
        try:
            self.completed.emit(AppointmentService(self._config).fetch_active_records(), "")
        except Exception as exc:  # noqa: BLE001
            self.completed.emit([], str(exc))


class _AppointmentActionThread(QThread):
    completed = Signal(str, object, object, str)

    def __init__(self, config: AppointmentConfig, action: str, record: AppointmentRecord, note: str) -> None:
        super().__init__()
        self._config = config
        self._action = action
        self._record = record
        self._note = note

    def run(self) -> None:
        try:
            service = AppointmentService(self._config)
            if self._action == "approve":
                result = service.approve(self._record, self._note)
            elif self._action == "reject":
                result = service.reject(self._record, self._note)
            elif self._action == "remove":
                result = service.remove(self._record, self._note)
            elif self._action == "update":
                result = service.update_active(self._record, self._note)
            else:
                raise ValueError(f"Невідома дія: {self._action}")
            self.completed.emit(self._action, self._record, result, "")
        except Exception as exc:  # noqa: BLE001
            self.completed.emit(
                self._action,
                self._record,
                AppointmentActionResult(False, str(exc)),
                str(exc),
            )


class _AppointmentTermSyncThread(QThread):
    completed = Signal(int, str)

    def __init__(self, config: AppointmentConfig) -> None:
        super().__init__()
        self._config = config

    def run(self) -> None:
        try:
            self.completed.emit(AppointmentService(self._config).sync_terms(), "")
        except Exception as exc:  # noqa: BLE001
            self.completed.emit(0, str(exc))


def _sanitize_console_command(value: str) -> str:
    normalized = " ".join(value.replace("\r", " ").replace("\n", " ").strip().split())
    return _strip_slash_command(normalized)


def _line_value(field: QLineEdit | None) -> str:
    return field.text().strip() if field is not None else ""


def _plain_value(field: QPlainTextEdit | None) -> str:
    return field.toPlainText().strip() if field is not None else ""


def _replace_line_value(field: QLineEdit | None, value: str) -> None:
    if field is None:
        return
    field.setText(value)
    field.setCursorPosition(len(value))


def _set_plain_value(field: QPlainTextEdit | None, value: str) -> None:
    if field is None:
        return
    field.setPlainText(value)


def _make_line_edit(parent: QWidget, placeholder: str, width: int | None = None) -> QLineEdit:
    field = QLineEdit(parent)
    field.setPlaceholderText(placeholder)
    field.setClearButtonEnabled(True)
    if width is not None:
        field.setFixedWidth(width)
    return field


def _make_card(parent: QWidget, title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    card = QFrame(parent)
    card.setProperty("class", "glassPanel")
    card.setProperty("contentCard", True)
    card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    title_label = QLabel(title, card)
    title_label.setProperty("class", "sectionTitle")
    layout.addWidget(title_label)
    if subtitle:
        subtitle_label = QLabel(subtitle, card)
        subtitle_label.setProperty("class", "muted")
        subtitle_label.setWordWrap(True)
        layout.addWidget(subtitle_label)

    _repolish(card)
    return card, layout


def _build_player_action_row(
    parent_layout: QGridLayout,
    row: int,
    title: str,
    fields: list[QLineEdit],
    button_text: str,
    callback,
    *,
    danger: bool = False,
) -> None:
    label = QLabel(title)
    label.setProperty("formLabel", True)
    parent_layout.addWidget(label, row, 0)
    parent_layout.setColumnMinimumWidth(0, 82)
    parent_layout.setColumnStretch(0, 0)
    parent_layout.setColumnStretch(1, 1)
    parent_layout.setColumnStretch(2, 0)

    field_host = QWidget()
    field_layout = QHBoxLayout(field_host)
    field_layout.setContentsMargins(0, 0, 0, 0)
    field_layout.setSpacing(8)
    for field in fields:
        field_layout.addWidget(field, 0 if field.maximumWidth() == field.minimumWidth() else 1)
    parent_layout.addWidget(field_host, row, 1)

    button = QPushButton(button_text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(callback)
    button.setProperty("class", "dangerGhost" if danger else "secondaryAction")
    button.setMinimumWidth(104)
    button.setMaximumWidth(128)
    parent_layout.addWidget(button, row, 2)


def _build_players_tab(self: MainWindow) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("playersTabScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.viewport().setObjectName("playersTabViewport")
    scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    host = QWidget()
    host.setObjectName("playersTabHost")
    host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    root = QVBoxLayout(host)
    root.setContentsMargins(18, 14, 18, 18)
    root.setSpacing(12)

    target_card, target_layout = _make_card(
        host,
        "Гравці",
        "Пошук за нікнеймом або ID, покарання, зняття та фракції в одному місці.",
    )
    target_row = QWidget(target_card)
    target_row_layout = QHBoxLayout(target_row)
    target_row_layout.setContentsMargins(0, 0, 0, 0)
    target_row_layout.setSpacing(8)

    self.player_target_input = _make_line_edit(target_row, "ID або нікнейм")
    self.player_target_input.textChanged.connect(lambda _text: _on_player_target_changed(self))
    self.player_target_input.returnPressed.connect(lambda: _start_player_lookup(self, _line_value(self.player_target_input)))
    self.lookup_btn = QPushButton("Перевірити", target_row)
    self.lookup_btn.clicked.connect(lambda: _start_player_lookup(self, _line_value(self.player_target_input)))
    self.from_report_player_btn = QPushButton("З репорту", target_row)
    self.from_report_player_btn.clicked.connect(lambda: _fill_player_from_report(self))
    self.target_id_badge = QLabel("ID: -", target_row)
    self.target_id_badge.setObjectName("targetBadge")
    self.target_name_label = QLabel("-", target_row)
    self.target_name_label.setObjectName("targetBadge")

    for button in (self.lookup_btn, self.from_report_player_btn):
        button.setCursor(Qt.CursorShape.PointingHandCursor)
    self.lookup_btn.setProperty("class", "primaryAction")
    self.from_report_player_btn.setProperty("class", "secondaryAction")

    target_row_layout.addWidget(self.player_target_input, 1)
    target_row_layout.addWidget(self.lookup_btn)
    target_row_layout.addWidget(self.from_report_player_btn)
    target_row_layout.addWidget(self.target_id_badge)
    target_row_layout.addWidget(self.target_name_label)
    target_layout.addWidget(target_row)
    root.addWidget(target_card)

    body = QWidget(host)
    body_layout = QHBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(12)

    punish_card, punish_layout = _make_card(body, "Покарання")
    punish_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    punish_layout.setContentsMargins(14, 12, 14, 12)
    punish_layout.setSpacing(7)
    punish_grid = QGridLayout()
    punish_grid.setContentsMargins(0, 0, 0, 0)
    punish_grid.setHorizontalSpacing(8)
    punish_grid.setVerticalSpacing(7)
    punish_grid.setColumnStretch(1, 1)

    self.ban_days_input = _make_line_edit(punish_card, "Днів", 74)
    self.ban_reason_input = _make_line_edit(punish_card, "Причина бану")
    _build_player_action_row(punish_grid, 0, "Бан", [self.ban_days_input, self.ban_reason_input], "Видати", lambda: _player_ban(self), danger=True)

    self.mute_minutes_input = _make_line_edit(punish_card, "Хв", 74)
    self.mute_reason_input = _make_line_edit(punish_card, "Причина муту")
    _build_player_action_row(punish_grid, 1, "Мут", [self.mute_minutes_input, self.mute_reason_input], "Видати", lambda: _player_mute(self), danger=True)

    self.jail_minutes_input = _make_line_edit(punish_card, "Хв", 74)
    self.jail_reason_input = _make_line_edit(punish_card, "Причина деморгану")
    _build_player_action_row(punish_grid, 2, "Деморган", [self.jail_minutes_input, self.jail_reason_input], "Посадити", lambda: _player_jail(self), danger=True)

    self.warn_reason_input = _make_line_edit(punish_card, "Причина warn")
    _build_player_action_row(punish_grid, 3, "Warn", [self.warn_reason_input], "Видати", lambda: _player_warn(self), danger=True)

    self.kick_reason_input = _make_line_edit(punish_card, "Причина кіку")
    _build_player_action_row(punish_grid, 4, "Кік", [self.kick_reason_input], "Кікнути", lambda: _player_kick(self))
    punish_layout.addLayout(punish_grid)
    punish_card.setMaximumHeight(punish_card.sizeHint().height() + 4)

    side = QWidget(body)
    side_layout = QVBoxLayout(side)
    side_layout.setContentsMargins(0, 0, 0, 0)
    side_layout.setSpacing(12)

    release_card, release_layout = _make_card(side, "Зняти / скасувати")
    release_grid = QGridLayout()
    release_grid.setContentsMargins(0, 0, 0, 0)
    release_grid.setSpacing(8)
    release_actions = (
        ("Розбан", lambda: _player_unban(self)),
        ("Зняти мут", lambda: _player_unmute(self)),
        ("Випустити", lambda: _player_unjail(self)),
        ("Зняти warn", lambda: _player_unwarn(self)),
    )
    for index, (label, callback) in enumerate(release_actions):
        button = QPushButton(label, release_card)
        button.clicked.connect(callback)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("class", "secondaryAction")
        release_grid.addWidget(button, index // 2, index % 2)
    release_layout.addLayout(release_grid)

    faction_card, faction_layout = _make_card(side, "Фракція")
    faction_grid = QGridLayout()
    faction_grid.setContentsMargins(0, 0, 0, 0)
    faction_grid.setSpacing(8)
    faction_grid.setColumnStretch(0, 1)

    self.faction_combo = QComboBox(faction_card)
    self.faction_combo.addItems(_FACTION_OPTIONS)
    set_faction_btn = QPushButton("Поставити", faction_card)
    set_faction_btn.clicked.connect(lambda: _player_set_faction(self))
    self.faction_level_combo = QComboBox(faction_card)
    self.faction_level_combo.addItems([str(index) for index in range(1, 13)])
    set_rank_btn = QPushButton("Змінити ранг", faction_card)
    set_rank_btn.clicked.connect(lambda: _player_set_faction_level(self))
    clear_faction_btn = QPushButton("Звільнити", faction_card)
    clear_faction_btn.clicked.connect(lambda: _player_clear_faction(self))

    for button in (set_faction_btn, set_rank_btn, clear_faction_btn):
        button.setCursor(Qt.CursorShape.PointingHandCursor)
    clear_faction_btn.setProperty("class", "dangerGhost")

    faction_grid.addWidget(self.faction_combo, 0, 0, 1, 2)
    faction_grid.addWidget(set_faction_btn, 0, 2)
    faction_grid.addWidget(self.faction_level_combo, 1, 0)
    faction_grid.addWidget(set_rank_btn, 1, 1)
    faction_grid.addWidget(clear_faction_btn, 1, 2)
    faction_layout.addLayout(faction_grid)

    log_card, log_layout = _make_card(side, "Лог дій")
    self.player_action_log = QPlainTextEdit(log_card)
    self.player_action_log.setReadOnly(True)
    self.player_action_log.setPlaceholderText("Тут буде історія команд цієї сесії.")
    self.player_action_log.setMinimumHeight(132)
    log_layout.addWidget(self.player_action_log)

    side_layout.addWidget(release_card)
    side_layout.addWidget(faction_card)
    side_layout.addWidget(log_card, 1)

    body_layout.addWidget(punish_card, 1, Qt.AlignmentFlag.AlignTop)
    body_layout.addWidget(side, 1)
    root.addWidget(body, 1)

    scroll.setWidget(host)
    self._resolved_player_id = ""
    self._resolved_player_name = ""
    self._pending_after_lookup = None
    self._lookup_running = False
    self._pending_offline_action = None
    _update_target_badges(self)
    return scroll


def _build_test_tab(self: MainWindow) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("testTabScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.viewport().setObjectName("testTabViewport")
    scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    host = QWidget()
    host.setObjectName("testTabHost")
    host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    root = QVBoxLayout(host)
    root.setContentsMargins(18, 14, 18, 18)
    root.setSpacing(12)

    form_card, form_layout = _make_card(
        host,
        "Тест консолі",
        "Тестова команда завжди відправляється як say <команда>, щоб перед PM або покаранням було видно, що саме піде в консоль.",
    )

    top_row = QWidget(form_card)
    top_layout = QHBoxLayout(top_row)
    top_layout.setContentsMargins(0, 0, 0, 0)
    top_layout.setSpacing(8)
    self.test_action_combo = QComboBox(top_row)
    for key, label in _TEST_ACTIONS:
        self.test_action_combo.addItem(label, key)
    self.test_player_id_input = _make_line_edit(top_row, "ID гравця")
    self.test_number_input = _make_line_edit(top_row, "Дні або хв", 110)
    self.fill_test_from_report_btn = QPushButton("З репорту", top_row)
    self.fill_test_from_report_btn.clicked.connect(lambda: _fill_test_from_report(self))
    self.send_test_btn = QPushButton("Відправити say", top_row)
    self.send_test_btn.clicked.connect(lambda: _send_console_test(self))
    self.send_test_btn.setProperty("class", "primaryAction")
    self.fill_test_from_report_btn.setProperty("class", "secondaryAction")

    top_layout.addWidget(self.test_action_combo, 1)
    top_layout.addWidget(self.test_player_id_input, 1)
    top_layout.addWidget(self.test_number_input)
    top_layout.addWidget(self.fill_test_from_report_btn)
    top_layout.addWidget(self.send_test_btn)
    form_layout.addWidget(top_row)

    self.test_custom_input = _make_line_edit(form_card, "Своя команда, наприклад mute 15 30 образа")
    form_layout.addWidget(self.test_custom_input)

    self.test_text_input = QPlainTextEdit(form_card)
    self.test_text_input.setPlaceholderText("Текст відповіді або причина")
    self.test_text_input.setMinimumHeight(114)
    form_layout.addWidget(self.test_text_input)

    preview_row = QWidget(form_card)
    preview_layout = QHBoxLayout(preview_row)
    preview_layout.setContentsMargins(0, 0, 0, 0)
    preview_layout.setSpacing(10)
    self.test_command_preview = QPlainTextEdit(preview_row)
    self.test_command_preview.setReadOnly(True)
    self.test_command_preview.setMinimumHeight(92)
    self.test_say_preview = QPlainTextEdit(preview_row)
    self.test_say_preview.setReadOnly(True)
    self.test_say_preview.setMinimumHeight(92)
    preview_layout.addWidget(self.test_command_preview)
    preview_layout.addWidget(self.test_say_preview)
    form_layout.addWidget(preview_row)

    for widget in (self.test_action_combo, self.test_player_id_input, self.test_number_input, self.test_custom_input, self.test_text_input):
        if isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(lambda _index: _update_console_test_preview(self))
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(lambda _text: _update_console_test_preview(self))
        else:
            widget.textChanged.connect(lambda: _update_console_test_preview(self))

    root.addWidget(form_card)
    root.addStretch(1)
    scroll.setWidget(host)
    _update_console_test_preview(self)
    return scroll


def _build_appointments_tab(self: MainWindow) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("appointmentsTabScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.viewport().setObjectName("appointmentsTabViewport")
    scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    host = QWidget()
    host.setObjectName("appointmentsTabHost")
    host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    root = QVBoxLayout(host)
    root.setContentsMargins(18, 14, 18, 18)
    root.setSpacing(12)

    top_card, top_layout = _make_card(
        host,
        "Призначення",
        "Нові заявки з Google Forms і готові тексти для Telegram.",
    )
    action_row = QWidget(top_card)
    action_layout = QHBoxLayout(action_row)
    action_layout.setContentsMargins(0, 0, 0, 0)
    action_layout.setSpacing(8)
    self.appointment_refresh_btn = QPushButton("Оновити список", action_row)
    self.appointment_count_label = QLabel("Нових заявок: -", action_row)
    self.appointment_sync_label = QLabel("Зняття винесено в окрему вкладку", action_row)
    self.appointment_sync_label.setProperty("class", "muted")
    self.appointment_refresh_btn.setProperty("class", "primaryAction")
    self.appointment_refresh_btn.clicked.connect(lambda: _start_appointments_fetch(self))
    action_layout.addWidget(self.appointment_refresh_btn)
    action_layout.addWidget(self.appointment_count_label)
    action_layout.addWidget(self.appointment_sync_label)
    action_layout.addStretch(1)
    top_layout.addWidget(action_row)
    root.addWidget(top_card)

    body = QWidget(host)
    body_layout = QHBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(12)

    queue_card, queue_layout = _make_card(body, "Нові заявки")
    queue_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    self.appointments_table = QTableWidget(0, 7, queue_card)
    _configure_appointment_table(self.appointments_table, ("Роль", "NickName", "ID", "Організація", "Telegram", "Дата", "Джерело"))
    self.appointments_table.currentCellChanged.connect(lambda *_args: _update_appointment_detail(self))
    queue_layout.addWidget(self.appointments_table)

    detail_card, detail_layout = _make_card(body, "Картка")
    detail_card.setMinimumWidth(380)
    detail_card.setMaximumWidth(520)
    self.appointment_detail_title = QLabel("Оберіть заявку", detail_card)
    self.appointment_detail_title.setProperty("class", "sectionTitle")
    self.appointment_detail_text = QPlainTextEdit(detail_card)
    self.appointment_detail_text.setReadOnly(True)
    self.appointment_detail_text.setMinimumHeight(146)

    telegram_row = QWidget(detail_card)
    telegram_layout = QHBoxLayout(telegram_row)
    telegram_layout.setContentsMargins(0, 0, 0, 0)
    telegram_layout.setSpacing(8)
    self.appointment_telegram_warning = QLabel("Додайте людину до Telegram групи", telegram_row)
    self.appointment_telegram_warning.setWordWrap(True)
    self.appointment_telegram_tag = QLineEdit(telegram_row)
    self.appointment_telegram_tag.setReadOnly(True)
    self.appointment_copy_telegram_btn = QPushButton("Копіювати тег", telegram_row)
    self.appointment_copy_telegram_btn.clicked.connect(lambda: _copy_appointment_telegram(self))
    telegram_layout.addWidget(self.appointment_telegram_warning, 1)
    telegram_layout.addWidget(self.appointment_telegram_tag)
    telegram_layout.addWidget(self.appointment_copy_telegram_btn)

    self.appointment_reason_input = _make_line_edit(detail_card, "Причина зняття / нотатка")
    self.appointment_reason_input.textChanged.connect(lambda _text: _update_appointment_announcement(self))
    self.appointment_announcement_preview = QPlainTextEdit(detail_card)
    self.appointment_announcement_preview.setReadOnly(True)
    self.appointment_announcement_preview.setMinimumHeight(94)

    button_grid = QGridLayout()
    button_grid.setContentsMargins(0, 0, 0, 0)
    button_grid.setSpacing(8)
    self.appointment_approve_btn = QPushButton("Призначити", detail_card)
    self.appointment_reject_btn = QPushButton("Відхилити", detail_card)
    self.appointment_remove_btn = QPushButton("Зняти з посади", detail_card)
    self.appointment_copy_announcement_btn = QPushButton("Копіювати оголошення", detail_card)
    self.appointment_rank_btn = QPushButton("Видати ранг", detail_card)
    self.appointment_approve_btn.setProperty("class", "primaryAction")
    self.appointment_reject_btn.setProperty("class", "secondaryAction")
    self.appointment_remove_btn.setProperty("class", "dangerGhost")
    self.appointment_copy_announcement_btn.setProperty("class", "secondaryAction")
    self.appointment_rank_btn.setProperty("class", "secondaryAction")
    self.appointment_approve_btn.clicked.connect(lambda: _start_appointment_action(self, "approve"))
    self.appointment_reject_btn.clicked.connect(lambda: _start_appointment_action(self, "reject"))
    self.appointment_remove_btn.clicked.connect(lambda: _start_appointment_action(self, "remove"))
    self.appointment_copy_announcement_btn.clicked.connect(lambda: _copy_appointment_announcement(self))
    self.appointment_rank_btn.clicked.connect(lambda: _issue_appointment_rank(self))
    button_grid.addWidget(self.appointment_approve_btn, 0, 0)
    button_grid.addWidget(self.appointment_reject_btn, 0, 1)
    button_grid.addWidget(self.appointment_remove_btn, 1, 0)
    button_grid.addWidget(self.appointment_rank_btn, 1, 1)
    button_grid.addWidget(self.appointment_copy_announcement_btn, 2, 0, 1, 2)

    detail_layout.addWidget(self.appointment_detail_title)
    detail_layout.addWidget(self.appointment_detail_text)
    detail_layout.addWidget(telegram_row)
    detail_layout.addWidget(self.appointment_reason_input)
    detail_layout.addWidget(self.appointment_announcement_preview)
    detail_layout.addLayout(button_grid)

    body_layout.addWidget(queue_card, 3)
    body_layout.addWidget(detail_card, 2)
    root.addWidget(body, 1)

    scroll.setWidget(host)
    self._appointment_records = []
    self._appointment_record_by_uid = {}
    self._appointment_fetch_thread = None
    self._appointment_action_threads = []
    self._appointment_term_thread = None
    _load_appointment_config_into_ui(self)
    _set_appointment_action_buttons_enabled(self, False)
    if not getattr(self, "_appointment_auto_fetch_scheduled", False):
        self._appointment_auto_fetch_scheduled = True
        QTimer.singleShot(700, lambda: _start_appointments_fetch(self))
    return scroll


def _build_appointment_removals_tab(self: MainWindow) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setObjectName("appointmentRemovalsTabScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.viewport().setObjectName("appointmentRemovalsTabViewport")
    scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    host = QWidget()
    host.setObjectName("appointmentRemovalsTabHost")
    host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    root = QVBoxLayout(host)
    root.setContentsMargins(18, 14, 18, 18)
    root.setSpacing(12)

    top_card, top_layout = _make_card(
        host,
        "Зняття",
        "Пошук активних лідерів, заступників і слідкуючих у GitHub Projects.",
    )
    controls = QWidget(top_card)
    controls_layout = QGridLayout(controls)
    controls_layout.setContentsMargins(0, 0, 0, 0)
    controls_layout.setSpacing(8)

    self.active_appointment_search_input = _make_line_edit(controls, "Пошук: NickName, ID, Telegram, організація")
    self.active_appointment_role_filter = QComboBox(controls)
    self.active_appointment_role_filter.addItem("Усі ролі", "")
    self.active_appointment_role_filter.addItem("Лідери", ROLE_LEADER)
    self.active_appointment_role_filter.addItem("Заступники", ROLE_DEPUTY)
    self.active_appointment_role_filter.addItem("Слідкуючі", ROLE_WATCHER)
    self.active_appointment_org_filter = QComboBox(controls)
    self.active_appointment_org_filter.addItem("Усі організації", "")
    for option in _FACTION_OPTIONS:
        code = option.split(" - ", 1)[-1].strip()
        self.active_appointment_org_filter.addItem(option, code)

    self.active_appointment_refresh_btn = QPushButton("Оновити активних", controls)
    self.active_appointment_sync_terms_btn = QPushButton("Синхронізувати терміни", controls)
    self.active_appointment_count_label = QLabel("Активних: -", controls)
    self.active_appointment_sync_label = QLabel("GitHub список ще не завантажено", controls)
    self.active_appointment_sync_label.setProperty("class", "muted")
    self.active_appointment_refresh_btn.setProperty("class", "primaryAction")
    self.active_appointment_sync_terms_btn.setProperty("class", "secondaryAction")

    self.active_appointment_search_input.textChanged.connect(lambda _text: _refresh_active_appointments_table(self))
    self.active_appointment_role_filter.currentIndexChanged.connect(lambda _index: _refresh_active_appointments_table(self))
    self.active_appointment_org_filter.currentIndexChanged.connect(lambda _index: _refresh_active_appointments_table(self))
    self.active_appointment_refresh_btn.clicked.connect(lambda: _start_active_appointments_fetch(self))
    self.active_appointment_sync_terms_btn.clicked.connect(lambda: _start_appointment_term_sync(self))

    controls_layout.addWidget(self.active_appointment_search_input, 0, 0, 1, 3)
    controls_layout.addWidget(self.active_appointment_role_filter, 0, 3)
    controls_layout.addWidget(self.active_appointment_org_filter, 0, 4)
    controls_layout.addWidget(self.active_appointment_refresh_btn, 1, 0)
    controls_layout.addWidget(self.active_appointment_sync_terms_btn, 1, 1)
    controls_layout.addWidget(self.active_appointment_count_label, 1, 2)
    controls_layout.addWidget(self.active_appointment_sync_label, 1, 3, 1, 2)
    top_layout.addWidget(controls)
    root.addWidget(top_card)

    body = QWidget(host)
    body_layout = QHBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(12)

    list_card, list_layout = _make_card(body, "Активні призначені")
    list_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    self.active_appointments_table = QTableWidget(0, 8, list_card)
    _configure_appointment_table(
        self.active_appointments_table,
        ("Роль", "NickName", "ID", "Організація", "Термін", "Telegram", "Дата", "Project"),
    )
    self.active_appointments_table.currentCellChanged.connect(lambda *_args: _update_active_appointment_detail(self))
    list_layout.addWidget(self.active_appointments_table)

    detail_card, detail_layout = _make_card(body, "Картка зняття")
    detail_card.setMinimumWidth(390)
    detail_card.setMaximumWidth(540)
    self.active_appointment_detail_title = QLabel("Оберіть людину", detail_card)
    self.active_appointment_detail_title.setProperty("class", "sectionTitle")
    self.active_appointment_detail_text = QPlainTextEdit(detail_card)
    self.active_appointment_detail_text.setReadOnly(True)
    self.active_appointment_detail_text.setMinimumHeight(170)

    telegram_row = QWidget(detail_card)
    telegram_layout = QHBoxLayout(telegram_row)
    telegram_layout.setContentsMargins(0, 0, 0, 0)
    telegram_layout.setSpacing(8)
    self.active_appointment_telegram_warning = QLabel("Кікніть людину з Telegram групи:", telegram_row)
    self.active_appointment_telegram_warning.setWordWrap(True)
    self.active_appointment_telegram_tag = QLineEdit(telegram_row)
    self.active_appointment_telegram_tag.setReadOnly(True)
    self.active_appointment_copy_telegram_btn = QPushButton("Копіювати тег", telegram_row)
    self.active_appointment_copy_telegram_btn.clicked.connect(lambda: _copy_active_appointment_telegram(self))
    telegram_layout.addWidget(self.active_appointment_telegram_warning, 1)
    telegram_layout.addWidget(self.active_appointment_telegram_tag)
    telegram_layout.addWidget(self.active_appointment_copy_telegram_btn)

    self.active_appointment_reason_input = _make_line_edit(detail_card, "Причина зняття")
    self.active_appointment_reason_input.textChanged.connect(lambda _text: _update_active_appointment_announcement(self))
    self.active_appointment_announcement_preview = QPlainTextEdit(detail_card)
    self.active_appointment_announcement_preview.setReadOnly(True)
    self.active_appointment_announcement_preview.setMinimumHeight(94)

    button_grid = QGridLayout()
    button_grid.setContentsMargins(0, 0, 0, 0)
    button_grid.setSpacing(8)
    self.active_appointment_remove_btn = QPushButton("Зняти з посади", detail_card)
    self.active_appointment_update_btn = QPushButton("Оновити картку", detail_card)
    self.active_appointment_copy_announcement_btn = QPushButton("Копіювати оголошення", detail_card)
    self.active_appointment_remove_btn.setProperty("class", "dangerGhost")
    self.active_appointment_update_btn.setProperty("class", "secondaryAction")
    self.active_appointment_copy_announcement_btn.setProperty("class", "secondaryAction")
    self.active_appointment_remove_btn.clicked.connect(lambda: _start_active_appointment_action(self, "remove"))
    self.active_appointment_update_btn.clicked.connect(lambda: _start_active_appointment_action(self, "update"))
    self.active_appointment_copy_announcement_btn.clicked.connect(lambda: _copy_active_appointment_announcement(self))
    button_grid.addWidget(self.active_appointment_remove_btn, 0, 0)
    button_grid.addWidget(self.active_appointment_update_btn, 0, 1)
    button_grid.addWidget(self.active_appointment_copy_announcement_btn, 1, 0, 1, 2)

    detail_layout.addWidget(self.active_appointment_detail_title)
    detail_layout.addWidget(self.active_appointment_detail_text)
    detail_layout.addWidget(telegram_row)
    detail_layout.addWidget(self.active_appointment_reason_input)
    detail_layout.addWidget(self.active_appointment_announcement_preview)
    detail_layout.addLayout(button_grid)

    body_layout.addWidget(list_card, 3)
    body_layout.addWidget(detail_card, 2)
    root.addWidget(body, 1)

    scroll.setWidget(host)
    self._appointment_active_records = []
    self._appointment_active_record_by_uid = {}
    self._appointment_active_fetch_thread = None
    self._appointment_active_action_threads = []
    self._appointment_active_loaded = False
    _set_active_appointment_buttons_enabled(self, False)
    return scroll


def _configure_appointment_table(table: QTableWidget, headers: tuple[str, ...]) -> None:
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    for column in range(len(headers)):
        mode = QHeaderView.ResizeMode.Stretch if column in {1, 3} else QHeaderView.ResizeMode.ResizeToContents
        table.horizontalHeader().setSectionResizeMode(column, mode)


def _load_appointment_config_into_ui(self: MainWindow) -> None:
    self._appointment_config = load_appointment_config()


def _appointment_config_from_ui(self: MainWindow) -> AppointmentConfig:
    config = getattr(self, "_appointment_config", None)
    if config is None:
        config = load_appointment_config()
        self._appointment_config = config
    return config


def _save_appointment_config_from_ui(self: MainWindow) -> None:
    config = _appointment_config_from_ui(self)
    save_appointment_config(config)
    self._appointment_config = config
    self._set_status("Налаштування призначень збережено")


def _line_int(field: QLineEdit | None, default: int) -> int:
    value = _line_value(field)
    try:
        return int(value)
    except ValueError:
        return default


def _start_appointments_fetch(self: MainWindow) -> None:
    config = _appointment_config_from_ui(self)
    if not config.apps_script_url:
        self._set_status("Apps Script URL не налаштовано")
        return
    if getattr(self, "_appointment_fetch_thread", None) is not None:
        self._set_status("Черга заявок уже оновлюється")
        return
    refresh_btn = getattr(self, "appointment_refresh_btn", None)
    if refresh_btn is not None:
        refresh_btn.setEnabled(False)
    self._set_status("Оновлюю призначення та зняття...")
    thread = _AppointmentFetchThread(config)
    self._appointment_fetch_thread = thread
    thread.completed.connect(lambda records, error: _finish_appointments_fetch(self, records, error))
    thread.finished.connect(lambda: setattr(self, "_appointment_fetch_thread", None))
    thread.start()


def _finish_appointments_fetch(self: MainWindow, records: list[AppointmentRecord], error: str) -> None:
    refresh_btn = getattr(self, "appointment_refresh_btn", None)
    if refresh_btn is not None:
        refresh_btn.setEnabled(True)
    if error:
        self._set_status(f"Помилка оновлення призначень: {error}")
        return
    self._appointment_records = records
    self._appointment_record_by_uid = {record.uid: record for record in records}
    _refresh_appointments_table(self)
    appoint_count = len([record for record in records if not record.is_removal])
    removal_count = len([record for record in records if record.is_removal])
    self._set_status(f"Завантажено нових заявок: {appoint_count}. Червоних рядків на зняття: {removal_count}")
    _refresh_active_appointments_table(self)


def _start_appointment_term_sync(self: MainWindow) -> None:
    if getattr(self, "_appointment_term_thread", None) is not None:
        return
    config = _appointment_config_from_ui(self)
    if not config.github_token:
        return
    label = getattr(self, "active_appointment_sync_label", None) or getattr(self, "appointment_sync_label", None)
    if label is not None:
        label.setText("Терміни перевіряються у фоні...")
    sync_btn = getattr(self, "active_appointment_sync_terms_btn", None)
    if sync_btn is not None:
        sync_btn.setEnabled(False)
    thread = _AppointmentTermSyncThread(config)
    self._appointment_term_thread = thread
    thread.completed.connect(lambda count, error: _finish_appointment_term_sync(self, count, error))
    thread.finished.connect(lambda: setattr(self, "_appointment_term_thread", None))
    thread.start()


def _finish_appointment_term_sync(self: MainWindow, count: int, error: str) -> None:
    sync_btn = getattr(self, "active_appointment_sync_terms_btn", None)
    if sync_btn is not None:
        sync_btn.setEnabled(True)
    label = getattr(self, "active_appointment_sync_label", None) or getattr(self, "appointment_sync_label", None)
    if label is None:
        return
    if error:
        label.setText("Терміни: фонова перевірка не завершилась")
    else:
        label.setText(f"Терміни оновлено: {count}")
        if getattr(self, "_appointment_active_loaded", False):
            _start_active_appointments_fetch(self)


def _start_active_appointments_fetch(self: MainWindow) -> None:
    config = _appointment_config_from_ui(self)
    if not config.github_token:
        self._set_status("GitHub token не налаштований у runtime-конфігу")
        return
    if getattr(self, "_appointment_active_fetch_thread", None) is not None:
        self._set_status("Список активних уже оновлюється")
        return
    refresh_btn = getattr(self, "active_appointment_refresh_btn", None)
    if refresh_btn is not None:
        refresh_btn.setEnabled(False)
    label = getattr(self, "active_appointment_sync_label", None)
    if label is not None:
        label.setText("Завантажую активних з GitHub...")
    self._set_status("Оновлюю активні призначення з GitHub...")
    thread = _AppointmentActiveFetchThread(config)
    self._appointment_active_fetch_thread = thread
    thread.completed.connect(lambda records, error: _finish_active_appointments_fetch(self, records, error))
    thread.finished.connect(lambda: setattr(self, "_appointment_active_fetch_thread", None))
    thread.start()


def _finish_active_appointments_fetch(self: MainWindow, records: list[AppointmentRecord], error: str) -> None:
    refresh_btn = getattr(self, "active_appointment_refresh_btn", None)
    if refresh_btn is not None:
        refresh_btn.setEnabled(True)
    label = getattr(self, "active_appointment_sync_label", None)
    if error:
        if label is not None:
            label.setText("GitHub список не завантажився")
        self._set_status(f"Помилка GitHub списку: {error}")
        return
    self._appointment_active_records = records
    self._appointment_active_loaded = True
    _refresh_active_appointments_table(self)
    if label is not None:
        label.setText("GitHub список оновлено")
    self._set_status(f"Активних призначених завантажено: {len(records)}")


def _active_record_key(record: AppointmentRecord) -> tuple[str, str]:
    return (record.role, record.player_id or record.nickname.casefold())


def _all_active_appointment_records(self: MainWindow) -> list[AppointmentRecord]:
    form_removals = [record for record in getattr(self, "_appointment_records", []) if record.is_removal]
    github_records = list(getattr(self, "_appointment_active_records", []))
    github_by_key = {_active_record_key(record): record for record in github_records}
    merged: list[AppointmentRecord] = []
    seen: set[tuple[str, str]] = set()

    for record in form_removals:
        match = github_by_key.get(_active_record_key(record))
        if match is not None:
            record.github_item_id = match.github_item_id
            if not record.telegram:
                record.telegram = match.telegram
            if not record.discord:
                record.discord = match.discord
            if not record.forum_url:
                record.forum_url = match.forum_url
            record.raw.setdefault("project", match.raw.get("project"))
            record.raw.setdefault("values", match.raw.get("values", {}))
        key = _active_record_key(record)
        seen.add(key)
        merged.append(record)

    for record in github_records:
        key = _active_record_key(record)
        if key in seen:
            continue
        seen.add(key)
        merged.append(record)
    return merged


def _compact_field_key(value: str) -> str:
    return re.sub(r"[^a-zа-яіїєґ0-9]+", "", value.casefold())


def _active_record_value(record: AppointmentRecord, *names: str) -> str:
    values = record.raw.get("values") if isinstance(record.raw, dict) else None
    if not isinstance(values, dict):
        return ""
    for name in names:
        key = _compact_field_key(name)
        if key in values:
            return str(values[key] or "")
    for name in names:
        key = _compact_field_key(name)
        for value_key, value in values.items():
            value_key_text = _compact_field_key(str(value_key))
            if key in value_key_text or value_key_text in key:
                return str(value or "")
    return ""


def _active_record_project_label(config: AppointmentConfig, record: AppointmentRecord) -> str:
    project_number = record.raw.get("project") if isinstance(record.raw, dict) else None
    try:
        number = int(project_number) if project_number else project_number_for_record(config, record)
    except (TypeError, ValueError):
        number = project_number_for_record(config, record)
    return f"#{number}"


def _active_record_term_text(record: AppointmentRecord) -> str:
    return _active_record_value(record, "Кількість термінів") or "-"


def _active_appointment_matches_filters(self: MainWindow, record: AppointmentRecord) -> bool:
    query = _line_value(getattr(self, "active_appointment_search_input", None)).casefold()
    role_filter = ""
    role_combo = getattr(self, "active_appointment_role_filter", None)
    if role_combo is not None:
        role_filter = str(role_combo.currentData() or "")
    org_filter = ""
    org_combo = getattr(self, "active_appointment_org_filter", None)
    if org_combo is not None:
        org_filter = str(org_combo.currentData() or "")

    if role_filter and record.role != role_filter:
        return False
    info = record.faction_info
    if org_filter and (info is None or info.code != org_filter):
        return False
    if not query:
        return True
    haystack = " ".join(
        (
            record.nickname,
            record.player_id,
            record.role_label,
            record.organization_name,
            record.faction,
            record.telegram_tag,
            record.discord,
            record.email,
            _active_record_value(record, "Міністерство", "Статус", "Посада"),
        )
    ).casefold()
    return query in haystack


def _filtered_active_appointment_records(self: MainWindow) -> list[AppointmentRecord]:
    records = [record for record in _all_active_appointment_records(self) if _active_appointment_matches_filters(self, record)]
    records.sort(key=lambda item: (item.role_label, item.organization_name, item.nickname))
    return records


def _refresh_active_appointments_table(self: MainWindow) -> None:
    table = getattr(self, "active_appointments_table", None)
    if table is None:
        return
    config = _appointment_config_from_ui(self)
    records = _filtered_active_appointment_records(self)
    self._appointment_active_record_by_uid = {record.uid: record for record in records}
    _fill_active_appointment_table(table, records, config)
    count_label = getattr(self, "active_appointment_count_label", None)
    if count_label is not None:
        total = len(_all_active_appointment_records(self))
        count_label.setText(f"Показано: {len(records)} / {total}")
    if table.rowCount() > 0 and table.currentRow() < 0:
        table.selectRow(0)
    _update_active_appointment_detail(self)


def _fill_active_appointment_table(table: QTableWidget, records: list[AppointmentRecord], config: AppointmentConfig) -> None:
    table.blockSignals(True)
    try:
        table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = (
                record.role_label,
                record.nickname,
                record.player_id,
                record.organization_name,
                _active_record_term_text(record),
                record.telegram_tag,
                record.appoint_date,
                _active_record_project_label(config, record),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record.uid)
                if record.source_key and not record.source_key.startswith("github:"):
                    item.setForeground(QColor("#f3a6a6"))
                table.setItem(row, column, item)
    finally:
        table.blockSignals(False)
    table.resizeRowsToContents()


def _selected_active_appointment(self: MainWindow) -> AppointmentRecord | None:
    table = getattr(self, "active_appointments_table", None)
    if table is None:
        return None
    row = table.currentRow()
    if row < 0:
        return None
    item = table.item(row, 0)
    if item is None:
        return None
    uid = str(item.data(Qt.ItemDataRole.UserRole) or "")
    return getattr(self, "_appointment_active_record_by_uid", {}).get(uid)


def _update_active_appointment_detail(self: MainWindow) -> None:
    record = _selected_active_appointment(self)
    title = getattr(self, "active_appointment_detail_title", None)
    detail = getattr(self, "active_appointment_detail_text", None)
    telegram_tag = getattr(self, "active_appointment_telegram_tag", None)
    if record is None:
        if title is not None:
            title.setText("Оберіть людину")
        if detail is not None:
            detail.setPlainText("")
        if telegram_tag is not None:
            telegram_tag.setText("")
        _set_active_appointment_buttons_enabled(self, False)
        _update_active_appointment_announcement(self)
        return

    config = _appointment_config_from_ui(self)
    project_label = _active_record_project_label(config, record)
    if title is not None:
        title.setText(f"{record.nickname} [{record.player_id}]")
    if detail is not None:
        detail.setPlainText(
            "\n".join(
                (
                    f"Посада: {record.position_title}",
                    f"GitHub Project: {project_label}",
                    f"ID організації: {record.faction_info.faction_id if record.faction_info else '-'}",
                    f"Назва організації: {record.organization_name or '-'}",
                    f"Міністерство / статус: {_active_record_value(record, 'Міністерство', 'Статус') or record.status or '-'}",
                    f"Дата призначення: {record.appoint_date or '-'}",
                    f"Кількість термінів: {_active_record_term_text(record)}",
                    f"Telegram: {record.telegram_tag or '-'}",
                    f"Discord: {record.discord or '-'}",
                    f"Ф.А.: {record.forum_url or '-'}",
                    f"Email: {record.email or '-'}",
                    f"Джерело: {record.sheet_name or record.source_label}",
                )
            )
        )
    if telegram_tag is not None:
        telegram_tag.setText(record.telegram_tag)
    _set_active_appointment_buttons_enabled(self, True)
    _update_active_appointment_announcement(self)


def _set_active_appointment_buttons_enabled(self: MainWindow, enabled: bool) -> None:
    for name in (
        "active_appointment_remove_btn",
        "active_appointment_update_btn",
        "active_appointment_copy_announcement_btn",
        "active_appointment_copy_telegram_btn",
    ):
        button = getattr(self, name, None)
        if button is not None:
            button.setEnabled(enabled)


def _active_appointment_note(self: MainWindow) -> str:
    return _line_value(getattr(self, "active_appointment_reason_input", None))


def _active_appointment_announcement(self: MainWindow, record: AppointmentRecord | None = None) -> str:
    record = record or _selected_active_appointment(self)
    if record is None:
        return ""
    reason = _active_appointment_note(self)
    return f"{record.nickname} - знятий з посади {record.position_title}\nПричина: {reason}".rstrip()


def _update_active_appointment_announcement(self: MainWindow) -> None:
    preview = getattr(self, "active_appointment_announcement_preview", None)
    if preview is not None:
        preview.setPlainText(_active_appointment_announcement(self))


def _copy_active_appointment_telegram(self: MainWindow) -> None:
    record = _selected_active_appointment(self)
    _copy_text_to_clipboard(self, record.telegram_tag if record else "", "Telegram тег скопійовано")


def _copy_active_appointment_announcement(self: MainWindow) -> None:
    _copy_text_to_clipboard(self, _active_appointment_announcement(self), "Оголошення скопійовано")


def _start_active_appointment_action(self: MainWindow, action: str) -> None:
    record = _selected_active_appointment(self)
    if record is None:
        self._set_status("Оберіть людину")
        return
    config = _appointment_config_from_ui(self)
    if not config.github_token:
        self._set_status("GitHub token не налаштований у runtime-конфігу")
        return
    note = _active_appointment_note(self)
    if action == "remove" and not note:
        self._set_status("Вкажіть причину зняття")
        if getattr(self, "active_appointment_reason_input", None) is not None:
            self.active_appointment_reason_input.setFocus()
        return
    if action == "remove":
        answer = QMessageBox.question(
            self,
            "Зняти з посади",
            f"Зняти {record.nickname} з посади?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

    action_label = "зняття" if action == "remove" else "оновлення картки"
    self._set_status(f"{action_label.capitalize()} запущено у фоні")
    if action == "remove":
        _remove_active_appointment_record_locally(self, record)
    thread = _AppointmentActionThread(config, action, record, note)
    threads = getattr(self, "_appointment_active_action_threads", None)
    if not isinstance(threads, list):
        threads = []
        self._appointment_active_action_threads = threads
    threads.append(thread)
    thread.completed.connect(lambda done_action, done_record, result, error: _finish_active_appointment_action(self, done_action, done_record, result, error))
    thread.finished.connect(lambda finished_thread=thread: _drop_active_appointment_action_thread(self, finished_thread))
    thread.start()


def _remove_active_appointment_record_locally(self: MainWindow, record: AppointmentRecord) -> None:
    self._appointment_active_records = [item for item in getattr(self, "_appointment_active_records", []) if item.uid != record.uid]
    self._appointment_records = [item for item in getattr(self, "_appointment_records", []) if item.uid != record.uid]
    _refresh_active_appointments_table(self)


def _drop_active_appointment_action_thread(self: MainWindow, thread: QThread) -> None:
    threads = getattr(self, "_appointment_active_action_threads", None)
    if isinstance(threads, list) and thread in threads:
        threads.remove(thread)


def _finish_active_appointment_action(
    self: MainWindow,
    action: str,
    record: AppointmentRecord,
    result: AppointmentActionResult,
    error: str,
) -> None:
    if error or not result.ok:
        self._set_status(f"Помилка дії: {error or result.message}")
        if action == "remove" and record.uid not in getattr(self, "_appointment_active_record_by_uid", {}):
            if record.source_key.startswith("github:"):
                self._appointment_active_records = [*getattr(self, "_appointment_active_records", []), record]
            else:
                self._appointment_records = [*getattr(self, "_appointment_records", []), record]
            _refresh_active_appointments_table(self)
        return
    self._set_status(result.message)
    if action == "update":
        _start_active_appointments_fetch(self)


def _refresh_appointments_table(self: MainWindow) -> None:
    appoint_table = getattr(self, "appointments_table", None)
    if appoint_table is None:
        return
    records = list(getattr(self, "_appointment_records", []))
    appointment_records = [record for record in records if not record.is_removal]

    _fill_appointment_table(appoint_table, appointment_records)

    count_label = getattr(self, "appointment_count_label", None)
    if count_label is not None:
        count_label.setText(f"Нових заявок: {len(appointment_records)}")
    active_table = getattr(self, "appointments_table", None)
    if active_table is not None and active_table.rowCount() > 0 and active_table.currentRow() < 0:
        active_table.selectRow(0)
    _update_appointment_detail(self)


def _select_first_appointment_row(self: MainWindow) -> None:
    table = _active_appointment_table(self)
    if table is not None and table.rowCount() > 0:
        table.selectRow(0)
    _update_appointment_detail(self)


def _fill_appointment_table(table: QTableWidget, records: list[AppointmentRecord]) -> None:
    table.blockSignals(True)
    try:
        table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = (
                record.role_label,
                record.nickname,
                record.player_id,
                record.organization_name,
                record.telegram_tag,
                record.appoint_date,
                record.source_label,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record.uid)
                if record.is_removal:
                    item.setForeground(QColor("#f3a6a6"))
                table.setItem(row, column, item)
    finally:
        table.blockSignals(False)
    table.resizeRowsToContents()


def _active_appointment_table(self: MainWindow) -> QTableWidget | None:
    return getattr(self, "appointments_table", None)


def _selected_appointment(self: MainWindow) -> AppointmentRecord | None:
    table = _active_appointment_table(self)
    if table is None:
        return None
    row = table.currentRow()
    if row < 0:
        return None
    item = table.item(row, 0)
    if item is None:
        return None
    uid = str(item.data(Qt.ItemDataRole.UserRole) or "")
    return getattr(self, "_appointment_record_by_uid", {}).get(uid)


def _update_appointment_detail(self: MainWindow) -> None:
    record = _selected_appointment(self)
    title = getattr(self, "appointment_detail_title", None)
    detail = getattr(self, "appointment_detail_text", None)
    telegram_warning = getattr(self, "appointment_telegram_warning", None)
    telegram_tag = getattr(self, "appointment_telegram_tag", None)
    rank_btn = getattr(self, "appointment_rank_btn", None)
    approve_btn = getattr(self, "appointment_approve_btn", None)
    reject_btn = getattr(self, "appointment_reject_btn", None)
    remove_btn = getattr(self, "appointment_remove_btn", None)
    reason_input = getattr(self, "appointment_reason_input", None)

    if record is None:
        if title is not None:
            title.setText("Оберіть заявку")
        if detail is not None:
            detail.setPlainText("")
        if telegram_warning is not None:
            telegram_warning.setText("Оберіть людину")
        if telegram_tag is not None:
            telegram_tag.setText("")
        _set_appointment_action_buttons_enabled(self, False)
        for button in (rank_btn, approve_btn, reject_btn, remove_btn):
            if button is not None:
                button.setVisible(False)
        if reason_input is not None:
            reason_input.setVisible(False)
        _update_appointment_announcement(self)
        return

    config = _appointment_config_from_ui(self)
    project_number = project_number_for_record(config, record)
    action_label = "Зняття" if record.is_removal else "Призначення"
    if title is not None:
        title.setText(f"{record.nickname} [{record.player_id}]")
    if detail is not None:
        detail.setPlainText(
            "\n".join(
                (
                    f"Дія: {action_label}",
                    f"Посада: {record.position_title}",
                    f"GitHub Project: #{project_number}",
                    f"ID організації: {record.faction_info.faction_id if record.faction_info else '-'}",
                    f"Назва організації: {record.organization_name or '-'}",
                    f"Дата: {record.appoint_date or '-'}",
                    f"Telegram: {record.telegram_tag or '-'}",
                    f"Discord: {record.discord or '-'}",
                    f"Ф.А.: {record.forum_url or '-'}",
                    f"Email: {record.email or '-'}",
                    f"2FA: {record.two_fa_url or '-'}",
                    f"Джерело: {record.sheet_name or record.source_label}{f', рядок {record.row_number}' if record.row_number else ''}",
                )
            )
        )
    if telegram_warning is not None:
        telegram_warning.setText(
            f"Кікніть {record.role_label.lower()} з Telegram групи:" if record.is_removal
            else f"Додайте {record.role_label.lower()} до Telegram групи:"
        )
    if telegram_tag is not None:
        telegram_tag.setText(record.telegram_tag)
    _set_appointment_action_buttons_enabled(self, True)
    if reason_input is not None:
        reason_input.setVisible(record.is_removal)
    if rank_btn is not None:
        level = record.rank_level
        rank_btn.setVisible(not record.is_removal)
        rank_btn.setEnabled(level is not None and bool(record.player_id))
        rank_btn.setText(f"Видати {level} ранг" if level else "Ранг не потрібен")
    if approve_btn is not None:
        approve_btn.setVisible(not record.is_removal)
        approve_btn.setEnabled(not record.is_removal)
    if reject_btn is not None:
        reject_btn.setVisible(not record.is_removal)
        reject_btn.setEnabled(not record.is_removal and record.row_number > 0)
    if remove_btn is not None:
        remove_btn.setVisible(record.is_removal)
        remove_btn.setEnabled(record.is_removal)
    _update_appointment_announcement(self)


def _set_appointment_action_buttons_enabled(self: MainWindow, enabled: bool) -> None:
    for name in (
        "appointment_approve_btn",
        "appointment_reject_btn",
        "appointment_remove_btn",
        "appointment_copy_announcement_btn",
        "appointment_copy_telegram_btn",
        "appointment_rank_btn",
    ):
        button = getattr(self, name, None)
        if button is not None:
            button.setEnabled(enabled)


def _appointment_note(self: MainWindow) -> str:
    return _line_value(getattr(self, "appointment_reason_input", None))


def _appointment_announcement(self: MainWindow, record: AppointmentRecord | None = None) -> str:
    record = record or _selected_appointment(self)
    if record is None:
        return ""
    position = record.position_title or record.role_label
    if record.is_removal:
        reason = _appointment_note(self)
        return f"{record.nickname} - знятий з посади {position}\nПричина: {reason}".rstrip()
    return f"{record.nickname} - призначений на посаду {position}\nВітаємо."


def _update_appointment_announcement(self: MainWindow) -> None:
    preview = getattr(self, "appointment_announcement_preview", None)
    if preview is not None:
        preview.setPlainText(_appointment_announcement(self))


def _copy_text_to_clipboard(self: MainWindow, text: str, status_message: str) -> None:
    app = QApplication.instance()
    if app is None or not text:
        self._set_status("Немає тексту для копіювання")
        return
    app.clipboard().setText(text)
    self._set_status(status_message)


def _copy_appointment_telegram(self: MainWindow) -> None:
    record = _selected_appointment(self)
    _copy_text_to_clipboard(self, record.telegram_tag if record else "", "Telegram тег скопійовано")


def _copy_appointment_announcement(self: MainWindow) -> None:
    _copy_text_to_clipboard(self, _appointment_announcement(self), "Оголошення скопійовано")


def _start_appointment_action(self: MainWindow, action: str) -> None:
    record = _selected_appointment(self)
    if record is None:
        self._set_status("Оберіть заявку")
        return
    config = _appointment_config_from_ui(self)
    if action in {"approve", "remove"} and not config.github_token:
        self._set_status("GitHub token не налаштований у runtime-конфігу")
        return
    if action == "reject":
        answer = QMessageBox.question(
            self,
            "Відхилити заявку",
            f"Відхилити заявку {record.nickname}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
    if action == "remove" and not _appointment_note(self):
        self._set_status("Вкажіть причину зняття")
        if getattr(self, "appointment_reason_input", None) is not None:
            self.appointment_reason_input.setFocus()
        return

    action_label = {"approve": "призначення", "reject": "відхилення", "remove": "зняття"}.get(action, action)
    self._set_status(f"{action_label.capitalize()} запущено у фоні")
    _remove_appointment_record_locally(self, record)
    thread = _AppointmentActionThread(config, action, record, _appointment_note(self))
    threads = getattr(self, "_appointment_action_threads", None)
    if not isinstance(threads, list):
        threads = []
        self._appointment_action_threads = threads
    threads.append(thread)
    thread.completed.connect(lambda done_action, done_record, result, error: _finish_appointment_action(self, done_action, done_record, result, error))
    thread.finished.connect(lambda finished_thread=thread: _drop_appointment_action_thread(self, finished_thread))
    thread.start()
    if action == "approve":
        _maybe_offer_appointment_rank(self, record)


def _remove_appointment_record_locally(self: MainWindow, record: AppointmentRecord) -> None:
    records = [item for item in getattr(self, "_appointment_records", []) if item.uid != record.uid]
    self._appointment_records = records
    self._appointment_record_by_uid = {item.uid: item for item in records}
    _refresh_appointments_table(self)


def _maybe_offer_appointment_rank(self: MainWindow, record: AppointmentRecord) -> None:
    if record.rank_level is None or not record.player_id:
        return
    answer = QMessageBox.question(
        self,
        "Видати ранг",
        f"Видати {record.rank_level} ранг для {record.nickname}[{record.player_id}] зараз?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if answer == QMessageBox.StandardButton.Yes:
        _issue_rank_for_record(self, record)


def _drop_appointment_action_thread(self: MainWindow, thread: QThread) -> None:
    threads = getattr(self, "_appointment_action_threads", None)
    if isinstance(threads, list) and thread in threads:
        threads.remove(thread)


def _finish_appointment_action(
    self: MainWindow,
    action: str,
    record: AppointmentRecord,
    result: AppointmentActionResult,
    error: str,
) -> None:
    if error or not result.ok:
        self._set_status(f"Помилка дії: {error or result.message}")
        if record.uid not in getattr(self, "_appointment_record_by_uid", {}):
            records = list(getattr(self, "_appointment_records", []))
            records.append(record)
            self._appointment_records = records
            self._appointment_record_by_uid = {item.uid: item for item in records}
            _refresh_appointments_table(self)
        return
    if action == "approve" and record.rank_level is not None:
        self._set_status(f"{result.message}. Ранг {record.rank_level} можна видати з гри.")
    else:
        self._set_status(result.message)


def _issue_appointment_rank(self: MainWindow) -> None:
    record = _selected_appointment(self)
    if record is None:
        self._set_status("Оберіть заявку")
        return
    _issue_rank_for_record(self, record)


def _issue_rank_for_record(self: MainWindow, record: AppointmentRecord) -> None:
    level = record.rank_level
    if level is None:
        self._set_status("Для цієї ролі ранг не потрібен")
        return
    player_id = _sanitize_console_command(record.player_id)
    if not player_id:
        self._set_status("У заявці немає ID")
        return
    _run_console_action(
        self,
        f"Ранг {level}",
        f"setfactionlevel {player_id} {level}",
        f"offsetfactionlevel {player_id} {level}",
    )


def _tab_index_by_object_name(tabs: QTabWidget, object_name: str) -> int | None:
    for index in range(tabs.count()):
        widget = tabs.widget(index)
        if widget is not None and widget.objectName() == object_name:
            return index
    return None


def _remove_extended_nav_button(self: MainWindow, key: str, fallback_text: str) -> None:
    nav_frame = self.findChild(QFrame, "navigationBar")
    if nav_frame is None:
        return
    for button in list(nav_frame.findChildren(QPushButton, "navButton")):
        if button.property("extendedNavKey") != key and button.text().strip().casefold() != fallback_text.casefold():
            continue
        host = button.parentWidget()
        if host is not None and host is not nav_frame:
            _detach_widget(host)
        else:
            _detach_widget(button)


def _remove_test_tab(self: MainWindow) -> None:
    tabs = getattr(self, "tabs", None)
    if tabs is None:
        return

    removed_current = False
    for index in range(tabs.count() - 1, -1, -1):
        widget = tabs.widget(index)
        if widget is None or widget.objectName() != "testTabScroll":
            continue
        removed_current = removed_current or tabs.currentIndex() == index
        tabs.removeTab(index)
        _detach_widget(widget)

    self._test_tab_index = -1
    _remove_extended_nav_button(self, "test", "Тест")
    if removed_current and tabs.count():
        tabs.setCurrentIndex(_REPORTS_TAB_INDEX)
        _update_shell_context(self, _REPORTS_TAB_INDEX)


def _navigate_to_tab_object(self: MainWindow, object_name: str) -> None:
    tabs = getattr(self, "tabs", None)
    if tabs is None:
        return
    index = _tab_index_by_object_name(tabs, object_name)
    if index is None:
        return
    tabs.setCurrentIndex(index)
    _update_shell_context(self, index)
    _sync_extended_nav_state(self, index)
    if object_name == "appointmentRemovalsTabScroll" and not getattr(self, "_appointment_active_loaded", False):
        _start_active_appointments_fetch(self)


def _bind_extended_nav_button(self: MainWindow, button: QPushButton, object_name: str, index: int) -> None:
    button.setProperty("tabIndex", index)
    button.setProperty("tabObjectName", object_name)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        try:
            button.clicked.disconnect()
        except Exception:
            pass
    button.clicked.connect(lambda _checked=False, tab_object_name=object_name: _navigate_to_tab_object(self, tab_object_name))


def _add_extended_nav_button(self: MainWindow, label: str, index: int, key: str, object_name: str) -> None:
    nav_frame = self.findChild(QFrame, "navigationBar")
    if nav_frame is None or nav_frame.layout() is None:
        return
    for button in nav_frame.findChildren(QPushButton, "navButton"):
        if button.property("extendedNavKey") == key:
            _bind_extended_nav_button(self, button, object_name, index)
            return

    host = QWidget(nav_frame)
    host.setProperty("navItem", True)
    host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    host.setFixedHeight(28)
    host_layout = QHBoxLayout(host)
    host_layout.setContentsMargins(5, 2, 5, 2)
    host_layout.setSpacing(0)

    button = QPushButton(label, host)
    button.setObjectName("navButton")
    button.setFlat(True)
    button.setFixedHeight(24)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setProperty("extendedNavKey", key)
    _bind_extended_nav_button(self, button, object_name, index)
    host_layout.addWidget(button)
    nav_frame.layout().addWidget(host)
    _repolish(button)
    _repolish(host)
    _repolish(nav_frame)


def _sync_extended_nav_state(self: MainWindow, active_index: int | None = None) -> None:
    tabs = getattr(self, "tabs", None)
    if tabs is None:
        return
    if active_index is None:
        active_index = tabs.currentIndex()

    buttons = self.findChildren(QPushButton, "navButton")
    for order, button in enumerate(buttons):
        tab_index = button.property("tabIndex")
        object_name = button.property("tabObjectName")
        object_index = _tab_index_by_object_name(tabs, str(object_name)) if object_name else None
        if object_index is not None:
            resolved_index = object_index
            button.setProperty("tabIndex", resolved_index)
        elif tab_index is None:
            tab_index = order
            button.setProperty("tabIndex", tab_index)
            resolved_index = order
        else:
            try:
                resolved_index = int(tab_index)
            except (TypeError, ValueError):
                resolved_index = order
        active = resolved_index == active_index
        button.setProperty("active", "true" if active else "false")
        _repolish(button)
        parent = button.parentWidget()
        if parent is not None:
            parent.setProperty("navItem", True)
            parent.setProperty("navActive", active)
            _repolish(parent)


def _connect_extended_log_watcher(self: MainWindow) -> None:
    if getattr(self, "_extended_raw_lines_connected", False):
        return
    watcher = getattr(self, "watcher", None)
    signal = getattr(watcher, "raw_lines_parsed", None)
    if signal is None:
        return
    signal.connect(lambda lines: _on_player_raw_log_lines(self, lines))
    self._extended_raw_lines_connected = True


def _ensure_extended_tabs(self: MainWindow) -> None:
    tabs = getattr(self, "tabs", None)
    if tabs is None:
        return

    _remove_test_tab(self)
    appointments_index = _tab_index_by_object_name(tabs, "appointmentsTabScroll")
    if appointments_index is None:
        appointments_index = tabs.count()
        tabs.addTab(_build_appointments_tab(self), "")

    removals_index = _tab_index_by_object_name(tabs, "appointmentRemovalsTabScroll")
    if removals_index is None:
        removals_index = tabs.count()
        tabs.addTab(_build_appointment_removals_tab(self), "")

    players_index = _tab_index_by_object_name(tabs, "playersTabScroll")
    if players_index is None:
        players_index = tabs.count()
        tabs.addTab(_build_players_tab(self), "")

    self._appointments_tab_index = appointments_index
    self._appointment_removals_tab_index = removals_index
    self._players_tab_index = players_index
    _SECTION_CONTEXT[appointments_index] = _SECTION_CONTEXT[_APPOINTMENTS_TAB_FALLBACK_INDEX]
    _SECTION_CONTEXT[removals_index] = _SECTION_CONTEXT[_REMOVALS_TAB_FALLBACK_INDEX]
    _SECTION_CONTEXT[players_index] = _SECTION_CONTEXT[_PLAYERS_TAB_FALLBACK_INDEX]

    for order, button in enumerate(self.findChildren(QPushButton, "navButton")):
        if button.property("tabIndex") is None:
            button.setProperty("tabIndex", order)
    _add_extended_nav_button(self, "Призначення", appointments_index, "appointments", "appointmentsTabScroll")
    _add_extended_nav_button(self, "Зняття", removals_index, "appointment_removals", "appointmentRemovalsTabScroll")
    _add_extended_nav_button(self, "Гравці", players_index, "players", "playersTabScroll")
    _connect_extended_log_watcher(self)
    _sync_extended_nav_state(self)
    _apply_action_button_classes(self)


def _on_player_target_changed(self: MainWindow) -> None:
    value = _line_value(getattr(self, "player_target_input", None))
    if value.isdigit():
        self._resolved_player_id = value
        self._resolved_player_name = ""
    else:
        self._resolved_player_id = ""
        self._resolved_player_name = ""
    _update_target_badges(self)


def _update_target_badges(self: MainWindow) -> None:
    id_badge = getattr(self, "target_id_badge", None)
    name_label = getattr(self, "target_name_label", None)
    if id_badge is not None:
        id_badge.setText(f"ID: {getattr(self, '_resolved_player_id', '') or '-'}")
    if name_label is not None:
        name_label.setText(getattr(self, "_resolved_player_name", "") or "-")


def _start_player_lookup(self: MainWindow, identifier: str, after_success=None) -> None:
    identifier = identifier.strip()
    if not identifier:
        self._set_status("Вкажіть ID або нікнейм")
        return
    if identifier.isdigit():
        self._resolved_player_id = identifier
        self._resolved_player_name = ""
        _update_target_badges(self)
        self._set_status("Ціль готова")
        if after_success:
            after_success()
        return
    if getattr(self, "_lookup_running", False):
        self._set_status("Пошук ID вже виконується")
        return

    self._pending_after_lookup = after_success
    self._lookup_running = True
    lookup_btn = getattr(self, "lookup_btn", None)
    if lookup_btn is not None:
        lookup_btn.setEnabled(False)
    self._set_status(f"Шукаю ID для {identifier}...")

    thread = _PlayerLookupThread(identifier)
    self._player_lookup_thread = thread
    thread.completed.connect(lambda result, error: _finish_player_lookup(self, result, error))
    thread.finished.connect(lambda: setattr(self, "_player_lookup_thread", None))
    thread.start()


def _finish_player_lookup(self: MainWindow, result: PlayerLookupResult | None, error: str) -> None:
    self._lookup_running = False
    lookup_btn = getattr(self, "lookup_btn", None)
    if lookup_btn is not None:
        lookup_btn.setEnabled(True)
    if error or result is None:
        self._pending_after_lookup = None
        self._resolved_player_id = ""
        self._resolved_player_name = ""
        _update_target_badges(self)
        self._set_status(error or "Гравця не знайдено")
        _append_player_log(self, f"Помилка пошуку: {error or 'Гравця не знайдено'}")
        return

    self._resolved_player_id = str(result.player_id)
    self._resolved_player_name = result.nickname
    _update_target_badges(self)
    self._set_status(f"Гравець вибраний: {result.nickname}[{result.player_id}]")
    callback = getattr(self, "_pending_after_lookup", None)
    self._pending_after_lookup = None
    if callback:
        callback()


def _with_target_id(self: MainWindow, callback) -> None:
    field = getattr(self, "player_target_input", None)
    value = _line_value(field)
    resolved_id = getattr(self, "_resolved_player_id", "")
    resolved_name = getattr(self, "_resolved_player_name", "")
    if resolved_id and (value.isdigit() or resolved_name or value == resolved_id):
        callback(resolved_id)
        return
    if value.isdigit():
        self._resolved_player_id = value
        _update_target_badges(self)
        callback(value)
        return
    _start_player_lookup(self, value, after_success=lambda: callback(getattr(self, "_resolved_player_id", "")))


def _require_text(self: MainWindow, field: QLineEdit, label: str) -> str | None:
    value = _sanitize_console_command(field.text())
    if not value:
        self._set_status(f"Заповніть поле: {label}")
        field.setFocus()
        return None
    return value


def _require_number(self: MainWindow, field: QLineEdit, label: str) -> str | None:
    value = field.text().strip()
    if not value.isdigit() or int(value) <= 0:
        self._set_status(f"У полі '{label}' має бути число більше 0")
        field.setFocus()
        return None
    return value


def _player_ban(self: MainWindow) -> None:
    days = _require_number(self, self.ban_days_input, "Днів")
    reason = _require_text(self, self.ban_reason_input, "Причина бану")
    if not days or reason is None:
        return
    _with_target_id(self, lambda pid: _run_console_action(self, "Бан", f"pban {pid} {days} {reason}", f"pbanoffline {pid} {days} {reason}"))


def _player_unban(self: MainWindow) -> None:
    _with_target_id(self, lambda pid: _run_console_action(self, "Розбан", f"punban {pid}"))


def _player_mute(self: MainWindow) -> None:
    minutes = _require_number(self, self.mute_minutes_input, "Хвилин")
    reason = _require_text(self, self.mute_reason_input, "Причина муту")
    if not minutes or reason is None:
        return
    _with_target_id(self, lambda pid: _run_console_action(self, "Мут", f"pmute {pid} {minutes} {reason}", f"offmute {pid} {minutes} {reason}"))


def _player_unmute(self: MainWindow) -> None:
    _with_target_id(self, lambda pid: _run_console_action(self, "Зняти мут", f"punmute {pid}", f"offunmute {pid}"))


def _player_jail(self: MainWindow) -> None:
    minutes = _require_number(self, self.jail_minutes_input, "Хвилин")
    reason = _require_text(self, self.jail_reason_input, "Причина деморгану")
    if not minutes or reason is None:
        return
    _with_target_id(self, lambda pid: _run_console_action(self, "Деморган", f"jail {pid} {minutes} {reason}", f"jailoffline {pid} {minutes} {reason}"))


def _player_unjail(self: MainWindow) -> None:
    _with_target_id(self, lambda pid: _run_console_action(self, "Випустити", f"unjail {pid}", f"offunjail {pid}"))


def _player_warn(self: MainWindow) -> None:
    reason = _require_text(self, self.warn_reason_input, "Причина warn")
    if reason is None:
        return
    _with_target_id(self, lambda pid: _run_console_action(self, "Warn", f"warn {pid} {reason}", f"offwarn {pid} {reason}"))


def _player_unwarn(self: MainWindow) -> None:
    _with_target_id(self, lambda pid: _run_console_action(self, "Зняти warn", f"unwarn {pid}", f"offunwarn {pid}"))


def _player_kick(self: MainWindow) -> None:
    reason = _require_text(self, self.kick_reason_input, "Причина кіку")
    if reason is None:
        return
    _with_target_id(self, lambda pid: _run_console_action(self, "Кік", f"pkick {pid} {reason}"))


def _player_set_faction(self: MainWindow) -> None:
    faction_id = self.faction_combo.currentText().split(" ", 1)[0]
    _with_target_id(self, lambda pid: _run_console_action(self, "Фракція", f"setfaction {pid} {faction_id}", f"offsetfaction {pid} {faction_id}"))


def _player_clear_faction(self: MainWindow) -> None:
    _with_target_id(self, lambda pid: _run_console_action(self, "Звільнення з фракції", f"setfaction {pid} 0", f"offsetfaction {pid} 0"))


def _player_set_faction_level(self: MainWindow) -> None:
    level = self.faction_level_combo.currentText().strip()
    if level not in {str(index) for index in range(1, 13)}:
        self._set_status("Ранг має бути від 1 до 12")
        return
    _with_target_id(self, lambda pid: _run_console_action(self, "Ранг", f"setfactionlevel {pid} {level}", f"offsetfactionlevel {pid} {level}"))


def _run_console_action(self: MainWindow, title: str, command: str, offline_command: str | None = None) -> None:
    command = _sanitize_console_command(command)
    offline_command = _sanitize_console_command(offline_command or "") or None
    if not command:
        self._set_status("Команда порожня")
        return
    _start_console_command(self, title, command, offline_command=offline_command)


def _start_console_command(
    self: MainWindow,
    title: str,
    command: str,
    *,
    offline_command: str | None = None,
    log_suffix: str = "",
) -> None:
    self._set_status(f"{title}: відправляю команду...")
    thread = _ConsoleCommandThread(getattr(self, "sender", None), command)
    threads = getattr(self, "_console_command_threads", None)
    if threads is None:
        threads = []
        self._console_command_threads = threads
    threads.append(thread)
    thread.completed.connect(
        lambda ok, message, sent_command: _finish_console_command(
            self,
            title,
            sent_command,
            ok,
            message,
            offline_command=offline_command,
            log_suffix=log_suffix,
        )
    )
    thread.finished.connect(lambda finished_thread=thread: _drop_console_thread(self, finished_thread))
    thread.start()


def _drop_console_thread(self: MainWindow, thread: QThread) -> None:
    threads = getattr(self, "_console_command_threads", None)
    if isinstance(threads, list) and thread in threads:
        threads.remove(thread)


def _finish_console_command(
    self: MainWindow,
    title: str,
    command: str,
    ok: bool,
    message: str,
    *,
    offline_command: str | None = None,
    log_suffix: str = "",
) -> None:
    self._set_status(message)
    suffix = f"  {log_suffix}" if log_suffix else ""
    _append_player_log(self, f"> {command}{suffix}")
    if ok and offline_command:
        self._pending_offline_action = {
            "expires": time.monotonic() + 5.0,
            "offline_command": offline_command,
            "title": title,
        }
        QTimer.singleShot(5200, lambda: _clear_expired_offline_action(self))


def _on_player_raw_log_lines(self: MainWindow, lines: list[str]) -> None:
    pending = getattr(self, "_pending_offline_action", None)
    if not pending:
        return
    if time.monotonic() > float(pending.get("expires", 0)):
        self._pending_offline_action = None
        return
    text = "\n".join(lines).casefold()
    if not any(marker in text for marker in _OFFLINE_MARKERS):
        return

    offline_command = str(pending.get("offline_command") or "")
    title = str(pending.get("title") or "Дія")
    self._pending_offline_action = None
    if offline_command:
        _start_console_command(self, f"{title}: offline fallback", offline_command, log_suffix="[offline fallback]")


def _clear_expired_offline_action(self: MainWindow) -> None:
    pending = getattr(self, "_pending_offline_action", None)
    if pending and time.monotonic() > float(pending.get("expires", 0)):
        self._pending_offline_action = None


def _append_player_log(self: MainWindow, text: str) -> None:
    log = getattr(self, "player_action_log", None)
    if log is None:
        return
    stamp = time.strftime("%H:%M:%S")
    log.appendPlainText(f"[{stamp}] {text}")


def _fill_player_from_report(self: MainWindow) -> None:
    report = self._target_report()
    if report is None:
        resolver = getattr(getattr(self, "store", None), "latest_received_report", None)
        report = resolver() if callable(resolver) else None
    if report is None:
        self._set_status("Оберіть репорт")
        return
    _replace_line_value(getattr(self, "player_target_input", None), str(report.player_id))
    self._resolved_player_id = str(report.player_id)
    self._resolved_player_name = report.player_name
    _update_target_badges(self)
    self._set_status(f"Ціль з репорту: {report.player_name}[{report.player_id}]")


def _fill_test_from_report(self: MainWindow) -> None:
    report = self._target_report()
    if report is None:
        resolver = getattr(getattr(self, "store", None), "latest_received_report", None)
        report = resolver() if callable(resolver) else None
    if report is None:
        self._set_status("Оберіть репорт")
        return
    combo = getattr(self, "test_action_combo", None)
    if combo is not None:
        index = combo.findData("pm")
        if index >= 0:
            combo.setCurrentIndex(index)
    _replace_line_value(getattr(self, "test_player_id_input", None), str(report.player_id))
    if not _plain_value(getattr(self, "test_text_input", None)):
        reply_input = getattr(self, "reply_input", None)
        _set_plain_value(getattr(self, "test_text_input", None), _plain_value(reply_input))
    _update_console_test_preview(self)
    self._set_status("Дані репорту перенесено у тест")


def _test_action_key(self: MainWindow) -> str:
    combo = getattr(self, "test_action_combo", None)
    if combo is None:
        return "custom"
    return str(combo.currentData() or "custom")


def _console_test_command(self: MainWindow, *, require_values: bool = False) -> tuple[str, str]:
    action = _test_action_key(self)
    player_id = _sanitize_console_command(_line_value(getattr(self, "test_player_id_input", None)))
    number = _sanitize_console_command(_line_value(getattr(self, "test_number_input", None)))
    text = _sanitize_console_command(_plain_value(getattr(self, "test_text_input", None)))
    custom = _sanitize_console_command(_line_value(getattr(self, "test_custom_input", None)))

    def value(current: str, placeholder: str, label: str) -> str:
        if current:
            return current
        if require_values:
            raise ValueError(f"Заповніть поле: {label}")
        return placeholder

    try:
        if action == "custom":
            if require_values and not custom:
                return "", "Заповніть поле: Своя команда"
            return custom or "mute {id} {хв} {причина}", ""
        if action == "pm":
            return f"pm {value(player_id, '{id}', 'ID')} {value(text, '{текст}', 'Текст / причина')}", ""
        if action == "warn":
            return f"warn {value(player_id, '{id}', 'ID')} {value(text, '{причина}', 'Текст / причина')}", ""
        if action == "pban":
            return f"pban {value(player_id, '{id}', 'ID')} {value(number, '{дні}', 'Число')} {value(text, '{причина}', 'Текст / причина')}", ""
        if action in {"mute", "pmute"}:
            return f"{action} {value(player_id, '{id}', 'ID')} {value(number, '{хв}', 'Число')} {value(text, '{причина}', 'Текст / причина')}", ""
        if action == "jail":
            return f"jail {value(player_id, '{id}', 'ID')} {value(number, '{хв}', 'Число')} {value(text, '{причина}', 'Текст / причина')}", ""
        if action == "pkick":
            return f"pkick {value(player_id, '{id}', 'ID')} {value(text, '{причина}', 'Текст / причина')}", ""
        if action == "pwarp":
            return f"pwarp {value(player_id, '{id}', 'ID')}", ""
        if action == "sp":
            return f"sp {value(player_id, '{id}', 'ID')}", ""
    except ValueError as exc:
        return "", str(exc)
    return custom, ""


def _update_console_test_preview(self: MainWindow) -> None:
    command_preview = getattr(self, "test_command_preview", None)
    say_preview = getattr(self, "test_say_preview", None)
    if command_preview is None or say_preview is None:
        return
    command, _error = _console_test_command(self, require_values=False)
    command = _sanitize_console_command(command)
    say_command = _sanitize_console_command(f"say {command}") if command else "say ..."
    command_preview.setPlainText(f"Команда:\n{command or '-'}")
    say_preview.setPlainText(f"Тестова відправка:\n{say_command}")


def _send_console_test(self: MainWindow) -> None:
    command, error = _console_test_command(self, require_values=True)
    command = _sanitize_console_command(command)
    if error:
        self._set_status(error)
        return
    if not command:
        self._set_status("Команда порожня")
        return
    test_command = _sanitize_console_command(f"say {command}")
    _start_console_command(self, "Тест", test_command, log_suffix="[test]")


_original_build_general_settings_group = MainWindow._build_general_settings_group
_original_load_settings_into_ui = MainWindow._load_settings_into_ui
_original_save_settings_from_ui = MainWindow._save_settings_from_ui
_original_on_nav_clicked = MainWindow._on_nav_clicked
_original_refresh_table = getattr(MainWindow, "_refresh_table", None)
_original_refresh_vip_ads_table = getattr(MainWindow, "_refresh_vip_ads_table", None)


def _patched_build_general_settings_group(self: MainWindow):
    group = _original_build_general_settings_group(self)
    _attach_theme_selector(self, group)
    return group


def _patched_load_settings_into_ui(self: MainWindow) -> None:
    _original_load_settings_into_ui(self)
    _sync_theme_selector(self)


def _patched_save_settings_from_ui(self: MainWindow) -> None:
    combo = getattr(self, "theme_mode_combo", None)
    if combo is not None:
        self.settings.theme_mode = normalize_theme_mode(combo.currentData())
    _original_save_settings_from_ui(self)
    _apply_selected_theme(self, getattr(self.settings, "theme_mode", "dark"))


def _patched_on_nav_clicked(self: MainWindow, index: int) -> None:
    _ensure_extended_tabs(self)
    tabs = getattr(self, "tabs", None)
    extended_indexes = {
        getattr(self, "_appointments_tab_index", _APPOINTMENTS_TAB_FALLBACK_INDEX),
        getattr(self, "_appointment_removals_tab_index", _REMOVALS_TAB_FALLBACK_INDEX),
        getattr(self, "_players_tab_index", _PLAYERS_TAB_FALLBACK_INDEX),
    }
    if tabs is not None and index in extended_indexes:
        tabs.setCurrentIndex(index)
    else:
        _original_on_nav_clicked(self, index)
    _update_shell_context(self, index)
    _normalize_runtime_texts(self)
    _apply_action_button_classes(self)
    app = QApplication.instance()
    if app is not None:
        _sync_inline_widget_styles(self, normalize_theme_mode(app.property("theme_mode")))
    _compact_button_metrics(self)
    _compact_report_reply_panel(self)
    _sync_extended_nav_state(self, index)
    if index == getattr(self, "_appointment_removals_tab_index", None) and not getattr(self, "_appointment_active_loaded", False):
        _start_active_appointments_fetch(self)
    for button in self.findChildren(QPushButton):
        if button.objectName() != "navButton":
            continue
        _repolish(button)
        parent = button.parentWidget()
        if parent is not None:
            parent.setProperty("navItem", True)
            parent.setProperty("navActive", button.property("active") == "true")
            _repolish(parent)


def _patched_refresh_table(self: MainWindow) -> None:
    if callable(_original_refresh_table):
        _original_refresh_table(self)
    _apply_queue_table_fixups(self)


def _patched_refresh_vip_ads_table(self: MainWindow) -> None:
    if callable(_original_refresh_vip_ads_table):
        _original_refresh_vip_ads_table(self)
    _sync_vip_active_badge(self)
    for badge in self.findChildren(QLabel, "reportCountBadge"):
        text = badge.text().casefold()
        if "активних" in text or "активні" in text or "активне" in text:
            _normalize_count_badge(badge)


def _restore_previous_design(self: MainWindow) -> None:
    subtitle = self.findChild(QLabel, "appSubtitle")
    _detach_widget(subtitle)

    _remove_labels_by_text(
        self,
        {
            "Операційна панель для репортів, VIP-модерації та швидких дій.",
            "Актуальні звернення, статус відповіді та остання дія по кожному репорту.",
            "Автоматичний моніторинг VIP-чату через AI: нейронка визначає намір повідомлення і відділяє рекламу або торгівлю від звичайних інформаційних питань.",
        },
    )

    for button in self.findChildren(QPushButton):
        if button.objectName() not in {"winControl", "winControl_close"}:
            button.setIcon(QIcon())
        if button.objectName() == "navButton":
            button.setFlat(True)
            button.setFixedHeight(24)
            parent = button.parentWidget()
            if parent is not None and parent.layout() is not None:
                parent.setProperty("navItem", True)
                parent.setProperty("navActive", button.property("active") == "true")
                parent.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                parent.setFixedHeight(28)
                parent.layout().setContentsMargins(5, 2, 5, 2)
                parent.layout().setSpacing(0)
                _repolish(parent)

    _normalize_runtime_texts(self)
    _compact_button_metrics(self)

    for checkbox in self.findChildren(QCheckBox):
        checkbox.setMinimumHeight(max(22, checkbox.sizeHint().height() + 4))
        checkbox.setContentsMargins(0, 1, 0, 1)
        form_container = checkbox.parentWidget()
        if form_container is not None and isinstance(form_container.layout(), QFormLayout):
            layout_hint = form_container.layout().sizeHint().height()
            form_container.setMinimumHeight(max(form_container.minimumHeight(), layout_hint))
            form_frame = form_container.parentWidget()
            if isinstance(form_frame, QFrame):
                form_frame.setMinimumHeight(max(form_frame.minimumHeight(), form_frame.sizeHint().height()))

    nav_frame = self.findChild(QFrame, "navigationBar")
    if nav_frame is not None and nav_frame.layout() is not None:
        nav_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        nav_frame.setFixedHeight(42)
        nav_frame.layout().setContentsMargins(10, 6, 10, 6)
        nav_frame.layout().setSpacing(4)
        _repolish(nav_frame)

    for frame in self.findChildren(QFrame):
        if frame.property("class") == "glassPanel":
            frame.setProperty("contentCard", True)
            frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            _repolish(frame)

    for frame in self.findChildren(QFrame, "heroBanner"):
        texts = {label.text().strip() for label in frame.findChildren(QLabel)}
        layout = frame.layout()
        if layout is None:
            continue
        if "RICHCORE V12" in texts:
            frame.setFixedHeight(74)
            layout.setContentsMargins(20, 12, 20, 12)
            layout.setSpacing(4)
        elif "AD VIP" in texts:
            frame.setFixedHeight(88)
            layout.setContentsMargins(22, 14, 22, 14)
            layout.setSpacing(5)

    _compact_report_reply_panel(self)

    vip_command = self.findChild(_RECOVERED.QLineEdit, "vipCommandPreview")
    if vip_command is not None:
        vip_frame = vip_command.parentWidget()
        while vip_frame is not None and not isinstance(vip_frame.parentWidget(), _RECOVERED.QSplitter):
            vip_frame = vip_frame.parentWidget()
        if isinstance(vip_frame, QFrame) and vip_frame.sizeHint().height() > vip_frame.height():
            vip_frame.setMinimumHeight(max(vip_frame.minimumHeight(), vip_frame.sizeHint().height()))
            _wrap_in_scroll_area(vip_frame)

    _wrap_tab_page_in_scroll(self, self.SETTINGS_TAB_INDEX, "settingsScrollArea")


def _post_layout_fixups(self: MainWindow) -> None:
    _wrap_tab_page_in_scroll(self, self.SETTINGS_TAB_INDEX, "settingsScrollArea")
    _normalize_runtime_texts(self)
    _apply_action_button_classes(self)
    app = QApplication.instance()
    if app is not None:
        _sync_inline_widget_styles(self, normalize_theme_mode(app.property("theme_mode")))
    _compact_button_metrics(self)
    _compact_report_reply_panel(self)

    vip_command = self.findChild(_RECOVERED.QLineEdit, "vipCommandPreview")
    if vip_command is not None:
        vip_panel = _find_splitter_panel(vip_command)
        if isinstance(vip_panel, QFrame):
            vip_panel.setMinimumHeight(max(vip_panel.minimumHeight(), vip_panel.sizeHint().height()))
            _wrap_in_scroll_area(vip_panel)
        _rebalance_splitter(_find_parent_splitter(vip_command), 0.56)

    for checkbox in self.findChildren(QCheckBox):
        checkbox.setMinimumHeight(max(22, checkbox.sizeHint().height() + 4))
        form_container = checkbox.parentWidget()
        if form_container is not None and isinstance(form_container.layout(), QFormLayout):
            layout_hint = form_container.layout().sizeHint().height()
            form_container.setMinimumHeight(max(form_container.minimumHeight(), layout_hint))
            form_frame = form_container.parentWidget()
            if isinstance(form_frame, QFrame):
                form_frame.setMinimumHeight(max(form_frame.minimumHeight(), form_frame.sizeHint().height()))

    for frame in self.findChildren(QFrame):
        if frame.property("class") == "glassPanel":
            frame.setProperty("contentCard", True)
            _repolish(frame)

    self.updateGeometry()


_original_init = MainWindow.__init__
_original_change_event = getattr(MainWindow, "changeEvent", None)
_original_resize_event = getattr(MainWindow, "resizeEvent", None)
_original_close_event = getattr(MainWindow, "closeEvent", None)


def _patched_change_event(self: MainWindow, event) -> None:
    if callable(_original_change_event):
        _original_change_event(self, event)
    if event is not None and event.type() == QEvent.Type.WindowStateChange:
        _sync_window_control_icons(self)
        QTimer.singleShot(0, lambda: _compact_report_reply_panel(self))


def _patched_resize_event(self: MainWindow, event) -> None:
    if callable(_original_resize_event):
        _original_resize_event(self, event)
    _sync_window_control_icons(self)
    QTimer.singleShot(0, lambda: _compact_report_reply_panel(self))


def _appointment_threads_running(self: MainWindow) -> bool:
    candidates = [
        getattr(self, "_appointment_fetch_thread", None),
        getattr(self, "_appointment_active_fetch_thread", None),
        getattr(self, "_appointment_term_thread", None),
    ]
    candidates.extend(getattr(self, "_appointment_action_threads", []) or [])
    candidates.extend(getattr(self, "_appointment_active_action_threads", []) or [])
    return any(bool(thread is not None and thread.isRunning()) for thread in candidates)


def _patched_close_event(self: MainWindow, event) -> None:
    if _appointment_threads_running(self):
        self._set_status("Дочекайтесь завершення фонового оновлення, щоб безпечно закрити RichCore")
        if event is not None:
            event.ignore()
        return
    if callable(_original_close_event):
        _original_close_event(self, event)
    elif event is not None:
        event.accept()


def _patched_init(self: MainWindow, *args, **kwargs) -> None:
    _original_init(self, *args, **kwargs)
    try:
        _restore_previous_design(self)
        _apply_action_button_classes(self)
        _compact_button_metrics(self)
        _compact_report_reply_panel(self)
        _sync_theme_selector(self)
        _apply_selected_theme(self, getattr(self.settings, "theme_mode", "dark"))
        _force_admin_vip_mode(self)
        _ensure_extended_tabs(self)
    except Exception:
        _LOGGER.exception("Initial UI restore failed")
    QTimer.singleShot(
        0,
        lambda: (
            _safe_post_layout_fixups(self),
            _ensure_extended_tabs(self),
            _apply_action_button_classes(self),
            _force_admin_vip_mode(self),
        ),
    )


def _patched_init(self: MainWindow, *args, **kwargs) -> None:
    _original_init(self, *args, **kwargs)
    try:
        _restore_previous_design(self)
        _apply_action_button_classes(self)
        _normalize_runtime_texts(self)
        _apply_action_button_classes(self)
        _compact_button_metrics(self)
        _compact_report_reply_panel(self)
        _sync_theme_selector(self)
        _apply_selected_theme(self, getattr(self.settings, "theme_mode", "dark"))
        _force_admin_vip_mode(self)
        _ensure_extended_tabs(self)
    except Exception:
        _LOGGER.exception("Initial UI restore failed")
    QTimer.singleShot(
        0,
        lambda: (
            _safe_post_layout_fixups(self),
            _apply_action_button_classes(self),
            _compact_button_metrics(self),
            _compact_report_reply_panel(self),
            _sync_theme_selector(self),
            _force_admin_vip_mode(self),
            _ensure_extended_tabs(self),
        ),
    )


MainWindow.__init__ = _patched_init
MainWindow.changeEvent = _patched_change_event
MainWindow.resizeEvent = _patched_resize_event
MainWindow.closeEvent = _patched_close_event
MainWindow._build_general_settings_group = _patched_build_general_settings_group
MainWindow._load_settings_into_ui = _patched_load_settings_into_ui
MainWindow._save_settings_from_ui = _patched_save_settings_from_ui
MainWindow._apply_nav_button_icon = _apply_nav_button_icon
MainWindow._format_pm_command = _format_pm_command
MainWindow._format_vip_punishment_command = _format_vip_punishment_command
MainWindow._on_vip_mode_changed = _on_vip_mode_changed
MainWindow._on_nav_clicked = _patched_on_nav_clicked
MainWindow._refresh_table = _patched_refresh_table
MainWindow._refresh_vip_ads_table = _patched_refresh_vip_ads_table
MainWindow._report_status_info = _report_status_info_patched
MainWindow._send_reply = _send_reply_patched
MainWindow._hotkey_last_report_pm = _hotkey_last_report_pm_patched
MainWindow._hotkey_last_reply_id = _hotkey_last_reply_id_patched
MainWindow._hotkey_other_reply = _hotkey_other_reply_patched
MainWindow._insert_other_admin_reply = _insert_other_admin_reply_patched
