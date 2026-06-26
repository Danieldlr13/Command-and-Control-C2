"""
Plugin !screenshot — captura pantalla y devuelve ruta del archivo.
Intenta primero scrot, luego import (ImageMagick), luego gnome-screenshot.
"""

import os
import subprocess
import time


_OUT = "/tmp/nexus_screenshot.png"


def run(args: str) -> tuple[int, str, str]:
    tools = [
        ["scrot", "-o", _OUT],
        ["import", "-window", "root", _OUT],
        ["gnome-screenshot", "-f", _OUT],
        ["spectacle", "-b", "-o", _OUT],
    ]
    for cmd in tools:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and os.path.exists(_OUT):
                size = os.path.getsize(_OUT)
                return 0, f"Screenshot guardado en {_OUT} ({size} bytes)\n  Usa: !download file://{_OUT} /dest/path", ""
        except FileNotFoundError:
            continue
        except Exception:
            continue
    return 1, "", "No se encontró ninguna herramienta de screenshot (scrot, import, gnome-screenshot, spectacle)"
