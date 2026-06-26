import asyncio
import json
import logging
import os
import time
import uuid

from aiohttp import web

from protocol import (
    MSG_HELLO, MSG_WELCOME, MSG_BEACON, MSG_TASK, MSG_RESULT,
    MSG_NOP, MSG_ERROR, MSG_NAMES,
    pack_clear, unpack_clear,
    server_process_hello, build_frame, parse_frame,
    generate_server_keypair, save_server_key, load_server_key, get_pub_bytes,
)
from cryptography.exceptions import InvalidTag

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexus.server")

SERVER_KEY_FILE  = "server_key.bin"
SERVER_PUB_FILE  = "server_pub.hex"
SESSION_TTL      = 300          # seconds — evict idle sessions after 5 min
TASK_QUEUE_MAX   = 100          # max pending tasks per agent
MAX_RESULTS      = 500          # max stored results per agent (circular)
MAX_OUTPUT_BYTES = 64 * 1024    # 64 KB — truncate stdout/stderr above this
OPERATOR_API_KEY = os.environ.get("NEXUS_API_KEY", "")

# ---------------------------------------------------------------------------
# Global state (safe: asyncio is single-threaded)
# ---------------------------------------------------------------------------
server_priv   = None          # X25519PrivateKey — loaded at startup
sessions: dict = {}           # session_id_hex -> SessionState
agents:   dict = {}           # agent_id -> AgentState
results:  dict = {}           # agent_id -> [ResultEntry]
tasks:    dict = {}           # agent_id -> asyncio.Queue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _truncate(s: str) -> str:
    encoded = s.encode("utf-8", errors="replace")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return s
    return encoded[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace") + "\n[truncated]"


@web.middleware
async def _operator_auth(request: web.Request, handler):
    """Require X-Api-Key on all /agents/* routes when NEXUS_API_KEY is set."""
    if OPERATOR_API_KEY and request.path != "/":
        if request.headers.get("X-Api-Key", "") != OPERATOR_API_KEY:
            return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)


class SessionState:
    def __init__(self, session_id: bytes, chacha, srv_nonce):
        self.session_id = session_id
        self.chacha     = chacha
        self.srv_nonce  = srv_nonce
        self.agent_id   = None
        self.last_seen  = time.time()
        self.encrypted  = chacha is not None


def _validate_agent_id(agent_id: str) -> bool:
    return bool(agent_id) and agent_id != "unknown" and len(agent_id) <= 128


def _ensure_agent(agent_id: str) -> None:
    if agent_id not in agents:
        agents[agent_id] = {
            "agent_id":     agent_id,
            "last_seen":    time.time(),
            "status":       "online",
            "pending_tasks": 0,
        }
        results[agent_id] = []
        tasks[agent_id]   = asyncio.Queue(maxsize=TASK_QUEUE_MAX)
        log.info("NEW   agent_id=%.8s", agent_id)
    else:
        agents[agent_id]["last_seen"] = time.time()
        agents[agent_id]["status"]    = "online"


# ---------------------------------------------------------------------------
# Nexus protocol handler (POST /)
# ---------------------------------------------------------------------------

async def handle_nexus(request: web.Request) -> web.Response:
    body       = await request.read()
    session_id_hex = request.headers.get("X-Session-Id")

    if not body:
        return web.Response(
            body=pack_clear(MSG_ERROR), status=400,
            content_type="application/octet-stream",
        )

    # ── Encrypted session (Fase 3+) ──────────────────────────────────────────
    if session_id_hex and session_id_hex in sessions:
        sess = sessions[session_id_hex]
        if sess.encrypted:
            try:
                msg_type, payload = parse_frame(body, sess.chacha)
            except Exception as exc:
                log.warning("decrypt failed session=%.8s: %s", session_id_hex, exc)
                return web.Response(
                    body=pack_clear(MSG_ERROR), status=401,
                    content_type="application/octet-stream",
                )
            return await _dispatch_encrypted(msg_type, payload, sess, session_id_hex)

    # ── Clear frames (Fase 1-2) or HELLO ─────────────────────────────────────
    msg_type, payload = unpack_clear(body)
    name = MSG_NAMES.get(msg_type, f"0x{msg_type:02x}")

    if msg_type == MSG_HELLO:
        return await _handle_hello(body)

    if msg_type == MSG_BEACON:
        return await _handle_beacon_clear(payload)

    if msg_type == MSG_RESULT:
        return await _handle_result_clear(payload)

    log.warning("unknown type=%s len=%d", name, len(body))
    return web.Response(
        body=pack_clear(MSG_ERROR), status=400,
        content_type="application/octet-stream",
    )


async def _handle_hello(body: bytes) -> web.Response:
    """Fase 3: ECDH handshake."""
    try:
        welcome, session_id, session_key, chacha, srv_nonce = \
            server_process_hello(body, server_priv)
    except Exception as exc:
        log.error("HELLO error: %s", exc)
        return web.Response(
            body=pack_clear(MSG_ERROR), status=400,
            content_type="application/octet-stream",
        )
    sid_hex = session_id.hex()
    sessions[sid_hex] = SessionState(session_id, chacha, srv_nonce)
    log.info("HELLO  session=%.16s", sid_hex)
    return web.Response(body=welcome, content_type="application/octet-stream")


async def _handle_beacon_clear(payload: bytes) -> web.Response:
    """Fase 1-2: BEACON in clear — parse JSON, register agent, return NOP or TASK."""
    try:
        data     = json.loads(payload.decode("utf-8"))
        agent_id = data.get("agent_id", "")
    except Exception:
        agent_id = ""
        data     = {}

    if not _validate_agent_id(agent_id):
        log.warning("BEACON with invalid agent_id=%r — ignored", agent_id)
        return web.Response(body=pack_clear(MSG_ERROR), status=400,
                            content_type="application/octet-stream")

    _ensure_agent(agent_id)
    log.info("BEACON agent_id=%.8s ts=%s", agent_id, data.get("ts", "?"))

    q = tasks.get(agent_id)
    if q and not q.empty():
        try:
            task = q.get_nowait()
            agents[agent_id]["pending_tasks"] = max(
                0, agents[agent_id]["pending_tasks"] - 1
            )
            frame = pack_clear(MSG_TASK, json.dumps(task).encode("utf-8"))
            log.info("TASK   agent_id=%.8s task_id=%.8s cmd=%r",
                     agent_id, task["task_id"], task["cmd"])
            return web.Response(body=frame, content_type="application/octet-stream")
        except asyncio.QueueEmpty:
            pass

    return web.Response(body=pack_clear(MSG_NOP), content_type="application/octet-stream")


async def _handle_result_clear(payload: bytes) -> web.Response:
    """Fase 2: RESULT in clear — store and log."""
    try:
        data     = json.loads(payload.decode("utf-8"))
        agent_id = data.get("agent_id", "")
    except Exception:
        data     = {}
        agent_id = ""

    if not _validate_agent_id(agent_id):
        return web.Response(body=pack_clear(MSG_ERROR), status=400,
                            content_type="application/octet-stream")

    data["stdout"] = _truncate(data.get("stdout", ""))
    data["stderr"] = _truncate(data.get("stderr", ""))

    _ensure_agent(agent_id)
    log.info("RESULT agent_id=%.8s task_id=%.8s exit=%s",
             agent_id, data.get("task_id", "?"), data.get("exit_code", "?"))

    if agent_id in results:
        bucket = results[agent_id]
        bucket.append(data)
        if len(bucket) > MAX_RESULTS:
            del bucket[0]

    return web.Response(body=pack_clear(MSG_NOP), content_type="application/octet-stream")


async def _dispatch_encrypted(
    msg_type: int, payload: bytes, sess: "SessionState", sid_hex: str
) -> web.Response:
    """Fase 3+: handle decrypted payload."""
    sess.last_seen = time.time()

    if msg_type == MSG_BEACON:
        try:
            data     = json.loads(payload.decode("utf-8"))
            agent_id = data.get("agent_id")
        except Exception:
            agent_id = None
            data     = {}

        if agent_id and not _validate_agent_id(agent_id):
            agent_id = None
        if agent_id and sess.agent_id is None:
            sess.agent_id = agent_id
            _ensure_agent(agent_id)
            log.info("BEACON(enc) agent_id=%.8s (first, session=%.8s)", agent_id, sid_hex)
        elif agent_id:
            _ensure_agent(agent_id)
            log.info("BEACON(enc) agent_id=%.8s", agent_id)

        q = tasks.get(agent_id or "")
        if q and not q.empty():
            try:
                task  = q.get_nowait()
                agents[agent_id]["pending_tasks"] = max(
                    0, agents[agent_id]["pending_tasks"] - 1
                )
                raw = build_frame(
                    MSG_TASK, json.dumps(task).encode("utf-8"),
                    sess.chacha, sess.srv_nonce,
                )
                return web.Response(body=raw, content_type="application/octet-stream")
            except asyncio.QueueEmpty:
                pass

        nop = build_frame(MSG_NOP, b"", sess.chacha, sess.srv_nonce)
        return web.Response(body=nop, content_type="application/octet-stream")

    if msg_type == MSG_RESULT:
        try:
            data     = json.loads(payload.decode("utf-8"))
            agent_id = sess.agent_id or data.get("agent_id", "")
        except Exception:
            data     = {}
            agent_id = sess.agent_id or ""

        if not _validate_agent_id(agent_id):
            nop = build_frame(MSG_NOP, b"", sess.chacha, sess.srv_nonce)
            return web.Response(body=nop, content_type="application/octet-stream")

        data["stdout"] = _truncate(data.get("stdout", ""))
        data["stderr"] = _truncate(data.get("stderr", ""))

        _ensure_agent(agent_id)
        log.info("RESULT(enc) agent_id=%.8s task_id=%.8s exit=%s",
                 agent_id, data.get("task_id", "?"), data.get("exit_code", "?"))
        bucket = results.setdefault(agent_id, [])
        bucket.append(data)
        if len(bucket) > MAX_RESULTS:
            del bucket[0]
        nop = build_frame(MSG_NOP, b"", sess.chacha, sess.srv_nonce)
        return web.Response(body=nop, content_type="application/octet-stream")

    log.warning("unexpected encrypted type=0x%02x session=%.8s", msg_type, sid_hex)
    return web.Response(
        body=pack_clear(MSG_ERROR), status=400,
        content_type="application/octet-stream",
    )


# ---------------------------------------------------------------------------
# Operator REST API
# ---------------------------------------------------------------------------

async def api_list_agents(request: web.Request) -> web.Response:
    out = [
        {
            "agent_id":     a["agent_id"],
            "last_seen":    a["last_seen"],
            "status":       a["status"],
            "pending_tasks": a["pending_tasks"],
        }
        for a in agents.values()
    ]
    return web.json_response(out)


async def api_enqueue_task(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if agent_id not in agents:
        return web.json_response({"error": "agent not found"}, status=404)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    cmd = body.get("cmd", "").strip()
    if not cmd:
        return web.json_response({"error": "missing cmd"}, status=400)
    timeout_s = max(1, min(int(body.get("timeout_s", 30)), 3600))
    task = {
        "task_id":   str(uuid.uuid4()),
        "cmd":       cmd,
        "timeout_s": timeout_s,
    }
    try:
        tasks[agent_id].put_nowait(task)
    except asyncio.QueueFull:
        return web.json_response({"error": "task queue full"}, status=429)
    agents[agent_id]["pending_tasks"] += 1
    log.info("ENQUEUE agent_id=%.8s task_id=%.8s cmd=%r",
             agent_id, task["task_id"], cmd)
    return web.json_response({"task_id": task["task_id"], "status": "PENDING"})


async def api_get_results(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]
    if agent_id not in results:
        return web.json_response({"error": "agent not found"}, status=404)
    return web.json_response(results[agent_id])


# ---------------------------------------------------------------------------
# Background: offline monitor
# ---------------------------------------------------------------------------

async def _monitor_agents() -> None:
    while True:
        now = time.time()
        for data in list(agents.values()):
            if now - data["last_seen"] > 30 and data["status"] == "online":
                data["status"] = "offline"
                log.warning("OFFLINE agent_id=%.8s", data["agent_id"])
        await asyncio.sleep(5)


async def _cleanup_sessions() -> None:
    """Evict sessions idle longer than SESSION_TTL to prevent memory leak."""
    while True:
        await asyncio.sleep(60)
        cutoff = time.time() - SESSION_TTL
        stale  = [sid for sid, s in sessions.items() if s.last_seen < cutoff]
        for sid in stale:
            del sessions[sid]
        if stale:
            log.info("evicted %d stale sessions", len(stale))


async def _on_startup(app: web.Application) -> None:
    global server_priv
    try:
        server_priv = load_server_key(SERVER_KEY_FILE)
        log.info("server key loaded from %s", SERVER_KEY_FILE)
    except FileNotFoundError:
        server_priv, _ = generate_server_keypair()
        save_server_key(server_priv, SERVER_KEY_FILE)
        log.info("server key generated")
    pub = get_pub_bytes(server_priv)
    try:
        with open(SERVER_PUB_FILE, "w") as f:
            f.write(pub.hex())
    except OSError as exc:
        raise RuntimeError(
            f"Cannot write {SERVER_PUB_FILE}: {exc}. Agents cannot obtain the server public key."
        ) from exc
    if not OPERATOR_API_KEY:
        log.warning("NEXUS_API_KEY not set — operator API is unauthenticated")
    log.info("server pub=%s", pub.hex())
    asyncio.create_task(_monitor_agents())
    asyncio.create_task(_cleanup_sessions())


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def build_app() -> web.Application:
    app = web.Application(
        middlewares=[_operator_auth],
        client_max_size=1 * 1024 * 1024,  # 1 MB max request body
    )
    app.router.add_post("/",                         handle_nexus)
    app.router.add_get("/agents",                    api_list_agents)
    app.router.add_post("/agents/{agent_id}/task",   api_enqueue_task)
    app.router.add_get("/agents/{agent_id}/results", api_get_results)
    app.on_startup.append(_on_startup)
    return app
