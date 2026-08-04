"""Maya Qt debug 工具：中键点击任意 Qt 控件，查看层级与详情（全 Maya 生效）。

- 全局事件过滤器：仅中键点击触发（鼠标移动不产生输出）；
- 左侧 QTreeView：点击控件的父链层级（类型 / objectName），选中行联动右侧详情；
- 右侧 QListView：选中控件的常见 Qt 设置与 layout；
- 顶部工具栏：监控开关、清空、隐藏/显示/启用/禁用选中控件。
"""

from __future__ import annotations

import re
import time

from shiboken2 import isValid, wrapInstance

from PySide2 import QtCore, QtGui, QtWidgets

import maya.OpenMayaUI as omui

_WINDOW = None

_DEBOUNCE_SECONDS = 0.3

_WIDGET_ROLE = QtCore.Qt.UserRole


def _maya_main_window() -> QtWidgets.QWidget:
    """返回 Maya 主窗口的 Qt 包装。"""
    main_window_ptr = omui.MQtUtil.mainWindow()
    if main_window_ptr is None:
        raise RuntimeError("Maya main window is not available.")
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)


class _MiddleClickInspector(QtCore.QObject):
    """全局事件过滤器：中键点击 Maya 任意控件时发出 clicked 信号。

    仅监听 MouseButtonPress + 中键；其余事件一律不拦截。
    一次物理点击可能传播出多个 MouseButtonPress 事件，用时间去抖。
    """

    clicked = QtCore.Signal(object)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._last_trigger: float = 0.0

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if (
            event.type() == QtCore.QEvent.MouseButtonPress
            and event.button() == QtCore.Qt.MiddleButton
        ):
            now = time.monotonic()
            if now - self._last_trigger < _DEBOUNCE_SECONDS:
                return False
            self._last_trigger = now
            widget = QtWidgets.QApplication.widgetAt(QtGui.QCursor.pos())
            if widget is not None:
                self.clicked.emit(widget)
        return False  # 不拦截事件，保持原行为


def qt_state_pairs(widget: QtWidgets.QWidget) -> list[tuple[str, str]]:
    """生成控件常见 Qt 设置的 (key, value) 对；控件已销毁时返回占位对。"""
    if not isValid(widget):
        return [("<widget>", "deleted")]
    geom = widget.geometry()
    policy = widget.sizePolicy()
    min_size = widget.minimumSize()
    max_size = widget.maximumSize()
    own_layout = widget.layout()
    layout_desc = (
        "none"
        if own_layout is None
        else f"{type(own_layout).__name__}({own_layout.count()})"
    )
    entries: list[tuple[str, str]] = [
        ("layout", layout_desc),
        ("className", type(widget).__name__),
        ("objectName", widget.objectName() or ""),
        ("visible", str(widget.isVisible())),
        ("enabled", str(widget.isEnabled())),
        ("window", str(widget.isWindow())),
        ("geometry", f"({geom.x()}, {geom.y()}, {geom.width()}, {geom.height()})"),
        ("minimumSize", f"{min_size.width()}x{min_size.height()}"),
        ("maximumSize", f"{max_size.width()}x{max_size.height()}"),
        ("sizePolicy", f"{policy.horizontalPolicy()}, {policy.verticalPolicy()}"),
        ("focusPolicy", str(widget.focusPolicy())),
        ("acceptDrops", str(widget.acceptDrops())),
        ("toolTip", widget.toolTip() or ""),
    ]
    if widget.isWindow():
        entries.append(("windowTitle", widget.windowTitle()))
    entries.extend(_asset_pairs(widget))
    return entries


def _widget_pixmap(widget: QtWidgets.QWidget) -> QtGui.QPixmap | None:
    """返回控件的位图（QLabel 等）；无位图时返回 None。"""
    getter = getattr(widget, "pixmap", None)
    if not callable(getter):
        return None
    pixmap = getter()
    if pixmap is None or pixmap.isNull():
        return None
    return pixmap


def _asset_pairs(widget: QtWidgets.QWidget) -> list[tuple[str, str]]:
    """检测控件携带的美术资源：图标、位图、样式表资源引用、窗口图标。"""
    icon_info = "none"
    icon_getter = getattr(widget, "icon", None)
    if callable(icon_getter):
        icon = icon_getter()
        if not icon.isNull():
            # PySide2 中 QIcon.name() 仅对 theme 图标有效，资源图标返回空字符串
            icon_info = f"{icon.name() or '<name-unavailable>'} {icon.availableSizes()}"

    pixmap_info = "none"
    pixmap = _widget_pixmap(widget)
    if pixmap is not None:
        dpr = pixmap.devicePixelRatio()
        pixmap_info = (
            f"{pixmap.width()}x{pixmap.height()} "
            f"dpr={dpr} "
            f"logical={int(pixmap.width() / dpr)}x{int(pixmap.height() / dpr)} "
            f"depth={pixmap.depth()} alpha={pixmap.hasAlphaChannel()}"
        )

    stylesheet = widget.styleSheet()
    if not stylesheet:
        style_info = "none"
    else:
        urls = re.findall(r"url\(([^)]+)\)", stylesheet)
        style_info = f"urls={urls}" if urls else f"len={len(stylesheet)}"

    window_icon = widget.windowIcon()
    window_icon_info = (
        "none"
        if window_icon.isNull()
        else (window_icon.name() or "<name-unavailable>")
    )

    return [
        ("icon", icon_info),
        ("pixmap", pixmap_info),
        ("styleSheet", style_info),
        ("windowIcon", window_icon_info),
    ]


class _FocusOverlay(QtWidgets.QWidget):
    """4px 橙色描边覆盖层：标记当前焦点控件。

    独立顶层透明窗口，不接收鼠标事件（不干扰 Maya 交互）；
    QTimer 轮询目标控件位置，布局变动时自动跟随。
    """

    _BORDER = 4
    _MARGIN = _BORDER // 2  # 边框线宽一半，向窗口内收

    def __init__(self) -> None:
        super().__init__(
            None,
            QtCore.Qt.Tool
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self._target: QtWidgets.QWidget | None = None
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._sync)
        self._timer.start()
        self.hide()

    def set_target(self, widget: QtWidgets.QWidget | None) -> None:
        self._target = widget
        self._sync()

    def _sync(self) -> None:
        target = self._target
        if target is None or not isValid(target) or not target.isVisible():
            self.hide()
            return
        rect = target.rect()
        rect.moveTopLeft(target.mapToGlobal(rect.topLeft()))
        margin = self._MARGIN
        self.setGeometry(rect.adjusted(-margin, -margin, margin, margin))
        if not self.isVisible():
            self.show()
            self.raise_()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 165, 0), self._BORDER))
        inset = self._BORDER // 2
        painter.drawRect(self.rect().adjusted(inset, inset, -inset, -inset))


class _RatioTree(QtWidgets.QTreeView):
    """按固定比例保持两列列宽的树（左:右 = ratio）。

    在自身 resizeEvent 中按视口宽度重设列宽，覆盖窗口缩放与 splitter 拖动两种情况。
    """

    def __init__(
        self,
        ratio: tuple[int, int] = (3, 1),
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ratio = ratio

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        header = self.header()
        total = self.viewport().width()
        if total > 0:
            left, right = self._ratio
            header.resizeSection(0, int(total * left / (left + right)))
            header.resizeSection(1, int(total * right / (left + right)))


class QtDebugWindow(QtWidgets.QDialog):
    """调试窗口：树形层级 + 详情面板 + 控件操作按钮。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Qt Debug Tool")
        self.resize(760, 420)

        self._inspector = _MiddleClickInspector(self)
        self._inspector.clicked.connect(self._on_widget_clicked)
        self._selected_widget: QtWidgets.QWidget | None = None
        # 调试操作还原记录：widget -> {属性名: 首次操作前的值}，关闭窗口时还原
        self._restore_ops: dict[QtWidgets.QWidget, dict[str, object]] = {}
        # 焦点控件橙色描边
        self._overlay = _FocusOverlay()

        self._build_ui()

    def _build_ui(self) -> None:
        self._monitor_button = QtWidgets.QPushButton("Start Monitor")
        self._monitor_button.setCheckable(True)
        self._monitor_button.toggled.connect(self._toggle_monitor)
        # 默认关闭监控，用户点击后开启

        self._visibility_button = QtWidgets.QPushButton("Hide")
        self._visibility_button.clicked.connect(self._toggle_visibility)
        self._enabled_button = QtWidgets.QPushButton("Disable")
        self._enabled_button.clicked.connect(self._toggle_enabled)
        clear_button = QtWidgets.QPushButton("Clear")
        clear_button.clicked.connect(self._clear)

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.addWidget(self._monitor_button)
        toolbar.addWidget(self._visibility_button)
        toolbar.addWidget(self._enabled_button)
        toolbar.addStretch()
        toolbar.addWidget(clear_button)

        self._tree_model = QtGui.QStandardItemModel(0, 2, self)
        self._tree_model.setHeaderData(0, QtCore.Qt.Horizontal, "Type")
        self._tree_model.setHeaderData(1, QtCore.Qt.Horizontal, "Object Name")
        self._tree = _RatioTree((3, 1))
        self._tree.setModel(self._tree_model)
        self._tree.setIndentation(15)
        self._tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self._tree.selectionModel().currentChanged.connect(self._on_tree_selection)
        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)

        self._detail_model = QtGui.QStandardItemModel(0, 2, self)
        self._detail_model.setHeaderData(0, QtCore.Qt.Horizontal, "Key")
        self._detail_model.setHeaderData(1, QtCore.Qt.Horizontal, "Value")
        self._detail_tree = _RatioTree((1, 1))
        self._detail_tree.setModel(self._detail_model)
        self._detail_tree.setRootIsDecorated(False)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._detail_tree)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(splitter)

    def _toggle_monitor(self, enabled: bool) -> None:
        app = QtWidgets.QApplication.instance()
        if enabled:
            app.installEventFilter(self._inspector)
            self._monitor_button.setText("Stop Monitor")
        else:
            app.removeEventFilter(self._inspector)
            self._monitor_button.setText("Start Monitor")

    def _on_widget_clicked(self, widget: QtWidgets.QWidget) -> None:
        """中键命中：以顶层窗口为根构建层级树，选中点击控件（叶子）。"""
        chain = []
        current = widget
        while current is not None:
            if not isValid(current):
                break
            chain.append(current)
            current = current.parentWidget()

        self._tree_model.removeRows(0, self._tree_model.rowCount())
        if not chain:
            return

        # chain: 点击控件 → 顶层窗口；rows: 顶层窗口 → 点击控件
        rows = []
        for w in reversed(chain):
            type_item = QtGui.QStandardItem(type(w).__name__)
            name_item = QtGui.QStandardItem(w.objectName() or "")
            for item in (type_item, name_item):
                item.setData(w, _WIDGET_ROLE)
            rows.append([type_item, name_item])

        self._tree_model.appendRow(rows[0])
        for parent_row, child_row in zip(rows, rows[1:]):
            parent_row[0].appendRow(child_row)

        self._tree.expandAll()
        self._tree.setCurrentIndex(rows[-1][0].index())  # 叶子 = 点击控件
        self._overlay.set_target(widget)

    def _on_tree_selection(
        self, current: QtCore.QModelIndex, previous: QtCore.QModelIndex
    ) -> None:
        if not current.isValid():
            return
        widget = current.data(_WIDGET_ROLE)
        if widget is None:
            return
        self._selected_widget = widget
        self._overlay.set_target(widget)
        self._detail_model.removeRows(0, self._detail_model.rowCount())
        pixmap = _widget_pixmap(widget)
        for key, value in qt_state_pairs(widget):
            key_item = QtGui.QStandardItem(key)
            value_item = QtGui.QStandardItem(value)
            if key == "pixmap" and pixmap is not None:
                dpr = pixmap.devicePixelRatio()
                thumb = pixmap.scaled(
                    32 * dpr,
                    32 * dpr,
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                thumb.setDevicePixelRatio(dpr)
                value_item.setIcon(QtGui.QIcon(thumb))
            self._detail_model.appendRow([key_item, value_item])
        self._refresh_action_buttons()

    def _record_before(self, widget: QtWidgets.QWidget, attr: str, value: object) -> None:
        """记录某属性首次被操作前的值，用于关闭窗口时还原。"""
        ops = self._restore_ops.setdefault(widget, {})
        if attr not in ops:
            ops[attr] = value

    def _toggle_visibility(self) -> None:
        widget = self._selected_widget
        if widget is None or not isValid(widget):
            return
        self._record_before(widget, "visible", widget.isVisible())
        widget.setVisible(not widget.isVisible())
        self._refresh_action_buttons()

    def _toggle_enabled(self) -> None:
        widget = self._selected_widget
        if widget is None or not isValid(widget):
            return
        self._record_before(widget, "enabled", widget.isEnabled())
        widget.setEnabled(not widget.isEnabled())
        self._refresh_action_buttons()

    def _refresh_action_buttons(self) -> None:
        """按钮文字随选中控件状态切换：可见→Hide / 隐藏→Show，启用→Disable / 禁用→Enable。"""
        widget = self._selected_widget
        if widget is None or not isValid(widget):
            self._visibility_button.setText("Hide")
            self._enabled_button.setText("Disable")
            return
        self._visibility_button.setText("Show" if not widget.isVisible() else "Hide")
        self._enabled_button.setText("Enable" if not widget.isEnabled() else "Disable")

    def _restore_operations(self) -> None:
        """还原调试期间修改过的控件属性（visible/enabled），并清空记录。"""
        for widget, attrs in self._restore_ops.items():
            if not isValid(widget):
                continue
            if "visible" in attrs:
                widget.setVisible(bool(attrs["visible"]))
            if "enabled" in attrs:
                widget.setEnabled(bool(attrs["enabled"]))
        self._restore_ops.clear()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """关闭窗口：还原被修改的控件、移除事件过滤器、复位监控按钮。"""
        app = QtWidgets.QApplication.instance()
        app.removeEventFilter(self._inspector)
        self._monitor_button.setChecked(False)  # 触发 toggled，复位按钮文字
        self._overlay.set_target(None)
        self._restore_operations()
        super().closeEvent(event)

    def _clear(self) -> None:
        """清空树/详情/选中，并放弃操作还原记录（Clear 后关窗不再还原）。"""
        self._tree_model.removeRows(0, self._tree_model.rowCount())
        self._detail_model.removeRows(0, self._detail_model.rowCount())
        self._selected_widget = None
        self._restore_ops.clear()
        self._overlay.set_target(None)
        self._refresh_action_buttons()


def get_selected_widget() -> QtWidgets.QWidget | None:
    """返回用户在层级树中最后选中的控件实例。

    返回 None 的情况：调试窗口未打开、尚未选择控件、或选中控件已被销毁。
    """
    if _WINDOW is None or not isValid(_WINDOW):
        return None
    widget = _WINDOW._selected_widget
    if widget is None or not isValid(widget):
        return None
    return widget


def show() -> QtDebugWindow:
    """显示调试窗口；重复调用复用单例并置前。"""
    global _WINDOW
    if _WINDOW is None or not isValid(_WINDOW):
        _WINDOW = QtDebugWindow(_maya_main_window())
    _WINDOW.show()
    _WINDOW.raise_()
    _WINDOW.activateWindow()
    return _WINDOW


if __name__ == "__main__":
    show()
