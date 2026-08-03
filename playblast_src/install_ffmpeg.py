"""Install FFmpeg into the project directory."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from urllib.request import Request, urlopen

import subprocess
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "ffmpeg"
MIRRORS = (
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://mirrors.cloud.tencent.com/pypi/simple",
    "https://repo.huaweicloud.com/repository/pypi/simple",
    "https://pypi.org/simple",
)


def _probe(index: str) -> tuple[float, str]:
    start = perf_counter()
    try:
        request = Request(f"{index}/imageio-ffmpeg/", headers={"User-Agent": "pip"})
        with urlopen(request, timeout=3) as response:
            response.read(1)
        return (perf_counter() - start, index)
    except OSError:
        return (float("inf"), index)


def _fastest_mirror() -> str:
    with ThreadPoolExecutor(max_workers=len(MIRRORS)) as pool:
        latency, index = min(pool.map(_probe, MIRRORS))
    print(f"[mirror] {index} ({latency:.2f}s)")
    return index


def install() -> int:
    python = Path(sys.executable)
    if python.name.lower() == "maya.exe":
        python = python.with_name("mayapy.exe")
    index = _fastest_mirror()

    subprocess.run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--progress-bar=on",
            "--index-url",
            index,
            "--target",
            TARGET,
            "imageio-ffmpeg",
        ],
        check=True,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    return 0
