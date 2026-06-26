import requests

MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def run(args: str) -> tuple[int, str, str]:
    """Download a remote file to disk. Usage: !download <url> <dest_path>"""
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        return 1, "", "uso: !download <url> <ruta_destino>"
    url, dest = parts[0], parts[1]
    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            total = 0
            for chunk in resp.iter_content(65536):
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    return 1, "", f"descarga cancelada: supera el límite de {MAX_DOWNLOAD_BYTES // 1024 // 1024} MB"
                f.write(chunk)
        return 0, f"OK — {total} bytes descargados → {dest}", ""
    except Exception as exc:
        return 1, "", str(exc)
