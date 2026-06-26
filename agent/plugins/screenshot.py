"""
Plugin !screenshot — captura silenciosa multiplataforma.
Cadena de intentos por entorno:
  Linux Wayland → grim → spectacle -b -n → import (ImageMagick) → mss
  Linux X11     → scrot → import (ImageMagick) → mss
  Windows       → Pillow ImageGrab
  macOS         → screencapture -x
"""

import os
import platform
import subprocess

_OUT = "/tmp/nexus_screenshot.png"


def _try(cmd: list, out_path: str) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10)
        return r.returncode == 0 and os.path.exists(out_path)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def _mss(out_path: str) -> bool:
    try:
        import mss
        import mss.tools
        with mss.mss() as sct:
            img = sct.grab(sct.monitors[0])
            mss.tools.to_png(img.rgb, img.size, output=out_path)
        return os.path.exists(out_path)
    except Exception:
        return False


def _pillow(out_path: str) -> bool:
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(out_path)
        return os.path.exists(out_path)
    except Exception:
        return False


def run(args: str) -> tuple[int, str, str]:
    system = platform.system()

    if system == "Windows":
        out = os.path.join(os.environ.get("TEMP", "C:\\Windows\\Temp"), "nexus_screenshot.png")
        ok = _pillow(out) or _mss(out)
        path = out

    elif system == "Darwin":
        ok = _try(["screencapture", "-x", _OUT], _OUT)
        path = _OUT

    else:
        # Linux — detectar Wayland vs X11
        # Verificar variable de entorno Y proceso de display server
        session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if not session:
            # Fallback: detectar por proceso
            try:
                r = subprocess.run(["loginctl", "show-session", "", "-p", "Type"],
                                   capture_output=True, text=True, timeout=5)
                if "wayland" in r.stdout.lower():
                    session = "wayland"
            except Exception:
                pass

        path = _OUT

        if session == "wayland":
            ok = (
                _try(["grim", _OUT], _OUT) or
                _try(["spectacle", "-b", "-n", "-o", _OUT], _OUT) or
                _try(["import", "-window", "root", _OUT], _OUT) or
                _mss(_OUT)
            )
        else:
            # X11 o desconocido — intentar todo
            ok = (
                _try(["scrot", _OUT], _OUT) or
                _try(["spectacle", "-b", "-n", "-o", _OUT], _OUT) or
                _try(["import", "-window", "root", _OUT], _OUT) or
                _mss(_OUT) or
                _try(["gnome-screenshot", "-f", _OUT], _OUT)
            )

    if ok:
        size = os.path.getsize(path)
        return 0, f"Screenshot guardado en {path} ({size} bytes)\n  Usa: !download file://{path} /dest/path", ""

    return 1, "", (
        "No se pudo capturar pantalla.\n"
        "Linux Wayland: instala grim  →  sudo dnf install grim\n"
        "Linux X11:     instala scrot →  sudo dnf install scrot\n"
        "Cualquier OS:  pip install mss   o   pip install Pillow"
    )
