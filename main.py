import ctypes
import ctypes.wintypes
import json
import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize, QFileInfo, Signal, QMimeData, QPoint
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QDrag,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import QGraphicsDropShadowEffect
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileIconProvider,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config_manager import ConfigManager
from start_menu import StartMenuScanner, parse_lnk_file
import theme as theme_module

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_MAP = {"Alt": MOD_ALT, "Ctrl": MOD_CONTROL, "Shift": MOD_SHIFT, "Win": MOD_WIN}

VK_MAP = {
    "Space": 0x20, "Enter": 0x0D, "Backspace": 0x08, "Tab": 0x09,
    "Escape": 0x1B, "Delete": 0x2E, "Home": 0x24, "End": 0x23,
}
for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"):
    VK_MAP[ch] = 0x41 + i if ch.isalpha() else 0x30 + (ord(ch) - 48)
for i in range(1, 13):
    VK_MAP[f"F{i}"] = 0x70 + i - 1

_icon_provider = QFileIconProvider()

LETTERS = "#ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _extract_icon(path: str, index: int) -> QIcon | None:
    try:
        from ctypes import windll, c_wchar_p, byref, c_int, POINTER, c_void_p
        from PySide6.QtGui import QPixmap
        hicon_large = c_void_p()
        ret = windll.shell32.ExtractIconExW(
            c_wchar_p(path), c_int(index),
            byref(hicon_large), None, c_int(1)
        )
        if ret > 0 and hicon_large:
            pm = QPixmap.fromHICON(int(hicon_large.value))
            windll.user32.DestroyIcon(hicon_large)
            if pm and not pm.isNull():
                return QIcon(pm)
    except Exception:
        pass
    return None


def _get_app_icon(app: dict) -> QIcon:
    target = app.get("target", "")
    icon_path = app.get("icon_path", "")
    icon_index = app.get("icon_index", 0)
    lnk_path = app.get("lnk_path", "")

    # Try icon_path with its specific index first (handles DLL resources)
    if icon_path and os.path.exists(icon_path):
        icon = _extract_icon(icon_path, icon_index)
        if icon:
            return icon

    # Try target at index 0 (no shortcut arrow overlay)
    if target and os.path.exists(target):
        icon = _extract_icon(target, 0)
        if icon:
            return icon

    # Fallback: lnk_path (may have shortcut arrow overlay, but better than nothing)
    if lnk_path and os.path.exists(lnk_path):
        return _icon_provider.icon(QFileInfo(lnk_path))

    return QIcon()


def _make_tray_pixmap() -> QPixmap:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(Qt.darkGreen)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(4, 4, 56, 56, 12, 12)
    p.setPen(Qt.white)
    f = p.font()
    f.setPixelSize(36)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "W")
    p.end()
    return pm


def _menu_style() -> str:
    c = theme_module.current()
    return f"""
        QMenu {{ background: {c['bg_widget']}; color: {c['text']}; border: 1px solid {c['border_light']}; border-radius: 8px; padding: 4px; }}
        QMenu::item {{ padding: 8px 24px; border-radius: 4px; margin: 1px 4px; }}
        QMenu::item:selected {{ background: {c['bg_active']}; color: #fff; }}
        QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
    """

logger = logging.getLogger("winlauncher")


def launch_app(app: dict) -> bool:
    target = app.get("target", "")
    args = app.get("args", "")
    work_dir = app.get("working_dir", "")
    if not target:
        return False
    try:
        cmd = [target]
        if args:
            cmd.extend(shlex.split(args, posix=False))
        subprocess.Popen(cmd, cwd=work_dir or None, close_fds=True)
        return True
    except (OSError, ValueError):
        logger.exception("Failed to launch %s", target)
        return False


# ─── App button (group) ───────────────────────────────────────

class AppButton(QToolButton):

    def __init__(self, app_info: dict, parent=None):
        super().__init__(parent)
        self.app_info = app_info
        self._drag_start = None
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setText(app_info.get("name", ""))
        tip = app_info.get("name", "")
        if app_info.get("target"):
            tip += f"\n{app_info['target']}"
        self.setToolTip(tip)
        self.setIcon(_get_app_icon(app_info))
        self.setIconSize(QSize(28, 28))
        self.setFixedSize(80, 72)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._apply_style()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.position().toPoint()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_start and event.buttons() == Qt.LeftButton:
            dist = (event.position().toPoint() - self._drag_start).manhattanLength()
            if dist > 10:
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(json.dumps(self.app_info))
                drag.setMimeData(mime)
                pm = self.grab()
                drag.setPixmap(pm.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                drag.setHotSpot(QPoint(32, 32))
                self._drag_start = None
                drag.exec(Qt.MoveAction)
                return
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_start = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self._drag_start = None
        launch_app(self.app_info)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(_menu_style())
        menu.addAction("Launch").triggered.connect(
            lambda: launch_app(self.app_info)
        )
        menu.addSeparator()
        menu.addAction("Remove from Group").triggered.connect(self._remove_self)
        menu.exec(self.mapToGlobal(pos))

    def _apply_style(self):
        c = theme_module.current()
        self.setStyleSheet(f"""
            QToolButton {{
                background: transparent; border: none;
                border-radius: 8px; padding: 4px 2px; color: {c['text_muted']}; font-size: 11px;
            }}
            QToolButton:hover {{ background-color: {c['bg_hover']}; }}
        """)

    def _remove_self(self):
        p = self.parent()
        while p and not hasattr(p, "remove_app"):
            p = p.parent()
        if p:
            p.remove_app(self.app_info)


# ─── Group widget ─────────────────────────────────────────────

class GroupWidget(QFrame):

    def __init__(self, group_index: int, group_data: dict, parent=None):
        super().__init__(parent)
        self.group_index = group_index
        self.group_data = group_data
        self._app_buttons = []
        self._setup_ui()
        self.setAcceptDrops(True)

    def _setup_ui(self):
        self._apply_theme()
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        self.name_label = QLabel(self.group_data.get("name", "Group"))
        self.name_label.setContextMenuPolicy(Qt.CustomContextMenu)
        self.name_label.customContextMenuRequested.connect(self._show_header_context_menu)
        header.addWidget(self.name_label)
        header.addStretch()

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.clicked.connect(self._request_remove_group)
        del_btn.setCursor(Qt.PointingHandCursor)
        header.addWidget(del_btn)

        layout.addLayout(header)

        self._grid = QHBoxLayout()
        self._grid.setSpacing(6)
        self._grid.addStretch()
        layout.addLayout(self._grid)
        self._populate_grid()

    def _apply_theme(self):
        c = theme_module.current()
        self.setStyleSheet(f"""
            GroupWidget {{
                background-color: {c['bg_widget']};
                border: 1px solid {c['border']};
                border-radius: 12px;
            }}
        """)
        if hasattr(self, 'name_label'):
            self.name_label.setStyleSheet(
                f"font-size: 14px; font-weight: 600; color: {c['text']}; background: transparent;"
            )
        children = self.findChildren(QPushButton)
        for btn in children:
            if btn.text() == "✕":
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; border: none; color: {c['text_disabled']}; font-size: 14px; }}"
                    f"QPushButton:hover {{ color: {c['text_danger']}; }}"
                )

    def _populate_grid(self):
        while self._grid.count() > 1:
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._app_buttons.clear()
        for app in self.group_data.get("apps", []):
            btn = AppButton(app)
            self._grid.insertWidget(self._grid.count() - 1, btn)
            self._app_buttons.append(btn)

    def refresh(self, group_data: dict):
        self.group_data = group_data
        self._populate_grid()

    def remove_app(self, app_info: dict):
        p = self.parent()
        while p and not hasattr(p, "_remove_app_from_group"):
            p = p.parent()
        if p:
            try:
                idx = self.group_data["apps"].index(app_info)
                p._remove_app_from_group(self.group_index, idx)
            except ValueError:
                pass

    def _launch_all(self):
        for app in self.group_data.get("apps", []):
            launch_app(app)

    def _request_remove_group(self):
        p = self.parent()
        while p and not hasattr(p, "_remove_group"):
            p = p.parent()
        if p:
            for idx, g in enumerate(p.config.groups):
                if g is self.group_data:
                    p._remove_group(idx)
                    return

    def _show_header_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(_menu_style())

        launch_all_action = menu.addAction("▶ Launch All")
        launch_all_action.triggered.connect(self._launch_all)

        rename_action = menu.addAction("✎ Rename Group")
        rename_action.triggered.connect(self._rename_group)

        menu.exec(self.name_label.mapToGlobal(pos))

    def _rename_group(self):
        p = self.parent()
        while p and not hasattr(p, "_input_dialog"):
            p = p.parent()
        if p:
            new_name = p._input_dialog(
                "Rename Group", "New name:", text=self.group_data.get("name", "")
            )
            if new_name:
                self.group_data["name"] = new_name
                p.config.save()
                p._rebuild_groups()

    # ── drag-drop reorder for app buttons ──

    def dragEnterEvent(self, event: QDragEnterEvent):
        if isinstance(event.source(), AppButton):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event: QDropEvent):
        if isinstance(event.source(), AppButton):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        src = event.source()
        if not isinstance(src, AppButton):
            event.ignore()
            return
        if src.parent() is not self:
            return
        event.acceptProposedAction()
        old_idx = self._app_buttons.index(src)
        new_idx = self._drop_index(event.position().x())
        if old_idx == new_idx:
            return
        apps = self.group_data["apps"]
        app = apps.pop(old_idx)
        if new_idx > old_idx:
            new_idx -= 1
        apps.insert(new_idx, app)
        p = self.parent()
        while p and not hasattr(p, "config"):
            p = p.parent()
        if p:
            p.config.save()
        self._populate_grid()

    def _drop_index(self, x: int) -> int:
        if not self._app_buttons:
            return 0
        best = len(self._app_buttons)
        for i, btn in enumerate(self._app_buttons):
            cx = btn.geometry().center().x()
            if x < cx:
                best = i
                break
        return best


# ─── All‑Apps view (A‑Z  /  Folders) ─────────────────────────

class AllAppsWidget(QWidget):

    def __init__(self, scanner: StartMenuScanner, parent=None):
        super().__init__(parent)
        self.scanner = scanner
        self._current_letter = "#"
        self._inner = QStackedWidget()

        # ── page 0: A‑Z ──
        self._az_widget = QWidget()
        self._build_az_view()
        self._inner.addWidget(self._az_widget)

        # ── page 1: Folders ──
        self._folder_widget = QWidget()
        self._build_folder_view()
        self._inner.addWidget(self._folder_widget)

        # ── outer layout ──
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # mode toggle
        toggle_bar = QHBoxLayout()
        toggle_bar.setContentsMargins(4, 4, 4, 0)
        self._btn_az = QPushButton("A–Z")
        self._btn_az.setCheckable(True)
        self._btn_az.setChecked(True)
        self._btn_az.clicked.connect(lambda: self._switch_mode(0))
        toggle_bar.addWidget(self._btn_az)

        self._btn_folders = QPushButton("Folders")
        self._btn_folders.setCheckable(True)
        self._btn_folders.clicked.connect(lambda: self._switch_mode(1))
        toggle_bar.addWidget(self._btn_folders)

        toggle_bar.addStretch()
        outer.addLayout(toggle_bar)
        outer.addWidget(self._inner, 1)

    def apply_theme(self, c: dict):
        tb = f"""
            QPushButton {{
                background: transparent; border: none;
                color: {c['text_muted']}; padding: 5px 16px; border-radius: 6px;
                font-size: 12px; font-weight: 500;
            }}
            QPushButton:hover {{ background: {c['bg_hover']}; color: {c['text_secondary']}; }}
            QPushButton:checked {{ background: {c['bg_active']}; color: #fff; }}
        """
        self._btn_az.setStyleSheet(tb)
        self._btn_folders.setStyleSheet(tb)

        self._list.setStyleSheet(f"""
            QListWidget {{ background: transparent; border: none; color: {c['text']}; font-size: 13px; }}
            QListWidget::item {{ padding: 6px 12px; border-radius: 4px; }}
            QListWidget::item:hover {{ background-color: {c['bg_hover']}; }}
            QListWidget::item:selected {{ background-color: {c['bg_active']}; }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px 0; }}
            QScrollBar::handle:vertical {{ background: {c['scrollbar']}; border-radius: 3px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: {c['scrollbar_hover']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background: transparent; border: none; color: {c['text']}; font-size: 13px;
            }}
            QTreeWidget::item {{ padding: 4px 8px; border-radius: 4px; }}
            QTreeWidget::item:hover {{ background-color: {c['bg_hover']}; }}
            QTreeWidget::item:selected {{ background-color: {c['bg_active']}; }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px 0; }}
            QScrollBar::handle:vertical {{ background: {c['scrollbar']}; border-radius: 3px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: {c['scrollbar_hover']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._highlight_letter(self._current_letter)
        panel = self._az_widget.findChild(QFrame, "letterPanel")
        if panel:
            panel.setStyleSheet(f"background: {c['bg']}; border: none;")
        div = self._az_widget.findChild(QFrame, "divider")
        if div:
            div.setStyleSheet(f"background: {c['border_light']};")

    # ── A‑Z sub-view ──

    def _build_az_view(self):
        layout = QHBoxLayout(self._az_widget)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(0)

        letter_panel = QFrame()
        letter_panel.setObjectName("letterPanel")
        letter_panel.setFixedWidth(36)
        lp = QVBoxLayout(letter_panel)
        lp.setContentsMargins(2, 4, 2, 4)
        lp.setSpacing(1)
        lp.setAlignment(Qt.AlignTop)

        self._letter_btns = {}
        for ch in LETTERS:
            btn = QPushButton(ch)
            btn.setFixedSize(32, 28)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, c=ch: self._jump_to(c))
            lp.addWidget(btn)
            self._letter_btns[ch] = btn

        layout.addWidget(letter_panel)

        div = QFrame()
        div.setObjectName("divider")
        div.setFixedWidth(1)
        layout.addWidget(div)

        self._list = QListWidget()
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._list.itemDoubleClicked.connect(self._on_launch)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context)
        layout.addWidget(self._list, 1)

        self._build_index()
        self._highlight_letter("#")

    def _build_index(self):
        self._index = {}
        for ch in LETTERS:
            self._index[ch] = []
        for a in self.scanner.apps:
            name = a.get("name", "")
            first = name[0].upper() if name else "#"
            if first in LETTERS:
                self._index[first].append(a)
            else:
                self._index["#"].append(a)

    def _highlight_letter(self, ch: str):
        c = theme_module.current()
        for k, btn in self._letter_btns.items():
            sel = f"QPushButton {{ background: {c['bg_active']}; border: none; color: #fff; font-size: 11px; font-weight: bold; border-radius: 4px; }}"
            norm = f"QPushButton {{ background: transparent; border: none; color: {c['text_muted']}; font-size: 11px; font-weight: bold; }} QPushButton:hover {{ color: {c['text']}; background: {c['bg_hover']}; border-radius: 4px; }}"
            btn.setStyleSheet(sel if k == ch else norm)

    def _jump_to(self, ch: str):
        self._current_letter = ch
        self._highlight_letter(ch)
        self._list.clear()
        for app in self._index.get(ch, []):
            item = QListWidgetItem()
            item.setIcon(_get_app_icon(app))
            item.setText(f"{app['name']}")
            item.setData(Qt.UserRole, app)
            item.setSizeHint(QSize(0, 36))
            self._list.addItem(item)

    # ── Folders sub‑view ──

    def _build_folder_view(self):
        layout = QVBoxLayout(self._folder_widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(20)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_tree_context)
        self._tree.itemDoubleClicked.connect(self._on_tree_launch)
        layout.addWidget(self._tree)

        self._rebuild_tree()

    def _rebuild_tree(self):
        self._tree.clear()
        folder_idx = self.scanner.get_folder_index()

        def add_app(title: str, app: dict, parent: QTreeWidget | QTreeWidgetItem):
            item = QTreeWidgetItem(parent, [title])
            item.setIcon(0, _get_app_icon(app))
            item.setData(0, Qt.UserRole, app)
            item.setSizeHint(0, QSize(0, 32))

        # Root apps first
        for app in sorted(folder_idx.get("(Root)", []), key=lambda x: x["name"]):
            add_app(app["name"], app, self._tree)

        # Then folders
        for fname in sorted(folder_idx.keys()):
            if fname == "(Root)":
                continue
            apps = folder_idx[fname]
            folder_item = QTreeWidgetItem(self._tree, [f"📁  {fname}"])
            folder_item.setChildIndicatorPolicy(
                QTreeWidgetItem.ShowIndicator
            )
            folder_item.setSizeHint(0, QSize(0, 32))
            folder_item.setExpanded(False)
            for app in sorted(apps, key=lambda x: x["name"]):
                add_app(app["name"], app, folder_item)

    def _on_tree_launch(self, item: QTreeWidgetItem, _col: int):
        app = item.data(0, Qt.UserRole)
        if app:
            launch_app(app)

    def _on_tree_context(self, pos):
        item = self._tree.itemAt(pos)
        if not item:
            return
        app = item.data(0, Qt.UserRole)
        if not app:
            return
        menu = QMenu(self)
        menu.setStyleSheet(_menu_style())
        menu.addAction("Launch").triggered.connect(lambda: launch_app(app))
        menu.addSeparator()
        p = self.parent()
        while p and not hasattr(p, "config"):
            p = p.parent()
        groups = p.config.groups if p and hasattr(p, "config") else []
        if groups:
            sub = menu.addMenu("Add to Group")
            for i, g in enumerate(groups):
                sub.addAction(g["name"]).triggered.connect(
                    lambda checked=False, idx=i: self._add_to_group(idx, app)
                )
        menu.exec(self._tree.mapToGlobal(pos))

    # ── shared ──

    def _switch_mode(self, mode: int):
        self._btn_az.setChecked(mode == 0)
        self._btn_folders.setChecked(mode == 1)
        self._inner.setCurrentIndex(mode)

    def refresh(self):
        self._build_index()
        self._jump_to(self._current_letter)
        self._rebuild_tree()

    def _on_launch(self, item: QListWidgetItem):
        app = item.data(Qt.UserRole)
        if app:
            launch_app(app)

    def _on_context(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        app = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet(_menu_style())
        menu.addAction("Launch").triggered.connect(lambda: launch_app(app))
        menu.addSeparator()
        p = self.parent()
        while p and not hasattr(p, "config"):
            p = p.parent()
        groups = p.config.groups if p and hasattr(p, "config") else []
        if groups:
            sub = menu.addMenu("Add to Group")
            for i, g in enumerate(groups):
                sub.addAction(g["name"]).triggered.connect(
                    lambda checked=False, idx=i: self._add_to_group(idx, app)
                )
        menu.exec(self._list.mapToGlobal(pos))

    def _add_to_group(self, group_index: int, app: dict):
        p = self.parent()
        while p and not hasattr(p, "_add_to_group"):
            p = p.parent()
        if p:
            p._add_to_group(group_index, app)


# ─── Draggable group list ─────────────────────────────────────

class GroupsListWidget(QListWidget):
    order_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.apply_theme(theme_module.current())

    def apply_theme(self, c: dict):
        self.setStyleSheet(f"""
            QListWidget {{ background: transparent; border: none; }}
            QListWidget::item {{ border: none; padding: 0; margin: 0; }}
            QListWidget::item:selected {{ background: transparent; }}
        """)
        sb = self.verticalScrollBar()
        sb.setStyleSheet(f"""
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px 0; }}
            QScrollBar::handle:vertical {{ background: {c['scrollbar']}; border-radius: 3px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: {c['scrollbar_hover']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def dropEvent(self, event: QDropEvent):
        super().dropEvent(event)
        self.order_changed.emit()


# ─── Main window ──────────────────────────────────────────────

class LauncherWindow(QMainWindow):

    PAGE_GROUPS = 0
    PAGE_SEARCH = 1
    PAGE_ALLAPPS = 2

    def __init__(self, config: ConfigManager, scanner: StartMenuScanner):
        super().__init__()
        self.config = config
        self.scanner = scanner
        self._drag_pos = None
        self._setup_ui()
        self._load_groups()
        self._register_hotkey()
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._perform_search)

    def _setup_ui(self):
        self.setWindowTitle("WinLauncher · Command Deck")
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(640, 520)
        self.resize(840, 620)

        self._central = QWidget()
        self._central.setObjectName("central")
        self.setCentralWidget(self._central)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(60)
        shadow.setColor(QColor(0, 0, 0, 140))
        shadow.setOffset(0, 10)
        self._central.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self._central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ── resize grip ──
        self._grip = QSizeGrip(self._central)
        self._grip.installEventFilter(self)

        # ── search bar ──
        self._search_frame = QFrame()
        self._search_frame.setObjectName("searchFrame")
        srch = QHBoxLayout(self._search_frame)
        srch.setContentsMargins(12, 8, 12, 8)

        icon_lbl = QLabel("🔍")
        srch.addWidget(icon_lbl)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索应用，按 Enter 启动…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self._on_search_enter)
        srch.addWidget(self.search_input)

        layout.addWidget(self._search_frame)

        # ── content stack ──
        self.content_stack = QStackedWidget()

        # page 0: groups (draggable reorder)
        self.groups_list = GroupsListWidget()
        self.groups_list.order_changed.connect(self._on_groups_reordered)
        self.content_stack.addWidget(self.groups_list)

        # page 1: search results
        self.results_list = QListWidget()
        self.results_list.setObjectName("resultsList")
        self.results_list.itemDoubleClicked.connect(self._launch_result)
        self.results_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.results_list.customContextMenuRequested.connect(
            self._search_context_menu
        )
        self.content_stack.addWidget(self.results_list)

        # page 2: all apps (A‑Z / Folders)
        self.allapps_view = AllAppsWidget(self.scanner, self)
        self.content_stack.addWidget(self.allapps_view)

        layout.addWidget(self.content_stack, 1)

        # ── bottom bar ──
        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        self._btn_groups = QPushButton("工作台")
        self._btn_groups.setCheckable(True)
        self._btn_groups.setChecked(True)
        self._btn_groups.clicked.connect(lambda: self._show_page(self.PAGE_GROUPS))
        bottom.addWidget(self._btn_groups)

        self._btn_allapps = QPushButton("全部应用")
        self._btn_allapps.setCheckable(True)
        self._btn_allapps.clicked.connect(lambda: self._show_page(self.PAGE_ALLAPPS))
        bottom.addWidget(self._btn_allapps)

        add_grp = QPushButton("＋ Group")
        add_grp.setText("＋ 新建分组")
        self._add_group_btn = add_grp
        add_grp.clicked.connect(self._add_group_dialog)
        bottom.addWidget(add_grp)

        bottom.addStretch()

        self._manage_btn = QPushButton("⚙")
        self._manage_btn.setFixedSize(32, 32)
        self._manage_btn.clicked.connect(self._show_settings)
        bottom.addWidget(self._manage_btn)

        self._hide_btn = QPushButton("✕ Hide")
        self._hide_btn.clicked.connect(self.hide)
        bottom.addWidget(self._hide_btn)

        layout.addLayout(bottom)

        # ── drag & drop ──
        self._central.setAcceptDrops(True)

        # ── apply initial theme ──
        self._apply_theme()

    # ── theme ──

    def _apply_theme(self):
        c = theme_module.current()
        qapp = QApplication.instance()

        qapp.setStyleSheet(f"""
            QToolTip {{
                background: {c['bg_widget']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 4px; padding: 4px;
            }}
        """)

        self._central.setStyleSheet(f"""
            QWidget#central {{
                background-color: {c['bg']};
                border: 1px solid {c['border']};
                border-radius: 12px;
            }}
        """)

        self._search_frame.setStyleSheet(f"""
            QFrame#searchFrame {{
                background-color: {c['bg_search']};
                border: 1px solid {c['border']};
                border-radius: 10px;
            }}
            QFrame#searchFrame:focus-within {{
                border-color: {c['bg_active']};
            }}
        """)

        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; border: none; color: {c['text']};
                font-size: 13px; padding: 4px;
            }}
        """)

        self.results_list.setStyleSheet(f"""
            QListWidget {{ background: transparent; border: none; color: {c['text']}; font-size: 13px; }}
            QListWidget::item {{ padding: 8px 12px; border-radius: 4px; }}
            QListWidget::item:hover {{ background-color: {c['bg_hover']}; }}
            QListWidget::item:selected {{ background-color: {c['bg_active']}; }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px 0; }}
            QScrollBar::handle:vertical {{ background: {c['scrollbar']}; border-radius: 3px; min-height: 30px; }}
            QScrollBar::handle:vertical:hover {{ background: {c['scrollbar_hover']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._btn_groups.setStyleSheet(self._nav_style(c))
        self._btn_allapps.setStyleSheet(self._nav_style(c))
        self._add_group_btn.setStyleSheet(f"""
            QPushButton {{ background: {c['bg_active']}; color: #ffffff; border: none;
                padding: 7px 16px; border-radius: 8px; font-size: 12px; font-weight: 700; }}
            QPushButton:hover {{ background: #1683d8; }}
            QPushButton:pressed {{ background: #005a9e; }}
        """)

        self._manage_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none;
                color: {c['text_muted']}; border-radius: 8px; font-size: 14px; }}
            QPushButton:hover {{ background-color: {c['bg_hover']}; color: {c['text']}; }}
        """)
        self._hide_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none;
                color: {c['text_danger']}; padding: 7px 18px; border-radius: 8px; font-size: 12px; }}
            QPushButton:hover {{ background-color: {c['danger_bg']}; color: {c['text_danger']}; }}
        """)

        self._rebuild_groups()
        self.allapps_view.apply_theme(c)
        self.groups_list.apply_theme(c)

    @staticmethod
    def _nav_style(c: dict) -> str:
        return f"""
            QPushButton {{
                background: transparent; border: none; color: {c['text_muted']};
                padding: 7px 18px; border-radius: 8px; font-size: 12px; font-weight: 500;
            }}
            QPushButton:hover {{ background-color: {c['bg_hover']}; color: {c['text']}; }}
            QPushButton:checked {{ background-color: {c['bg_active']}; color: #fff; }}
        """

    def _rebuild_groups(self):
        self.groups_list.clear()
        self.groups_list.setSpacing(8)
        for i, gd in enumerate(self.config.groups):
            gw = GroupWidget(i, gd)
            n = len(gd.get("apps", []))
            h = max(110, 72 + ((n - 1) // 7 + 1) * 82)
            gw.setFixedHeight(h)
            item = QListWidgetItem()
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
            item.setSizeHint(QSize(0, h))
            self.groups_list.addItem(item)
            self.groups_list.setItemWidget(item, gw)

    # ── page switching ──

    def _show_page(self, page: int):
        self._btn_groups.setChecked(page == self.PAGE_GROUPS)
        self._btn_allapps.setChecked(page == self.PAGE_ALLAPPS)
        self.search_input.clear()
        self.content_stack.setCurrentIndex(page)
        if page == self.PAGE_ALLAPPS:
            self.allapps_view.refresh()

    # ── window dragging ──

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and event.position().y() < 60:
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() == Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None

    # ── drag & drop ──

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".lnk"):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event: QDropEvent):
        files = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".lnk"):
                files.append(path)
        if files:
            self._handle_dropped_files(files)

    def _handle_dropped_files(self, paths: list[str]):
        apps = []
        for p in paths:
            app = parse_lnk_file(p)
            if app:
                apps.append(app)
        if not apps:
            QMessageBox.information(
                self, "Drop", "No valid shortcut files found."
            )
            return

        if not self.config.groups:
            reply = QMessageBox.question(
                self, "Drop Shortcut",
                f"Parsed {len(apps)} shortcut(s). No groups exist yet.\n"
                'Create a new group "Dropped Apps" and add them?',
                QMessageBox.Yes | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Yes:
                self.config.add_group("Dropped Apps", apps)
                self._load_groups()
            return

        c = theme_module.current()
        dlg = QDialog(self)
        dlg.setWindowTitle("Add to Group")
        dlg.setMinimumWidth(320)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {c['bg_widget']}; color: {c['text']}; border-radius: 8px; }}
            QLabel {{ background: transparent; }}
        """)
        dlg_layout = QVBoxLayout(dlg)

        dlg_layout.addWidget(QLabel(f"{len(apps)} shortcut(s) dropped. Add to which group?"))

        combo = QComboBox()
        combo.setStyleSheet(f"""
            QComboBox {{ background: {c['bg_search']}; color: {c['text']}; border: 1px solid {c['border_light']};
                padding: 6px 10px; border-radius: 6px; }}
            QComboBox::drop-down {{ border: none; padding-right: 4px; }}
            QComboBox QAbstractItemView {{ background: {c['bg_widget']}; color: {c['text']};
                selection-background-color: {c['bg_active']}; selection-color: #fff; }}
        """)
        for g in self.config.groups:
            combo.addItem(g["name"])
        combo.addItem("＋ New group...")
        combo.setCurrentIndex(0)
        dlg_layout.addWidget(combo)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.setStyleSheet(f"""
            QPushButton {{ padding: 6px 24px; background: {c['bg_hover']}; color: {c['text']};
                border: none; border-radius: 6px; font-weight: 500; }}
            QPushButton:hover {{ background: {c['border_light']}; }}
            QPushButton[text="Cancel"] {{ color: {c['text_muted']}; }}
        """)
        dlg_layout.addWidget(btns)

        result = {"ok": False, "group_name": None}

        def on_accept():
            result["ok"] = True
            if combo.currentIndex() == combo.count() - 1:
                name = self._input_dialog("New Group", "Group name:")
                if name:
                    result["group_name"] = name
                    dlg.accept()
                else:
                    result["ok"] = False
            else:
                result["group_name"] = combo.currentText()
                dlg.accept()

        btns.accepted.connect(on_accept)
        btns.rejected.connect(dlg.reject)

        dlg.exec()

        if result["ok"] and result["group_name"]:
            name = result["group_name"]
            found = None
            for i, g in enumerate(self.config.groups):
                if g["name"] == name:
                    found = i
                    break
            if found is not None:
                for app in apps:
                    self.config.add_app_to_group(found, app)
            else:
                self.config.add_group(name, apps)
            self._load_groups()

    # ── search ──

    def _on_search_changed(self, text: str):
        if text.strip():
            self._search_timer.start(200)
            self.content_stack.setCurrentIndex(self.PAGE_SEARCH)
        else:
            self.content_stack.setCurrentIndex(self.PAGE_GROUPS)
            self.results_list.clear()

    def _perform_search(self):
        query = self.search_input.text().strip()
        if not query:
            return
        results = self.scanner.search(query)
        self.results_list.clear()
        for app in results:
            item = QListWidgetItem()
            item.setIcon(_get_app_icon(app))
            item.setText(f"{app['name']}\n{app.get('target', '')}")
            item.setData(Qt.UserRole, app)
            item.setSizeHint(QSize(0, 48))
            self.results_list.addItem(item)

    def _on_search_enter(self):
        item = self.results_list.currentItem()
        if item:
            self._launch_result(item)

    def _launch_result(self, item: QListWidgetItem):
        app = item.data(Qt.UserRole)
        if app:
            launch_app(app)
            self.hide()

    def _search_context_menu(self, pos):
        item = self.results_list.itemAt(pos)
        if not item:
            return
        app = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet(_menu_style())
        menu.addAction("Launch").triggered.connect(
            lambda: (launch_app(app), self.hide())
        )
        menu.addSeparator()
        if self.config.groups:
            sub = menu.addMenu("Add to Group")
            for i, g in enumerate(self.config.groups):
                sub.addAction(g["name"]).triggered.connect(
                    lambda checked, idx=i: self._add_to_group(idx, app)
                )
        menu.exec(self.results_list.mapToGlobal(pos))

    # ── groups ──

    def _load_groups(self):
        self._rebuild_groups()

    def _on_groups_reordered(self):
        new_order = []
        for i in range(self.groups_list.count()):
            w = self.groups_list.itemWidget(self.groups_list.item(i))
            if hasattr(w, "group_data"):
                new_order.append(w.group_data)
                w.group_index = i
        self.config.groups = new_order
        self.config.save()

    def _add_group_dialog(self):
        name = self._input_dialog("New Group", "Group name:")
        if name:
            self.config.add_group(name)
            self._load_groups()

    def _remove_group(self, index: int):
        name = (
            self.config.groups[index]["name"]
            if index < len(self.config.groups)
            else ""
        )
        c = theme_module.current()
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Remove Group")
        confirm.setText(f'Remove group "{name}"?')
        confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm.setStyleSheet(f"""
            QMessageBox {{ background: {c['bg_widget']}; color: {c['text']}; }}
            QPushButton {{ padding: 6px 24px; background: {c['bg_hover']}; color: {c['text']};
                border: none; border-radius: 6px; }}
            QPushButton:hover {{ background: {c['border_light']}; }}
        """)
        if confirm.exec() == QMessageBox.Yes:
            self.config.remove_group(index)
            self._load_groups()

    def _remove_app_from_group(self, group_index: int, app_index: int):
        self.config.remove_app_from_group(group_index, app_index)
        self._load_groups()

    def _add_to_group(self, group_index: int, app: dict):
        self.config.add_app_to_group(group_index, app)
        self._load_groups()

    # ── settings ──

    def _show_settings(self):
        c = theme_module.current()
        dlg = QDialog(self)
        dlg.setWindowTitle("WinLauncher Settings")
        dlg.setFixedSize(360, 260)

        fl = QFormLayout(dlg)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {c['bg_widget']}; color: {c['text']}; border-radius: 8px; }}
            QLabel {{ background: transparent; }}
            QCheckBox {{ background: transparent; spacing: 8px; }}
            QComboBox {{ background: {c['bg_search']}; color: {c['text']}; border: 1px solid {c['border_light']};
                padding: 4px 8px; border-radius: 4px; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{ background: {c['bg_widget']}; color: {c['text']};
                selection-background-color: {c['bg_active']}; }}
        """)

        # Auto start
        auto_ck = QCheckBox("Start with Windows")
        auto_ck.setChecked(self.config.get("auto_start", False))
        fl.addRow(auto_ck)

        # Theme selector
        theme_combo = QComboBox()
        theme_combo.addItems(["Dark", "Light", "Follow System"])
        current_theme = self.config.get("theme", "dark")
        theme_map = {"dark": 0, "light": 1, "auto": 2}
        theme_combo.setCurrentIndex(theme_map.get(current_theme, 0))
        fl.addRow("Theme:", theme_combo)

        # Hotkey capture
        hotkey_btn = QPushButton(self._hotkey_label())
        hotkey_btn.setFixedHeight(32)
        hotkey_btn.setToolTip("Click, then press the new hotkey combination")
        hotkey_btn.setStyleSheet(f"""
            QPushButton {{ background: {c['bg_search']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 4px; padding: 4px 12px;
                font-family: Consolas, monospace; }}
            QPushButton:hover {{ border-color: #60a5fa; }}
        """)
        fl.addRow("Hotkey:", hotkey_btn)

        new_hotkey = [None]

        def start_capture():
            hotkey_btn.setText("Press new hotkey...")
            hotkey_btn.setStyleSheet(f"""
                QPushButton {{ background: {c['bg_active']}; color: #fff;
                    border: 1px solid {c['bg_active']}; border-radius: 4px; padding: 4px 12px;
                    font-family: Consolas, monospace; }}
            """)
            hotkey_btn.grabKeyboard()

        def finish_capture(mod_flags, vk_name):
            new_hotkey[0] = (mod_flags, vk_name)
            hotkey_btn.setText("+".join(
                [m for m, f in MOD_MAP.items() if mod_flags & f] + [vk_name]
            ))
            hotkey_btn.setStyleSheet(f"""
                QPushButton {{ background: {c['bg_search']}; color: {c['text']};
                    border: 1px solid {c['border']}; border-radius: 4px; padding: 4px 12px;
                    font-family: Consolas, monospace; }}
                QPushButton:hover {{ border-color: #60a5fa; }}
            """)
            hotkey_btn.releaseKeyboard()

        def on_hotkey_key(e):
            mods = 0
            if e.modifiers() & Qt.ControlModifier:
                mods |= MOD_CONTROL
            if e.modifiers() & Qt.AltModifier:
                mods |= MOD_ALT
            if e.modifiers() & Qt.ShiftModifier:
                mods |= MOD_SHIFT
            if e.modifiers() & Qt.MetaModifier:
                mods |= MOD_WIN
            key = e.key()
            vk_name = None
            if key in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta):
                return
            for name, code in VK_MAP.items():
                if code == key:
                    vk_name = name
                    break
            if vk_name is None:
                key_text = e.text()
                if key_text and key_text.upper() in VK_MAP:
                    vk_name = key_text.upper()
            if vk_name is None:
                return
            finish_capture(mods, vk_name)

        hotkey_btn.clicked.connect(start_capture)
        hotkey_btn.keyPressEvent = lambda e: on_hotkey_key(e)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.setStyleSheet(f"""
            QPushButton {{ padding: 6px 24px; background: {c['bg_hover']}; color: {c['text']};
                border: none; border-radius: 6px; font-weight: 500; }}
            QPushButton:hover {{ background: {c['border']}; }}
            QPushButton[text="OK"] {{ background: {c['bg_active']}; color: #fff; }}
            QPushButton[text="OK"]:hover {{ background: #106ebe; }}
        """)

        hotkey_result = [None]

        def on_accept():
            theme_idx = theme_combo.currentIndex()
            theme_rev = {0: "dark", 1: "light", 2: "auto"}
            new_theme = theme_rev[theme_idx]
            self.config.set("theme", new_theme)
            theme_module.set_setting(new_theme)

            if new_hotkey[0] is not None:
                mods, vk_name = new_hotkey[0]
                mod_list = [m for m, f in MOD_MAP.items() if mods & f]
                self.config.set("hotkey_modifiers", mod_list)
                self.config.set("hotkey_key", vk_name)
                self._unregister_hotkey()
                self._register_hotkey()

            self.config.set_auto_start(auto_ck.isChecked())
            self._update_auto_start(auto_ck.isChecked())
            self._apply_theme()
            dlg.accept()

        btns.accepted.connect(on_accept)
        btns.rejected.connect(dlg.reject)
        fl.addRow(btns)

        dlg.exec()

    def _input_dialog(self, title: str, label: str, text: str = "") -> str | None:
        c = theme_module.current()
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setFixedSize(320, 140)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {c['bg_widget']}; color: {c['text']}; border-radius: 8px; }}
            QLabel {{ background: transparent; font-size: 13px; }}
            QLineEdit {{ background: {c['bg_search']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 6px; padding: 8px 12px;
                font-size: 13px; }}
            QLineEdit:focus {{ border-color: {c['bg_active']}; }}
        """)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(label))
        inp = QLineEdit()
        inp.setText(text)
        inp.selectAll()
        layout.addWidget(inp)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.setStyleSheet(f"""
            QPushButton {{ padding: 6px 24px; background: {c['bg_hover']}; color: {c['text']};
                border: none; border-radius: 6px; font-weight: 500; }}
            QPushButton:hover {{ background: {c['border_light']}; }}
            QPushButton[text="OK"] {{ background: {c['bg_active']}; color: #fff; }}
        """)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        inp.returnPressed.connect(dlg.accept)
        if dlg.exec() == QDialog.Accepted and inp.text().strip():
            return inp.text().strip()
        return None

    @staticmethod
    def _update_auto_start(enabled: bool):
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
            )
            if enabled:
                exe = sys.executable
                winreg.SetValueEx(key, "WinLauncher", 0, winreg.REG_SZ, f'"{exe}"')
            else:
                try:
                    winreg.DeleteValue(key, "WinLauncher")
                except OSError:
                    pass
            winreg.CloseKey(key)
        except Exception:
            pass

    # ── hotkey ──

    def _parse_hotkey(self) -> tuple[int, int] | None:
        mods = self.config.get("hotkey_modifiers", ["Ctrl", "Alt"])
        key = self.config.get("hotkey_key", "Space")
        mod_flags = 0
        for m in mods:
            mod_flags |= MOD_MAP.get(m, 0)
        vk = VK_MAP.get(key)
        if vk is None:
            return None
        return mod_flags, vk

    def _register_hotkey(self):
        try:
            hwnd = int(self.winId())
            parsed = self._parse_hotkey()
            if parsed is None:
                return
            mod_flags, vk = parsed
            registered = ctypes.windll.user32.RegisterHotKey(hwnd, 1, mod_flags, vk)
            if not registered:
                logger.warning("Global hotkey is already in use: %s", self._hotkey_label())
            return bool(registered)
        except (AttributeError, OSError, ValueError):
            logger.exception("Unable to register global hotkey")
            return False

    def _unregister_hotkey(self):
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.UnregisterHotKey(hwnd, 1)
        except Exception:
            pass

    def _hotkey_label(self) -> str:
        mods = self.config.get("hotkey_modifiers", ["Ctrl", "Alt"])
        key = self.config.get("hotkey_key", "Space")
        return "+".join(mods + [key])

    def nativeEvent(self, event_type, message):
        if event_type == "windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            if msg.message == WM_HOTKEY:
                self._toggle_visibility()
                return True, 0
        return super().nativeEvent(event_type, message)

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - self.width()) // 2
            y = screen.height() // 4
            self.move(x, y)
            self.show()
            self.activateWindow()
            self.raise_()
            self.search_input.setFocus()
            self.search_input.selectAll()

    def closeEvent(self, event: QCloseEvent):
        event.ignore()
        self.hide()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.hide()
        super().keyPressEvent(event)


# ── entry ─────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("WinLauncher")
    app.setOrganizationName("WinLauncher")

    font = QFont("Microsoft YaHei", 9)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    config_dir = Path.home() / ".winlauncher"
    config_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=config_dir / "winlauncher.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    cfg = ConfigManager(config_dir)

    # init theme from config
    theme_module.set_setting(cfg.get("theme", "dark"))

    scanner = StartMenuScanner()
    scanner.scan()

    window = LauncherWindow(cfg, scanner)

    exe_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    ico_file = exe_dir / "icon.ico"
    tray_icon = QIcon(str(ico_file)) if ico_file.exists() else QIcon(_make_tray_pixmap())
    app.setWindowIcon(tray_icon)
    window.setWindowIcon(tray_icon)
    tray = QSystemTrayIcon(tray_icon)
    hotkey_label = window._hotkey_label()
    tray.setToolTip(f"WinLauncher ({hotkey_label})")

    menu = QMenu()
    menu.setStyleSheet(_menu_style())
    menu.addAction(f"Show / Hide  ({hotkey_label})").triggered.connect(
        window._toggle_visibility
    )
    menu.addSeparator()
    menu.addAction("Quit").triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: window._toggle_visibility()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()

    window.hide()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
