"""Playblast UI 预设的存储与校验层。

只负责 preset 文件（presets/*.json）的读写与内容校验，
菜单交互（应用/保存/删除）由 playblast_ui 负责。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

from pb_src.config import (
    CONTAINER_CODECS,
    FRAME_FORMATS,
    QUALITY_CRF,
    RESOLUTION_CHOICES,
    SCALES,
)

DEFAULT_PRESET_NAME = "Default"
PRESET_DIR = Path(__file__).resolve().parent.parent.parent / "presets"
INVALID_PRESET_NAME = re.compile(r'[<>:"/\\|?*]')


def normalize_preset(data: object) -> dict[str, object]:
    """校验并归一化 preset 内容；非法内容抛 ValueError。"""
    if not isinstance(data, dict):
        raise ValueError("Preset root must be a JSON object.")

    frame_format = str(data.get("frame_format", "")).lower()
    container = str(data.get("container", "")).lower()
    codec = str(data.get("codec", "")).lower()
    resolution = str(data.get("resolution", "")).lower()
    quality = str(data.get("quality", "")).lower()
    scale = data.get("scale")
    auto_play = data.get("auto_play")
    sound = data.get("sound")

    if frame_format not in FRAME_FORMATS:
        raise ValueError(f"Invalid frame format: {frame_format}")
    if container not in CONTAINER_CODECS:
        raise ValueError(f"Invalid container: {container}")
    if codec not in CONTAINER_CODECS[container]:
        raise ValueError(f"Invalid codec for {container}: {codec}")
    if resolution not in RESOLUTION_CHOICES:
        raise ValueError(f"Invalid resolution: {resolution}")
    if isinstance(scale, bool) or scale not in SCALES:
        raise ValueError(f"Invalid scale: {scale}")
    if quality not in QUALITY_CRF:
        raise ValueError(f"Invalid quality: {quality}")
    if type(auto_play) is not bool:
        raise ValueError(f"Invalid Auto Play value: {auto_play}")
    # 旧版 preset 没有 sound 键，默认 False，避免整份 preset 被忽略。
    if sound is None:
        sound = False
    elif type(sound) is not bool:
        raise ValueError(f"Invalid Sound value: {sound}")

    return {
        "frame_format": frame_format,
        "container": container,
        "codec": codec,
        "resolution": resolution,
        "scale": scale,
        "quality": quality,
        "auto_play": auto_play,
        "sound": sound,
    }


def load_presets(
    default_settings: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    """读取全部 preset；Default 缺失或与默认值不一致时自动重建。"""
    default_path = PRESET_DIR / f"{DEFAULT_PRESET_NAME}.json"
    try:
        stored_default = normalize_preset(json.loads(default_path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        stored_default = None
    if stored_default != default_settings:
        save_preset(DEFAULT_PRESET_NAME, default_settings)

    presets = {}
    for path in sorted(PRESET_DIR.glob("*.json"), key=lambda item: item.stem.casefold()):
        try:
            presets[path.stem] = normalize_preset(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, ValueError) as err:
            print(f'Ignoring invalid preset "{path}": {err}')
    return presets


def save_preset(name: str, settings: Mapping[str, object]) -> Path:
    """把 preset 写入 JSON 文件（原子替换）。"""
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    path = PRESET_DIR / f"{name}.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def delete_preset(name: str) -> None:
    """删除指定 preset 文件。"""
    (PRESET_DIR / f"{name}.json").unlink()


def is_valid_name(name: str) -> bool:
    """名称合法：非 Default、无 Windows 非法字符、无尾随点或空格。"""
    return not (name.casefold() == DEFAULT_PRESET_NAME.casefold() or INVALID_PRESET_NAME.search(name) or name != name.rstrip(". "))
