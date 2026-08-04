"""场景数据收集、时间滑块音频读取与图像序列渲染工作流。

SceneSequenceData 持有一次拍屏所需的全部场景数据，并从当前场景收集；
render_sequence 把数据渲染为临时目录中的图像序列。
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from maya import cmds, mel
from maya.api import OpenMaya, OpenMayaUI

from pb_src.config import (
    DEFAULT_FRAME_FORMAT,
    DEFAULT_SCALE,
    FRAME_PADDING,
    SEQUENCE_NAME,
    _PLAYBLAST_DISPLAY_OPTIONS,
)


@dataclass
class SceneSequenceData:
    """一次拍屏所需的全部场景数据。

    Attributes:
        editor: 激活视图的 modelEditor 名。
        view_size: 视图（面板）尺寸（宽, 高）。
        render_size: Render Settings 分辨率；设置无效时为 None。
        fps: 场景帧率。
        start_time: 播放范围起点（场景时间单位）。
        end_time: 播放范围终点（场景时间单位）。
        audio_path: 时间滑块音频文件路径；场景无音频时 None。
        audio_start: 音频在时间轴上的开始时间（秒）。
        audio_end: 音频在时间轴上的结束时间（秒）。
        output_size: 最终输出分辨率；None 表示跟随视图尺寸（由 playblast 决策）。
        percent: 渲染百分比。
        frame_format: 单帧格式（jpg/png）。
        frame_padding: 帧编号补零位数。
    """

    editor: str
    view_size: tuple[int, int]
    render_size: tuple[int, int] | None
    fps: float
    start_time: float
    end_time: float
    audio_path: Path | None = None
    audio_start: float | None = None
    audio_end: float | None = None
    output_size: tuple[int, int] | None = None
    percent: int = DEFAULT_SCALE
    frame_format: str = DEFAULT_FRAME_FORMAT
    frame_padding: int = FRAME_PADDING

    @classmethod
    def instance_from_scene(cls) -> SceneSequenceData:
        """从当前场景收集全部拍屏数据（分辨率/音频决策留给 playblast）。"""
        editor, view_size = cls.get_active_panel()
        fps = cls.get_current_fps()
        start_time, end_time = cls.get_playback_range()

        audio_path = audio_start = audio_end = None
        audio_data = cls.get_playblast_audio()
        if audio_data is not None:
            audio_path, audio_start, audio_end = audio_data

        return cls(
            editor=editor,
            view_size=view_size,
            render_size=cls.get_render_size(),
            fps=fps,
            start_time=start_time,
            end_time=end_time,
            audio_path=audio_path,
            audio_start=audio_start,
            audio_end=audio_end,
        )

    @staticmethod
    def get_active_panel() -> tuple[str, tuple[int, int]]:
        """获取激活视图数据：modelEditor 名与视图逻辑尺寸。"""
        view = OpenMayaUI.M3dView.active3dView()
        name = cmds.playblast(activeEditor=True)
        width = view.portWidth()  # int
        height = view.portHeight()  # int
        return (name, (width, height))

    @staticmethod
    def get_current_fps() -> float:
        """查询当前场景FPS"""
        unit = OpenMaya.MTime.uiUnit()
        one_sec = OpenMaya.MTime(1.0, OpenMaya.MTime.kSeconds)
        return one_sec.asUnits(unit)

    @staticmethod
    def get_playback_range() -> tuple[float, float]:
        """查询当前播放范围（场景时间单位）。"""
        start_time = cmds.playbackOptions(query=True, minTime=True)
        end_time = cmds.playbackOptions(query=True, maxTime=True)
        return (start_time, end_time)

    @staticmethod
    def get_render_size() -> tuple[int, int] | None:
        """查询 Render Settings 分辨率；设置无效时返回 None。"""
        width = int(cmds.getAttr("defaultResolution.width"))
        height = int(cmds.getAttr("defaultResolution.height"))
        if width <= 0 or height <= 0:
            return None
        return (width, height)

    @staticmethod
    def _get_sound_node() -> str | None:
        """返回主时间滑块上挂载的声音节点名；没有则返回 None。"""
        time_controls = cmds.lsUI(type="timeControl")
        if not time_controls:
            return None
        sound = cmds.timeControl(time_controls[0], query=True, sound=True)
        return sound or None

    @staticmethod
    def to_seconds(value: float) -> float:
        """把 time 类型属性值从当前时间单位换算成秒。

        audio 节点的 offset/endFrame 等属性是 time 类型，
        cmds.getAttr 返回值跟随当前时间单位（帧/秒/…），必须统一换算成秒。
        """
        return OpenMaya.MTime(value, OpenMaya.MTime.uiUnit()).asUnits(OpenMaya.MTime.kSeconds)

    @classmethod
    def get_playblast_audio(cls) -> tuple[Path, float, float] | None:
        """获取时间滑块音频：返回 (文件路径, 开始秒, 结束秒)；无音频时返回 None。

        时间轴对齐语义（Maya audio 节点，均已实测验证）：
        - offset：音频整体在时间轴上右移的秒数，即音频在时间轴上的开始时间；
        - endFrame：音频在时间轴上的结束时间（含 offset 右移与 sourceStart 裁剪）。
        """
        node = cls._get_sound_node()
        if node is None:
            return None

        filename = str(cmds.getAttr(f"{node}.filename"))
        if not filename:
            return None

        start = cls.to_seconds(cmds.getAttr(f"{node}.offset"))
        end = cls.to_seconds(cmds.getAttr(f"{node}.endFrame"))
        return (Path(filename), start, end)


def _initialize_playblast_options() -> None:
    """初始化 Maya Playblast 缺失的基础与显示 optionVar。"""
    mel.eval('source "performPlayblast.mel";')
    mel.eval("setPlayblastOptionVars(false);")

    # Autodesk 的显示初始化过程不是 global proc，外部无法直接调用。
    for option in _PLAYBLAST_DISPLAY_OPTIONS:
        if not cmds.optionVar(exists=option):
            cmds.optionVar(intValue=(option, 1))


def render_sequence(
    data: SceneSequenceData,
) -> tuple[Path, Path, float, int]:
    """将指定视图输出为唯一临时目录中的图像序列。

    Args:
        data: 场景数据（含 editor、分辨率、时间范围与渲染选项）。

    Returns:
        (输出目录, 序列匹配模式, fps, 实际帧数)。
    """
    frame_format = data.frame_format.lower()
    frame_padding = data.frame_padding

    output_dir = Path(tempfile.mkdtemp(prefix="maya_playblast_"))
    sequence_prefix = output_dir / SEQUENCE_NAME
    sequence_pattern = output_dir / f"{SEQUENCE_NAME}.%0{frame_padding}d.{frame_format}"

    try:
        _initialize_playblast_options()
        mel.eval('source "doPlayblastArgList.mel";')
        mel.eval("getEditorViewVars();")
        try:
            mel.eval("setPlayblastViewVars();")
            cmds.playblast(
                filename=sequence_prefix.as_posix(),
                editorPanelName=data.editor,
                format="image",
                compression=frame_format,
                forceOverwrite=True,
                offScreen=data.output_size is not None,
                percent=data.percent,
                framePadding=frame_padding,
                indexFromZero=True,
                showOrnaments=bool(
                    cmds.optionVar(  # ty:ignore[no-matching-overload]
                        query="playblastShowOrnaments"
                    )
                ),
                throwOnError=True,
                widthHeight=data.output_size or data.view_size,
                viewer=False,
                startTime=data.start_time,
                endTime=data.end_time,
            )
        finally:
            mel.eval("restoreEditorViewVars();")

        if next(output_dir.glob(f"{SEQUENCE_NAME}.*.{frame_format}"), None) is None:
            raise RuntimeError("Maya did not create any playblast frames.")
    except Exception as err:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise RuntimeError(f"Write sequence error: {err}") from err
    frame_count = len(list(output_dir.glob(f"{SEQUENCE_NAME}.*.{frame_format}")))
    print(output_dir, sequence_pattern, data.fps, frame_count)
    return (output_dir, sequence_pattern, data.fps, frame_count)
