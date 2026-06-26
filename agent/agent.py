import json
import logging
import os
import random
import socket
import subprocess
import time
import uuid

import requests
from cryptography.exceptions import InvalidTag

from protocol import (
    MSG_NOP, MSG_TASK, MSG_RESULT, MSG_BEACON, MSG_ERROR, MSG_NAMES,
    build_frame, parse_frame, encode_beacon, esperar_beacon,
    agent_handshake, agent_process_welcome,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexus.agent")

SERVER_URL       = os.environ.get("NEXUS_SERVER", "http://127.0.0.1:8080")
AGENT_ID_FILE    = "agent_id.txt"
MAX_OUTPUT_BYTES = 64 * 1024   # 64 KB — truncate before sending
_MAX_BACKOFF     = 300.0       # 5 min cap on reconnect sleep


# ── Identity ───────────────────────────────────────────────────────────────────

def load_or_create_agent_id() -> str:
    # Direct override — useful for multi-agent deployments on the same host
    if direct := os.environ.get("NEXUS_AGENT_ID", "").strip():
        return direct
    if os.path.exists(AGENT_ID_FILE):
        with open(AGENT_ID_FILE) as f:
            aid = f.read().strip()
        if aid:
            return aid
    aid = str(uuid.uuid4())
    with open(AGENT_ID_FILE, "w") as f:
        f.write(aid)
    log.info("new agent_id=%s (saved to %s)", aid, AGENT_ID_FILE)
    return aid


def _load_server_pub() -> bytes:
    """Load server static public key (key pinning). Env var > file > error."""
    hex_key = os.environ.get("NEXUS_SERVER_PUB", "")
    if not hex_key and os.path.exists("server_pub.hex"):
        with open("server_pub.hex") as f:
            hex_key = f.read().strip()
    if not hex_key:
        raise RuntimeError(
            "Server public key not configured. "
            "Set NEXUS_SERVER_PUB env var or run server first to generate server_pub.hex"
        )
    try:
        pub = bytes.fromhex(hex_key)
    except ValueError as exc:
        raise RuntimeError(f"Invalid server public key (not valid hex): {exc}") from exc
    if len(pub) != 32:
        raise RuntimeError(f"Invalid server public key: expected 32 bytes, got {len(pub)}")
    return pub


def _backoff(attempt: int) -> float:
    """Exponential backoff: 10s, 20s, 40s … capped at 5 min, with ±10% jitter."""
    base = min(10.0 * (2 ** min(attempt, 8)), _MAX_BACKOFF)
    return base * (0.9 + random.random() * 0.2)


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _post(session: requests.Session, frame: bytes, session_id_hex: str = "") -> bytes:
    headers = {"Content-Type": "application/octet-stream"}
    if session_id_hex:
        headers["X-Session-Id"] = session_id_hex
    resp = session.post(SERVER_URL + "/", data=frame, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.content


# ── Handshake ─────────────────────────────────────────────────────────────────

def _do_handshake(session: requests.Session, server_pub: bytes):
    """X25519 ECDH handshake with key pinning. Returns (session_id_hex, chacha, agent_nonce)."""
    hello, agent_priv, agent_pub = agent_handshake(server_pub)
    welcome_raw = _post(session, hello)
    # expected_server_pub enforces key pinning — raises ValueError on mismatch
    session_id, _, chacha, agent_nonce = agent_process_welcome(
        welcome_raw, agent_priv, agent_pub, expected_server_pub=server_pub
    )
    return session_id.hex(), chacha, agent_nonce


# ── Output truncation ─────────────────────────────────────────────────────────

def _trunc(s: str) -> str:
    encoded = s.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return s
    return encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace") + "\n[truncated]"


# ── Task execution ─────────────────────────────────────────────────────────────

def _run_task(
    session: requests.Session,
    agent_id: str,
    payload: bytes,
    chacha,
    agent_nonce,
    sid_hex: str,
) -> None:
    try:
        task    = json.loads(payload)
        task_id = task.get("task_id", "?")
        cmd     = task.get("cmd", "")
        timeout = int(task.get("timeout_s", 30))
    except Exception as exc:
        log.error("parse TASK: %s", exc)
        return

    log.info("TASK  task_id=%.8s cmd=%r", task_id, cmd)
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
        )
        result = {
            "agent_id":  agent_id,
            "task_id":   task_id,
            "exit_code": proc.returncode,
            "stdout":    _trunc(proc.stdout),
            "stderr":    _trunc(proc.stderr),
            "ts":        int(time.time()),
        }
    except subprocess.TimeoutExpired:
        result = {
            "agent_id":  agent_id,
            "task_id":   task_id,
            "exit_code": -1,
            "stdout":    "",
            "stderr":    f"timeout after {timeout}s",
            "ts":        int(time.time()),
        }

    frame = build_frame(MSG_RESULT, json.dumps(result).encode(), chacha, agent_nonce)
    _post(session, frame, sid_hex)
    log.info("RESULT task_id=%.8s exit=%d", task_id, result["exit_code"])


# ── Main loop ──────────────────────────────────────────────────────────────────

def run() -> None:
    agent_id   = load_or_create_agent_id()
    hostname   = socket.gethostname()
    server_pub = _load_server_pub()
    log.info("starting agent_id=%.8s server=%s", agent_id, SERVER_URL)

    with requests.Session() as http:
        attempt = 0
        while True:
            try:
                log.info("handshake (attempt %d)...", attempt + 1)
                sid_hex, chacha, agent_nonce = _do_handshake(http, server_pub)
                log.info("session=%.16s", sid_hex)
                attempt = 0  # reset on success

                while True:
                    beacon = encode_beacon(agent_id, hostname, ts=int(time.time()))
                    frame  = build_frame(MSG_BEACON, beacon, chacha, agent_nonce)
                    try:
                        raw = _post(http, frame, sid_hex)
                    except requests.RequestException as exc:
                        log.error("connection error: %s — re-handshake", exc)
                        break

                    try:
                        msg_type, payload = parse_frame(raw, chacha)
                    except InvalidTag:
                        log.error("InvalidTag — re-handshake")
                        break

                    if msg_type == MSG_NOP:
                        log.info("NOP")
                    elif msg_type == MSG_TASK:
                        _run_task(http, agent_id, payload, chacha, agent_nonce, sid_hex)
                    elif msg_type == MSG_ERROR:
                        log.error("ERROR from server — re-handshake")
                        break
                    else:
                        log.warning("unexpected: %s", MSG_NAMES.get(msg_type, f"0x{msg_type:02x}"))

                    esperar_beacon()

            except ValueError as exc:
                # Key pinning mismatch or malformed WELCOME — do NOT retry silently
                log.critical("SECURITY: %s — agent stopped", exc)
                return
            except requests.RequestException as exc:
                delay = _backoff(attempt)
                log.error("handshake failed: %s — retry in %.0fs", exc, delay)
                attempt += 1
                time.sleep(delay)
            except Exception as exc:
                delay = _backoff(attempt)
                log.error("unexpected: %s — retry in %.0fs", exc, delay)
                attempt += 1
                time.sleep(delay)
