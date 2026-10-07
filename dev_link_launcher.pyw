"""Abre enlaces OT de desarrollo sin mostrar una consola de PowerShell."""

import ctypes
import os
import subprocess
import traceback


def main():
    os.environ["MAXIMO_DESKTOP_DEV"] = "1"
    if os.name == "nt":
        running = subprocess.run(
            ["tasklist.exe", "/FI", "IMAGENAME eq MaximoDesktop.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if "maximodesktop.exe" in running.stdout.lower():
            ctypes.windll.user32.MessageBoxW(
                None, "Cierra Maximo Desktop estable antes de abrir la UI de desarrollo.",
                "Maximo Desktop - UI de desarrollo", 0x30,
            )
            return 1

    from ui_qt import main as run_ui
    return run_ui()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        from app_paths import LOG_DIR

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "deep_link_errors.log").open("a", encoding="utf-8") as log:
            traceback.print_exc(file=log)
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(
                None, "No se pudo abrir la OT. Consulta el registro de errores de Maximo Desktop.",
                "Maximo Desktop - UI de desarrollo", 0x10,
            )
