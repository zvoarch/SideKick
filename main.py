"""
First run: click the bubble, open Settings (gear icon), paste your Gemini
API key (from https://aistudio.google.com/apikey), hit Save.
"""

import sys
import ctypes
from html import escape
import os
import traceback

from PySide6.QtCore import (
    Qt, QRect, QRectF, QSize, QPoint, QPointF, QVariantAnimation, QTimer,
    QEasingCurve, QThread, Signal,
)
from PySide6.QtGui import (
    QGuiApplication, QFont, QTextCursor, QIcon, QPainter, QColor, QBrush, QLinearGradient, QRadialGradient, QPen,
    QPolygonF, QPainterPath, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit, QTextEdit, QVBoxLayout, QHBoxLayout, QDialog, QFormLayout,
    QAbstractItemView,
    QTabWidget, QListWidget, QListWidgetItem,
    QFileDialog, QMenu, QMessageBox, QColorDialog,
)
import math

import settings_store
from gemini import ToolCallingGeminiClient as GeminiClient
from shortcuts import (
    resolve_shortcut, display_name_for, list_installed_applications,
)
from tools.applications import (
    add_approved_application, list_approved_applications,
    set_approved_application_enabled,
)
from tools.files import (
    add_approved_folder, list_approved_folders, set_approved_folder_enabled,
)

BUBBLE_SIZE = 64
CHAT_SIZE = QSize(380, 560)
SCREEN_MARGIN = 24


def set_windows_taskbar_identity(widget):
    """Make a frameless top-level widget appear as a normal taskbar window."""
    if sys.platform != "win32":
        return

    try:
        from ctypes import wintypes

        hwnd = int(widget.winId())
        user32 = ctypes.windll.user32
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            get_style = user32.GetWindowLongPtrW
            set_style = user32.SetWindowLongPtrW
            style_value = ctypes.c_ssize_t
        else:
            get_style = user32.GetWindowLongW
            set_style = user32.SetWindowLongW
            style_value = ctypes.c_long
        get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        get_style.restype = style_value
        set_style.argtypes = [wintypes.HWND, ctypes.c_int, style_value]
        set_style.restype = style_value
        ex_style = get_style(hwnd, -20)  # GWL_EXSTYLE
        ex_style = (ex_style | 0x00040000) & ~0x00000080  # APPWINDOW, not TOOLWINDOW
        set_style(hwnd, -20, ex_style)
        set_pos = user32.SetWindowPos
        set_pos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int, wintypes.UINT]
        set_pos.restype = wintypes.BOOL
        set_pos(
            hwnd, None, 0, 0, 0, 0,
            0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020,  # frame changed; keep position/state
        )
    except (AttributeError, OSError, TypeError, ValueError):
        # Qt's normal top-level-window taskbar handling remains the fallback.
        pass

GEMINI_MODEL = "gemini-3.5-flash-lite"

STYLESHEET = """
QFrame#chatCard, QWidget#chatCard {
    background-color: #0A0A0D;
    border: 1px solid #1E1E24;
    border-radius: 20px;
}
QLabel#titleLabel {
    color: #F2F2F5;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.3px;
}
QPushButton#iconButton {
    background: transparent;
    border: none;
    border-radius: 8px;
}
QPushButton#iconButton:hover {
    background-color: #1A1A20;
}
QTextEdit#chatLog {
    background-color: #000000;
    border: none;
    border-radius: 14px;
    color: #E8E8ED;
    padding: 12px;
    font-size: 14px;
    font-family: "Segoe UI", "Calibri", sans-serif;
}
QLineEdit#chatInput {
    background-color: transparent;
    border: none;
    color: white;
    padding: 8px 4px;
    font-size: 13px;
    font-family: "Segoe UI", "Calibri", sans-serif;
    selection-background-color: #FF3D8A;
}
QPushButton#sendButton {
    background-color: #FF2E88;
    color: white;
    border: none;
    border-radius: 16px;
    font-weight: 600;
    padding: 9px 18px;
}
QPushButton#sendButton:hover { background-color: #FF4C9A; }
QPushButton#sendButton:disabled { background-color: #3A2530; color: #7A6470; }

QDialog {
    background-color: #0A0A0D;
    color: #E8E8ED;
}
QLabel { color: #E8E8ED; }
QLineEdit {
    background-color: #131317;
    border: 1px solid #232329;
    border-radius: 10px;
    color: white;
    padding: 6px 10px;
}
QLineEdit:focus { border: 1px solid #FF3D8A; }
QPushButton {
    background-color: #1A1A20;
    color: #E8E8ED;
    border: none;
    border-radius: 10px;
    padding: 7px 16px;
}
QPushButton:hover { background-color: #24242C; }
QPushButton#exitButton {
    background-color: #2A171F;
    color: #FF8DBA;
}
QPushButton#exitButton:hover { background-color: #3A1D2A; }
QListWidget {
    background-color: #131317;
    border: 1px solid #232329;
    border-radius: 10px;
    color: #E8E8ED;
    padding: 4px;
}
QListWidget::item {
    padding: 6px 8px;
    border-radius: 6px;
}
QListWidget::item:selected {
    background-color: #2A1A22;
    color: #FF6FA8;
}
QTabWidget::pane {
    border: 1px solid #232329;
    border-radius: 10px;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    color: #8A8B95;
    padding: 7px 14px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    color: #FF6FA8;
    border-bottom: 2px solid #FF2E88;
}
"""


def appearance_palette(settings: dict) -> dict:
    accent = QColor(settings.get("accent_color", "#FF2E88"))
    if not accent.isValid():
        accent = QColor("#FF2E88")
    dark = settings.get("theme", "dark") != "light"
    if dark:
        colors = {
            "window": "#0A0A0D", "border": "#1E1E24", "text": "#E8E8ED",
            "title": "#F2F2F5", "muted": "#8A8B95", "surface": "#131317",
            "chat": "#000000", "control": "#1A1A20", "hover": "#24242C",
            "selection": accent.darker(220).name(), "exit": accent.darker(240).name(),
            "disabled": "#3A2530", "disabled_text": "#7A6470",
        }
    else:
        colors = {
            "window": "#FFFFFF", "border": "#DEDEE5", "text": "#272731",
            "title": "#20202A", "muted": "#747482", "surface": "#F5F5F8",
            "chat": "#EEEEF3", "control": "#ECECF1", "hover": "#E1E1E8",
            "selection": accent.lighter(175).name(), "exit": accent.lighter(185).name(),
            "disabled": "#D8D8DF", "disabled_text": "#777782",
        }
    colors["accent"] = accent.name().upper()
    colors["accent_hover"] = accent.lighter(115).name().upper()
    colors["accent_soft"] = accent.lighter(165).name().upper() if not dark else accent.darker(215).name().upper()
    colors["accent_foreground"] = "#20202A" if accent.lightness() > 175 else "#FFFFFF"
    colors["dark"] = dark
    colors["accent_color"] = accent
    return colors


def build_stylesheet(settings: dict) -> str:
    colors = appearance_palette(settings)
    style = STYLESHEET
    replacements = {
        "#0A0A0D": colors["window"], "#1E1E24": colors["border"],
        "#F2F2F5": colors["title"], "#E8E8ED": colors["text"],
        "#000000": colors["chat"], "#131317": colors["surface"],
        "#232329": colors["border"], "#1A1A20": colors["control"],
        "#24242C": colors["hover"], "#FF3D8A": colors["accent"],
        "#FF2E88": colors["accent"], "#FF4C9A": colors["accent_hover"],
        "#FF8DBA": colors["accent"], "#FF6FA8": colors["accent"],
        "#3A2530": colors["disabled"], "#7A6470": colors["disabled_text"],
        "#2A171F": colors["exit"], "#3A1D2A": colors["selection"],
        "#2A1A22": colors["selection"], "#8A8B95": colors["muted"],
    }
    tokens = {}
    for index, (old, new) in enumerate(replacements.items()):
        token = f"__PALETTE_COLOR_{index}__"
        style = style.replace(old, token)
        tokens[token] = new
    for token, color in tokens.items():
        style = style.replace(token, color)
    style = style.replace("color: white;\n    padding: 9px 14px;", f"color: {colors['text']};\n    padding: 9px 14px;")
    style = style.replace("color: white;\n    border: none;\n    border-radius: 16px;", f"color: {colors['accent_foreground']};\n    border: none;\n    border-radius: 16px;")
    return style


def migrate_legacy_approvals(settings: dict):
    """Copy old JSON approvals into SQLite once, leaving an existing DB authoritative."""
    if not list_approved_applications(include_disabled=True):
        for app in settings.get("approved_apps", []):
            if app.get("name") and app.get("path"):
                add_approved_application(app["name"], app["path"])
    if not list_approved_folders(include_disabled=True):
        used_names = set()
        for folder in settings.get("approved_folders", []):
            if folder:
                name = _unique_folder_name(folder, used_names)
                add_approved_folder(name, folder)


def _normalized_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def _unique_folder_name(path: str, used_names: set[str]) -> str:
    base_name = os.path.basename(path.rstrip("\\/")) or path
    candidate = base_name
    suffix = 2
    while candidate.casefold() in used_names:
        candidate = f"{base_name} ({suffix})"
        suffix += 1
    used_names.add(candidate.casefold())
    return candidate


def sync_approved_items(settings: dict):
    """Synchronize the settings lists with the database used by Gemini tools."""
    apps = settings.get("approved_apps", [])
    folders = settings.get("approved_folders", [])
    wanted_apps = {app["name"].casefold() for app in apps if app.get("name") and app.get("path")}
    wanted_folder_paths = {_normalized_path(path) for path in folders if path}

    for app in list_approved_applications(include_disabled=True):
        if app["enabled"] and app["name"].casefold() not in wanted_apps:
            set_approved_application_enabled(app["name"], False)
    for app in apps:
        if app.get("name") and app.get("path"):
            add_approved_application(app["name"], app["path"])

    existing_folders = list_approved_folders(include_disabled=True)
    folder_names_by_path = {_normalized_path(folder["path"]): folder["name"] for folder in existing_folders}
    used_folder_names = {folder["name"].casefold() for folder in existing_folders}
    for folder in existing_folders:
        if folder["enabled"] and _normalized_path(folder["path"]) not in wanted_folder_paths:
            set_approved_folder_enabled(folder["name"], False)
    for path in folders:
        if path:
            normalized = _normalized_path(path)
            name = folder_names_by_path.get(normalized)
            if name is None:
                name = _unique_folder_name(path, used_folder_names)
            add_approved_folder(name, path)


def primary_screen_rect() -> QRect:
    return QGuiApplication.primaryScreen().availableGeometry()


def _star_polygon(center: QPointF, outer_r: float, inner_r: float, points: int = 4, rotation_deg: float = -90) -> QPolygonF:
    """Build the sparkle glyph used in the floating app icon."""
    poly = QPolygonF()
    step = 360 / (points * 2)
    for i in range(points * 2):
        angle = math.radians(rotation_deg + i * step)
        radius = outer_r if i % 2 == 0 else inner_r
        poly.append(QPointF(center.x() + radius * math.cos(angle), center.y() + radius * math.sin(angle)))
    return poly


class GeminiWorker(QThread):
    """Runs one Gemini call off the UI thread so the window never freezes."""
    reply_ready = Signal(str)
    error = Signal(str)

    def __init__(self, client: GeminiClient, text: str):
        super().__init__()
        self.client = client
        self.text = text

    def run(self):
        try:
            reply = self.client.send_message(self.text)
            self.reply_ready.emit(reply)
        except Exception as exc:  # noqa: BLE001 - surface any API error to the UI
            traceback.print_exc()
            self.error.emit(str(exc))


class ThemeSwitch(QPushButton):
    """Compact dark/light toggle with a moon or sun in the switch thumb."""

    def __init__(self, dark: bool, accent: QColor, parent=None):
        super().__init__(parent)
        self.accent = QColor(accent)
        self.setCheckable(True)
        self.setChecked(dark)
        self.setFixedSize(68, 34)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("Dark mode" if dark else "Light mode")
        self.toggled.connect(
            lambda checked: self.setAccessibleName("Dark mode" if checked else "Light mode")
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(2, 4, self.width() - 4, self.height() - 8)
        track_color = self.accent if self.isChecked() else QColor("#888892")
        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)

        thumb_size = track.height() - 4
        thumb_x = track.right() - thumb_size - 2 if self.isChecked() else track.left() + 2
        thumb = QRectF(thumb_x, track.top() + 2, thumb_size, thumb_size)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(thumb)
        painter.setPen(QColor("#33333D"))
        painter.setFont(QFont("Segoe UI Symbol", 12))
        painter.drawText(thumb, Qt.AlignCenter, "☾" if self.isChecked() else "☀")


class SettingsDialog(QDialog):
    def __init__(self, current_settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(420, 460)
        self.settings = current_settings
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_general_tab(current_settings), "General")
        self.tabs.addTab(self._build_apps_tab(current_settings), "Approved Applications")
        self.tabs.addTab(self._build_folders_tab(current_settings), "Approved Folders")

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._save_settings)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.exit_btn = QPushButton("Exit Application")
        self.exit_btn.setObjectName("exitButton")
        self.exit_btn.clicked.connect(QApplication.instance().quit)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.exit_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addLayout(btn_row)

    # ---- General ----------------------------------------------------------
    def _build_general_tab(self, current_settings: dict) -> QWidget:
        self.api_key_input = QLineEdit(current_settings.get("api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("Gemini API key")

        form = QFormLayout()
        form.addRow("API key", self.api_key_input)
        form.addRow("Model", QLabel("Gemini 3.5 Flash-Lite"))

        self.accent_color = QColor(current_settings.get("accent_color", "#FF2E88"))
        if not self.accent_color.isValid():
            self.accent_color = QColor("#FF2E88")
        self.accent_button = QPushButton()
        self.accent_button.clicked.connect(self._choose_accent_color)
        form.addRow("Accent color", self.accent_button)

        self.theme_switch = ThemeSwitch(
            current_settings.get("theme", "dark") == "dark", self.accent_color
        )
        self.theme_label = QLabel()
        self._update_theme_label(self.theme_switch.isChecked())
        self.theme_switch.toggled.connect(self._update_theme_label)
        self._refresh_accent_button()
        form.addRow(self.theme_label, self.theme_switch)

        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.addLayout(form)
        tab_layout.addStretch()

        return tab

    def _refresh_accent_button(self):
        accent = self.accent_color.name().upper()
        foreground = "#20202A" if self.accent_color.lightness() > 175 else "#FFFFFF"
        self.accent_button.setText("Select Color")
        self.accent_button.setStyleSheet(
            f"background-color: {accent}; color: {foreground}; border-radius: 8px;"
        )
        self.theme_switch.accent = QColor(self.accent_color)
        self.theme_switch.update()

    def _choose_accent_color(self):
        selected = QColorDialog.getColor(self.accent_color, self, "Choose accent color")
        if selected.isValid():
            self.accent_color = selected
            self._refresh_accent_button()

    def _update_theme_label(self, dark: bool):
        self.theme_label.setText("☾ Dark mode" if dark else "☀ Light mode")

    # ---- Approved Applications ---------------------------------------------
    def _build_apps_tab(self, current_settings: dict) -> QWidget:
        self.apps_list = QListWidget()
        for app in list_approved_applications():
            self._add_app_item(app.get("name", ""), app.get("path", ""))

        add_btn = QPushButton("Add Application…")
        add_btn.clicked.connect(self._add_application)
        installed_btn = QPushButton("Find Start Menu Apps…")
        installed_btn.clicked.connect(self._add_installed_application)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(lambda: self._remove_selected(self.apps_list))

        hint = QLabel(
            "Browse for an app or choose a shortcut from the Windows Start Menu."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8A8B95; font-size: 11px;")

        add_row = QHBoxLayout()
        add_row.addWidget(add_btn, 1)
        add_row.addWidget(installed_btn, 1)

        remove_row = QHBoxLayout()
        remove_row.addStretch(1)
        remove_row.addWidget(remove_btn, 1)
        remove_row.addStretch(1)

        button_layout = QVBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addLayout(add_row)
        button_layout.addLayout(remove_row)

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(self.apps_list, 1)
        layout.addLayout(button_layout)
        layout.addWidget(hint)
        return tab

    def _add_application(self):
        file_filter = "Applications (*.exe *.lnk);;All files (*)"
        path, _ = QFileDialog.getOpenFileName(self, "Add Application", "", file_filter)
        if not path:
            return
        try:
            resolved = resolve_shortcut(path)
        except RuntimeError as exc:
            QMessageBox.warning(self, "Can't read shortcut", str(exc))
            return
        self._add_app_item(display_name_for(resolved), resolved)

    def _add_installed_application(self):
        applications = list_installed_applications()
        if not applications:
            QMessageBox.information(
                self,
                "No app shortcuts found",
                "Windows didn't return any app shortcuts from the Start Menu.",
            )
            return

        picker = QDialog(self)
        picker.setWindowTitle("Find Start Menu Applications")
        picker.setFixedSize(340, 390)
        search = QLineEdit()
        search.setPlaceholderText("Search installed apps…")
        selection_hint = QLabel("Click each app to select it. Click again to deselect.")
        selection_hint.setStyleSheet("color: #8A8B95; font-size: 11px;")
        app_list = QListWidget()
        # MultiSelection toggles each row on a normal click, so multiple apps
        # can be selected without holding Ctrl or Shift.
        app_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        app_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for application in applications:
            item = QListWidgetItem(application["name"])
            item.setData(Qt.UserRole, application["path"])
            app_list.addItem(item)

        def filter_apps(query):
            query = query.casefold().strip()
            for index in range(app_list.count()):
                item = app_list.item(index)
                item.setHidden(query not in item.text().casefold())

        search.textChanged.connect(filter_apps)
        add_selected = QPushButton("Add Selected")
        add_selected.setEnabled(False)

        def update_add_button():
            selected_count = len(app_list.selectedItems())
            add_selected.setEnabled(selected_count > 0)
            add_selected.setText(
                f"Add Selected ({selected_count})" if selected_count else "Add Selected"
            )

        app_list.itemSelectionChanged.connect(update_add_button)
        add_selected.clicked.connect(picker.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(picker.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(cancel)
        button_row.addWidget(add_selected)
        layout = QVBoxLayout(picker)
        layout.addWidget(search)
        layout.addWidget(selection_hint)
        layout.addWidget(app_list, 1)
        layout.addLayout(button_row)

        if picker.exec() != QDialog.Accepted or not app_list.selectedItems():
            return
        existing_paths = {
            os.path.normcase(self.apps_list.item(i).data(Qt.UserRole))
            for i in range(self.apps_list.count())
        }
        added = 0
        for selected in app_list.selectedItems():
            path = selected.data(Qt.UserRole)
            normalized_path = os.path.normcase(path)
            if normalized_path in existing_paths:
                continue
            self._add_app_item(selected.text(), path)
            existing_paths.add(normalized_path)
            added += 1
        if added == 0:
            QMessageBox.information(
                self, "Already added", "All selected apps are already approved."
            )

    def _add_app_item(self, name: str, path: str):
        item = QListWidgetItem(name)
        item.setData(Qt.UserRole, path)
        item.setToolTip(path)
        self.apps_list.addItem(item)

    # ---- Approved Folders ---------------------------------------------------
    def _build_folders_tab(self, current_settings: dict) -> QWidget:
        self.folders_list = QListWidget()
        for folder in list_approved_folders():
            path = folder.get("path", "")
            item = QListWidgetItem(path)
            item.setToolTip(path)
            self.folders_list.addItem(item)

        add_btn = QPushButton("Add Folder…")
        add_btn.clicked.connect(self._add_folder)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(lambda: self._remove_selected(self.folders_list))

        btn_row = QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(self.folders_list, 1)
        layout.addLayout(btn_row)
        return tab

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Add Folder")
        if not folder:
            return
        if any(self.folders_list.item(i).text() == folder for i in range(self.folders_list.count())):
            return
        item = QListWidgetItem(folder)
        item.setToolTip(folder)
        self.folders_list.addItem(item)

    @staticmethod
    def _remove_selected(list_widget: QListWidget):
        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))

    def _save_settings(self):
        try:
            sync_approved_items(self.result_settings())
        except Exception as error:  # keep settings open if SQLite reports a problem
            QMessageBox.critical(self, "Couldn't save approved items", str(error))
            return
        self.accept()

    # ---- collect result -------------------------------------------------
    def result_settings(self) -> dict:
        apps = []
        for i in range(self.apps_list.count()):
            item = self.apps_list.item(i)
            apps.append({"name": item.text(), "path": item.data(Qt.UserRole)})

        folders = [self.folders_list.item(i).text() for i in range(self.folders_list.count())]

        return {
            "api_key": self.api_key_input.text().strip(),
            "model": GEMINI_MODEL,
            "accent_color": self.accent_color.name().upper(),
            "theme": "dark" if self.theme_switch.isChecked() else "light",
            "approved_apps": apps,
            "approved_folders": folders,
        }


class Bubble(QWidget):
    """The small companion orb shown when the chat is minimized."""
    clicked = Signal()

    def __init__(self, settings: dict | None = None):
        super().__init__()
        self.settings = settings or {}
        self.apply_appearance(self.settings)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(BUBBLE_SIZE, BUBBLE_SIZE)
        self.setWindowTitle("SideKick")

        self._drag_offset = QPoint()
        self._dragging = False

    def apply_appearance(self, settings: dict):
        self.settings = settings
        self.appearance = appearance_palette(settings)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        accent = self.appearance["accent_color"]
        # Keep all glow painting inside the translucent top-level window. A
        # QGraphicsDropShadowEffect expands Qt's dirty region past the window
        # bounds on Windows and can make UpdateLayeredWindowIndirect fail.
        for inset, alpha in ((0, 18), (1, 24), (2, 32)):
            glow = self.rect().adjusted(inset, inset, -inset, -inset)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), alpha))
            painter.drawEllipse(glow)

        rect = self.rect().adjusted(5, 5, -5, -5)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor(self.appearance["control"]))
        gradient.setColorAt(1.0, QColor(self.appearance["window"]))
        painter.setBrush(gradient)
        painter.setPen(QPen(accent, 1.5))
        painter.drawEllipse(rect)

        symbol_color = accent.lighter(140) if self.appearance["dark"] else accent.darker(125)
        # A small orbit-and-companion mark, drawn directly so it stays crisp
        # at the bubble's compact size and adapts to the chosen accent color.
        painter.save()
        painter.translate(rect.center())
        painter.rotate(-32)
        orbit_color = QColor(symbol_color)
        orbit_color.setAlpha(190)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(orbit_color, 1.5))
        painter.drawEllipse(QRectF(-15, -8, 30, 16))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(symbol_color)
        painter.drawEllipse(QPointF(-13, 0), 2.4, 2.4)
        painter.drawEllipse(QPointF(13, 0), 2.0, 2.0)
        painter.setBrush(QColor(symbol_color.red(), symbol_color.green(), symbol_color.blue(), 75))
        painter.drawEllipse(QPointF(0, 0), 7.0, 7.0)
        painter.setBrush(symbol_color)
        painter.drawEllipse(QPointF(0, 0), 4.2, 4.2)
        painter.restore()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._dragging = False

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._dragging = True
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            screen = primary_screen_rect()
            new_pos.setX(max(screen.left(), min(new_pos.x(), screen.right() - self.width())))
            new_pos.setY(max(screen.top(), min(new_pos.y(), screen.bottom() - self.height())))
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and not self._dragging:
            self.clicked.emit()
        self._dragging = False

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.exec(event.globalPos())


class SettingsButton(QPushButton):
    """A flat 'sliders' icon drawn by hand — no gear emoji."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("iconButton")
        self.setFixedSize(28, 28)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#B5B5C0"), 1.6)
        painter.setPen(pen)

        w, h = self.width(), self.height()
        xs = [w * 0.30, w * 0.50, w * 0.70]
        knob_y = [h * 0.38, h * 0.62, h * 0.42]
        for x, ky in zip(xs, knob_y):
            painter.drawLine(QPointF(x, h * 0.2), QPointF(x, h * 0.8))
            painter.setBrush(QColor("#B5B5C0"))
            painter.drawEllipse(QPointF(x, ky), 2.6, 2.6)


class MinimizeButton(QPushButton):
    """A flat single-line minimize glyph."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("iconButton")
        self.setFixedSize(28, 28)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#B5B5C0"), 2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        w, h = self.width(), self.height()
        painter.drawLine(QPointF(w * 0.28, h * 0.5), QPointF(w * 0.72, h * 0.5))


class StatusDot(QWidget):
    """A small pulsing dot used as a companion 'online' indicator."""

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.setFixedSize(9, 9)
        self._color = QColor(color)
        self._opacity = 1.0

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(900)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setStartValue(0.35)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_value_changed)
        self._anim.finished.connect(self._reverse)
        self._anim.start()

    def _on_value_changed(self, value):
        self._opacity = value
        self.update()

    def _reverse(self):
        start = self._anim.startValue()
        end = self._anim.endValue()
        self._anim.setStartValue(end)
        self._anim.setEndValue(start)
        self._anim.start()

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        color = QColor(self._color)
        color.setAlphaF(self._opacity)
        painter.setBrush(color)
        painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))


class TypingIndicator(QWidget):
    """A small animated wave of three dots for the current reply."""

    DOT_COUNT = 3
    DOT_RADIUS = 4.0
    SPACING = 11
    AMPLITUDE = 4.0

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(36, 18)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._advance)
        self.hide()

    def start(self):
        self._phase = 0.0
        self.show()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self.update()

    def _advance(self):
        self._phase = (self._phase + 0.22) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(self.DOT_COUNT):
            wave = math.sin(self._phase - index * (math.pi / 2.2))
            color = QColor(self._color)
            color.setAlphaF(0.55 + 0.45 * ((wave + 1) / 2))
            painter.setBrush(color)
            radius = self.DOT_RADIUS * (0.75 + 0.25 * ((wave + 1) / 2))
            x = self.DOT_RADIUS + 2 + index * self.SPACING
            y = self.height() / 2 - wave * self.AMPLITUDE
            painter.drawEllipse(QPointF(x, y), radius, radius)


class ChatWindow(QWidget):
    minimize_requested = Signal()
    settings_changed = Signal(dict)

    def __init__(self, settings: dict):
        super().__init__()
        self.setObjectName("chatCard")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("SideKick")

        self.settings = settings
        self.appearance = appearance_palette(settings)
        self.client = None
        self.worker = None
        self._request_in_flight = False
        self._init_client()

        self._drag_offset = QPoint()
        self._build_ui()

    # ---- background ---------------------------------------------------------
    def paintEvent(self, event):
        """Manually paint the card background so it always stays fully
        opaque — relying only on the stylesheet on a translucent, animated
        top-level window can leave stale/transparent pixels during resize."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), 20, 20)
        painter.fillPath(path, QColor(self.appearance["window"]))
        painter.setPen(QPen(QColor(self.appearance["border"]), 1))
        painter.drawPath(path)
        super().paintEvent(event)

    # ---- client lifecycle -------------------------------------------------
    def _init_client(self):
        api_key = self.settings.get("api_key", "")
        self.client = None
        self.client_error = None
        if api_key:
            try:
                self.client = GeminiClient(api_key, GEMINI_MODEL)
            except Exception as exc:  # noqa: BLE001 - missing package, bad key, etc.
                self.client_error = str(exc)

    def apply_settings(self, new_settings: dict):
        self.settings = new_settings
        settings_store.save(new_settings)
        self.appearance = appearance_palette(new_settings)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(build_stylesheet(new_settings))
        self.divider.setStyleSheet(f"background-color: {self.appearance['border']};")
        self.greeting_label.setStyleSheet(
            f"color: {self.appearance['muted']}; font-size: 12px; "
            "font-family: 'Segoe UI Semibold', 'Segoe UI', sans-serif;"
        )
        self.status_dot.set_color(QColor(self.appearance["accent"]))
        self.typing_indicator.set_color(QColor(self.appearance["accent"]))
        self.update()
        self._init_client()
        self.settings_changed.emit(new_settings)

    # ---- UI -----------------------------------------------------------------
    def _build_ui(self):
        title_bar = QHBoxLayout()
        title = QLabel("SideKick")
        title.setObjectName("titleLabel")

        settings_btn = SettingsButton()
        settings_btn.clicked.connect(self.open_settings)

        minimize_btn = MinimizeButton()
        minimize_btn.clicked.connect(self.minimize_requested.emit)

        title_bar.addWidget(title)
        title_bar.addStretch()
        title_bar.addWidget(settings_btn)
        title_bar.addWidget(minimize_btn)

        self.divider = QWidget()
        self.divider.setFixedHeight(1)
        self.divider.setStyleSheet(f"background-color: {self.appearance['border']};")

        # Greeting row shown at the top of the chat area so it never opens
        # to a blank/empty-feeling log — a pulsing dot + friendly hello.
        self.status_dot = StatusDot(QColor(self.appearance["accent"]))
        self.greeting_label = QLabel("Hey, Sidekick here to help!")
        self.greeting_label.setStyleSheet(
            f"color: {self.appearance['muted']}; font-size: 12px; "
            "font-family: 'Segoe UI Semibold', 'Segoe UI', sans-serif;"
        )
        greeting_row = QHBoxLayout()
        greeting_row.setContentsMargins(2, 0, 0, 4)
        greeting_row.setSpacing(8)
        greeting_row.addWidget(self.status_dot)
        greeting_row.addWidget(self.greeting_label)
        greeting_row.addStretch()

        self.chat_log = QTextEdit()
        self.chat_log.setObjectName("chatLog")
        self.chat_log.setReadOnly(True)
        self.typing_indicator = TypingIndicator(
            QColor(self.appearance["accent"]), self.chat_log.viewport()
        )
        self.chat_log.verticalScrollBar().valueChanged.connect(
            self._position_thinking_indicator
        )

        self._thinking_active = False
        self._thinking_anchor = None

        self.input_box = QLineEdit()
        self.input_box.setObjectName("chatInput")
        self.input_box.setPlaceholderText("Message your companion…")
        self.input_box.returnPressed.connect(self.send_message)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("sendButton")
        self.send_btn.clicked.connect(self.send_message)

        input_row = QHBoxLayout()
        input_row.addWidget(self.input_box, 1)
        input_row.addWidget(self.send_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.addLayout(title_bar)
        layout.addWidget(self.divider)
        layout.addLayout(greeting_row)
        layout.addWidget(self.chat_log, 1)
        layout.addLayout(input_row)

        if not self.client:
            if self.client_error:
                print(f"Gemini setup error: {self.client_error}")
                self._append("system", "Gemini couldn't start. See the Run console for details.")
            else:
                self._append("system", "No API key set yet — click Settings to add your Gemini API key.")

    # ---- dragging by the title area (whole window is frameless) ------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() < 40:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and event.position().y() < 40:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    # ---- chat logic -----------------------------------------------------
    def _append(self, sender: str, text: str):
        self.chat_log.append(self._message_html(sender, text))
        self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())

    def _message_html(self, sender: str, text: str) -> str:
        color = {
            "you": self.appearance["accent"],
            "companion": self.appearance["title"],
            "system": self.appearance["muted"],
        }[sender]
        label = {"you": "You", "companion": "Companion", "system": ""}[sender]
        prefix = f"<b style='color:{color}'>{label}:</b> " if label else ""
        safe_text = escape(text, quote=True).replace("\r\n", "\n").replace("\r", "\n")
        safe_text = safe_text.replace("\n", "<br>")
        return (
            "<div style=\"margin:6px 0; font-family:'Segoe UI','Calibri',sans-serif; "
            f"font-size:13.5px; line-height:1.45;\">{prefix}{safe_text}</div>"
        )

    def _start_thinking_message(self):
        self._thinking_active = True
        # Keep the indicator as a separate widget over a reserved blank row.
        # It never modifies any existing message text.
        self.chat_log.append("<div style='margin:0;font-size:13px'>&nbsp;</div>")
        cursor = QTextCursor(self.chat_log.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self._thinking_anchor = cursor
        self.chat_log.verticalScrollBar().setValue(self.chat_log.verticalScrollBar().maximum())
        self.typing_indicator.start()
        QTimer.singleShot(0, self._position_thinking_indicator)

    def _position_thinking_indicator(self, *_args):
        if not self._thinking_active or self._thinking_anchor is None:
            return
        rect = self.chat_log.cursorRect(self._thinking_anchor)
        viewport = self.chat_log.viewport()
        x = max(4, rect.left())
        y = min(max(0, rect.top()), max(0, viewport.height() - self.typing_indicator.height()))
        self.typing_indicator.move(x, y)

    def _stop_thinking_message(self):
        self.typing_indicator.stop()
        self._thinking_active = False
        if self._thinking_anchor is not None:
            block = self._thinking_anchor.block()
            if block.isValid() and not block.text().replace("\u00a0", "").strip():
                cursor = QTextCursor(block)
                cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                cursor.removeSelectedText()
                if cursor.block().previous().isValid():
                    cursor.deletePreviousChar()
        self._thinking_anchor = None

    def send_message(self):
        if self._request_in_flight:
            return
        text = self.input_box.text().strip()
        if not text:
            return
        self._append("you", text)
        self.input_box.clear()

        if not self.client:
            if self.client_error:
                print(f"Gemini setup error: {self.client_error}")
                self._append("system", "Gemini couldn't start. See the Run console for details.")
            else:
                self._append("system", "No API key set yet — click Settings to add one.")
            return
        self._request_in_flight = True
        self.send_btn.setEnabled(False)
        self.input_box.setEnabled(False)
        self._start_thinking_message()

        self.worker = GeminiWorker(self.client, text)
        self.worker.reply_ready.connect(self._on_reply)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self):
        self._request_in_flight = False
        self.send_btn.setEnabled(True)
        self.input_box.setEnabled(True)

    def _on_reply(self, text: str):
        self._stop_thinking_message()
        self._append("companion", text)

    def _on_error(self, message: str):
        self._stop_thinking_message()
        details = message.casefold()
        if "getaddrinfo failed" in details or "name resolution" in details or "11001" in details:
            friendly = "I couldn't reach an online service. Check your internet connection and try again."
        elif "api key" in details or "unauthenticated" in details or "401" in details:
            friendly = "Gemini rejected the API key. Check the key in Settings."
        elif "429" in details or "resource_exhausted" in details or "rate limit" in details:
            friendly = "Gemini is at its request limit right now. Wait a little, then try again."
        else:
            friendly = "I couldn't complete that request. See the Run console for details."
        self._append("system", friendly)

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.Accepted:
            self.apply_settings(dialog.result_settings())
            self._append("system", "Settings updated.")


class CompanionController:
    """Owns the bubble + chat window and animates between them."""

    def __init__(self):
        self.settings = settings_store.load()
        if self.settings.get("model") != GEMINI_MODEL:
            self.settings["model"] = GEMINI_MODEL
            settings_store.save(self.settings)
        migrate_legacy_approvals(self.settings)
        self.bubble = Bubble(self.settings)
        app_icon = QIcon(self.bubble.grab())
        self.bubble.setWindowIcon(app_icon)
        self.chat = ChatWindow(self.settings)
        self.chat.setWindowIcon(app_icon)
        self.overlay = None
        self.progress_anim = None
        self._pending_target = None
        self._last_bubble_rect = None

        self.bubble.clicked.connect(self.expand)
        self.chat.minimize_requested.connect(self.collapse)
        self.chat.settings_changed.connect(self._apply_settings)

        screen = primary_screen_rect()
        bubble_rect = QRect(
            screen.left() + SCREEN_MARGIN,
            screen.bottom() - SCREEN_MARGIN - BUBBLE_SIZE,
            BUBBLE_SIZE, BUBBLE_SIZE,
        )
        self.bubble.setGeometry(bubble_rect)
        self.bubble.show()
        set_windows_taskbar_identity(self.bubble)
        self.chat.setGeometry(self._chat_target_rect(bubble_rect))
        set_windows_taskbar_identity(self.chat)
        QTimer.singleShot(120, self.expand)

    def _chat_target_rect(self, anchor: QRect) -> QRect:
        screen = primary_screen_rect()
        x = anchor.left()
        y = anchor.bottom() - CHAT_SIZE.height()

        x = max(screen.left(), min(x, screen.right() - CHAT_SIZE.width()))
        y = max(screen.top(), min(y, screen.bottom() - CHAT_SIZE.height()))

        return QRect(x, y, CHAT_SIZE.width(), CHAT_SIZE.height())

    def _apply_settings(self, settings: dict):
        self.settings = settings
        self.bubble.apply_appearance(settings)
        self.bubble.repaint()
        app_icon = QIcon(self.bubble.grab())
        self.bubble.setWindowIcon(app_icon)
        self.chat.setWindowIcon(app_icon)
        app = QApplication.instance()
        if app:
            app.setWindowIcon(app_icon)

    def _run_genie(self, pixmap: QPixmap, full_rect: QRect, bubble_rect: QRect,
                    start: float, end: float, on_finished):
        self.overlay = GenieOverlay(
            pixmap, full_rect, bubble_rect,
            self.settings.get("accent_color", "#FF2E88"),
        )
        self.overlay.show()

        anim = QVariantAnimation()
        anim.setDuration(720)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.valueChanged.connect(self.overlay.set_progress)
        anim.finished.connect(on_finished)
        anim.start()
        self.progress_anim = anim  # keep a reference alive

    def _clear_overlay(self):
        if self.overlay:
            self.overlay.hide()
            self.overlay.deleteLater()
            self.overlay = None

    def expand(self):
        bubble_rect = self.bubble.geometry()
        self._last_bubble_rect = bubble_rect
        target = self._chat_target_rect(bubble_rect)
        self._pending_target = target

        # Render the window at its final size/content first so we have
        # something to warp, then hide it again until the animation lands.
        self.chat.setGeometry(target)
        self.chat.show()
        set_windows_taskbar_identity(self.chat)
        pixmap = self.chat.grab()
        self.chat.setWindowOpacity(0.0)
        self.bubble.hide()

        self._run_genie(pixmap, target, bubble_rect, start=1.0, end=0.0, on_finished=self._finish_expand)

    def _finish_expand(self):
        self._clear_overlay()
        self.chat.setGeometry(self._pending_target)
        self.chat.setWindowOpacity(1.0)
        self.chat.show()

    def collapse(self):
        chat_rect = self.chat.geometry()
        screen = primary_screen_rect()

        if self._last_bubble_rect is not None:
            x = max(screen.left(), min(self._last_bubble_rect.left(), screen.right() - BUBBLE_SIZE))
            y = max(screen.top(), min(self._last_bubble_rect.top(), screen.bottom() - BUBBLE_SIZE))
        else:
            x = chat_rect.left()
            y = screen.bottom() - SCREEN_MARGIN - BUBBLE_SIZE
        bubble_rect = QRect(x, y, BUBBLE_SIZE, BUBBLE_SIZE)

        pixmap = self.chat.grab()
        self.chat.setWindowOpacity(0.0)

        def finish():
            self._clear_overlay()
            self.chat.hide()
            self.chat.setWindowOpacity(1.0)
            self.bubble.setGeometry(bubble_rect)
            self.bubble.show()

        self._run_genie(pixmap, chat_rect, bubble_rect, start=0.0, end=1.0, on_finished=finish)


class GenieOverlay(QWidget):
    """
    Gathers a snapshot of the chat into the bubble with a soft 2D corner fold.
    The three distant corners travel first; the icon-side corner follows so
    the motion feels pulled into the bubble. Progress runs 0 -> 1 on minimize
    and 1 -> 0 on restore, giving both directions the same shape and timing.
    """

    GRID_COLS = 14
    GRID_ROWS = 20

    def __init__(self, pixmap: QPixmap, full_rect: QRect, bubble_rect: QRect,
                 accent_color: str = "#FF2E88"):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._pixmap = pixmap
        self._full_rect = full_rect
        self._bubble_rect = bubble_rect
        self._accent_color = QColor(accent_color)
        if not self._accent_color.isValid():
            self._accent_color = QColor("#FF2E88")
        self._progress = 0.0  # 0 = full window shape, 1 = collapsed into the bubble

        bounds = full_rect.united(bubble_rect).adjusted(-4, -4, 4, 4)
        self._origin = bounds.topLeft()
        self.setGeometry(bounds)

    def set_progress(self, value: float):
        self._progress = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        full = self._full_rect.translated(-self._origin)
        bubble = self._bubble_rect.translated(-self._origin)
        icon_x = bubble.center().x()
        shrink_t = self._progress

        # A faint pink pulse follows the warp and dies away at either end.
        pulse = math.sin(math.pi * shrink_t)
        if pulse > 0:
            glow_center = QPointF(icon_x, bubble.center().y())
            glow = QRadialGradient(glow_center, max(bubble.width(), bubble.height()) * 1.55)
            accent = self._accent_color
            glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), int(28 * pulse)))
            glow.setColorAt(0.55, QColor(accent.red(), accent.green(), accent.blue(), int(12 * pulse)))
            glow.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(glow))
            radius = max(bubble.width(), bubble.height()) * 1.55
            painter.drawEllipse(glow_center, radius, radius)

        src_h = self._pixmap.height()
        src_w = self._pixmap.width()
        progress = shrink_t

        def map_point(u: float, v: float) -> QPointF:
            # The icon sits at the lower-left corner. Points farther from it
            # start moving sooner, so the other three corners visibly gather in.
            distance = math.sqrt(u * u + (1.0 - v) * (1.0 - v)) / math.sqrt(2.0)
            travel = progress * (0.62 + 0.38 * distance)
            start_x = full.left() + u * full.width()
            start_y = full.top() + v * full.height()
            end_x = bubble.left() + u * bubble.width()
            end_y = bubble.top() + v * bubble.height()
            return QPointF(
                start_x + (end_x - start_x) * travel,
                start_y + (end_y - start_y) * travel,
            )

        fade = max(0.0, min(1.0, (progress - 0.93) / 0.07))
        fade = fade * fade * (3.0 - 2.0 * fade)
        painter.setOpacity(1.0 - fade)

        for row in range(self.GRID_ROWS):
            v0 = row / self.GRID_ROWS
            v1 = (row + 1) / self.GRID_ROWS
            sy0 = int(v0 * src_h)
            sy1 = min(src_h, int(v1 * src_h) + 1)

            for col in range(self.GRID_COLS):
                u0 = col / self.GRID_COLS
                u1 = (col + 1) / self.GRID_COLS
                sx0 = int(u0 * src_w)
                sx1 = min(src_w, int(u1 * src_w) + 1)

                corners = (
                    map_point(u0, v0), map_point(u1, v0),
                    map_point(u0, v1), map_point(u1, v1),
                )
                xs = [point.x() for point in corners]
                ys = [point.y() for point in corners]
                left, right = min(xs), max(xs)
                top, bottom = min(ys), max(ys)
                dest_rect = QRectF(left, top, max(0.5, right - left), max(0.5, bottom - top))
                src_rect = QRectF(sx0, sy0, max(1, sx1 - sx0), max(1, sy1 - sy0))
                painter.drawPixmap(dest_rect, self._pixmap, src_rect)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SideKick")
    if sys.platform == "win32":
        try:
            from ctypes import wintypes

            set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
            set_app_id.argtypes = [wintypes.LPCWSTR]
            set_app_id.restype = ctypes.c_long
            set_app_id("SideKick.Chat")
        except (AttributeError, OSError):
            pass
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(build_stylesheet(settings_store.load()))
    app.setFont(QFont("Segoe UI", 10))

    controller = CompanionController()  # noqa: F841 - keep alive for app lifetime
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
