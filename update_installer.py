"""Aplica una actualización descargada tras cerrar Maximo Desktop."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path


def start_update(installed_executable: Path, source_dir: Path) -> None:
    """Lanza un script externo: espera el cierre, copia y reinicia la app."""
    executable = Path(installed_executable).resolve()
    source = Path(source_dir).resolve()
    script = source.parent / "apply-update.cmd"
    script.write_text(
        "@echo off\r\nsetlocal\r\n"
        f"set \"PID_TO_WAIT={os.getpid()}\"\r\n"
        f"set \"TARGET={executable.parent}\"\r\nset \"SOURCE={source}\"\r\n"
        ":wait_for_app\r\n"
        "tasklist /FI \"PID eq %PID_TO_WAIT%\" /NH | find \"%PID_TO_WAIT%\" >nul\r\n"
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait_for_app)\r\n"
        "xcopy \"%SOURCE%\\*\" \"%TARGET%\\\" /E /I /Y /Q >nul\r\n"
        f"start \"\" \"%TARGET%\\{executable.name}\"\r\ndel \"%~f0\"\r\n",
        encoding="utf-8",
    )
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(["cmd.exe", "/c", str(script)], close_fds=True, creationflags=flags)
