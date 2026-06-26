import os
import platform
import socket
import subprocess


def run(args: str) -> tuple[int, str, str]:
    lines = [
        "╔══════════════════════════════╗",
        "║    NEXUS C2 — SYSINFO        ║",
        "╚══════════════════════════════╝",
        f"OS        : {platform.system()} {platform.release()} ({platform.machine()})",
        f"Distro    : {platform.platform()}",
        f"Hostname  : {socket.gethostname()}",
        f"User      : {os.getenv('USER', os.getenv('USERNAME', 'unknown'))}",
        f"UID       : {os.getuid() if hasattr(os, 'getuid') else 'N/A'}",
        f"PID       : {os.getpid()}",
        f"CWD       : {os.getcwd()}",
    ]

    # Network interfaces
    try:
        r = subprocess.run(["ip", "-br", "addr"], capture_output=True, text=True, timeout=5)
        if r.stdout.strip():
            lines += ["", "─── Interfaces de red ───────────────", r.stdout.strip()]
    except Exception:
        try:
            r = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=5)
            if r.stdout.strip():
                lines += ["", "─── Interfaces (ifconfig) ───────────", r.stdout.strip()]
        except Exception:
            pass

    # Active sessions
    try:
        r = subprocess.run(["who"], capture_output=True, text=True, timeout=5)
        if r.stdout.strip():
            lines += ["", "─── Sesiones activas ────────────────", r.stdout.strip()]
    except Exception:
        pass

    # Sudoers check
    try:
        r = subprocess.run(["sudo", "-n", "-l"], capture_output=True, text=True, timeout=5)
        out = (r.stdout + r.stderr).strip()
        if out:
            lines += ["", "─── Privilegios sudo ────────────────", out]
    except Exception:
        pass

    return 0, "\n".join(lines), ""
