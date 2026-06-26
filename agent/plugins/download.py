import requests


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
                f.write(chunk)
                total += len(chunk)
        return 0, f"OK — {total} bytes descargados → {dest}", ""
    except Exception as exc:
        return 1, "", str(exc)
