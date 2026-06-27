"""
Plugin !unhook — detecta y elimina hooks de seguridad activos en el proceso.
Verifica: LD_PRELOAD, tracers (anti-debug), librerías de hooking en memoria,
y procesos AV/EDR conocidos.
"""

import os
import subprocess


_AV_SIGNATURES = [
    "clamav", "clamd", "sophos", "crowdstrike", "falcon-sensor",
    "carbonblack", "cbagent", "sentinel", "sentineld", "cylance",
    "malwarebytes", "eset", "bitdefender", "fsav", "avast",
    "comodo", "fireeye", "xagt", "wdavdaemon",
]

_HOOK_LIBS = ["frida-agent", "frida_", "libinject", "dyninst", "valgrind", "libpintool"]


def run(args: str) -> tuple[int, str, str]:
    results = []

    # 1. LD_PRELOAD
    ld = os.environ.get("LD_PRELOAD", "")
    if ld:
        results.append(f"[!] LD_PRELOAD activo: {ld}")
        os.environ.pop("LD_PRELOAD", None)
        results.append("[+] LD_PRELOAD eliminado del entorno del proceso")
    else:
        results.append("[+] LD_PRELOAD limpio")

    # 2. Anti-debug: TracerPid en /proc/self/status
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("TracerPid:"):
                    tracer = int(line.split(":")[1].strip())
                    if tracer != 0:
                        results.append(f"[!] Proceso siendo trazado — TracerPid={tracer} (posible debugger/AV)")
                    else:
                        results.append("[+] Sin tracers activos (TracerPid=0)")
                    break
    except OSError:
        results.append("[?] No se pudo leer /proc/self/status")

    # 3. Librerías sospechosas en el mapa de memoria
    try:
        with open("/proc/self/maps") as f:
            maps = f.read().lower()
        found_libs = [lib for lib in _HOOK_LIBS if lib in maps]
        if found_libs:
            results.append(f"[!] Librerías de hooking detectadas en memoria: {found_libs}")
        else:
            results.append("[+] No se detectaron librerías de hooking en memoria")
    except OSError:
        results.append("[?] No se pudo leer /proc/self/maps")

    # 4. Procesos AV/EDR activos
    try:
        r = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        found_av = []
        for line in r.stdout.lower().splitlines():
            for sig in _AV_SIGNATURES:
                if sig in line and "grep" not in line:
                    found_av.append(line.strip())
                    break
        if found_av:
            results.append(f"[!] Procesos de seguridad detectados ({len(found_av)}):")
            results.extend(f"    {p}" for p in found_av)
        else:
            results.append("[+] No se detectaron procesos AV/EDR conocidos")
    except Exception as exc:
        results.append(f"[?] No se pudo listar procesos: {exc}")

    return 0, "\n".join(results), ""
