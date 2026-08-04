from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
import maya.utils

from maya import cmds, mel
from maya.api import OpenMaya, OpenMayaUI

import imageio_ffmpeg  # ty:ignore[unresolved-import]

FFMPEG_PATH = Path(imageio_ffmpeg.get_ffmpeg_exe())

SEQUENCE_NAME = "SEQUENCE"

DEFAULT_FRAME_FORMAT = "jpg"
DEFAULT_CONTAINER = "mp4"
DEFAULT_CODEC = "h264"
DEFAULT_RESOLUTION = "view"
DEFAULT_SCALE = 100
DEFAULT_QUALITY = "high"
_LAST_OUTPUT_PATH_OPTION = "playblastToolsLastOutputPath"

FRAME_FORMATS = ("png", "jpg")
CONTAINER_CODECS = {
    "mp4": ("h264", "hevc", "av1"),
    "mov": ("h264", "hevc"),
    "mkv": ("h264", "hevc", "av1"),
}
CODEC_ENCODERS = {
    "h264": "libx264",
    "hevc": "libx265",
    "av1": "libaom-av1",
}
RESOLUTION_PRESETS = {
    "1280x720": (1280, 720),
    "1920x1080": (1920, 1080),
    "2560x1440": (2560, 1440),
    "3840x2160": (3840, 2160),
    "4096x2160": (4096, 2160),
}
RESOLUTION_CHOICES = (*RESOLUTION_PRESETS, "view", "render")
SCALES = (25, 50, 75, 100)
QUALITY_CRF = {
    "high": {"h264": "18", "hevc": "21", "av1": "28"},
    "medium": {"h264": "23", "hevc": "26", "av1": "34"},
    "low": {"h264": "28", "hevc": "31", "av1": "40"},
}

FRAME_PADDING = 4

_PLAYBLAST_DISPLAY_OPTIONS = (
    "playblastShowControllers",
    "playblastShowNURBSCurves",
    "playblastShowNURBSSurfaces",
    "playblastShowPolyMeshes",
    "playblastShowSubdivSurfaces",
    "playblastShowPlanes",
    "playblastShowLights",
    "playblastShowCameras",
    "playblastShowJoints",
    "playblastShowIKHandles",
    "playblastShowDeformers",
    "playblastShowDynamics",
    "playblastShowParticleInstancers",
    "playblastShowFluids",
    "playblastShowHairSystems",
    "playblastShowFollicles",
    "playblastShowNCloths",
    "playblastShowNParticles",
    "playblastShowNRigids",
    "playblastShowDynamicConstraints",
    "playblastShowLocators",
    "playblastShowDimensions",
    "playblastShowPivots",
    "playblastShowHandles",
    "playblastShowTextures",
    "playblastShowStrokes",
    "playblastShowMotionTrails",
    "playblastShowPluginShapes",
    "playblastShowManipulators",
    "playblastShowClipGhosts",
    "playblastShowBluePencil",
    "playblastShowCVs",
    "playblastShowHulls",
    "playblastShowGrid",
    "playblastShowHUD",
    "playblastShowHoldOuts",
    "playblastShowSelectionHighlighting",
    "playblastShowImagePlane",
)


def _validate_frame_format(frame_format: str) -> None:
    if frame_format not in FRAME_FORMATS:
        raise ValueError(
            f"Unsupported frame format: {frame_format}. "
            f"Expected one of: {', '.join(FRAME_FORMATS)}."
        )


def _validate_video_format(container: str, codec: str) -> None:
    if container not in CONTAINER_CODECS:
        raise ValueError(
            f"Unsupported video container: {container}. "
            f"Expected one of: {', '.join(CONTAINER_CODECS)}."
        )
    if codec not in CONTAINER_CODECS[container]:
        raise ValueError(f"{codec} is not supported in the {container} container.")


def _validate_scale(scale: int) -> None:
    if not 10 <= scale <= 100:
        raise ValueError("Resolution scale must be between 10 and 100 percent.")


def _validate_quality(quality: str) -> None:
    if quality not in QUALITY_CRF:
        raise ValueError(
            f"Unsupported video quality: {quality}. "
            f"Expected one of: {', '.join(QUALITY_CRF)}."
        )


def _resolve_width_height(resolution: str) -> tuple[int, int] | None:
    if resolution == "view":
        return None
    if resolution == "render":
        width = int(cmds.getAttr("defaultResolution.width"))
        height = int(cmds.getAttr("defaultResolution.height"))
        if width <= 0 or height <= 0:
            raise RuntimeError("Render Settings contains an invalid image size.")
        return (width, height)
    if resolution not in RESOLUTION_PRESETS:
        raise ValueError(
            f"Unsupported resolution: {resolution}. "
            f"Expected one of: {', '.join(RESOLUTION_CHOICES)}."
        )
    return RESOLUTION_PRESETS[resolution]


def _initialize_playblast_options() -> None:
    """初始化 Maya Playblast 缺失的基础与显示 optionVar。"""
    mel.eval('source "performPlayblast.mel";')
    mel.eval("setPlayblastOptionVars(false);")

    # Autodesk 的显示初始化过程不是 global proc，外部无法直接调用。
    for option in _PLAYBLAST_DISPLAY_OPTIONS:
        if not cmds.optionVar(exists=option):
            cmds.optionVar(intValue=(option, 1))


def _get_current_fps() -> float:
    """查询当前场景FPS"""
    unit = OpenMaya.MTime.uiUnit()
    one_sec = OpenMaya.MTime(1.0, OpenMaya.MTime.kSeconds)
    return one_sec.asUnits(unit)


def _get_active_panel_data():
    """获取激活视图数据"""
    view = OpenMayaUI.M3dView.active3dView()
    name = cmds.playblast(activeEditor=True)
    width = view.portWidth()  # int
    height = view.portHeight()  # int
    return (name, (width, height))


def _load_path(container: str) -> Path:
    """选择视频输出路径，并恢复 fileDialog2 打断的 viewport 焦点。"""
    starting_directory = ""
    if cmds.optionVar(exists=_LAST_OUTPUT_PATH_OPTION):
        previous_path = Path(str(cmds.optionVar(query=_LAST_OUTPUT_PATH_OPTION)))
        starting_directory = previous_path.parent.as_posix()

    active_editor, _ = _get_active_panel_data()
    try:
        dialog_path = cmds.fileDialog2(
            fileFilter=f"{container.upper()} Video (*.{container})",
            dialogStyle=2,
            caption="Select Video Save Location",
            startingDirectory=starting_directory,
            fileMode=0,
        )
    finally:
        _focus_panel(active_editor)

    if not dialog_path:
        raise RuntimeError("Please select output path.")

    output_path = Path(dialog_path[0])
    suffix = f".{container}"
    if output_path.suffix.lower() != suffix:
        output_path = output_path.with_suffix(suffix)

    cmds.optionVar(stringValue=(_LAST_OUTPUT_PATH_OPTION, output_path.as_posix()))
    cmds.savePrefs(general=True)
    return output_path


def _focus_panel(panel: str) -> str:
    """激活 modelPanel 或 modelEditor，并返回 modelEditor 名称。"""
    if cmds.modelPanel(panel, exists=True):
        editor = cmds.modelPanel(panel, query=True, modelEditor=True)
    elif cmds.modelEditor(panel, exists=True):
        editor = panel
    else:
        raise RuntimeError(f"Viewport panel/editor does not exist: {panel}")

    if not editor:
        raise RuntimeError(f"Viewport panel has no modelEditor: {panel}")
    editor = str(editor)
    cmds.modelEditor(editor, edit=True, activeView=True)
    return editor


def _playblast_sequence(
    panel: str | None = None,
    width_height: tuple[int, int] | None = None,
    percent: int = DEFAULT_SCALE,
    frame_padding: int = FRAME_PADDING,
    frame_format: str = DEFAULT_FRAME_FORMAT,
) -> tuple[Path, Path, float]:
    """将指定 viewport 输出为唯一临时目录中的图像序列。"""
    frame_format = frame_format.lower()
    _validate_frame_format(frame_format)
    _validate_scale(percent)

    if panel is None:
        editor, panel_size = _get_active_panel_data()
    else:
        editor = _focus_panel(panel)
        _, panel_size = _get_active_panel_data()
    editor = _focus_panel(editor)

    offscreen = width_height is not None
    if width_height is None:
        width_height = panel_size

    fps = _get_current_fps()
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
                editorPanelName=editor,
                format="image",
                compression=frame_format,
                forceOverwrite=True,
                offScreen=offscreen,
                percent=percent,
                framePadding=frame_padding,
                indexFromZero=True,
                showOrnaments=bool(cmds.optionVar(query="playblastShowOrnaments")),
                throwOnError=True,
                widthHeight=width_height,
                viewer=False,
            )
        finally:
            mel.eval("restoreEditorViewVars();")

        if next(output_dir.glob(f"{SEQUENCE_NAME}.*.{frame_format}"), None) is None:
            raise RuntimeError("Maya did not create any playblast frames.")
    except Exception as err:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise RuntimeError(f"Write sequence error: {err}") from err

    return (output_dir, sequence_pattern, fps)


def sequence_to_video(
    sequence_pattern: str | Path,
    fps: float,
    output_path: str | Path,
    container: str = DEFAULT_CONTAINER,
    codec: str = DEFAULT_CODEC,
    quality: str = DEFAULT_QUALITY,
    ffmpeg: str | Path = FFMPEG_PATH,
) -> Path:
    """使用 FFmpeg 将连续图像序列转换为视频。"""
    container = container.lower()
    codec = codec.lower()
    quality = quality.lower()
    _validate_video_format(container, codec)
    _validate_quality(quality)

    sequence_pattern = Path(sequence_pattern)
    output_path = Path(output_path)
    expected_suffix = f".{container}"
    if output_path.suffix.lower() != expected_suffix:
        raise ValueError(f"{container} output path must end with {expected_suffix}.")

    encoder = CODEC_ENCODERS[codec]
    crf = QUALITY_CRF[quality][codec]
    cmd = [
        Path(ffmpeg).as_posix(),
        "-y",
        "-framerate",
        f"{fps:g}",
        "-start_number",
        "0",
        "-i",
        sequence_pattern.as_posix(),
        "-c:v",
        encoder,
        "-vf",
        "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-pix_fmt",
        "yuv420p",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-crf",
        crf,
    ]
    if codec == "av1":
        cmd.extend(("-b:v", "0", "-cpu-used", "6"))
    if codec == "hevc" and container in {"mp4", "mov"}:
        cmd.extend(("-tag:v", "hvc1"))
    if container == "mp4":
        cmd.extend(("-movflags", "+faststart"))
    cmd.append(output_path.as_posix())

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"FFmpeg conversion failed: {err.stderr or err}") from err
    except FileNotFoundError as err:
        raise RuntimeError(f"FFmpeg not found: {ffmpeg}") from err
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
    auto_play: bool = False,
    clean_cache: bool = True,
) -> Path:
    """输出激活 viewport 为视频。

    Args:
        clean_cache: True 时转换完成后清理临时图像序列目录；
            False 时保留中间图片（便于排查 FFmpeg / 序列问题）。
    """
    frame_format = frame_format.lower()
    container = container.lower()
    codec = codec.lower()
    resolution = resolution.lower()
    quality = quality.lower()
    _validate_frame_format(frame_format)
    _validate_video_format(container, codec)
    _validate_scale(scale)
    _validate_quality(quality)
    width_height = _resolve_width_height(resolution)

    video_path = _load_path(container)
    sequence_dir, sequence_pattern, fps = _playblast_sequence(
        width_height=width_height,
        percent=scale,
        frame_format=frame_format,
    )

    try:
        result = sequence_to_video(
            sequence_pattern,
            fps,
            video_path,
            container=container,
            codec=codec,
            quality=quality,
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
            raise RuntimeError(
                f"Video created, but temporary directory cleanup failed: {sequence_dir}"
            ) from err
    else:
        print(f"Temporary image sequence kept at: {sequence_dir}")
    if auto_play:
        cmds.launch(movie=result.as_posix())
    maya.utils.executeDeferred(_notify_output_path, result.as_posix())
    return result


if __name__ == "__main__":
    playblast()
