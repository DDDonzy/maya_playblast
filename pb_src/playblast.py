"""Playblast 最终执行入口。

场景收集与序列渲染在 scene_sequence，FFmpeg 合成在 video，本文件只负责
参数校验、输出路径选择与整体流程编排。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import maya.utils

from maya import cmds

from pb_src import scene_sequence, video
from pb_src.scene_sequence import SceneSequenceData
from pb_src.config import (
    DEFAULT_CODEC,
    DEFAULT_CONTAINER,
    DEFAULT_FRAME_FORMAT,
    DEFAULT_QUALITY,
    DEFAULT_RESOLUTION,
    DEFAULT_SCALE,
    RESOLUTION_CHOICES,
    RESOLUTION_PRESETS,
    _LAST_OUTPUT_PATH_OPTION,
    ensure_frame_format,
    ensure_quality,
    ensure_scale,
    ensure_video_format,
)


def select_output_path(container: str) -> Path:
    """弹窗选择视频输出路径，并记忆上次目录供下次使用。"""
    starting_directory = ""
    if cmds.optionVar(exists=_LAST_OUTPUT_PATH_OPTION):
        previous_path = Path(
            str(
                cmds.optionVar(  # ty:ignore[no-matching-overload]
                    query=_LAST_OUTPUT_PATH_OPTION
                )
            )
        )
        starting_directory = previous_path.parent.as_posix()

    dialog_path = cmds.fileDialog2(
        fileFilter=f"{container.upper()} Video (*.{container})",
        dialogStyle=2,
        caption="Select Video Save Location",
        startingDirectory=starting_directory,
        fileMode=0,
    )
    if not dialog_path:
        raise RuntimeError("Please select output path.")

    output_path = Path(dialog_path[0])
    suffix = f".{container}"
    if output_path.suffix.lower() != suffix:
        output_path = output_path.with_suffix(suffix)

    cmds.optionVar(stringValue=(_LAST_OUTPUT_PATH_OPTION, output_path.as_posix()))
    cmds.savePrefs(general=True)
    return output_path


def _notify_output_path(output_path: str) -> None:
    cmds.inViewMessage(amg=output_path, pos="botCenter", fade=True)
    print(output_path)


def playblast(
    frame_format: str = DEFAULT_FRAME_FORMAT,
    container: str = DEFAULT_CONTAINER,
    codec: str = DEFAULT_CODEC,
    resolution: str = DEFAULT_RESOLUTION,
    scale: int = DEFAULT_SCALE,
    quality: str = DEFAULT_QUALITY,
    auto_play: bool = True,
    clean_cache: bool = True,
    sound: bool = True,
) -> Path:
    """输出激活 viewport 为视频。

    Args:
        clean_cache: True 时转换完成后清理临时图像序列目录；
            False 时保留中间图片（便于排查 FFmpeg / 序列问题）。
        sound: True 时从场景时间滑块读取音频并混入视频；
            场景无音频时警告并继续输出无声视频。
    """
    frame_format = frame_format.lower()
    container = container.lower()
    codec = codec.lower()
    resolution = resolution.lower()
    quality = quality.lower()

    ensure_frame_format(frame_format)
    ensure_video_format(container, codec)
    ensure_scale(scale)
    ensure_quality(quality)

    # 命令最开始记录 panel 等场景数据，后续弹窗不依赖视图焦点
    data = SceneSequenceData.instance_from_scene()
    # 输出分辨率决策：view 用视图尺寸、render 用 Render Settings、否则查预设表
    if resolution == "view":
        data.output_size = None
    elif resolution == "render":
        if data.render_size is None:
            raise RuntimeError("Render Settings contains an invalid image size.")
        data.output_size = data.render_size
    elif resolution in RESOLUTION_PRESETS:
        data.output_size = RESOLUTION_PRESETS[resolution]
    else:
        raise ValueError(f"Unsupported resolution: {resolution}. Expected one of: {', '.join(RESOLUTION_CHOICES)}.")
    if sound and data.audio_path is None:
        cmds.warning("No audio loaded on the time slider; exporting without sound.")
    # 渲染选项填入数据（frame_padding 使用 dataclass 默认值 4）
    data.percent = scale
    data.frame_format = frame_format

    output_path = select_output_path(container)

    sequence_dir, sequence_pattern, fps, frame_count = scene_sequence.render_sequence(data)

    try:
        result = video.sequence_to_video(
            sequence_pattern,
            fps,
            output_path,
            container=container,
            codec=codec,
            quality=quality,
            audio_path=data.audio_path if sound else None,
            audio_start=data.audio_start or 0.0,
            start_time=SceneSequenceData.to_seconds(data.start_time),
            frame_count=frame_count,
        )
    except Exception:
        if clean_cache:
            shutil.rmtree(sequence_dir, ignore_errors=True)
        raise

    if clean_cache:
        try:
            shutil.rmtree(sequence_dir)
        except FileNotFoundError:
            pass
        except OSError as err:
            raise RuntimeError(f"Video created, but temporary directory cleanup failed: {sequence_dir}") from err
    else:
        print(f"Temporary image sequence kept at: {sequence_dir}")
    if auto_play:
        cmds.launch(movie=result.as_posix())
    maya.utils.executeDeferred(_notify_output_path, result.as_posix())
    return result


if __name__ == "__main__":
    playblast()
