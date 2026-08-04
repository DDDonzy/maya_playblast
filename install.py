from __future__ import annotations

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from urllib.request import Request, urlopen

from maya import cmds

this_python_file_path = Path(__file__)
project_path = this_python_file_path.parent

module = this_python_file_path.parent / "modules" / "playblastTools.mod"

sys.path.append(str(project_path))

FFMPEG_TARGET = project_path / "ffmpeg"
FFMPEG_MIRRORS = (
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
    with ThreadPoolExecutor(max_workers=len(FFMPEG_MIRRORS)) as pool:
        latency, index = min(pool.map(_probe, FFMPEG_MIRRORS))
    print(f"[mirror] {index} ({latency:.2f}s)")
    return index


def install_module():
    app_dir = cmds.internalVar(userAppDir=True)
    target_module = Path(app_dir) / "modules" / "playblastTools.mod"

    if module.exists():
        lines = module.read_text(encoding="utf-8").splitlines()
        if lines:
            first_line_parts = lines[0].split()
            if len(first_line_parts) >= 3:
                new_first_line = f"{first_line_parts[0]} {first_line_parts[1]} {first_line_parts[2]} {project_path.as_posix()}"
                lines[0] = new_first_line
                target_module.parent.mkdir(parents=True, exist_ok=True)
                target_module.write_text("\n".join(lines), encoding="utf-8")
                print(f'Modules path: "{target_module}"')
                print("Installation complete.")
            else:
                print(f"'{module}' file's first line does not have enough parts.")
    else:
        print("Installation failed, original .mod file not found.")


def _ensure_python_path() -> None:
    """把 .mod 注入的 PYTHONPATH 同步到当前会话（无需重启 Maya）。

    拖拽安装后 .mod 的环境变量要重启才生效，这里先补齐本次会话；
    下次启动由 .mod 正常接管。
    """
    for path in (
        project_path / "ffmpeg",
        project_path / "scripts",
        project_path / "pb_src",
    ):
        if str(path) not in sys.path:
            sys.path.append(str(path))


def install_ffmpeg() -> int:
    """Download and install FFmpeg (imageio-ffmpeg) into the project directory."""
    python = Path(sys.executable)
    if python.name.lower() == "maya.exe":
        python = python.with_name("mayapy.exe")
    index = _fastest_mirror()

    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--progress-bar=on",
            "--index-url",
            index,
            "--target",
            str(FFMPEG_TARGET),
            "imageio-ffmpeg",
        ],
        check=True,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    return 0


def onMayaDroppedPythonFile(*args, **kwargs):
    install_module()
    _ensure_python_path()
    try:
        install_ffmpeg()
    except Exception as err:  # noqa: BLE001
        cmds.warning(f"FFmpeg install failed: {err}")
        return
    # 安装成功（install_ffmpeg 抛异常则不会执行到这里）后挂载 UI 按钮
    from pb_src.ui import playblast_ui
    import maya.utils

    maya.utils.executeDeferred(playblast_ui.attach_button_in_maya)
