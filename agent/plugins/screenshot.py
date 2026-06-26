"""
Plugin !screenshot — captura pantalla y devuelve ruta del archivo.
Prueba herramientas del sistema; si ninguna está disponible usa mss (Python puro).
"""

import os
import subprocess


_OUT = "/tmp/nexus_screenshot.png"


def _try_system_tools() -> bool:
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
                return True
        except (FileNotFoundError, Exception):
            continue
    return False


def _try_mss() -> bool:
    try:
        import mss
        import mss.tools
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # monitor 0 = todos los monitores combinados
            img = sct.grab(monitor)
            mss.tools.to_png(img.rgb, img.size, output=_OUT)
        return os.path.exists(_OUT)
    except Exception:
        return False


def run(args: str) -> tuple[int, str, str]:
    if _try_system_tools() or _try_mss():
        size = os.path.getsize(_OUT)
        return 0, f"Screenshot guardado en {_OUT} ({size} bytes)\n  Usa: !download file://{_OUT} /dest/path", ""
    return 1, "", "No se pudo capturar pantalla (sin herramientas del sistema ni mss disponible)"
