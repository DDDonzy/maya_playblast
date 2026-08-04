"""Maya timeSlider 旁的 Playblast 按钮。

左键点击触发 playblast；右键点击弹出输出选项菜单。
"""

from __future__ import annotations

from typing import Dict

from maya import cmds

import shiboken2  # ty:ignore[unresolved-import]
from PySide2 import QtCore, QtGui, QtWidgets  # ty:ignore[unresolved-import]

from pb_src import playblast
from pb_src.config import (
    CODEC_ENCODERS,
    CONTAINER_CODECS,
    DEFAULT_CODEC,
    DEFAULT_CONTAINER,
    DEFAULT_FRAME_FORMAT,
    DEFAULT_QUALITY,
    DEFAULT_RESOLUTION,
    DEFAULT_SCALE,
    FRAME_FORMATS,
    QUALITY_CRF,
    RESOLUTION_CHOICES,
    SCALES,
    _AUTO_PLAY_OPTION,
    _CODEC_OPTION,
    _CONTAINER_OPTION,
    _FRAME_FORMAT_OPTION,
    _PRESET_OPTION,
    _QUALITY_OPTION,
    _RESOLUTION_OPTION,
    _SCALE_OPTION,
    _SOUND_OPTION,
)
from pb_src.ui import attach_timeSlider, presets
from pb_src.ui import qrc_res_playblast  # noqa: F401 注册 Qt 资源 :/res_playblast_play.svg

BUTTON_NAME = "playblastButton"
MENU_NAME = "playblastOptionsMenu"
ICON_RESOURCE = ":/res_playblast_play.svg"
ICON_RESOURCE_HOVER = ":/res_playblast_play_hover.svg"

_FRAME_FORMAT_LABELS = (("jpg", "JPEG"), ("png", "PNG"))
_CONTAINER_LABELS = (("mp4", "MP4"), ("mkv", "MKV"), ("mov", "MOV"))
_CODEC_LABELS = (
    ("h264", "H.264 / AVC"),
    ("hevc", "H.265 / HEVC"),
    ("av1", "AV1"),
)
_RESOLUTION_LABELS = (
    ("1280x720", "1280 × 720"),
    ("1920x1080", "1920 × 1080"),
    ("2560x1440", "2560 × 1440"),
    ("3840x2160", "3840 × 2160"),
    ("4096x2160", "4096 × 2160"),
    ("view", "From View"),
    ("render", "From Render Settings"),
)
_SCALE_LABELS = (("25", "25%"), ("50", "50%"), ("75", "75%"), ("100", "100%"))
_QUALITY_LABELS = (("high", "High"), ("medium", "Medium"), ("low", "Low"))

_BUTTON = None
_DEBUG_WINDOW = None

# 输出选项集合（optionVar 记忆 / preset 文件共用）
Settings = Dict[str, object]


# ---- optionVar 读写 ----

def _read_choice(option: str, allowed: tuple[str, ...], default: str) -> str:
    if cmds.optionVar(exists=option):
        value = str(cmds.optionVar(  # ty:ignore[no-matching-overload]
            query=option
        )).lower()
        if value in allowed:
            return value

    cmds.optionVar(stringValue=(option, default))
    return default


def _set_choice(option: str, value: str) -> None:
    cmds.optionVar(stringValue=(option, value))


def _read_flag(option: str, default: bool) -> bool:
    if not cmds.optionVar(exists=option):
        cmds.optionVar(intValue=(option, int(default)))
    return bool(cmds.optionVar(  # ty:ignore[no-matching-overload]
        query=option
    ))


def _read_video_settings() -> tuple[str, str]:
    container = _read_choice(_CONTAINER_OPTION, tuple(CONTAINER_CODECS), DEFAULT_CONTAINER)
    codec = _read_choice(_CODEC_OPTION, tuple(CODEC_ENCODERS), DEFAULT_CODEC)
    if codec not in CONTAINER_CODECS[container]:
        codec = DEFAULT_CODEC
        _set_choice(_CODEC_OPTION, codec)
    return (container, codec)


def _default_settings() -> Settings:
    return {
        "frame_format": DEFAULT_FRAME_FORMAT,
        "container": DEFAULT_CONTAINER,
        "codec": DEFAULT_CODEC,
        "resolution": DEFAULT_RESOLUTION,
        "scale": DEFAULT_SCALE,
        "quality": DEFAULT_QUALITY,
        "auto_play": True,
        "sound": True,
    }


def _read_settings() -> Settings:
    frame_format = _read_choice(_FRAME_FORMAT_OPTION, FRAME_FORMATS, DEFAULT_FRAME_FORMAT)
    container, codec = _read_video_settings()
    resolution = _read_choice(_RESOLUTION_OPTION, RESOLUTION_CHOICES, DEFAULT_RESOLUTION)
    scale = int(_read_choice(_SCALE_OPTION, tuple(str(value) for value in SCALES), str(DEFAULT_SCALE)))
    quality = _read_choice(_QUALITY_OPTION, tuple(QUALITY_CRF), DEFAULT_QUALITY)
    return {
        "frame_format": frame_format,
        "container": container,
        "codec": codec,
        "resolution": resolution,
        "scale": scale,
        "quality": quality,
        "auto_play": _read_flag(_AUTO_PLAY_OPTION, True),
        "sound": _read_flag(_SOUND_OPTION, True),
    }


def _write_settings(settings: Settings) -> None:
    _set_choice(_FRAME_FORMAT_OPTION, str(settings["frame_format"]))
    _set_choice(_CONTAINER_OPTION, str(settings["container"]))
    _set_choice(_CODEC_OPTION, str(settings["codec"]))
    _set_choice(_RESOLUTION_OPTION, str(settings["resolution"]))
    _set_choice(_SCALE_OPTION, str(settings["scale"]))
    _set_choice(_QUALITY_OPTION, str(settings["quality"]))
    cmds.optionVar(intValue=(_AUTO_PLAY_OPTION, int(bool(settings["auto_play"]))))
    cmds.optionVar(intValue=(_SOUND_OPTION, int(bool(settings["sound"]))))


def _run_playblast() -> None:
    settings = _read_settings()
    playblast.playblast(
        frame_format=str(settings["frame_format"]),
        container=str(settings["container"]),
        codec=str(settings["codec"]),
        resolution=str(settings["resolution"]),
        scale=int(str(settings["scale"])),
        quality=str(settings["quality"]),
        auto_play=bool(settings["auto_play"]),
        sound=bool(settings["sound"]),
    )


# ---- 右键菜单构建 ----

def _add_choice_actions(
    menu: QtWidgets.QMenu,
    labels: tuple[tuple[str, str], ...],
    selected: str,
    group: QtWidgets.QActionGroup | None = None,
) -> dict[str, QtWidgets.QAction]:
    if group is None:
        group = QtWidgets.QActionGroup(menu)
        group.setExclusive(True)
    actions = {}
    for value, label in labels:
        action = menu.addAction(label)
        action.setCheckable(True)
        action.setData(value)
        action.setChecked(value == selected)
        group.addAction(action)
        actions[value] = action
    return actions


class _StayOpenMenu(QtWidgets.QMenu):
    """点击菜单内选项不关闭菜单，可连续修改参数。

    - 点击普通选项：触发该选项（执行修改）但保持菜单打开；
    - 点击 _close_action（Playblast 项）或菜单外：正常关闭；
    - 点击子菜单项（Preset）：展开并保持打开。
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._close_action: QtWidgets.QAction | None = None

    def mouseReleaseEvent(self, event) -> None:
        action = self.actionAt(event.pos())
        if action is None:
            event.accept()
            return
        if action.menu() is not None:
            # 子菜单：交给默认处理展开
            super().mouseReleaseEvent(event)
            return
        if action is not self._close_action:
            action.trigger()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _OptionsMenuBuilder:
    """构建右键选项菜单；管理各选项状态与 preset 联动。"""

    def __init__(self, button: QtWidgets.QWidget) -> None:
        self._button = button
        self._menu = _StayOpenMenu(button)
        self._menu.setObjectName(MENU_NAME)
        self._flag_actions: dict[str, QtWidgets.QAction] = {}
        self._choice_actions: dict[str, dict[str, QtWidgets.QAction]] = {}
        self._preset_actions: dict[str, QtWidgets.QAction] = {}
        self._preset_menu: QtWidgets.QMenu | None = None
        self._preset_group: QtWidgets.QActionGroup | None = None
        self._delete_preset_action: QtWidgets.QAction | None = None
        self._applying_preset = False
        self._loaded_presets: dict[str, dict[str, object]] = {}

    def build(self) -> QtWidgets.QMenu:
        self._build_flags()
        self._build_container_section()
        self._build_choice_section(
            "Frame Format", _FRAME_FORMAT_OPTION, _FRAME_FORMAT_LABELS,
            FRAME_FORMATS, DEFAULT_FRAME_FORMAT, "frame",
        )
        self._build_choice_section(
            "Resolution", _RESOLUTION_OPTION, _RESOLUTION_LABELS,
            RESOLUTION_CHOICES, DEFAULT_RESOLUTION, "resolution", separate_after=5,
        )
        self._build_choice_section(
            "Quality", _QUALITY_OPTION, _QUALITY_LABELS,
            tuple(QUALITY_CRF), DEFAULT_QUALITY, "quality",
        )
        self._build_choice_section(
            "Scale", _SCALE_OPTION, _SCALE_LABELS,
            tuple(str(value) for value in SCALES), str(DEFAULT_SCALE), "scale",
        )
        self._build_presets()
        self._build_playblast_action()
        return self._menu

    def _build_flags(self) -> None:
        for label, option, key in (
            ("Auto Play", _AUTO_PLAY_OPTION, "auto_play"),
            ("Sound", _SOUND_OPTION, "sound"),
        ):
            action = self._menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(_read_flag(option, True))
            action.toggled.connect(
                lambda checked, opt=option: self._on_flag(opt, checked)
            )
            self._flag_actions[key] = action

    def _build_container_section(self) -> None:
        self._menu.addSection("Container")
        container, codec = _read_video_settings()
        container_actions = _add_choice_actions(self._menu, _CONTAINER_LABELS, container)
        self._choice_actions["container"] = container_actions

        self._menu.addSection("Video Codec")
        codec_actions = _add_choice_actions(self._menu, _CODEC_LABELS, codec)
        self._choice_actions["codec"] = codec_actions
        for value, action in codec_actions.items():
            action.triggered.connect(
                lambda _checked=False, choice=value: self._set_choice(_CODEC_OPTION, choice)
            )
        for value, action in container_actions.items():
            action.triggered.connect(
                lambda _checked=False, choice=value: self._on_container_selected(choice, True)
            )
        self._on_container_selected(container)

    def _build_choice_section(
        self,
        title: str,
        option: str,
        labels: tuple[tuple[str, str], ...],
        allowed: tuple[str, ...],
        default: str,
        key: str,
        separate_after: int | None = None,
    ) -> None:
        self._menu.addSection(title)
        current = _read_choice(option, allowed, default)
        if separate_after is None:
            actions = _add_choice_actions(self._menu, labels, current)
        else:
            group = QtWidgets.QActionGroup(self._menu)
            group.setExclusive(True)
            actions = _add_choice_actions(self._menu, labels[:separate_after], current, group)
            self._menu.addSeparator()
            actions.update(_add_choice_actions(self._menu, labels[separate_after:], current, group))
        self._choice_actions[key] = actions
        for value, action in actions.items():
            action.triggered.connect(
                lambda _checked=False, choice=value: self._set_choice(option, choice)
            )

    def _build_presets(self) -> None:
        self._loaded_presets = presets.load_presets(_default_settings())
        self._menu.addSection("Preset")
        self._preset_menu = _StayOpenMenu(self._menu)
        self._preset_menu.setTitle("Preset")
        self._menu.addMenu(self._preset_menu)
        self._preset_group = QtWidgets.QActionGroup(self._preset_menu)
        self._preset_group.setExclusive(True)

        self._add_preset_action(presets.DEFAULT_PRESET_NAME)
        for name in sorted(
            (name for name in self._loaded_presets if name != presets.DEFAULT_PRESET_NAME),
            key=str.casefold,
        ):
            self._add_preset_action(name)

        self._menu.addSeparator()
        save_preset_action = self._menu.addAction("Save Preset")
        save_preset_action.triggered.connect(self._save_preset)
        self._delete_preset_action = self._menu.addAction("Delete Current Preset")
        self._delete_preset_action.triggered.connect(self._delete_preset)

        current_preset = presets.DEFAULT_PRESET_NAME
        if cmds.optionVar(exists=_PRESET_OPTION):
            stored_preset = str(cmds.optionVar(  # ty:ignore[no-matching-overload]
                query=_PRESET_OPTION
            ))
            if stored_preset in self._loaded_presets:
                current_preset = stored_preset
        self._apply_preset(current_preset)

    def _build_playblast_action(self) -> None:
        self._menu.addSection("Playblast")
        playblast_action = self._menu.addAction(QtGui.QIcon(ICON_RESOURCE), "Playblast")
        playblast_action.triggered.connect(_run_playblast)
        # 唯一点击后关闭菜单的选项
        self._menu._close_action = playblast_action

    def _add_preset_action(self, name: str) -> QtWidgets.QAction:
        assert self._preset_menu is not None and self._preset_group is not None
        action = self._preset_menu.addAction(name)
        action.setCheckable(True)
        self._preset_group.addAction(action)
        action.triggered.connect(
            lambda _checked=False, preset_name=name: self._apply_preset(preset_name)
        )
        self._preset_actions[name] = action
        return action

    def _mark_custom_settings(self) -> None:
        if self._applying_preset:
            return
        _set_choice(_PRESET_OPTION, "")
        if self._preset_group is not None:
            self._preset_group.setExclusive(False)
            for action in self._preset_actions.values():
                action.setChecked(False)
            self._preset_group.setExclusive(True)
        if self._delete_preset_action is not None:
            self._delete_preset_action.setEnabled(False)

    def _set_choice(self, option: str, choice: str) -> None:
        _set_choice(option, choice)
        self._mark_custom_settings()

    def _on_flag(self, option: str, checked: bool) -> None:
        cmds.optionVar(intValue=(option, int(checked)))
        self._mark_custom_settings()

    def _on_container_selected(self, choice: str, manual: bool = False) -> None:
        _set_choice(_CONTAINER_OPTION, choice)
        allowed = CONTAINER_CODECS[choice]
        for value, action in self._choice_actions["codec"].items():
            action.setEnabled(value in allowed)
        current = _read_choice(_CODEC_OPTION, tuple(CODEC_ENCODERS), DEFAULT_CODEC)
        if current not in allowed:
            current = DEFAULT_CODEC
            _set_choice(_CODEC_OPTION, current)
            self._choice_actions["codec"][current].setChecked(True)
        if manual:
            self._mark_custom_settings()

    def _apply_preset(self, name: str) -> None:
        self._applying_preset = True
        try:
            settings = self._loaded_presets[name]
            _write_settings(settings)
            self._flag_actions["auto_play"].setChecked(bool(settings["auto_play"]))
            self._flag_actions["sound"].setChecked(bool(settings["sound"]))
            self._choice_actions["frame"][str(settings["frame_format"])].setChecked(True)
            container_value = str(settings["container"])
            self._choice_actions["container"][container_value].setChecked(True)
            self._on_container_selected(container_value)
            self._choice_actions["codec"][str(settings["codec"])].setChecked(True)
            self._choice_actions["resolution"][str(settings["resolution"])].setChecked(True)
            self._choice_actions["quality"][str(settings["quality"])].setChecked(True)
            self._choice_actions["scale"][str(settings["scale"])].setChecked(True)
        finally:
            self._applying_preset = False
        _set_choice(_PRESET_OPTION, name)
        self._preset_actions[name].setChecked(True)
        if self._delete_preset_action is not None:
            self._delete_preset_action.setEnabled(name != presets.DEFAULT_PRESET_NAME)

    def _save_preset(self) -> None:
        name, accepted = QtWidgets.QInputDialog.getText(
            self._button, "Save Preset", "Preset name:"
        )
        name = name.strip()
        if not accepted or not name:
            return
        if not presets.is_valid_name(name):
            QtWidgets.QMessageBox.warning(
                self._button,
                "Invalid Preset Name",
                "Use a name other than Default and avoid Windows filename characters.",
            )
            return

        path = presets.PRESET_DIR / f"{name}.json"
        if path.exists():
            answer = QtWidgets.QMessageBox.question(
                self._button,
                "Replace Preset",
                f'Replace preset "{name}"?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return

        settings = _read_settings()
        try:
            presets.save_preset(name, settings)
        except OSError as err:
            QtWidgets.QMessageBox.critical(self._button, "Save Preset Failed", str(err))
            return
        self._loaded_presets[name] = settings
        if name not in self._preset_actions:
            self._add_preset_action(name)
        _set_choice(_PRESET_OPTION, name)
        self._preset_actions[name].setChecked(True)
        if self._delete_preset_action is not None:
            self._delete_preset_action.setEnabled(True)

    def _delete_preset(self) -> None:
        name = str(cmds.optionVar(  # ty:ignore[no-matching-overload]
            query=_PRESET_OPTION
        ))
        if name not in self._preset_actions or name == presets.DEFAULT_PRESET_NAME:
            return
        answer = QtWidgets.QMessageBox.question(
            self._button,
            "Delete Preset",
            f'Delete preset "{name}"?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            presets.delete_preset(name)
        except OSError as err:
            QtWidgets.QMessageBox.critical(self._button, "Delete Preset Failed", str(err))
            return
        action = self._preset_actions.pop(name)
        if self._preset_group is not None:
            self._preset_group.removeAction(action)
        action.deleteLater()
        self._loaded_presets.pop(name, None)
        self._apply_preset(presets.DEFAULT_PRESET_NAME)


def _create_options_menu(button: QtWidgets.QWidget) -> QtWidgets.QMenu:
    """构建按钮的右键选项菜单。"""
    return _OptionsMenuBuilder(button).build()


# ---- 按钮外观与交互 ----

class _OptionsMenuEventFilter(QtCore.QObject):
    """消费按钮右键事件，阻止 Maya timeSlider 菜单接管；左键触发 playblast。"""

    def __init__(
        self,
        menu: QtWidgets.QMenu,
        parent: QtWidgets.QWidget,
        normal_icon: QtGui.QIcon,
        hover_icon: QtGui.QIcon,
    ) -> None:
        super().__init__(parent)
        self._menu = menu
        self._button = parent
        self._normal_icon = normal_icon
        self._hover_icon = hover_icon

    def eventFilter(self, watched, event) -> bool:
        event_type = event.type()
        if event_type == QtCore.QEvent.Enter:
            self._button.setIcon(self._hover_icon)
        elif event_type == QtCore.QEvent.Leave:
            self._button.setIcon(self._normal_icon)
        elif event_type == QtCore.QEvent.MouseButtonPress:
            if event.button() == QtCore.Qt.RightButton:
                event.accept()
                return True
        elif event_type == QtCore.QEvent.MouseButtonRelease:
            if event.button() == QtCore.Qt.RightButton:
                self._menu.popup(event.globalPos())
                event.accept()
                return True
            if event.button() == QtCore.Qt.LeftButton:
                _run_playblast()
                event.accept()
                return True
        elif event_type == QtCore.QEvent.ContextMenu:
            if not self._menu.isVisible():
                self._menu.popup(event.globalPos())
            event.accept()
            return True
        return super().eventFilter(watched, event)


def _build_button(parent: QtWidgets.QWidget | None = None) -> QtWidgets.QToolButton:
    """在 parent 下创建 Playblast 按钮，接好左键播放 / 右键菜单逻辑。"""
    button = QtWidgets.QToolButton(parent)
    button.setObjectName(BUTTON_NAME)
    # 与 Maya 原生图标按钮一致（40x40）
    button.setFixedSize(40, 40)
    button.setFocusPolicy(QtCore.Qt.NoFocus)

    # 美术资源：SVG 矢量图标，QIcon 按尺寸无损渲染（UI 缩放自适应）
    icon_size = 40
    normal_icon = QtGui.QIcon(ICON_RESOURCE)
    hover_icon = QtGui.QIcon(ICON_RESOURCE_HOVER)
    button.setIcon(normal_icon)
    button.setIconSize(QtCore.QSize(icon_size, icon_size))
    button.setToolTip("Playblast\nRight-click for output options")
    button.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
    # 悬停时仅高亮 icon，不显示背景框
    button.setStyleSheet(
        f"QToolButton#{BUTTON_NAME} {{ background: transparent; border: none; }}"
        f"QToolButton#{BUTTON_NAME}:hover {{ background: transparent; }}"
    )

    menu = _create_options_menu(button)
    menu_filter = _OptionsMenuEventFilter(menu, button, normal_icon, hover_icon)
    button.installEventFilter(menu_filter)
    return button


def show_debug_window() -> QtWidgets.QDialog:
    """调试用：在独立窗口中显示 Playblast 按钮（不挂到 Maya 原生控件）。

    左键触发 playblast；右键弹出输出选项菜单。重复调用会复用窗口。
    """
    global _DEBUG_WINDOW

    if _DEBUG_WINDOW is not None and shiboken2.isValid(_DEBUG_WINDOW):
        _DEBUG_WINDOW.show()
        _DEBUG_WINDOW.raise_()
        _DEBUG_WINDOW.activateWindow()
        return _DEBUG_WINDOW

    _DEBUG_WINDOW = QtWidgets.QDialog()
    _DEBUG_WINDOW.setObjectName("playblastDebugWindow")
    _DEBUG_WINDOW.setWindowTitle("Playblast Button Debug")
    layout = QtWidgets.QVBoxLayout(_DEBUG_WINDOW)
    layout.addWidget(_build_button(_DEBUG_WINDOW))
    _DEBUG_WINDOW.show()
    return _DEBUG_WINDOW


def create_button() -> QtWidgets.QToolButton:
    """创建 Playblast 按钮（左键播放，右键选项），不附加到 Maya。

    返回的按钮没有父控件，需要自己调用 show() 或挂到某个布局/窗口。
    """
    global _BUTTON

    if _BUTTON is not None and shiboken2.isValid(_BUTTON):
        return _BUTTON

    _BUTTON = _build_button(None)
    return _BUTTON


def attach_button_in_maya() -> None:
    btn = create_button()
    attach_timeSlider.attach(btn)
