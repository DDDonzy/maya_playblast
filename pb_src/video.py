"""纯 FFmpeg 视频合成模块（不依赖 Maya）。

把连续图像序列（可选音频）合成为目标容器/编码的视频文件。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg  # ty:ignore[unresolved-import]

from pb_src.config import (
    CODEC_ENCODERS,
    DEFAULT_CODEC,
    DEFAULT_CONTAINER,
    DEFAULT_QUALITY,
    QUALITY_CRF,
    ensure_quality,
    ensure_video_format,
)

FFMPEG_PATH = Path(imageio_ffmpeg.get_ffmpeg_exe())


def sequence_to_video(
    sequence_pattern: str | Path,
    fps: float,
    output_path: str | Path,
    container: str = DEFAULT_CONTAINER,
    codec: str = DEFAULT_CODEC,
    quality: str = DEFAULT_QUALITY,
    audio_path: Path | None = None,
    audio_start: float = 0.0,
    start_time: float = 0.0,
    frame_count: int | None = None,
    ffmpeg: str | Path = FFMPEG_PATH,
) -> Path:
    """使用 FFmpeg 将连续图像序列转换为视频。

    Args:
        sequence_pattern: 图像序列匹配模式（如 dir/SEQUENCE.%04d.jpg）。
        fps: 帧率。
        output_path: 输出视频路径。
        container: 容器格式（mp4/mov/mkv）。
        codec: 视频编码（h264/hevc/av1）。
        quality: 画质档位（high/medium/low）。
        audio_path: 音频文件路径；None 时不带音轨。
        audio_start: 音频在时间轴上的开始时间（秒），用于对齐。
        start_time: 拍屏范围起点（秒），用于音频与视频的时间轴对齐。
        frame_count: 序列实际帧数，用于计算视频时长并精确裁切音频。
        ffmpeg: ffmpeg 可执行文件路径。
    """
    container = container.lower()
    codec = codec.lower()
    quality = quality.lower()
    ensure_video_format(container, codec)
    ensure_quality(quality)

    sequence_pattern = Path(sequence_pattern)
    output_path = Path(output_path)
    expected_suffix = f".{container}"
    if output_path.suffix.lower() != expected_suffix:
        raise ValueError(f"{container} output path must end with {expected_suffix}.")

    audio_input: list[str] = []
    audio_output: list[str] = []
    if audio_path is not None:
        if frame_count is None or frame_count <= 0:
            raise ValueError("frame_count is required when audio is provided.")
        video_duration = frame_count / fps
        # 音频时间轴起点 = audio_start；视频 0 时刻 = 时间轴起点。
        # skip：音频已早于视频开始的部分（跳过文件开头）；
        # delay：音频晚于视频开始的部分（补静音）；
        # audio_len：只裁音频不裁视频，避免 -shortest 提前截断视频。
        skip = max(0.0, start_time - audio_start)
        delay = max(0.0, audio_start - start_time)
        audio_len = video_duration - delay
        if audio_len <= 0:
            print(
                f"audio starts after the playblast range ends; "
                f"exporting without sound: {audio_path}"
            )
        else:
            if skip > 0:
                audio_input.extend(("-ss", f"{skip:g}"))
            audio_input.extend(("-t", f"{audio_len:g}", "-i", audio_path.as_posix()))
            audio_output.extend(("-c:a", "aac", "-b:a", "192k"))
            delay_ms = int(round(delay * 1000))
            if delay_ms > 0:
                audio_output.extend(("-af", f"adelay={delay_ms}:all=1"))

    cmd = [
        Path(ffmpeg).as_posix(),
        "-y",
        "-framerate",
        f"{fps:g}",
        "-start_number",
        "0",
        "-i",
        sequence_pattern.as_posix(),
    ]
    cmd.extend(audio_input)
    cmd.extend(
        [
            "-c:v",
            CODEC_ENCODERS[codec],
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
            QUALITY_CRF[quality][codec],
        ]
    )
    cmd.extend(audio_output)
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
