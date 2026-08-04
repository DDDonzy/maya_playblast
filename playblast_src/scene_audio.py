"""从 Maya 场景读取当前时间滑块上挂载的音频信息。

时间轴对齐语义（Maya audio 节点，均已实测验证）：
- ``offset``：音频整体在时间轴上右移的秒数，即音频在时间轴上的开始时间；
- ``endFrame``：音频在时间轴上的结束时间（含 offset 右移与 sourceStart 裁剪），
  随 ``offset`` / ``sourceStart`` / ``sourceEnd`` 自动维护，直接读取即可；
- ``filename``：音频源文件路径。
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from maya import cmds
from maya.api import OpenMaya


class SceneAudio(NamedTuple):
    """场景音频在时间轴上的位置信息。

    Attributes:
        path: 音频文件路径。
        start: 音频在时间轴上的开始时间（秒）。
        end: 音频在时间轴上的结束时间（秒）。
    """

    path: Path
    start: float
    end: float


def _get_sound_node() -> str | None:
    """返回主时间滑块上挂载的声音节点名；没有则返回 None。"""
    time_controls = cmds.lsUI(type="timeControl")
    if not time_controls:
        return None
    sound = cmds.timeControl(time_controls[0], query=True, sound=True)
    return sound or None


def to_seconds(value: float) -> float:
    """把 time 类型属性值从当前时间单位换算成秒。

    audio 节点的 offset/endFrame 等属性是 time 类型，
    cmds.getAttr 返回值跟随当前时间单位（帧/秒/…），必须统一换算成秒。
    """
    return OpenMaya.MTime(value, OpenMaya.MTime.uiUnit()).asUnits(OpenMaya.MTime.kSeconds)


def get_scene_audio() -> SceneAudio | None:
    """获取当前场景音频信息。

    Returns:
        音频路径与时间轴起止时间（秒）；场景无音频（或音频无源文件）时返回 None。
    """
    node = _get_sound_node()
    if node is None:
        return None

    filename = str(cmds.getAttr(f"{node}.filename"))
    if not filename:
        return None

    start = to_seconds(cmds.getAttr(f"{node}.offset"))
    end = to_seconds(cmds.getAttr(f"{node}.endFrame"))
    return SceneAudio(Path(filename), start, end)
