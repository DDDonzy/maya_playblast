from __future__ import annotations

import maya.OpenMayaUI as omui
from shiboken2 import wrapInstance  # ty:ignore[unresolved-import]
from PySide2 import QtWidgets  # ty:ignore[unresolved-import]

from maya import cmds

TARGET_LAYOUT_NAME = "MainTimeSliderLayout"
MAX_PARENT_STEPS = 20


def _get_maya_control(name: str) -> QtWidgets.QWidget | None:
    """按 Maya 控件名取回其 Qt 控件；找不到返回 None。"""
    maya_control = omui.MQtUtil.findControl(name)  # ty:ignore[unresolved-attribute]
    if not maya_control:
        return None
    return wrapInstance(int(maya_control), QtWidgets.QWidget)


def _find_layout_from(widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
    """从给定控件向上查父级，直到名字 == TARGET_LAYOUT_NAME。

    超过 MAX_PARENT_STEPS 步或走到顶层还没找到都会 raise。
    """
    current = widget
    steps = 0
    while current is not None and current.objectName() != TARGET_LAYOUT_NAME:
        current = current.parent()
        steps += 1
        if steps > MAX_PARENT_STEPS:
            raise RuntimeError(f"Exceeded {MAX_PARENT_STEPS} parent steps while looking for '{TARGET_LAYOUT_NAME}' from '{widget.objectName() or widget}'.")
    if current is None:
        raise RuntimeError(f"Reached the top of the widget tree without finding '{TARGET_LAYOUT_NAME}' from '{widget.objectName() or widget}'.")
    return current


def attach(widget: QtWidgets.QWidget) -> list[QtWidgets.QWidget]:
    """把传入的 Qt 控件挂到 Maya timeSlider 的 MainTimeSliderLayout 旁边。

    Args:
        widget: 要插入的自定义 Qt 控件（建议先设好尺寸，如 setMinimumHeight）。

    Returns:
        创建的所有 host 控件列表（每个 timeControl 对应一个）。
    """
    time_controls = cmds.lsUI(type="timeControl") or []
    hosts = []

    for index, tc_name in enumerate(time_controls):
        time_control_widget = _get_maya_control(tc_name)
        if time_control_widget is None:
            continue

        widget.__keepSrc = []
        child_to_wrap = _find_layout_from(time_control_widget)
        target_parent = child_to_wrap.parent()
        widget.__keepSrc.append(child_to_wrap)
        widget.__keepSrc.append(target_parent)

        host = QtWidgets.QWidget(target_parent)
        host.setObjectName(f"MyCustomHamburgerBox_{index}")

        h_layout = QtWidgets.QHBoxLayout(host)
        h_layout.setContentsMargins(0, 0, 20, 0)

        h_layout.addWidget(child_to_wrap)  # 原来的 timeSlider 内容
        h_layout.addWidget(widget)  # 传入的自定义控件（替换原 my_new_btn）

        if target_parent.layout() is not None:
            target_parent.layout().addWidget(host)

        hosts.append(host)

    return hosts
