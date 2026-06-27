"""
Plugin !unhook — detecta y elimina hooks de seguridad activos en el proceso.
Verifica: LD_PRELOAD, tracers (anti-debug), librerías de hooking en memoria,
y procesos AV/EDR conocidos.
"""

import os
import platform
import subprocess
import sys


_AV_SIGNATURES = [
    "clamav", "clamd", "sophos", "crowdstrike", "falcon-sensor",
    "carbonblack", "cbagent", "sentinel", "sentineld", "cylance",
    "malwarebytes", "eset", "bitdefender", "fsav", "avast",
    "comodo", "fireeye", "xagt", "wdavdaemon",
    # Windows específicos
    "mssense", "msmpeng", "mpcmdrun", "mbamservice", "avgnt",
]

_HOOK_LIBS = ["frida-agent", "frida_", "libinject", "dyninst", "valgrind", "libpintool"]

_IS_WINDOWS = sys.platform == "win32"


def _check_ldpreload(results: list) -> None:
    if _IS_WINDOWS:
        results.append("[+] LD_PRELOAD no aplica en Windows")
        return
    ld = os.environ.get("LD_PRELOAD", "")
    if ld:
        results.append(f"[!] LD_PRELOAD activo: {ld}")
        os.environ.pop("LD_PRELOAD", None)
        results.append("[+] LD_PRELOAD eliminado del entorno del proceso")
    else:
        results.append("[+] LD_PRELOAD limpio")


def _check_debugger(results: list) -> None:
    if _IS_WINDOWS:
        try:
            import ctypes
            is_dbg = ctypes.windll.kernel32.IsDebuggerPresent()
            if is_dbg:
                results.append("[!] Debugger detectado (IsDebuggerPresent=True)")
            else:
                results.append("[+] Sin debugger activo (IsDebuggerPresent=False)")
        except Exception as exc:
            results.append(f"[?] No se pudo comprobar debugger en Windows: {exc}")
        return

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


def _check_hook_libs(results: list) -> None:
    if _IS_WINDOWS:
        try:
            import ctypes
            psapi = ctypes.windll.psapi
            kernel32 = ctypes.windll.kernel32
            buf = (ctypes.c_char_p * 1024)()
            count = ctypes.c_ulong()
            psapi.EnumProcessModules(
                kernel32.GetCurrentProcess(),
                ctypes.byref(buf), ctypes.sizeof(buf), ctypes.byref(count)
            )
            # Si falla, fallback silencioso
        except Exception:
            pass
        # En Windows leemos los módulos cargados con tasklist /m en el proceso actual
        try:
            pid = os.getpid()
            r = subprocess.run(
                ["tasklist", "/m", "/fi", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5
            )
            mods = r.stdout.lower()
            found = [lib for lib in _HOOK_LIBS if lib in mods]
            if found:
                results.append(f"[!] Librerías de hooking detectadas: {found}")
            else:
                results.append("[+] No se detectaron librerías de hooking en módulos cargados")
        except Exception as exc:
            results.append(f"[?] No se pudo listar módulos del proceso: {exc}")
        return

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


def _check_av_processes(results: list) -> None:
    try:
        if _IS_WINDOWS:
            r = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=5
            )
        else:
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


def run(args: str) -> tuple[int, str, str]:
    results = [f"[*] Plataforma: {platform.system()} {platform.release()}"]
    _check_ldpreload(results)
    _check_debugger(results)
    _check_hook_libs(results)
    _check_av_processes(results)
    return 0, "\n".join(results), ""
