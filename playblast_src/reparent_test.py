"""测试：把 qt_debug 选中的 Maya 控件移入独立窗口，缩放控件与 pixmap/icon。

目的：观察 Maya 控件在不同显示尺寸下是否提供不同清晰度的美术资源。
"""

from __future__ import annotations

from shiboken2 import isValid, wrapInstance

from PySide2 import QtCore, QtGui, QtWidgets

import maya.OpenMayaUI as omui

import qt_debug

_WINDOW = None


def _maya_main_window() -> QtWidgets.QWidget:
    main_window_ptr = omui.MQtUtil.mainWindow()
    if main_window_ptr is None:
        raise RuntimeError("Maya main window is not available.")
    return wrapInstance(int(main_window_ptr), QtWidgets.QWidget)


class ReparentWindow(QtWidgets.QDialog):
    """容纳被移入控件的测试窗口。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Reparent Test")
        self.resize(640, 420)

        self._widget: QtWidgets.QWidget | None = None
        self._original_parent: QtWidgets.QWidget | None = None
        self._base_size: QtCore.QSize | None = None
        self._base_icon_size: QtCore.QSize | None = None
        self._base_pixmap: QtGui.QPixmap | None = None
        self._scale = 1.0

        move_button = QtWidgets.QPushButton("Move Selected")
        move_button.clicked.connect(move_selected_widget)
        enlarge_button = QtWidgets.QPushButton("Enlarge x2")
        enlarge_button.clicked.connect(lambda: self._scale_widget(2.0))
        shrink_button = QtWidgets.QPushButton("Shrink /2")
        shrink_button.clicked.connect(lambda: self._scale_widget(0.5))
        reset_button = QtWidgets.QPushButton("Reset")
        reset_button.clicked.connect(lambda: self._scale_widget(1.0))
        restore_button = QtWidgets.QPushButton("Restore to Maya")
        restore_button.clicked.connect(self._restore_widget)
        export_button = QtWidgets.QPushButton("Export PNG")
        # clicked 信号会传 checked(bool)，必须用 lambda 丢弃
        export_button.clicked.connect(lambda: self.export_png())

        self._info_label = QtWidgets.QLabel("no widget moved")
        self._host = QtWidgets.QWidget()
        # 用 palette 而非 styleSheet 设置背景：
        # styleSheet 会让子孙控件改走 QStyleSheetStyle 渲染路径，pixmap 绘制变模糊
        self._host.setAutoFillBackground(True)
        palette = self._host.palette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#2b2b2b"))
        self._host.setPalette(palette)

        toolbar = QtWidgets.QHBoxLayout()
        for button in (
            move_button,
            enlarge_button,
            shrink_button,
            reset_button,
            restore_button,
            export_button,
        ):
            toolbar.addWidget(button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(self._info_label)
        layout.addWidget(self._host, 1)

    def place_widget(self, widget: QtWidgets.QWidget) -> None:
        """把控件移入测试窗口，记录初始尺寸/icon/pixmap 作为缩放基准。"""
        self._restore_widget()
        self._widget = widget
        self._original_parent = widget.parentWidget()
        self._base_size = widget.size()
        self._base_icon_size = (
            widget.iconSize() if hasattr(widget, "iconSize") else None
        )
        self._base_pixmap = qt_debug._widget_pixmap(widget)
        widget.setParent(self._host)
        widget.move(12, 12)
        widget.show()
        self._info_label.setText(
            f"scale=1  widget={type(widget).__name__} "
            f"size={widget.width()}x{widget.height()}"
        )

    def _scale_widget(self, scale: float) -> None:
        widget = self._widget
        if widget is None or not isValid(widget):
            return
        self._scale = scale
        size = self._base_size
        widget.resize(int(size.width() * scale), int(size.height() * scale))
        if self._base_icon_size is not None and hasattr(widget, "setIconSize"):
            widget.setIconSize(
                QtCore.QSize(
                    int(self._base_icon_size.width() * scale),
                    int(self._base_icon_size.height() * scale),
                )
            )
        if self._base_pixmap is not None and hasattr(widget, "setPixmap"):
            if abs(scale - 1.0) < 1e-9:
                # 不缩放：直接放回原 pixmap，避免 scaled 重采样与丢 dpr
                widget.setPixmap(self._base_pixmap)
            else:
                # 按逻辑尺寸缩放并保留 dpr，保证高 DPI 下清晰
                dpr = self._base_pixmap.devicePixelRatio()
                scaled = self._base_pixmap.scaled(
                    int(self._base_pixmap.width() / dpr * scale * dpr),
                    int(self._base_pixmap.height() / dpr * scale * dpr),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                scaled.setDevicePixelRatio(dpr)
                widget.setPixmap(scaled)
        self._info_label.setText(
            f"scale={scale:g}  widget={type(widget).__name__} "
            f"size={widget.width()}x{widget.height()}"
        )

    def export_png(self, path: str | None = None) -> str | None:
        """导出当前控件的 pixmap/icon 为 PNG。

        Args:
            path: 保存路径；None 时弹出文件对话框。
        Returns:
            保存成功返回路径，取消或无资源返回 None。
        """
        widget = self._widget
        if widget is None or not isValid(widget):
            widget = qt_debug.get_selected_widget()
        if widget is None:
            print("no widget to export")
            return None

        pixmap = qt_debug._widget_pixmap(widget)
        if pixmap is None:
            icon_getter = getattr(widget, "icon", None)
            if callable(icon_getter):
                icon = icon_getter()
                if not icon.isNull():
                    sizes = icon.availableSizes()
                    if sizes:
                        pixmap = icon.pixmap(sizes[-1])  # 最大可用尺寸
                    else:
                        pixmap = icon.pixmap(64, 64)
        if pixmap is None:
            print(f"{type(widget).__name__} has no pixmap/icon asset")
            return None

        if path is None:
            default_name = f"{widget.objectName() or type(widget).__name__}.png"
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export PNG", default_name, "PNG (*.png)"
            )
            if not path:
                return None

        if not pixmap.save(path):
            print(f"failed to save: {path}")
            return None
        dpr = pixmap.devicePixelRatio()
        print(
            f"exported: {path} "
            f"{pixmap.width()}x{pixmap.height()} dpr={dpr} "
            f"logical={pixmap.width() / dpr}x{pixmap.height() / dpr}"
        )
        return path

    def _restore_widget(self) -> None:
        widget = self._widget
        if widget is not None and isValid(widget):
            # 无条件还原：原父级仍有效则回原父级，否则脱离 host 成为无父控件
            target = (
                self._original_parent
                if self._original_parent is not None and isValid(self._original_parent)
                else None
            )
            widget.setParent(target)
            if self._base_size is not None:
                widget.resize(self._base_size)
            widget.show()
        self._widget = None
        self._original_parent = None
        self._base_size = None
        self._base_icon_size = None
        self._base_pixmap = None
        self._info_label.setText("no widget moved")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._restore_widget()
        super().closeEvent(event)


def create_window() -> ReparentWindow:
    """创建/复用测试窗口（隐藏的旧窗口会重新显示并置前）。"""
    global _WINDOW
    if _WINDOW is None or not isValid(_WINDOW):
        _WINDOW = ReparentWindow(_maya_main_window())
    _WINDOW.show()
    _WINDOW.raise_()
    _WINDOW.activateWindow()
    return _WINDOW


def move_selected_widget() -> None:
    """把 qt_debug 最后选中的控件移入测试窗口。"""
    widget = qt_debug.get_selected_widget()
    if widget is None:
        print("No widget selected in qt_debug.")
        return
    create_window().place_widget(widget)


if __name__ == "__main__":
    create_window()
