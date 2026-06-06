from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..hotkeys import VK_MAP
from ..models import BindConfig
from ..paths import asset_path


KEY_NAME_MAP = {
    Qt.Key.Key_Space: "SPACE",
    Qt.Key.Key_Tab: "TAB",
    Qt.Key.Key_Return: "ENTER",
    Qt.Key.Key_Enter: "ENTER",
    Qt.Key.Key_Escape: "ESC",
    Qt.Key.Key_Up: "UP",
    Qt.Key.Key_Down: "DOWN",
    Qt.Key.Key_Left: "LEFT",
    Qt.Key.Key_Right: "RIGHT",
    Qt.Key.Key_Home: "HOME",
    Qt.Key.Key_End: "END",
    Qt.Key.Key_Insert: "INSERT",
    Qt.Key.Key_Delete: "DELETE",
    Qt.Key.Key_PageUp: "PAGEUP",
    Qt.Key.Key_PageDown: "PAGEDOWN",
}


class HotkeyLineEdit(QLineEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setPlaceholderText("Натисніть бажану комбінацію")
        self.setReadOnly(True)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        parts: list[str] = []
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("CTRL")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("ALT")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("SHIFT")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("WIN")

        key_name = self._key_name(event)
        if key_name:
            parts.append(key_name)

        hotkey = "+".join(parts)
        if hotkey and hotkey.split("+")[-1] in VK_MAP:
            self.setText(hotkey)

    def _key_name(self, event: QKeyEvent) -> str:
        key = event.key()
        nsc = event.nativeScanCode()  # hardware scan code

        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            return f"F{key - Qt.Key.Key_F1 + 1}"

        # NumPad digits: virtual key codes 0x60–0x69 (sc 0x52, 0x4F–0x53, 0x4C, 0x4B, ...
        # The safest: check KeypadModifier OR native VK in numpad range
        native_vk = event.nativeVirtualKey()
        if 0x60 <= native_vk <= 0x69:
            return f"NUM{native_vk - 0x60}"

        # Numpad operators
        if native_vk == 0x6B:
            return "NUMPLUS"
        if native_vk == 0x6D:
            return "NUMMINUS"
        if native_vk == 0x6A:
            return "NUMMULT"
        if native_vk == 0x6F:
            return "NUMDIV"

        # Regular digits
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return str(key - Qt.Key.Key_0)

        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return chr(key)

        return KEY_NAME_MAP.get(Qt.Key(key), "")


class BindDialog(QDialog):
    def __init__(self, category: str, bind: BindConfig | None = None, parent=None) -> None:
        super().__init__(parent)
        self._category = category
        self.setWindowTitle("Налаштування бінду")
        self.resize(600, 420)
        
        # We don't use frameless for dialogs to keep them manageable, 
        # but we style them heavily via theme.py
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        form = QFormLayout()
        form.setSpacing(15)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.name_edit = QLineEdit(bind.name if bind else "")
        self.name_edit.setPlaceholderText("Наприклад: Привітання")
        
        self.hotkey_edit = HotkeyLineEdit()
        self.hotkey_edit.setText(bind.hotkey if bind else "")
        
        self.text_edit = QPlainTextEdit(bind.text if bind else "")
        self.text_edit.setPlaceholderText("Введіть текст або команду (можна використовувати {player_id})")
        self.text_edit.setMinimumHeight(120)
        
        self.open_chat = QCheckBox("Автоматично відкривати чат")
        self.open_chat.setChecked(bind.open_chat if bind else True)

        form.addRow("НАЗВА", self.name_edit)
        form.addRow("КЛАВІША", self.hotkey_edit)
        form.addRow("ТЕКСТ / КОМАНДА", self.text_edit)
        form.addRow("", self.open_chat)
        layout.addLayout(form)

        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        
        save_btn = QPushButton("ЗБЕРЕГТИ")
        save_btn.setProperty("class", "primaryAction")
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("СКАСУВАТИ")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.clicked.connect(self.reject)
        
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

    def accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "RichCore", "Вкажіть назву бінду.")
            return
        if not self.hotkey_edit.text().strip():
            QMessageBox.warning(self, "RichCore", "Натисніть клавішу або комбінацію.")
            return
        if not self.text_edit.toPlainText().strip():
            QMessageBox.warning(self, "RichCore", "Вкажіть текст або команду.")
            return
        super().accept()

    def bind_config(self) -> BindConfig:
        return BindConfig(
            name=self.name_edit.text().strip(),
            hotkey=self.hotkey_edit.text().strip(),
            text=self.text_edit.toPlainText(),
            category=self._category,
            open_chat=self.open_chat.isChecked(),
        )
