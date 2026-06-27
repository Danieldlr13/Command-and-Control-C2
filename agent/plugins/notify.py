"""
Plugin !notify — muestra un mensaje en la pantalla del equipo vulnerado.
!notify <mensaje>  → notificación de escritorio en tiempo real
"""

import os
import shutil
import subprocess
import sys


def run(args: str) -> tuple[int, str, str]:
    msg = args.strip()
    if not msg:
        return 1, "", "uso: !notify <mensaje>"

    title = "Nexus C2"

    if sys.platform == "win32":
        try:
            safe_msg = msg.replace('"', '`"')
            subprocess.Popen([
                "powershell", "-WindowStyle", "Hidden", "-Command",
                f'Add-Type -AssemblyName System.Windows.Forms;'
                f'[System.Windows.Forms.MessageBox]::Show("{safe_msg}","{title}")',
            ])
            return 0, f"Ventana mostrada en Windows: {msg}", ""
        except Exception as exc:
            return 1, "", f"Error PowerShell: {exc}"

    if sys.platform == "darwin":
        try:
            subprocess.Popen(["osascript", "-e",
                              f'display dialog "{msg}" with title "{title}" buttons {{"OK"}}'])
            return 0, f"Diálogo mostrado en macOS: {msg}", ""
        except Exception as exc:
            return 1, "", f"Error osascript: {exc}"

    # Linux — cadena de intentos
    env = os.environ.copy()

    # 1. notify-send — notificación nativa del escritorio
    if shutil.which("notify-send"):
        try:
            r = subprocess.run(
                ["notify-send", "--urgency=critical", "--expire-time=0", title, msg],
                capture_output=True, timeout=5, env=env,
            )
            if r.returncode == 0:
                return 0, f"Notificación enviada al escritorio: {msg}", ""
        except Exception:
            pass

    # 2. zenity — ventana de alerta que bloquea hasta que la cierren
    if shutil.which("zenity"):
        try:
            subprocess.Popen(
                ["zenity", "--warning", f"--text={msg}", f"--title={title}",
                 "--width=400"],
                env=env,
            )
            return 0, f"Ventana de alerta abierta: {msg}", ""
        except Exception:
            pass

    # 3. xmessage — fallback X11 clásico
    if shutil.which("xmessage"):
        try:
            subprocess.Popen(["xmessage", "-center", f"{title}\n\n{msg}"], env=env)
            return 0, f"xmessage mostrado: {msg}", ""
        except Exception:
            pass

    # 4. wall — escribe en todos los terminales abiertos (sin GUI)
    if shutil.which("wall"):
        try:
            subprocess.run(["wall"], input=f"\n[{title}] {msg}\n",
                           capture_output=True, timeout=5, text=True)
            return 0, f"Mensaje enviado a terminales via wall: {msg}", ""
        except Exception:
            pass

    return 1, "", "No se encontró notify-send, zenity, xmessage ni wall en el sistema"
