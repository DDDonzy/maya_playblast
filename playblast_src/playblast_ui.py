"""Maya timeSlider 旁的 Playblast 按钮。

左键点击触发 playblast；右键点击弹出输出选项菜单。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from maya import cmds

import shiboken2  # ty:ignore[unresolved-import]
from PySide2 import QtCore, QtGui, QtWidgets  # ty:ignore[unresolved-import]


import playblast
import attach_timeslider

BUTTON_NAME = "playblastButton"

MENU_NAME = "playblastOptionsMenu"
_AUTO_PLAY_OPTION = "playblastToolsAutoPlay"
_FRAME_FORMAT_OPTION = "playblastToolsFrameFormat"
_CONTAINER_OPTION = "playblastToolsContainer"
_CODEC_OPTION = "playblastToolsCodec"
_RESOLUTION_OPTION = "playblastToolsResolution"
_SCALE_OPTION = "playblastToolsScale"
_QUALITY_OPTION = "playblastToolsQuality"
_PRESET_OPTION = "playblastToolsPreset"

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

_DEFAULT_PRESET_NAME = "Default"
_PRESET_DIR = Path(__file__).resolve().parent.parent / "presets"
_INVALID_PRESET_NAME = re.compile(r'[<>:"/\\|?*]')

_BUTTON = None
_DEBUG_WINDOW = None


class _OptionsMenuEventFilter(QtCore.QObject):
    """消费按钮右键事件，阻止 Maya timeSlider 菜单接管。"""

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
        elif event_type == QtCore.QEvent.ContextMenu:
            if not self._menu.isVisible():
                self._menu.popup(event.globalPos())
            event.accept()
            return True
        return super().eventFilter(watched, event)


def _read_choice(option: str, allowed: tuple[str, ...], default: str) -> str:
    if cmds.optionVar(exists=option):
        value = str(cmds.optionVar(query=option)).lower()
        if value in allowed:
            return value

    cmds.optionVar(stringValue=(option, default))
    return default


def _set_choice(option: str, value: str) -> None:
    cmds.optionVar(stringValue=(option, value))


def _read_auto_play() -> bool:
    if not cmds.optionVar(exists=_AUTO_PLAY_OPTION):
        cmds.optionVar(intValue=(_AUTO_PLAY_OPTION, 1))
    return bool(cmds.optionVar(query=_AUTO_PLAY_OPTION))


def _read_video_settings() -> tuple[str, str]:
    container = _read_choice(
        _CONTAINER_OPTION,
        tuple(playblast.CONTAINER_CODECS),
        playblast.DEFAULT_CONTAINER,
    )
    codecs = tuple(playblast.CODEC_ENCODERS)
    codec = _read_choice(_CODEC_OPTION, codecs, playblast.DEFAULT_CODEC)
    if codec not in playblast.CONTAINER_CODECS[container]:
        codec = playblast.DEFAULT_CODEC
        _set_choice(_CODEC_OPTION, codec)
    return (container, codec)


def _default_settings() -> dict[str, object]:
    return {
        "frame_format": playblast.DEFAULT_FRAME_FORMAT,
        "container": playblast.DEFAULT_CONTAINER,
        "codec": playblast.DEFAULT_CODEC,
        "resolution": playblast.DEFAULT_RESOLUTION,
        "scale": playblast.DEFAULT_SCALE,
        "quality": playblast.DEFAULT_QUALITY,
        "auto_play": True,
    }


def _read_settings() -> dict[str, object]:
    frame_format = _read_choice(
        _FRAME_FORMAT_OPTION,
        playblast.FRAME_FORMATS,
        playblast.DEFAULT_FRAME_FORMAT,
    )
    container, codec = _read_video_settings()
    resolution = _read_choice(
        _RESOLUTION_OPTION,
        playblast.RESOLUTION_CHOICES,
        playblast.DEFAULT_RESOLUTION,
    )
    scale = int(
        _read_choice(
            _SCALE_OPTION,
            tuple(str(value) for value in playblast.SCALES),
            str(playblast.DEFAULT_SCALE),
        )
    )
    quality = _read_choice(
        _QUALITY_OPTION,
        tuple(playblast.QUALITY_CRF),
        playblast.DEFAULT_QUALITY,
    )
    return {
        "frame_format": frame_format,
        "container": container,
        "codec": codec,
        "resolution": resolution,
        "scale": scale,
        "quality": quality,
        "auto_play": _read_auto_play(),
    }


def _write_settings(settings: dict[str, object]) -> None:
    _set_choice(_FRAME_FORMAT_OPTION, str(settings["frame_format"]))
    _set_choice(_CONTAINER_OPTION, str(settings["container"]))
    _set_choice(_CODEC_OPTION, str(settings["codec"]))
    _set_choice(_RESOLUTION_OPTION, str(settings["resolution"]))
    _set_choice(_SCALE_OPTION, str(settings["scale"]))
    _set_choice(_QUALITY_OPTION, str(settings["quality"]))
    cmds.optionVar(intValue=(_AUTO_PLAY_OPTION, int(bool(settings["auto_play"]))))


def _normalize_preset_settings(data: object) -> dict[str, object]:
    if not isinstance(data, dict):
        raise ValueError("Preset root must be a JSON object.")

    frame_format = str(data.get("frame_format", "")).lower()
    container = str(data.get("container", "")).lower()
    codec = str(data.get("codec", "")).lower()
    resolution = str(data.get("resolution", "")).lower()
    quality = str(data.get("quality", "")).lower()
    scale = data.get("scale")
    auto_play = data.get("auto_play")

    if frame_format not in playblast.FRAME_FORMATS:
        raise ValueError(f"Invalid frame format: {frame_format}")
    if container not in playblast.CONTAINER_CODECS:
        raise ValueError(f"Invalid container: {container}")
    if codec not in playblast.CONTAINER_CODECS[container]:
        raise ValueError(f"Invalid codec for {container}: {codec}")
    if resolution not in playblast.RESOLUTION_CHOICES:
        raise ValueError(f"Invalid resolution: {resolution}")
    if isinstance(scale, bool) or scale not in playblast.SCALES:
        raise ValueError(f"Invalid scale: {scale}")
    if quality not in playblast.QUALITY_CRF:
        raise ValueError(f"Invalid quality: {quality}")
    if type(auto_play) is not bool:
        raise ValueError(f"Invalid Auto Play value: {auto_play}")

    return {
        "frame_format": frame_format,
        "container": container,
        "codec": codec,
        "resolution": resolution,
        "scale": scale,
        "quality": quality,
        "auto_play": auto_play,
    }


def _load_presets() -> dict[str, dict[str, object]]:
    default_settings = _default_settings()
    default_path = _PRESET_DIR / f"{_DEFAULT_PRESET_NAME}.json"
    try:
        stored_default = _normalize_preset_settings(json.loads(default_path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        stored_default = None
    if stored_default != default_settings:
        _save_preset(_DEFAULT_PRESET_NAME, default_settings)

    presets = {}
    for path in sorted(_PRESET_DIR.glob("*.json"), key=lambda item: item.stem.casefold()):
        try:
            presets[path.stem] = _normalize_preset_settings(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, ValueError) as err:
            cmds.warning(f'Ignoring invalid preset "{path}": {err}')
    return presets


def _save_preset(name: str, settings: dict[str, object]) -> Path:
    _PRESET_DIR.mkdir(parents=True, exist_ok=True)
    path = _PRESET_DIR / f"{name}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _run_playblast() -> None:
    settings = _read_settings()
    playblast.playblast(**settings)


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


def _create_options_menu(button: QtWidgets.QPushButton) -> QtWidgets.QMenu:
    menu = QtWidgets.QMenu(button)
    menu.setObjectName(MENU_NAME)

    preset_actions = {}
    preset_group = None
    delete_preset_action = None
    applying_preset = False

    def mark_custom_settings() -> None:
        if applying_preset:
            return
        _set_choice(_PRESET_OPTION, "")
        if preset_group is not None:
            preset_group.setExclusive(False)
            for action in preset_actions.values():
                action.setChecked(False)
            preset_group.setExclusive(True)
        if delete_preset_action is not None:
            delete_preset_action.setEnabled(False)

    def set_menu_choice(option: str, choice: str) -> None:
        _set_choice(option, choice)
        mark_custom_settings()

    auto_play = menu.addAction("Auto Play")
    auto_play.setCheckable(True)
    auto_play.setChecked(_read_auto_play())

    def set_auto_play(checked: bool) -> None:
        cmds.optionVar(intValue=(_AUTO_PLAY_OPTION, int(checked)))
        mark_custom_settings()

    auto_play.toggled.connect(set_auto_play)

    menu.addSection("Container")
    container, codec = _read_video_settings()
    container_actions = _add_choice_actions(menu, _CONTAINER_LABELS, container)

    menu.addSection("Video Codec")
    codec_actions = _add_choice_actions(menu, _CODEC_LABELS, codec)
    for value, action in codec_actions.items():
        action.triggered.connect(lambda _checked=False, choice=value: set_menu_choice(_CODEC_OPTION, choice))

    def select_container(choice: str, manual: bool = False) -> None:
        _set_choice(_CONTAINER_OPTION, choice)
        allowed = playblast.CONTAINER_CODECS[choice]
        for value, action in codec_actions.items():
            action.setEnabled(value in allowed)
        current = _read_choice(
            _CODEC_OPTION,
            tuple(playblast.CODEC_ENCODERS),
            playblast.DEFAULT_CODEC,
        )
        if current not in allowed:
            current = playblast.DEFAULT_CODEC
            _set_choice(_CODEC_OPTION, current)
            codec_actions[current].setChecked(True)
        if manual:
            mark_custom_settings()

    for value, action in container_actions.items():
        action.triggered.connect(lambda _checked=False, choice=value: select_container(choice, True))
    select_container(container)
    menu.addSection("Frame Format")
    frame_format = _read_choice(
        _FRAME_FORMAT_OPTION,
        playblast.FRAME_FORMATS,
        playblast.DEFAULT_FRAME_FORMAT,
    )
    frame_actions = _add_choice_actions(menu, _FRAME_FORMAT_LABELS, frame_format)
    for value, action in frame_actions.items():
        action.triggered.connect(lambda _checked=False, choice=value: set_menu_choice(_FRAME_FORMAT_OPTION, choice))

    menu.addSection("Resolution")
    resolution = _read_choice(
        _RESOLUTION_OPTION,
        playblast.RESOLUTION_CHOICES,
        playblast.DEFAULT_RESOLUTION,
    )
    resolution_group = QtWidgets.QActionGroup(menu)
    resolution_group.setExclusive(True)
    resolution_actions = _add_choice_actions(menu, _RESOLUTION_LABELS[:5], resolution, resolution_group)
    menu.addSeparator()
    resolution_actions.update(_add_choice_actions(menu, _RESOLUTION_LABELS[5:], resolution, resolution_group))
    for value, action in resolution_actions.items():
        action.triggered.connect(lambda _checked=False, choice=value: set_menu_choice(_RESOLUTION_OPTION, choice))

    menu.addSection("Quality")
    quality = _read_choice(
        _QUALITY_OPTION,
        tuple(playblast.QUALITY_CRF),
        playblast.DEFAULT_QUALITY,
    )
    quality_actions = _add_choice_actions(menu, _QUALITY_LABELS, quality)
    for value, action in quality_actions.items():
        action.triggered.connect(lambda _checked=False, choice=value: set_menu_choice(_QUALITY_OPTION, choice))

    menu.addSection("Scale")
    scale = _read_choice(
        _SCALE_OPTION,
        tuple(str(value) for value in playblast.SCALES),
        str(playblast.DEFAULT_SCALE),
    )
    scale_actions = _add_choice_actions(menu, _SCALE_LABELS, scale)
    for value, action in scale_actions.items():
        action.triggered.connect(lambda _checked=False, choice=value: set_menu_choice(_SCALE_OPTION, choice))

    presets = _load_presets()
    menu.addSection("Preset")
    preset_menu = menu.addMenu("Preset")
    preset_group = QtWidgets.QActionGroup(preset_menu)
    preset_group.setExclusive(True)

    def apply_preset(name: str) -> None:
        nonlocal applying_preset
        applying_preset = True
        try:
            settings = presets[name]
            _write_settings(settings)
            auto_play.setChecked(bool(settings["auto_play"]))
            frame_actions[str(settings["frame_format"])].setChecked(True)
            container_value = str(settings["container"])
            container_actions[container_value].setChecked(True)
            select_container(container_value)
            codec_actions[str(settings["codec"])].setChecked(True)
            resolution_actions[str(settings["resolution"])].setChecked(True)
            quality_actions[str(settings["quality"])].setChecked(True)
            scale_actions[str(settings["scale"])].setChecked(True)
        finally:
            applying_preset = False
        _set_choice(_PRESET_OPTION, name)
        preset_actions[name].setChecked(True)
        if delete_preset_action is not None:
            delete_preset_action.setEnabled(name != _DEFAULT_PRESET_NAME)

    def add_preset_action(name: str) -> QtWidgets.QAction:
        action = preset_menu.addAction(name)
        action.setCheckable(True)
        preset_group.addAction(action)
        action.triggered.connect(lambda _checked=False, preset_name=name: apply_preset(preset_name))
        preset_actions[name] = action
        return action

    add_preset_action(_DEFAULT_PRESET_NAME)
    for name in sorted(
        (name for name in presets if name != _DEFAULT_PRESET_NAME),
        key=str.casefold,
    ):
        add_preset_action(name)

    menu.addSeparator()
    save_preset_action = menu.addAction("Save Preset")
    delete_preset_action = menu.addAction("Delete Current Preset")

    def save_current_preset(_checked: bool = False) -> None:
        name, accepted = QtWidgets.QInputDialog.getText(
            button,
            "Save Preset",
            "Preset name:",
        )
        name = name.strip()
        if not accepted or not name:
            return
        if name.casefold() == _DEFAULT_PRESET_NAME.casefold() or _INVALID_PRESET_NAME.search(name) or name != name.rstrip(". "):
            QtWidgets.QMessageBox.warning(
                button,
                "Invalid Preset Name",
                "Use a name other than Default and avoid Windows filename characters.",
            )
            return

        path = _PRESET_DIR / f"{name}.json"
        if path.exists():
            answer = QtWidgets.QMessageBox.question(
                button,
                "Replace Preset",
                f'Replace preset "{name}"?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if answer != QtWidgets.QMessageBox.Yes:
                return

        settings = _read_settings()
        try:
            _save_preset(name, settings)
        except OSError as err:
            QtWidgets.QMessageBox.critical(
                button,
                "Save Preset Failed",
                str(err),
            )
            return
        presets[name] = settings
        if name not in preset_actions:
            add_preset_action(name)
        _set_choice(_PRESET_OPTION, name)
        preset_actions[name].setChecked(True)
        delete_preset_action.setEnabled(True)

    def delete_current_preset(_checked: bool = False) -> None:
        name = str(cmds.optionVar(query=_PRESET_OPTION))
        if name not in preset_actions or name == _DEFAULT_PRESET_NAME:
            return
        answer = QtWidgets.QMessageBox.question(
            button,
            "Delete Preset",
            f'Delete preset "{name}"?',
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            (_PRESET_DIR / f"{name}.json").unlink()
        except OSError as err:
            QtWidgets.QMessageBox.critical(
                button,
                "Delete Preset Failed",
                str(err),
            )
            return
        action = preset_actions.pop(name)
        preset_group.removeAction(action)
        preset_menu.removeAction(action)
        presets.pop(name, None)
        action.deleteLater()
        apply_preset(_DEFAULT_PRESET_NAME)

    save_preset_action.triggered.connect(save_current_preset)
    delete_preset_action.triggered.connect(delete_current_preset)

    current_preset = _DEFAULT_PRESET_NAME
    if cmds.optionVar(exists=_PRESET_OPTION):
        stored_preset = str(cmds.optionVar(query=_PRESET_OPTION))
        if stored_preset in presets:
            current_preset = stored_preset
    apply_preset(current_preset)

    menu.addSection("Playblast")
    playblast_action = menu.addAction(QtGui.QIcon(":playblast.png"), "Playblast")
    playblast_action.triggered.connect(_run_playblast)

    button.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
    return menu


def _hover_pixmap(pixmap: QtGui.QPixmap) -> QtGui.QPixmap:
    """把 PNG 图标提亮一档，用于悬停高亮（不画背景框）。"""
    highlighted = QtGui.QPixmap(pixmap)
    painter = QtGui.QPainter(highlighted)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceAtop)
    painter.fillRect(highlighted.rect(), QtGui.QColor(255, 255, 255, 110))
    painter.end()
    return highlighted


def _crop_transparent_padding(pixmap: QtGui.QPixmap) -> QtGui.QPixmap:
    """裁掉图标四周的透明留白，让图形尽量占满，放大后更显眼。"""
    image = pixmap.toImage()
    if image.isNull() or not image.hasAlphaChannel():
        return pixmap

    left = image.width()
    top = image.height()
    right = -1
    bottom = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() <= 8:
                continue
            left = min(left, x)
            top = min(top, y)
            right = max(right, x)
            bottom = max(bottom, y)

    if right < left or bottom < top:
        return pixmap
    return pixmap.copy(left, top, right - left + 1, bottom - top + 1)


def _build_button(parent: QtWidgets.QWidget | None = None) -> QtWidgets.QPushButton:
    """在 parent 下创建 Playblast 按钮，接好左键播放 / 右键菜单逻辑。"""
    button = QtWidgets.QPushButton(parent)
    button.setObjectName(BUTTON_NAME)
    button.setFixedSize(32, 32)

    # 强制缩放：先裁透明留白，再平滑放大到接近按钮大小，让图标显眼
    icon_size = button.height() - 2
    base = _crop_transparent_padding(QtGui.QPixmap(":playblast.png")).scaled(
        icon_size,
        icon_size,
        QtCore.Qt.KeepAspectRatio,
        QtCore.Qt.SmoothTransformation,
    )
    normal_icon = QtGui.QIcon(base)
    hover_icon = QtGui.QIcon(_hover_pixmap(base))

    button.setIcon(normal_icon)
    button.setIconSize(QtCore.QSize(icon_size, icon_size))
    button.setToolTip("Playblast\nRight-click for output options")
    # 无背景框：透明背景 + 无边框，悬停高亮直接体现在 PNG 图标上
    button.setStyleSheet(f"QPushButton#{BUTTON_NAME} {{background: transparent; border: none;}}")

    menu = _create_options_menu(button)
    menu_filter = _OptionsMenuEventFilter(menu, button, normal_icon, hover_icon)
    button.installEventFilter(menu_filter)
    button.clicked.connect(_run_playblast)
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


def create_button() -> QtWidgets.QPushButton:
    """创建 Playblast 按钮（左键播放，右键选项），不附加到 Maya。

    返回的按钮没有父控件，需要自己调用 show() 或挂到某个布局/窗口。
    """
    global _BUTTON

    if _BUTTON is not None and shiboken2.isValid(_BUTTON):
        return _BUTTON

    _BUTTON = _build_button(None)
    return _BUTTON


def attach_button_in_maya():
    btn = create_button()
    attach_timeslider.attach(btn)
