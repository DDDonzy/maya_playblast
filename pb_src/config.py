"""Playblast 工具的常量与选项配置。

纯配置模块，无 Maya / Qt 依赖，供 playblast / scene_sequence / video / ui 引用。
"""

from __future__ import annotations

SEQUENCE_NAME = "SEQUENCE"
FRAME_PADDING = 4

DEFAULT_FRAME_FORMAT = "jpg"
DEFAULT_CONTAINER = "mp4"
DEFAULT_CODEC = "h264"
DEFAULT_RESOLUTION = "view"
DEFAULT_SCALE = 100
DEFAULT_QUALITY = "high"

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

_LAST_OUTPUT_PATH_OPTION = "playblastToolsLastOutputPath"

_AUTO_PLAY_OPTION = "playblastToolsAutoPlay"
_SOUND_OPTION = "playblastToolsSound"
_FRAME_FORMAT_OPTION = "playblastToolsFrameFormat"
_CONTAINER_OPTION = "playblastToolsContainer"
_CODEC_OPTION = "playblastToolsCodec"
_RESOLUTION_OPTION = "playblastToolsResolution"
_SCALE_OPTION = "playblastToolsScale"
_QUALITY_OPTION = "playblastToolsQuality"
_PRESET_OPTION = "playblastToolsPreset"


def ensure_frame_format(frame_format: str) -> None:
    if frame_format not in FRAME_FORMATS:
        raise ValueError(
            f"Unsupported frame format: {frame_format}. "
            f"Expected one of: {', '.join(FRAME_FORMATS)}."
        )


def ensure_video_format(container: str, codec: str) -> None:
    if container not in CONTAINER_CODECS:
        raise ValueError(
            f"Unsupported video container: {container}. "
            f"Expected one of: {', '.join(CONTAINER_CODECS)}."
        )
    if codec not in CONTAINER_CODECS[container]:
        raise ValueError(f"{codec} is not supported in the {container} container.")


def ensure_scale(scale: int) -> None:
    if not 10 <= scale <= 100:
        raise ValueError("Resolution scale must be between 10 and 100 percent.")


def ensure_quality(quality: str) -> None:
    if quality not in QUALITY_CRF:
        raise ValueError(
            f"Unsupported video quality: {quality}. "
            f"Expected one of: {', '.join(QUALITY_CRF)}."
        )
