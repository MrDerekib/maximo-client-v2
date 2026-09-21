"""Aplica una actualización descargada tras cerrar Maximo Desktop."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app_paths import LOG_DIR


def start_update(installed_executable: Path, source_dir: Path) -> None:
    """Lanza un script externo: espera el cierre, copia y reinicia la app."""
    executable = Path(installed_executable).resolve()
    source = Path(source_dir).resolve()
    script = source.parent / "apply-update.cmd"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "update-installer.log"
    script.write_text(
        "@echo off\r\nsetlocal EnableExtensions\r\n"
        f"set \"PID_TO_WAIT={os.getpid()}\"\r\n"
        f"set \"TARGET={executable.parent}\"\r\nset \"SOURCE={source}\"\r\n"
        f"set \"LOG={log_path}\"\r\n"
        "call :log \"Inicio del aplicador de actualización.\"\r\n"
        ":wait_for_app\r\n"
        "tasklist /FI \"PID eq %PID_TO_WAIT%\" /NH | find \"%PID_TO_WAIT%\" >nul\r\n"
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait_for_app)\r\n"
        "call :log \"Cerrada la aplicación. Copiando archivos nuevos.\"\r\n"
        "xcopy \"%SOURCE%\\*\" \"%TARGET%\\\" /E /I /Y /Q >> \"%LOG%\" 2>&1\r\n"
        "if errorlevel 1 goto :failed\r\n"
        "call :log \"Archivos copiados. Iniciando Maximo Desktop.\"\r\n"
        f"start \"\" \"%TARGET%\\{executable.name}\"\r\n"
        "if errorlevel 1 goto :failed\r\n"
        "call :log \"Actualización aplicada correctamente.\"\r\n"
        "del \"%~f0\"\r\nexit /b 0\r\n"
        ":failed\r\n"
        "call :log \"ERROR: no se pudo completar la actualización.\"\r\n"
        "exit /b 1\r\n"
        ":log\r\n"
        ">> \"%LOG%\" echo [%date% %time%] %~1\r\n"
        "exit /b 0\r\n",
        encoding="utf-8",
    )
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(["cmd.exe", "/c", str(script)], close_fds=True, creationflags=flags)
