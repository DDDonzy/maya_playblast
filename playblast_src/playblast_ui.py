"""Maya timeSlider 旁的 Playblast 按钮。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from maya import cmds
from maya import OpenMayaUI as omui

import shiboken2  # ty:ignore[unresolved-import]
from PySide2 import QtCore, QtGui, QtWidgets  # ty:ignore[unresolved-import]

import playblast

BUTTON_NAME = "playblastButton"
BUTTON_HOST_NAME = "playblastButtonHost"
_LAYOUT_FILTER_NAME = "playblastButtonLayoutFilter"
HIGHLIGHT_FRAME_NAME = "playblastHighlightFrame"
_BUTTON_BORDER_WIDTH = 4
_ICON_ALPHA_THRESHOLD = 8
_ICON_OVERSCAN = 8
_HIGHLIGHT_PADDING = 6
_HOVER_ICON_OPACITY = 72

MENU_NAME = "playblastOptionsMenu"
_AUTO_PLAY_OPTION = "playblastToolsAutoPlay"
_FRAME_FORMAT_OPTION = "playblastToolsFrameFormat"
_CONTAINER_OPTION = "playblastToolsContainer"
_CODEC_OPTION = "playblastToolsCodec"
_RESOLUTION_OPTION = "playblastToolsResolution"
_SCALE_OPTION = "playblastToolsScale"
_QUALITY_OPTION = "playblastToolsQuality"
_PRESET_OPTION = "playblastToolsPreset"
_HIGHLIGHT_OPTION = "playblastToolsHighlight"

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
_BUTTON_HOST = None
_HIGHLIGHT_FRAME = None
_MENU = None
_MENU_FILTER = None
_LAYOUT_FILTER = None


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


class _PlaybackButtonLayoutFilter(QtCore.QObject):
    """保持按钮与 Maya 原生播放按钮像素级对齐。"""

    def __init__(
        self,
        row: QtWidgets.QWidget,
        reference: QtWidgets.QWidget,
        host: QtWidgets.QWidget,
        button: QtWidgets.QPushButton,
        highlight_parent: QtWidgets.QWidget,
        highlight_frame: QtWidgets.QFrame,
    ) -> None:
        super().__init__(row)
        self.setObjectName(_LAYOUT_FILTER_NAME)
        self._row = row
        self._reference = reference
        self._host = host
        self._button = button
        self._highlight_parent = highlight_parent
        self._highlight_frame = highlight_frame

    def _highlight_geometry(self) -> QtCore.QRect:
        pixmap = self._button.icon().pixmap(self._button.iconSize())
        if pixmap.isNull():
            icon_size = self._button.iconSize()
        else:
            ratio = max(1.0, pixmap.devicePixelRatio())
            icon_size = QtCore.QSize(
                round(pixmap.width() / ratio),
                round(pixmap.height() / ratio),
            )
        icon_position = QtCore.QPoint(
            round((self._button.width() - icon_size.width()) / 2),
            round((self._button.height() - icon_size.height()) / 2),
        )
        top_left = self._button.mapTo(self._highlight_parent, icon_position)
        padding = QtCore.QPoint(_HIGHLIGHT_PADDING, _HIGHLIGHT_PADDING)
        frame_size = icon_size + QtCore.QSize(
            2 * _HIGHLIGHT_PADDING, 2 * _HIGHLIGHT_PADDING
        )
        return QtCore.QRect(top_left - padding, frame_size)

    def align(self) -> None:
        widgets = (
            self._row,
            self._reference,
            self._host,
            self._button,
            self._highlight_parent,
            self._highlight_frame,
        )
        if not all(shiboken2.isValid(widget) for widget in widgets):
            return
        button_size = self._reference.size()
        host_size = QtCore.QSize(button_size.width(), self._row.height())
        if self._host.size() != host_size:
            self._host.setFixedSize(host_size)
        if self._button.size() != button_size:
            self._button.setFixedSize(button_size)
        position = QtCore.QPoint(0, self._reference.y() - self._host.y())
        if self._button.pos() != position:
            self._button.move(position)

        visible = self._button.isVisible() and _read_highlight()
        if visible:
            self._highlight_frame.setGeometry(self._highlight_geometry())
            self._highlight_frame.raise_()
            self._highlight_frame.show()
        else:
            self._highlight_frame.hide()

    def eventFilter(self, watched, event) -> bool:
        if event.type() in (
            QtCore.QEvent.Hide,
            QtCore.QEvent.LayoutRequest,
            QtCore.QEvent.Move,
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
        ):
            QtCore.QTimer.singleShot(0, self.align)
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


def _read_highlight() -> bool:
    if not cmds.optionVar(exists=_HIGHLIGHT_OPTION):
        cmds.optionVar(intValue=(_HIGHLIGHT_OPTION, 1))
    return bool(cmds.optionVar(query=_HIGHLIGHT_OPTION))


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
        stored_default = _normalize_preset_settings(
            json.loads(default_path.read_text(encoding="utf-8"))
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        stored_default = None
    if stored_default != default_settings:
        _save_preset(_DEFAULT_PRESET_NAME, default_settings)

    presets = {}
    for path in sorted(
        _PRESET_DIR.glob("*.json"), key=lambda item: item.stem.casefold()
    ):
        try:
            presets[path.stem] = _normalize_preset_settings(
                json.loads(path.read_text(encoding="utf-8"))
            )
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
        action.triggered.connect(
            lambda _checked=False, choice=value: set_menu_choice(_CODEC_OPTION, choice)
        )

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
        action.triggered.connect(
            lambda _checked=False, choice=value: select_container(choice, True)
        )
    select_container(container)
    menu.addSection("Frame Format")
    frame_format = _read_choice(
        _FRAME_FORMAT_OPTION,
        playblast.FRAME_FORMATS,
        playblast.DEFAULT_FRAME_FORMAT,
    )
    frame_actions = _add_choice_actions(menu, _FRAME_FORMAT_LABELS, frame_format)
    for value, action in frame_actions.items():
        action.triggered.connect(
            lambda _checked=False, choice=value: set_menu_choice(
                _FRAME_FORMAT_OPTION, choice
            )
        )

    menu.addSection("Resolution")
    resolution = _read_choice(
        _RESOLUTION_OPTION,
        playblast.RESOLUTION_CHOICES,
        playblast.DEFAULT_RESOLUTION,
    )
    resolution_group = QtWidgets.QActionGroup(menu)
    resolution_group.setExclusive(True)
    resolution_actions = _add_choice_actions(
        menu, _RESOLUTION_LABELS[:5], resolution, resolution_group
    )
    menu.addSeparator()
    resolution_actions.update(
        _add_choice_actions(menu, _RESOLUTION_LABELS[5:], resolution, resolution_group)
    )
    for value, action in resolution_actions.items():
        action.triggered.connect(
            lambda _checked=False, choice=value: set_menu_choice(
                _RESOLUTION_OPTION, choice
            )
        )

    menu.addSection("Quality")
    quality = _read_choice(
        _QUALITY_OPTION,
        tuple(playblast.QUALITY_CRF),
        playblast.DEFAULT_QUALITY,
    )
    quality_actions = _add_choice_actions(menu, _QUALITY_LABELS, quality)
    for value, action in quality_actions.items():
        action.triggered.connect(
            lambda _checked=False, choice=value: set_menu_choice(
                _QUALITY_OPTION, choice
            )
        )

    menu.addSection("Scale")
    scale = _read_choice(
        _SCALE_OPTION,
        tuple(str(value) for value in playblast.SCALES),
        str(playblast.DEFAULT_SCALE),
    )
    scale_actions = _add_choice_actions(menu, _SCALE_LABELS, scale)
    for value, action in scale_actions.items():
        action.triggered.connect(
            lambda _checked=False, choice=value: set_menu_choice(_SCALE_OPTION, choice)
        )

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
        action.triggered.connect(
            lambda _checked=False, preset_name=name: apply_preset(preset_name)
        )
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
        if (
            name.casefold() == _DEFAULT_PRESET_NAME.casefold()
            or _INVALID_PRESET_NAME.search(name)
            or name != name.rstrip(". ")
        ):
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

    menu.addSeparator()
    highlight_action = menu.addAction("Hight Light")
    highlight_action.setCheckable(True)
    highlight_action.setChecked(_read_highlight())

    def set_highlight(checked: bool) -> None:
        cmds.optionVar(intValue=(_HIGHLIGHT_OPTION, int(checked)))
        if _LAYOUT_FILTER is not None and shiboken2.isValid(_LAYOUT_FILTER):
            _LAYOUT_FILTER.align()

    highlight_action.toggled.connect(set_highlight)

    playblast_action = menu.addAction(QtGui.QIcon(":playblast.png"), "Playblast")
    playblast_action.triggered.connect(_run_playblast)

    button.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
    return menu


def _crop_transparent_padding(pixmap: QtGui.QPixmap) -> QtGui.QPixmap:
    image = pixmap.toImage()
    if image.isNull() or not image.hasAlphaChannel():
        return pixmap

    left = image.width()
    top = image.height()
    right = -1
    bottom = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() <= _ICON_ALPHA_THRESHOLD:
                continue
            left = min(left, x)
            top = min(top, y)
            right = max(right, x)
            bottom = max(bottom, y)

    if right < left or bottom < top:
        return pixmap
    return pixmap.copy(left, top, right - left + 1, bottom - top + 1)


def _highlight_icon_pixmap(pixmap: QtGui.QPixmap) -> QtGui.QPixmap:
    highlighted = QtGui.QPixmap(pixmap)
    painter = QtGui.QPainter(highlighted)
    painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceAtop)
    painter.fillRect(
        highlighted.rect(), QtGui.QColor(255, 255, 255, _HOVER_ICON_OPACITY)
    )
    painter.end()
    return highlighted


def _style_button(
    button: QtWidgets.QPushButton,
) -> tuple[QtGui.QIcon, QtGui.QIcon]:
    icon_size = max(
        1,
        min(button.width(), button.height())
        - 2 * _BUTTON_BORDER_WIDTH
        + _ICON_OVERSCAN,
    )
    background_content_width = max(1, button.width() - 2 * _BUTTON_BORDER_WIDTH)
    background_content_height = max(1, button.height() - 2 * _BUTTON_BORDER_WIDTH)
    pixmap = _crop_transparent_padding(QtGui.QPixmap(":playblast.png")).scaled(
        icon_size,
        icon_size,
        QtCore.Qt.KeepAspectRatio,
        QtCore.Qt.SmoothTransformation,
    )
    normal_icon = QtGui.QIcon(pixmap)
    hover_icon = QtGui.QIcon(_highlight_icon_pixmap(pixmap))
    button.setIcon(normal_icon)
    button.setIconSize(QtCore.QSize(icon_size, icon_size))
    button.setToolTip("Playblast\nRight-click for output options")
    button.setStyleSheet(
        "QPushButton#playblastButton {"
        f"border: {_BUTTON_BORDER_WIDTH}px solid transparent; "
        "border-radius: 4px; background: transparent; padding: 0;"
        f"min-width: {background_content_width}px; "
        f"max-width: {background_content_width}px; "
        f"min-height: {background_content_height}px; "
        f"max-height: {background_content_height}px; "
        "}"
        "QPushButton#playblastButton:hover {background: transparent;}"
        "QPushButton#playblastButton:pressed {background: transparent;}"
    )
    return normal_icon, hover_icon


def install_button() -> QtWidgets.QPushButton:
    """将 Playblast 按钮安装到 Maya 原生播放控件的 rowLayout。"""
    global _BUTTON, _BUTTON_HOST, _HIGHLIGHT_FRAME
    global _MENU, _MENU_FILTER, _LAYOUT_FILTER

    if _BUTTON is not None and shiboken2.isValid(_BUTTON):
        return _BUTTON

    controls = cmds.lsUI(type="timeControl")
    if not controls:
        raise RuntimeError("Maya timeSlider was not found.")

    pointer = omui.MQtUtil.findControl(controls[0])
    if pointer is None:
        raise RuntimeError("Cannot access the Maya timeSlider widget.")

    slider = shiboken2.wrapInstance(int(pointer), QtWidgets.QWidget)
    frame = slider.parentWidget().parentWidget()
    form = frame.parentWidget()
    form_name = form.objectName()
    frame_name = frame.objectName()
    children = cmds.formLayout(form_name, query=True, childArray=True)
    time_field_row = children[children.index(frame_name) + 1]
    playback_controls = children[children.index(time_field_row) + 1]
    playback_short_name = playback_controls.rsplit("|", 1)[-1]
    row = next(
        (
            child
            for child in form.findChildren(
                QtWidgets.QWidget, options=QtCore.Qt.FindDirectChildrenOnly
            )
            if child.objectName() in {playback_controls, playback_short_name}
        ),
        None,
    )
    if row is None or row.layout() is None:
        raise RuntimeError("Cannot access the Maya playback controls layout.")

    for old_filter in row.findChildren(QtCore.QObject, _LAYOUT_FILTER_NAME):
        row.removeEventFilter(old_filter)
        old_filter.deleteLater()
    if cmds.control(BUTTON_NAME, exists=True):
        cmds.deleteUI(BUTTON_NAME)
    old_hosts = [
        host
        for host in row.findChildren(QtWidgets.QWidget, BUTTON_HOST_NAME)
        if host.parentWidget() is row
    ]
    for old_host in old_hosts:
        old_host.setParent(None)
        old_host.deleteLater()
    old_highlight_frames = [
        highlight_frame
        for highlight_frame in form.findChildren(QtWidgets.QFrame, HIGHLIGHT_FRAME_NAME)
        if highlight_frame.parentWidget() is form
    ]
    for old_highlight_frame in old_highlight_frames:
        old_highlight_frame.setParent(None)
        old_highlight_frame.deleteLater()
    QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)

    row_children = cmds.layout(playback_controls, query=True, childArray=True) or []
    native_buttons = [
        name for name in row_children if cmds.symbolButton(name, exists=True)
    ]
    if not native_buttons:
        raise RuntimeError("Maya playback controls do not contain any buttons.")
    reference_pointer = omui.MQtUtil.findControl(native_buttons[-1])
    if reference_pointer is None:
        raise RuntimeError("Cannot access a Maya playback button.")
    reference = shiboken2.wrapInstance(int(reference_pointer), QtWidgets.QWidget)

    cmds.formLayout(
        form_name,
        edit=True,
        attachForm=[
            (frame_name, "left", 16),
            (playback_controls, "right", 7),
        ],
        attachControl=[(frame_name, "right", 8, time_field_row)],
    )

    button_size = reference.size()
    _BUTTON_HOST = QtWidgets.QWidget(row)
    _BUTTON_HOST.setObjectName(BUTTON_HOST_NAME)
    _BUTTON_HOST.setFixedSize(button_size.width(), row.height())
    _BUTTON_HOST.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
    _BUTTON = QtWidgets.QPushButton(_BUTTON_HOST)
    _BUTTON.setObjectName(BUTTON_NAME)
    _BUTTON.setFixedSize(button_size)
    _BUTTON.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
    row.layout().addWidget(_BUTTON_HOST)
    QtWidgets.QApplication.processEvents()
    normal_icon, hover_icon = _style_button(_BUTTON)

    _HIGHLIGHT_FRAME = QtWidgets.QFrame(form)
    _HIGHLIGHT_FRAME.setObjectName(HIGHLIGHT_FRAME_NAME)
    _HIGHLIGHT_FRAME.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
    _HIGHLIGHT_FRAME.setFocusPolicy(QtCore.Qt.NoFocus)
    _HIGHLIGHT_FRAME.setStyleSheet(
        f"QFrame#{HIGHLIGHT_FRAME_NAME} {{"
        f"border: {_BUTTON_BORDER_WIDTH}px solid #66CC66; "
        "border-radius: 4px; background: transparent;"
        "}"
    )

    _LAYOUT_FILTER = _PlaybackButtonLayoutFilter(
        row,
        reference,
        _BUTTON_HOST,
        _BUTTON,
        form,
        _HIGHLIGHT_FRAME,
    )
    for watched in (form, row, _BUTTON_HOST, _BUTTON):
        watched.installEventFilter(_LAYOUT_FILTER)
    _LAYOUT_FILTER.align()
    _MENU = _create_options_menu(_BUTTON)
    _MENU_FILTER = _OptionsMenuEventFilter(_MENU, _BUTTON, normal_icon, hover_icon)
    _BUTTON.installEventFilter(_MENU_FILTER)
    _BUTTON.clicked.connect(_run_playblast)
    return _BUTTON
