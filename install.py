from __future__ import annotations

import sys
from pathlib import Path

from maya import cmds

this_python_file_path = Path(__file__)
project_path = this_python_file_path.parent

module = this_python_file_path.parent / "modules" / "playblastTools.mod"

sys.path.append(str(project_path))


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


def onMayaDroppedPythonFile(*args, **kwargs):
    from playblast_src import install_ffmpeg

    install_module()
    install_ffmpeg.install()
