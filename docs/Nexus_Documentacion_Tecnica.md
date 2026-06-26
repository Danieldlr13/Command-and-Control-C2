# Nexus C2 — Documentación Técnica de Referencia

> **Propósito.** Recopilación de la documentación oficial de todas las librerías y módulos que vamos a usar para implementar el Nexus C2 según `Nexus_C2_Spec.md`. Todo lo que está aquí ha sido extraído de las fuentes oficiales y cruzado con los documentos del equipo (`docs.md` P1, `Nexus_C2_Briefing_P2_Agente.md`, `Nexus_C2_Briefing_P3_Servidor.md`, `Nexus_C2_Briefing_P4_Operador.md`).
>
> **Cómo usar este documento.** Está ordenado por **librería**, no por fase del plan, para que sirva como índice rápido. Al final hay una guía de mapeo Fase → API y una sección de contratos de integración entre personas del equipo con las discrepancias resueltas.
>
> **Estado:** v1.2 — actualizada tras cruzar los cinco docs del equipo (incluido P3). Decisión de framework y contrato de cripto resueltos en §10.

---

## Tabla de contenidos

1. [Stack y versiones](#1-stack-y-versiones)
2. [aiohttp — servidor C2 (P3)](#2-aiohttp--servidor-c2-p3)
3. [FastAPI — panel de operador web (P4, opcional)](#3-fastapi--panel-de-operador-web-p4-opcional)
4. [httpx / requests — cliente del agente y CLI de operador](#4-httpx--requests--cliente-del-agente-y-cli-de-operador)
5. [cryptography (pyca) — handshake y AEAD](#5-cryptography-pyca--handshake-y-aead)
6. [Librería estándar de Python](#6-librería-estándar-de-python)
7. [Mapeo Fase → API utilizada](#7-mapeo-fase--api-utilizada)
8. [Anti-patrones y errores conocidos](#8-anti-patrones-y-errores-conocidos)
9. [Referencias oficiales](#9-referencias-oficiales)
10. [Contratos de integración entre personas del equipo](#10-contratos-de-integración-entre-personas-del-equipo)

---

## 1. Stack y versiones

Decisiones fijadas en `Nexus_C2_Spec.md` §10, cruzadas con los cuatro briefings del equipo:

| Componente | Quién lo usa | Librería | Versión mínima |
|---|---|---|---|
| Lenguaje | todos | Python | **3.11+** |
| Servidor HTTP async (broker) | **P3** | **`aiohttp`** | 3.9+ |
| CLI de operador | **P4** | `requests` | 2.31+ |
| Panel web (opcional Fase 5) | P3+P4 | `aiohttp` sirve estáticos | — |
| Cliente HTTP del agente | **P2** | `requests` o `httpx` | 2.31+ / 0.27+ |
| Criptografía (todos importan) | **P1** entrega módulo | `cryptography` | **40.0+** |
| Serialización payload | todos | `json` (stdlib) | — |
| Frame binario | todos (via `protocol.py`) | slicing manual | — |

**`requirements.txt` — servidor (P3):**
```
aiohttp>=3.9
cryptography>=40.0
```

**`requirements.txt` — agente (P2):**
```
requests>=2.31
cryptography>=40.0
```

**`requirements.txt` — operador CLI (P4):**
```
requests>=2.31
```

> **Decisión de framework:** P3 usa `aiohttp` (ya tiene código escrito con él). El skeleton de FastAPI en `docs.md` (P1) es referencia de lógica, no el código final del servidor. FastAPI queda como opción solo si P4 necesita un backend para servir el panel web con WebSocket (Fase 5), pero aiohttp también lo soporta nativamente.

---

## 2. aiohttp — servidor C2 (P3)

> Fuente: `https://docs.aiohttp.org/en/stable/web.html` (doc oficial). P3 usa aiohttp como servidor HTTP async del broker.

### 2.1 App mínima con endpoint POST

```python
from aiohttp import web

async def handle_post(request: web.Request) -> web.Response:
    body: bytes = await request.read()          # bytes crudos del frame
    session_id  = request.headers.get("X-Session-Id")
    # ... procesar frame
    return web.Response(
        body=response_frame,
        content_type="application/octet-stream",
    )

app = web.Application()
app.router.add_post("/", handle_post)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8080)
```

**`await request.read()`** devuelve `bytes` crudos. Nunca usar `await request.json()` con frames binarios.

### 2.2 Rutas de la API del operador

```python
app.router.add_get("/agents",                    api_listar_agentes)
app.router.add_post("/agents/{agent_id}/task",   api_encolar_tarea)
app.router.add_get("/agents/{agent_id}/results", api_ver_resultados)
```

Leer el `agent_id` del path:

```python
async def api_encolar_tarea(request: web.Request) -> web.Response:
    agent_id = request.match_info["agent_id"]   # del path {agent_id}
    datos    = await request.json()             # body JSON del operador
    ...
    return web.json_response({"task_id": task_id})
```

### 2.3 Respuestas JSON y binarias

```python
# JSON (para API del operador):
return web.json_response({"agent_id": "...", "status": "online"})

# Binario (para frames Nexus):
return web.Response(body=frame_bytes, content_type="application/octet-stream")

# Error HTTP:
return web.Response(body=error_frame, status=401, content_type="application/octet-stream")
```

### 2.4 Estado global — sin locks en asyncio

asyncio es **single-threaded**: solo un coroutine corre en cada momento. Modificar diccionarios entre puntos `await` es seguro sin `asyncio.Lock`.

```python
# Estado global del broker (P3)
sesiones: dict = {}   # session_id (str) -> SessionData
agentes:  dict = {}   # agent_id  (str) -> AgentData
```

**Regla:** modificar estos diccionarios solo entre `await`s — nunca dentro de un `await`. asyncio garantiza atomicidad entre dos puntos de suspensión.

### 2.5 Tarea background — monitor de offline

```python
async def monitor_agentes():
    import time
    while True:
        ahora = time.time()
        for agent_id, datos in agentes.items():
            if ahora - datos["last_seen"] > 30:
                if datos["status"] == "online":
                    print(f"[!] Agente {agent_id[:8]} → offline")
                datos["status"] = "offline"
        await asyncio.sleep(5)

async def on_startup(app):
    asyncio.create_task(monitor_agentes())

app.on_startup.append(on_startup)
```

### 2.6 Servir HTML estático para el panel (Fase 5)

```python
# Ruta GET / que sirve index.html del panel web de P4
async def serve_panel(request):
    return web.FileResponse("./index.html")

app.router.add_get("/", serve_panel)
```

### 2.7 Lo que usamos de aiohttp en Nexus

| Funcionalidad | Uso en Nexus |
|---|---|
| `await request.read()` | Leer frame binario crudo |
| `request.headers.get("X-Session-Id")` | Correlación de sesión |
| `web.Response(body=bytes, content_type=...)` | Responder frame binario |
| `web.json_response(dict)` | API del operador (P4) |
| `request.match_info["agent_id"]` | Rutas `/agents/{agent_id}/...` |
| `app.on_startup.append(fn)` | Lanzar `monitor_agentes()` al arrancar |
| `asyncio.create_task(coro)` | Tarea background sin bloquear |
| `web.FileResponse("index.html")` | Servir panel web (Fase 5) |

---

## 3. FastAPI — panel de operador web (P4, opcional)

> Fuente: `fastapi/fastapi` (repo oficial, rama `master`). FastAPI queda como referencia secundaria — el servidor usa aiohttp. Solo relevante si P4 necesita un backend separado para el panel.

### 2.1 Recibir un frame binario en `POST /`

El servidor Nexus tiene **un único endpoint** que recibe el frame `[TYPE 1B][NONCE 12B][CIPHERTEXT+TAG]` como cuerpo binario y la cabecera `X-Session-Id` para correlacionar la sesión (Spec §3.2, §4.3).

Patrón oficial para leer bytes crudos (fuente: `docs/en/docs/advanced/path-operation-advanced-configuration.md`):

```python
from typing import Annotated
from fastapi import FastAPI, Request, Header, Response

app = FastAPI()

@app.post("/")
async def nexus_endpoint(
    request: Request,
    x_session_id: Annotated[str | None, Header()] = None,
):
    raw: bytes = await request.body()
    # ... parsear [TYPE][NONCE][PAYLOAD]
    response_frame: bytes = b"..."
    return Response(content=response_frame, media_type="application/octet-stream")
```

**Reglas a recordar:**

- `await request.body()` devuelve `bytes` literales. FastAPI **no** intenta JSON-parsear si el path operation no declara un parámetro Pydantic.
- El nombre del parámetro de cabecera se convierte automáticamente: `X-Session-Id` ↔ `x_session_id` (los guiones se mapean a guiones bajos). Para forzar el nombre exacto: `Header(..., alias="X-Session-Id")`.
- Para responder binario crudo: `Response(content=bytes, media_type="application/octet-stream")`. No usar `JSONResponse` aquí.

### 2.2 Lifespan: estado compartido del broker

El servidor C2 mantiene un diccionario `session_id -> { session_key, agent_id, cola, contadores de nonce, último beacon }` (Spec §5). Este estado debe crearse al arrancar la app y limpiarse al cerrarla. El patrón oficial recomendado es **lifespan** con `asynccontextmanager`, no los `startup`/`shutdown` deprecados.

Fuente: `docs/en/docs/release-notes.md`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

sessions: dict = {}      # session_id -> SessionState
agents: dict = {}        # agent_id -> AgentState
operator_pubsub = None   # canal para WebSockets del panel

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: inicializar broker
    sessions.clear()
    agents.clear()
    print("[broker] arriba")
    yield
    # Shutdown: limpiar
    sessions.clear()
    agents.clear()
    print("[broker] abajo")

app = FastAPI(lifespan=lifespan)
```

En Nexus podemos colgar el estado directamente en `app.state.sessions` (mejor que globales) o en módulos importables — usar lo que sea más limpio para el equipo.

### 2.3 Errores: `HTTPException`

Fuente: `docs/en/docs/release-notes.md`:

```python
from fastapi import HTTPException

if x_session_id not in sessions:
    raise HTTPException(status_code=401, detail="unknown session")
```

Nexus va a usar esto para:
- Sesión desconocida o expirada → 401.
- Frame mal formado (TYPE inválido, longitud mínima no satisfecha) → 400.
- Error de descifrado (tag inválido) → 401 (no revelar más; lo trata como sesión rota).

### 2.4 `BackgroundTasks` — ejecutar trabajo tras enviar la respuesta

Útil para auditar eventos (escribir un log de beacon, publicar al panel) sin bloquear la respuesta al agente.

Fuente: `docs_src/background_tasks/tutorial002_an_py310.py`:

```python
from fastapi import BackgroundTasks

@app.post("/")
async def nexus_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    x_session_id: Annotated[str | None, Header()] = None,
):
    raw = await request.body()
    # ... procesar frame
    background_tasks.add_task(audit_log, agent_id, "beacon", ts)
    return Response(content=response_frame, media_type="application/octet-stream")
```

**Aviso importante de la doc oficial** (`docs/en/docs/advanced/advanced-dependencies.md`): los `BackgroundTasks` se ejecutan **después** de que se cierren los `Depends` con `yield`. Si un task necesita un recurso (DB, fichero), debe crearlo dentro del propio task, no recibirlo del Depends.

### 2.5 WebSocket — panel de operador en tiempo real (Fase 5)

Para el panel web que muestra agentes vivos y resultados en streaming.

Fuente: `docs/en/docs/advanced/websockets.md`:

```python
from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.websocket("/ws/operator")
async def operator_panel(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"echo: {data}")
```

**Métodos clave del objeto `WebSocket`** (fuente: `docs/en/docs/reference/websockets.md`):

- `accept()` — aceptar la conexión.
- `receive_text()` / `receive_bytes()` / `receive_json()`.
- `send_text()` / `send_bytes()` / `send_json()`.
- `iter_text()` / `iter_bytes()` / `iter_json()` — iteradores async.
- `close()` — cerrar limpia.

**Aviso de la doc oficial:** mantener "lista de conexiones" en memoria sólo funciona con un único proceso. Para multi-proceso, la doc remite a [`encode/broadcaster`](https://github.com/encode/broadcaster) con backend Redis o Postgres. Para la hackathon esto es irrelevante: un solo proceso uvicorn nos vale.

### 2.6 Lo que usamos de FastAPI en Nexus

| Funcionalidad FastAPI | Dónde la usamos en Nexus |
|---|---|
| `@app.post("/")` + `await request.body()` | Endpoint único del protocolo Nexus (todas las fases) |
| `Header()` con alias `X-Session-Id` | Correlación de sesión sobre HTTP sin estado (Fase 3+) |
| `Response(content=bytes, media_type=...)` | Devolver el frame de respuesta binario |
| `lifespan` con `asynccontextmanager` | Estado del broker (sesiones, agentes, colas) — Fase 4 |
| `HTTPException` | Sesión inválida, frame malformado |
| `BackgroundTasks` | Notificar al panel de operador sin bloquear el beacon |
| `@app.websocket(...)` | Panel de operador en tiempo real — Fase 5 |

---

## 3. Uvicorn — servidor ASGI

> Fuente: `https://www.uvicorn.org` (doc oficial). Uvicorn es el ASGI runner que FastAPI documenta como recomendado.

### 3.1 Arranque típico

```bash
# Desarrollo (autorecarga al editar):
uvicorn nexus.server:app --reload --host 0.0.0.0 --port 8000

# "Producción" (para la demo):
uvicorn nexus.server:app --host 0.0.0.0 --port 8000 --log-level info
```

- `--reload`: sólo en desarrollo. Vigila ficheros y reinicia. No usar en demo (latencia y warnings).
- `--host 0.0.0.0`: escucha en todas las interfaces (importante si el equipo prueba desde otra máquina del lab).
- `--workers N`: NO usar en Nexus. El broker mantiene estado en memoria (sesiones, colas); múltiples workers romperían eso. Un único proceso async.

### 3.2 Arranque programático

A veces conviene levantar uvicorn desde un `main.py` (más fácil de debuggear desde el IDE):

```python
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "nexus.server:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=False,
    )
```

### 3.3 Lo que usamos de uvicorn en Nexus

- Modo `--reload` durante desarrollo.
- Modo single-process (sin `--workers`) para que el estado del broker en memoria sea coherente.
- `[standard]` extras → `uvloop` (más rendimiento) + `websockets` (panel de operador).

---

## 4. httpx — cliente del agente y del CLI de operador

> Fuente: `encode/httpx` y `https://www.python-httpx.org`. Snippets verificados.

### 4.1 POST con bytes crudos y cabecera de sesión

El agente Nexus hace `POST /` con el frame binario y la cabecera `X-Session-Id`.

Fuente: `python-httpx.org/quickstart`:

```python
import httpx

content = b'Hello, world'
r = httpx.post("https://httpbin.org/post", content=content)
```

Custom headers (misma fuente):

```python
headers = {'user-agent': 'my-app/0.0.1'}
r = httpx.get(url, headers=headers)
```

**Patrón Nexus aplicado:**

```python
import httpx, time

with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10.0) as client:
    while True:
        frame: bytes = build_beacon_frame(agent_id)
        r = client.post(
            "/",
            content=frame,                              # bytes crudos
            headers={"X-Session-Id": session_id},       # vacío en Fase 1
        )
        process_response(r.content)                     # r.content = bytes
        time.sleep(5)
```

**Reglas:**

- `content=` para bytes crudos. `data=` es form-encoded — **no usar**.
- `json=` reserializa a JSON — **no usar**, nuestro frame es binario propio.
- `r.content` devuelve `bytes`; `r.text` los decodifica como UTF-8 (no aplica aquí).

### 4.2 Timeouts

Fuente: `python-httpx.org/advanced/timeouts`:

```python
httpx.get('http://example.com/api/v1/example', timeout=10.0)

with httpx.Client() as client:
    client.get("http://example.com/api/v1/example", timeout=10.0)
```

Por defecto httpx pone timeout de 5 s. Para beaconing conviene explicitarlo. Para `RESULT` con salidas grandes podemos subirlo a 30-60 s.

### 4.3 Manejo de errores y reintentos

Excepciones específicas que el agente debe esperar (fuente: `context7.com/encode/httpx/llms.txt`):

```python
import httpx

try:
    response = httpx.get('https://httpbin.org/delay/10', timeout=1.0)
except httpx.ConnectTimeout:
    print("Failed to connect in time")
except httpx.ReadTimeout:
    print("Server took too long to respond")
except httpx.ConnectError:
    print("Failed to establish connection")
except httpx.NetworkError:
    print("Network-level error occurred")
```

Para reintentos automáticos en errores de conexión (no en errores HTTP) — fuente `docs/advanced/transports.md`:

```python
import httpx
transport = httpx.HTTPTransport(retries=1)
client = httpx.Client(transport=transport)
```

Aviso de la doc: este `retries=` **solo cubre `ConnectError` y `ConnectTimeout`**, no fallos de aplicación. Para reintentos por exit-code o por descifrado fallido hay que hacer la lógica a mano (o usar `tenacity`).

### 4.4 Cliente async (Fase 4+)

Cuando el agente o el CLI necesiten concurrencia (varios beacons en paralelo, panel que dispara muchas tareas), `AsyncClient`:

Fuente: `docs/async.md`:

```python
import httpx

async def use_custom_transport():
    transport = httpx.AsyncHTTPTransport(retries=3)
    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get('https://www.example.com/')
        print(response.status_code)
```

### 4.5 Lo que usamos de httpx en Nexus

| Funcionalidad httpx | Uso en Nexus |
|---|---|
| `httpx.Client(base_url=..., timeout=...)` | Cliente del agente (loop de beaconing) |
| `client.post("/", content=bytes, headers={"X-Session-Id": ...})` | Cada BEACON/RESULT del agente |
| `r.content` | Recuperar el frame de respuesta crudo |
| `httpx.ConnectError`, `httpx.NetworkError` | Caída del servidor → backoff y reintento (Fase 4) |
| `HTTPTransport(retries=N)` | Resiliencia básica del agente ante red flaky |
| `httpx.AsyncClient` | CLI operador o agente concurrente (Fase 4+) |

---

## 5. cryptography (pyca) — handshake y AEAD

> Fuente: `pyca/cryptography` (repo oficial), rama `main`. Snippets verificados.

Esta librería es la que el jurado va a mirar con lupa: forward secrecy, AEAD, y nonce management están todos aquí. **Las tres primitivas que necesitamos están en este único paquete.**

### 5.1 X25519 — intercambio de claves del handshake

Spec §4.2: ECDH sobre Curve25519, clave estática del servidor + clave efímera del agente.

Fuente: `docs/hazmat/primitives/asymmetric/x25519.rst`:

```python
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

private_key = X25519PrivateKey.generate()
peer_public_key = X25519PrivateKey.generate().public_key()
shared_key = private_key.exchange(peer_public_key)

derived_key = HKDF(
    algorithm=hashes.SHA256(),
    length=32,
    salt=None,
    info=b'handshake data',
).derive(shared_key)
```

### 5.2 Serialización de claves públicas (formato raw 32 bytes)

Crítico para meter la `pub_efimera_agente` y `pub_server` dentro del frame HELLO/WELCOME.

Fuente: `docs/hazmat/primitives/asymmetric/x25519.rst`:

```python
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization

private_key = x25519.X25519PrivateKey.generate()
public_key = private_key.public_key()

# Opción A — atajo disponible desde cryptography >= 40.0 (versión mínima del proyecto)
pub_bytes = public_key.public_bytes_raw()               # 32 bytes

# Opción B — forma explícita equivalente (siempre disponible)
pub_bytes = public_key.public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)

# Reconstruir desde 32 bytes recibidos (igual en ambos casos)
loaded_public_key = x25519.X25519PublicKey.from_public_bytes(pub_bytes)
```

Usar la **Opción A** (`public_bytes_raw()`) en el código final — más corta y menos propensa a errores de parámetros. Confirmed en `docs.md` (P1) §4.1.

### 5.3 ChaCha20-Poly1305 — AEAD del canal

Spec §4.2: cifrado autenticado del payload con clave de sesión derivada.

Fuente: `docs/hazmat/primitives/aead.rst`:

```python
import os
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

data = b"a secret message"
aad = b"authenticated but unencrypted data"
key = ChaCha20Poly1305.generate_key()
chacha = ChaCha20Poly1305(key)
nonce = os.urandom(12)
ct = chacha.encrypt(nonce, data, aad)
plaintext = chacha.decrypt(nonce, ct, aad)
```

**Importante:** en Nexus **no** usamos `os.urandom(12)` para el nonce — usamos contador por sesión (Spec §4.2: servidor pares, agente impares). El ejemplo de arriba es el patrón general; en Nexus el nonce viene del estado de sesión.

### 5.4 Aviso oficial sobre nonce reuse

Cita textual de la doc (`docs/hazmat/primitives/aead.rst`):

> *"reuse of a nonce with a given key compromises the security of any message encrypted with that pair, so nonces must be unique for every operation."*

Esto **justifica directamente** la decisión del Spec §4.2: nonce como contador, no aleatorio, con separación de espacio (pares/impares) para que las dos direcciones no colisionen compartiendo `session_key`.

### 5.5 HKDF — derivación de la clave de sesión

Spec §4.2: HKDF-SHA256 sobre el secreto compartido ECDH → clave simétrica de 32 bytes.

```python
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

session_key = HKDF(
    algorithm=hashes.SHA256(),
    length=32,
    salt=salt,                   # 16 bytes aleatorios generados por el servidor en WELCOME
    info=b"nexus-c2-v1-session-key" + agent_pub_bytes + server_pub_bytes,
).derive(shared_secret)
```

**Reglas críticas (confirmadas por P1 `docs.md` §4.2):**
- `info` **debe incluir ambas claves públicas** — vincula la `session_key` a esta sesión concreta y previene ataques de replay con claves distintas. Un `info` solo con una etiqueta de texto (`b"nexus-v1-session"`) es insuficiente.
- **HKDF es single-use**: llamar `.derive()` más de una vez en la misma instancia lanza `AlreadyFinalized`. Crear una nueva instancia por derivación.
- `salt` nunca `None` — lo genera el servidor con `os.urandom(16)` y lo envía en WELCOME.

### 5.6 Plantilla del handshake Nexus completo

Juntando 5.1 + 5.2 + 5.5 según Spec §4.3:

**Lado servidor (clave estática persistida en disco):**

```python
import secrets
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Al arrancar: cargar o generar clave estática del servidor
server_static_priv = X25519PrivateKey.generate()  # en producción: cargar de disco
server_static_pub_bytes = server_static_priv.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)

# Al recibir HELLO { pub_efimera_agente }:
def handle_hello(agent_pub_bytes: bytes):
    agent_pub = X25519PublicKey.from_public_bytes(agent_pub_bytes)
    shared = server_static_priv.exchange(agent_pub)
    salt = secrets.token_bytes(16)
    session_key = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=salt,
        info=b"nexus-v1-session",
    ).derive(shared)
    session_id = secrets.token_urlsafe(16)
    # responder WELCOME { pub_server, salt, session_id }
    return server_static_pub_bytes, salt, session_id, session_key
```

**Lado agente:**

```python
# La pub estática del servidor está pinneada en el binario del agente:
SERVER_STATIC_PUB = bytes.fromhex("...")  # 32 bytes hardcodeados

# Al hacer handshake:
agent_eph_priv = X25519PrivateKey.generate()
agent_eph_pub_bytes = agent_eph_priv.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)
# enviar HELLO { agent_eph_pub_bytes }
# recibir WELCOME { server_pub_bytes, salt, session_id }

# (verificar que server_pub_bytes == SERVER_STATIC_PUB — pinning)
shared = agent_eph_priv.exchange(X25519PublicKey.from_public_bytes(server_pub_bytes))
session_key = HKDF(
    algorithm=hashes.SHA256(), length=32, salt=salt,
    info=b"nexus-v1-session",
).derive(shared)
```

### 5.7 Lo que usamos de cryptography en Nexus

| Primitiva | Uso en Nexus |
|---|---|
| `X25519PrivateKey.generate()` / `.exchange()` | Handshake ECDH (Fase 3) |
| `public_bytes(Raw, Raw)` / `from_public_bytes()` | Serializar claves públicas en HELLO/WELCOME |
| `HKDF(SHA256, length=32, salt, info)` | Derivar `session_key` desde el shared secret |
| `ChaCha20Poly1305(key).encrypt(nonce, pt, aad)` | Cifrar payloads BEACON/TASK/RESULT |
| `ChaCha20Poly1305(key).decrypt(nonce, ct, aad)` | Descifrar y verificar tag |

---

## 6. Librería estándar de Python

Sin dependencias externas. Doc oficial: `https://docs.python.org/3/library/<modulo>.html`.

### 6.1 Frame binario — empaquetar/desempaquetar

El frame Nexus es `[TYPE 1B][NONCE 12B][CIPHERTEXT+TAG]`. Slicing directo o `struct`:

```python
# Construcción del frame cifrado (patrón de P1 docs.md §4.3)
def build_frame(msg_type: int, plaintext: bytes, chacha, nonce_counter) -> bytes:
    nonce = nonce_counter.next()
    ct    = chacha.encrypt(nonce, plaintext, None)
    return bytes([msg_type]) + nonce + ct

# Parseo del frame cifrado
def parse_frame(raw: bytes, chacha) -> tuple[int, bytes]:
    from cryptography.exceptions import InvalidTag
    msg_type  = raw[0]
    nonce     = raw[1:13]
    ct_tag    = raw[13:]
    plaintext = chacha.decrypt(nonce, ct_tag, None)  # lanza InvalidTag si manipulado
    return msg_type, plaintext
```

**Alternativa con `struct` (más explícito para mensajes en claro):**

```python
import struct

def pack_frame_clear(msg_type: int, payload: bytes) -> bytes:
    # Para HELLO/WELCOME que van en claro — sin NONCE
    return bytes([msg_type]) + payload

def unpack_frame_clear(raw: bytes) -> tuple[int, bytes]:
    return raw[0], raw[1:]
```

**Wire format de WELCOME** (formato exacto fijado por P1 `docs.md` §4.6):
```
[TYPE=0x02 1B][pub_server 32B][salt 16B][len(session_id) 1B][session_id Nbytes]
```

**Nonce: contador little-endian** (crítico — servidor y agente deben coincidir):

```python
class NonceCounter:
    """start=0 para servidor (pares), start=1 para agente (impares)."""
    def __init__(self, start: int):
        self._n    = start
        self._step = 2

    def next(self) -> bytes:
        nonce    = self._n.to_bytes(12, byteorder="little")
        self._n += self._step
        return nonce
```

`byteorder="little"` — especificado en `docs.md` (P1) §4.4. Ambos lados deben usar el mismo orden o el nonce no coincidirá y `InvalidTag` saltará siempre.

### 6.2 `uuid` — `agent_id` y `task_id`

```python
import uuid

agent_id = str(uuid.uuid4())   # ej. "550e8400-e29b-41d4-a716-446655440000"
task_id = str(uuid.uuid4())
```

UUID v4 (aleatorio). Suficiente para el lab cerrado. Persistir en disco (`agent_id.txt`) en el lado agente (Spec §5).

### 6.3 `secrets` — `session_id`, salt, claves PSK

```python
import secrets

session_id = secrets.token_urlsafe(16)   # ASCII URL-safe, ~22 chars
salt = secrets.token_bytes(16)            # 16 bytes crudos para HKDF
```

`secrets` está pensado precisamente para tokens criptográficos. No usar `random` para esto.

### 6.4 `json` — payload dentro del ciphertext

Spec §3.4: empezar con JSON, migrar a binario sólo si sobra tiempo.

```python
import json

payload = json.dumps({"agent_id": agent_id, "ts": int(time.time())}).encode("utf-8")
data = json.loads(plaintext.decode("utf-8"))
```

Usar siempre `.encode("utf-8")` / `.decode("utf-8")` explícito antes/después de cifrar.

### 6.5 `asyncio` — colas por agente

Spec §5: cola de tareas por agente. `asyncio.Queue` es la primitiva natural.

```python
import asyncio

class AgentState:
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.last_beacon: float = 0.0
        self.send_nonce: int = 0    # servidor envía con nonces pares
        self.recv_nonce: int = 0    # esperando que el agente mande impares

# Operador encola:
await agent.task_queue.put(task_frame_or_dict)

# BEACON handler intenta dequeue sin bloquear:
try:
    task = agent.task_queue.get_nowait()
    return pack_task_response(task)
except asyncio.QueueEmpty:
    return pack_nop_response()
```

### 6.6 `random` — jitter en el beaconing (Fase 5)

Spec §3.1: beacon con jitter para romper el patrón de tráfico fijo.

```python
import random, time

BASE_INTERVAL = 5.0
JITTER = 2.0

def next_sleep() -> float:
    return BASE_INTERVAL + random.uniform(-JITTER, JITTER)

time.sleep(next_sleep())
```

**No usar `random` para nada criptográfico** — ahí va `secrets`. `random` sólo para temporización.

### 6.7 `time` — timestamps y temporización

```python
import time

ts = int(time.time())           # epoch entero, va en los payloads
elapsed = time.monotonic() - t0 # para medir intervalos (no afectado por NTP)
```

### 6.8 `logging` — logs del servidor y agente

```python
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("nexus.server")
log.info("BEACON agent_id=%s", agent_id)
```

Mejor que `print` desde el día uno: el video de demo se ve más profesional con logs estructurados.

---

## 7. Mapeo Fase → API utilizada

Esta tabla cruza el plan por fases del Spec §7 con las APIs documentadas arriba. Sirve como checklist al implementar.

### Fase 1 — Servidor acepta conexión + BEACON en claro

- **FastAPI:** `@app.post("/")`, `await request.body()`, `Response(content=..., media_type=...)`.
- **httpx:** `httpx.Client(base_url=...)`, `client.post("/", content=frame)`.
- **stdlib:** `struct.pack("!B12s", ...)`, `uuid.uuid4()`, `json.dumps(...).encode()`, `time.time()`, `logging`.
- **Cripto:** ninguna (todo en claro; el NONCE va a ceros como placeholder).

### Fase 2 — TASK/RESULT en claro

- Añadir: `asyncio.Queue` por agente (Spec §5), `BackgroundTasks` para auditoría opcional.
- **stdlib:** `subprocess` (lado agente, no documentado aquí porque es responsabilidad del equipo P2, Spec §9).

### Fase 3 — Handshake ECDH + cifrado AEAD

- **cryptography:** `X25519PrivateKey`, `X25519PublicKey.from_public_bytes`, `public_bytes(Raw, Raw)`, `HKDF`, `ChaCha20Poly1305`.
- **stdlib:** `secrets.token_bytes(16)` (salt), `secrets.token_urlsafe(16)` (session_id).
- **FastAPI:** ahora `Header(alias="X-Session-Id")` es obligatorio en BEACON/TASK/RESULT.

### Fase 4 — Múltiples agentes + cola + reconexión

- **FastAPI:** `lifespan` con estado compartido (`app.state.sessions`, `app.state.agents`).
- **httpx:** `HTTPTransport(retries=1)`, manejo de `ConnectError`/`NetworkError` con backoff en el agente.
- **stdlib:** `asyncio.Lock` si hay race conditions al actualizar contadores de nonce.

### Fase 5 — Panel de operador + jitter

- **FastAPI:** `@app.websocket("/ws/operator")`, `websocket.send_json(...)`.
- **stdlib:** `random.uniform(-JITTER, JITTER)` para temporizar beacon.
- Frontend HTML mínimo (no documentado aquí, fuera del alcance Python).

### Fase 6 — Documentación + video

- Esta misma documentación entra como entregable técnico.
- `Nexus_C2_Spec.md` queda como "spec de diseño"; este fichero, como "manual de implementación".

---

## 8. Anti-patrones y errores conocidos

### Criptografía

| # | Regla | Consecuencia de ignorarla |
|---|---|---|
| 1 | **Nunca reutilizar nonce con la misma clave** (pyca textual: *"reuse compromises security"*) | Attacker XOR cancela el keystream → plaintext expuesto + MACs forjables |
| 2 | **Nunca usar `shared_secret` directamente como clave** | Output de X25519 tiene estructura matemática, no es uniforme; siempre pasar por HKDF |
| 3 | **HKDF es single-use** — nueva instancia por cada derivación | `AlreadyFinalized` exception al segundo `.derive()` |
| 4 | **`info` de HKDF debe incluir ambas claves públicas** | Un `info` solo textual no vincula la clave a la sesión; vulnerable a replay |
| 5 | **Nonce: contador, no aleatorio** | Birthday bound ≈ 2⁴⁸ mensajes; con beaconing frecuente la colisión es real |
| 6 | **Nonce byteorder: `little`** — servidor y agente deben coincidir | Nonces distintos → `InvalidTag` en todo mensaje → canal roto |
| 7 | **Incrementar nonce ANTES de cifrar, incluso en reintentos** | Un mensaje reenviado nunca reutiliza el nonce anterior |
| 8 | **Capturar siempre `InvalidTag`** — importar de `cryptography.exceptions` | Procesar payload no autenticado → ejecución de comandos arbitrarios |
| 9 | **Tag va appended en `encrypt()`** — `ciphertext || tag` como blob único | `decrypt()` espera el blob completo; separarlo manualmente falla |

### Servidor / HTTP

| # | Regla | Consecuencia de ignorarla |
|---|---|---|
| 10 | **`await request.body()`** para frames binarios | `request.json()` intenta parsear JSON y corrompe/rechaza el payload binario |
| 11 | **Leer `X-Session-Id` antes de descifrar** | Sin él no se recupera la `session_key` — problema huevo-y-gallina |
| 12 | **`asyncio.Lock`** alrededor del dict de sesiones | Race condition en lecturas/escrituras concurrentes del event loop async |
| 13 | **No usar `--workers >1` en uvicorn** | El broker en memoria ve diccionarios distintos por proceso → sesiones rotas |
| 14 | **No usar `--reload` en la demo** | Autorecarga reinicia el proceso → sesiones activas perdidas en la grabación |

### Protocolo

| # | Regla | Consecuencia de ignorarla |
|---|---|---|
| 15 | **`agent_id` en el primer BEACON cifrado, no en HELLO** | HELLO va en claro → ID enlazable entre sesiones |
| 16 | **Idempotencia por `task_id`**, no por nonce | Nonce es criptográfico; `task_id` evita ejecutar el mismo comando dos veces |
| 17 | **HELLO y WELCOME van en claro sin NONCE** | Todavía no existe `session_key`; su wire format es diferente al de BEACON/TASK/RESULT |
| 18 | **No mezclar `content=` y `json=` en httpx/requests** | `json=` reserializa y cambia Content-Type; el frame binario queda corrupto |

---

## 9. Referencias oficiales

### FastAPI
- Repo: <https://github.com/fastapi/fastapi>
- Path operations advanced configuration (raw body): <https://github.com/fastapi/fastapi/blob/master/docs/en/docs/advanced/path-operation-advanced-configuration.md>
- Custom request and route: <https://github.com/fastapi/fastapi/blob/master/docs/en/docs/how-to/custom-request-and-route.md>
- Lifespan events: <https://github.com/fastapi/fastapi/blob/master/docs/en/docs/release-notes.md> (sección `lifespan`)
- Background tasks: <https://github.com/fastapi/fastapi/blob/master/docs/en/docs/tutorial/background-tasks.md>
- WebSockets: <https://github.com/fastapi/fastapi/blob/master/docs/en/docs/advanced/websockets.md>
- WebSocket reference: <https://github.com/fastapi/fastapi/blob/master/docs/en/docs/reference/websockets.md>

### Uvicorn
- Web: <https://www.uvicorn.org>
- Settings: <https://www.uvicorn.org/settings/>

### httpx
- Web: <https://www.python-httpx.org>
- Repo: <https://github.com/encode/httpx>
- Quickstart: <https://www.python-httpx.org/quickstart>
- Async client: <https://github.com/encode/httpx/blob/master/docs/async.md>
- Timeouts: <https://www.python-httpx.org/advanced/timeouts>
- Transports (retries): <https://github.com/encode/httpx/blob/master/docs/advanced/transports.md>

### cryptography (pyca)
- Web: <https://cryptography.io>
- Repo: <https://github.com/pyca/cryptography>
- X25519: <https://github.com/pyca/cryptography/blob/main/docs/hazmat/primitives/asymmetric/x25519.rst>
- AEAD (ChaCha20-Poly1305): <https://github.com/pyca/cryptography/blob/main/docs/hazmat/primitives/aead.rst>
- HKDF: <https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#cryptography.hazmat.primitives.kdf.hkdf.HKDF>
- Serialization: <https://cryptography.io/en/latest/hazmat/primitives/asymmetric/serialization/>

### Python stdlib
- `struct`: <https://docs.python.org/3/library/struct.html>
- `uuid`: <https://docs.python.org/3/library/uuid.html>
- `secrets`: <https://docs.python.org/3/library/secrets.html>
- `json`: <https://docs.python.org/3/library/json.html>
- `asyncio` queues: <https://docs.python.org/3/library/asyncio-queue.html>
- `random`: <https://docs.python.org/3/library/random.html>
- `time`: <https://docs.python.org/3/library/time.html>
- `logging`: <https://docs.python.org/3/library/logging.html>

### Spec del proyecto
- Diseño: `Nexus_C2_Spec.md` (en este mismo directorio).

---

---

## 10. Contratos de integración entre personas del equipo

> Esta sección resuelve las discrepancias encontradas al cruzar `docs.md` (P1), `Nexus_C2_Briefing_P2_Agente.md` y `Nexus_C2_Briefing_P4_Operador.md`. Son los puntos donde cada persona asumía algo distinto y que, si no se acuerdan ahora, rompen la integración en Fase 2-3.

---

### Contrato 1 — Wire format de HELLO (P1 ↔ P2)

**Discrepancia encontrada:** `Briefing_P2` decía que HELLO lleva `{ "pub_key": "<hex>" }` (JSON). `docs.md` P1 dice que HELLO es binario puro.

**Resolución (según Spec §3.2 y `docs.md` §4.6 — ambos coinciden):**

```
HELLO = bytes([0x01]) + agent_eph_pub_bytes   # 33 bytes total
         ^^^             ^^^^^^^^^^^^^^^^^
         TYPE           32 bytes raw X25519
```

No hay NONCE en HELLO. No hay JSON. Solo TYPE + 32 bytes de clave pública raw. El servidor lee `raw[1:33]` para extraer la clave. **P2 debe corregir su implementación.**

---

### Contrato 2 — Wire format de WELCOME (P1 ↔ P2)

El servidor responde con (fijado en `docs.md` §4.6):

```
WELCOME = bytes([0x02]) + server_pub_bytes(32) + salt(16) + bytes([len(session_id)]) + session_id_bytes
```

- `session_id` es `os.urandom(32)` — 32 bytes aleatorios. El byte que lo precede es su longitud (32).
- P2 extrae: `body[32:48]` = salt, `body[48]` = longitud, `body[49:49+len]` = session_id.
- Para la cabecera HTTP `X-Session-Id` se usa `session_id.hex()` (string hexadecimal).

---

### Contrato 3 — API del operador (P3 ↔ P4)

**Discrepancia encontrada:** `Briefing_P4` esperaba `/agents` y `/agents/<agent_id>/task`. El skeleton de P1 exponía `/operator/sessions` y `/operator/task/{session_id}`.

**Resolución acordada — P3 expone los siguientes endpoints para P4:**

```
GET  /agents
     → lista de agentes: [{ "agent_id": str, "last_seen": ISO8601, "status": str, "pending_tasks": int }]

POST /agents/{agent_id}/task
     body: { "cmd": "..." }
     → { "task_id": str, "status": "PENDING" }

GET  /agents/{agent_id}/results
     → [{ "task_id": str, "exit_code": int, "stdout": str, "stderr": str, "ts": int }]

GET  /
     → sirve index.html del panel web (P4 lo pide, P3 lo implementa)
```

El identificador externo es siempre `agent_id` (UUID estable del agente). Internamente el broker usa `session_id`, pero P4 nunca lo ve.

---

### Contrato 4 — Jitter del beacon (P1 ↔ P2)

**Discrepancia encontrada:** fórmulas distintas en distintos docs.

**Resolución — usar jitter solo positivo (más simple, nunca baja del intervalo base):**

```python
import random, time

INTERVALO_BASE = 5    # segundos (ajustable)
JITTER_MAX     = 3    # variación máxima hacia arriba

def esperar_beacon():
    jitter = random.uniform(0, JITTER_MAX)
    time.sleep(INTERVALO_BASE + jitter)
```

P1 y P2 usan la misma función. Está en `protocol.py` para que los dos la importen.

---

### Contrato 5 — Módulo compartido `protocol.py` (P1 → P2, P3, P4)

P1 entrega un módulo `protocol.py` con estas funciones/clases públicas que todos importan:

```python
# Constantes
MSG_HELLO   = 0x01
MSG_WELCOME = 0x02
MSG_BEACON  = 0x03
MSG_TASK    = 0x04
MSG_RESULT  = 0x05
MSG_NOP     = 0x06
MSG_ERROR   = 0x07

# Clases
class NonceCounter:             # start=0 servidor, start=1 agente
    def next(self) -> bytes: ...

# Funciones de frame
def build_frame(msg_type, plaintext, chacha, nonce_counter) -> bytes: ...
def parse_frame(raw, chacha) -> tuple[int, bytes]: ...        # lanza InvalidTag

# Funciones de handshake
def agent_handshake(server_static_pub_bytes) -> tuple[bytes, bytes, bytes]: ...
def agent_process_welcome(welcome_raw, agent_priv, agent_pub_bytes) -> tuple[bytes, bytes, ChaCha20Poly1305, NonceCounter]: ...
def server_process_hello(hello_raw, server_static_priv) -> tuple[bytes, bytes, bytes, ChaCha20Poly1305, NonceCounter]: ...
```

P2 solo necesita llamar `agent_handshake()` + `agent_process_welcome()` + `build_frame()` + `parse_frame()`. No necesita entender la cripto.

---

### Contrato 6 — Framework del servidor (P1 ↔ P3)

**Discrepancia encontrada:** P1 (`docs.md`) escribió el broker skeleton en FastAPI. P3 (`Briefing_P3`) usa aiohttp.

**Resolución:** **P3 usa aiohttp**. El skeleton de FastAPI de P1 es referencia de lógica (colas, handshake, manejo de tipos de mensaje), no el código a ejecutar. P3 traduce esa lógica a aiohttp con sus propias rutas. FastAPI no entra en el servidor.

---

### Contrato 7 — Wire format de HELLO y WELCOME (P1 ↔ P3)

**Discrepancia encontrada:** P3 tiene HELLO/WELCOME con JSON (`{"pub_key": "<hex>", ...}`). P1 y el Spec tienen HELLO/WELCOME binarios.

**Resolución — formato binario único (P3 debe adaptar su código):**

```
HELLO   = bytes([0x01]) + agent_eph_pub_bytes    # 33 bytes: TYPE(1) + pub(32)
WELCOME = bytes([0x02]) + server_pub_bytes(32) + salt(16) + bytes([len(session_id)]) + session_id_bytes
```

**P3: cómo adaptar `handle_hello`** (reemplazar la versión JSON):

```python
async def handle_hello(body: bytes) -> web.Response:
    # body[0] = 0x01 (TYPE), body[1:33] = pub_efimera_agente (32 bytes raw)
    agent_pub_bytes = body[1:33]

    # Derivar session_key con el módulo de P1
    welcome_frame, session_id, session_key, chacha, srv_nonce = \
        server_process_hello(body, SERVER_STATIC_PRIV)

    # Guardar sesión
    sesiones[session_id.hex()] = {
        "session_key": session_key,
        "chacha":      chacha,
        "srv_nonce":   srv_nonce,
        "agent_id":    None,
        "last_seen":   time.time(),
    }

    return web.Response(body=welcome_frame, content_type="application/octet-stream")
```

**P3: cómo adaptar el agente extrae el WELCOME** (lo hace P2, no P3, pero que quede documentado):
```python
# P2 recibe WELCOME binario:
assert welcome_raw[0] == 0x02
server_pub_bytes = welcome_raw[1:33]    # 32 bytes
salt             = welcome_raw[33:49]   # 16 bytes
sid_len          = welcome_raw[49]      # 1 byte
session_id       = welcome_raw[50:50 + sid_len]  # sid_len bytes
```

---

### Contrato 8 — Interfaz del módulo `cripto.py` / `protocol.py` (P1 → P3)

**Discrepancia encontrada:** P3 espera `cripto.cifrar(session_key, nonce_int, payload)`. P1 entrega `build_frame(msg_type, plaintext, chacha, nonce_counter)`.

**Resolución — P1 entrega TWO niveles de interfaz:**

**Nivel alto (lo que P3 usa directamente):**
```python
# En server_process_hello — ya documentado en Contrato 7
welcome_frame, session_id, session_key, chacha, srv_nonce = \
    server_process_hello(hello_raw, SERVER_STATIC_PRIV)

# Cifrar una respuesta (TASK, NOP, ERROR):
frame = build_frame(msg_type, payload_json_bytes, chacha, srv_nonce)
# srv_nonce.next() se llama internamente — P3 nunca toca el entero

# Descifrar frame entrante (BEACON, RESULT):
from cryptography.exceptions import InvalidTag
try:
    msg_type, plaintext = parse_frame(raw_body, chacha)
except InvalidTag:
    return web.Response(body=error_frame, status=401, ...)
```

**Nivel bajo (wrappers que P1 añade para P3 si prefiere el estilo del Briefing):**
```python
# Wrappers opcionales en protocol.py para compatibilidad con el estilo de P3
def cifrar(session_key: bytes, nonce_int: int, payload: bytes) -> bytes:
    nonce = nonce_int.to_bytes(12, "little")
    return ChaCha20Poly1305(session_key).encrypt(nonce, payload, None)

def descifrar(session_key: bytes, nonce_int: int, frame_body: bytes) -> bytes:
    nonce  = frame_body[:12]
    ct_tag = frame_body[12:]
    return ChaCha20Poly1305(session_key).decrypt(nonce, ct_tag, None)
```

**Recomendación:** usar el nivel alto (`build_frame`/`parse_frame`) porque el `NonceCounter` interno garantiza que nunca se reutiliza un nonce. Con el nivel bajo, P3 gestiona el contador manualmente y es más fácil cometer un error.

---

### Resumen de dependencias entre personas

```
P1 (protocolo/cripto)
  └─► entrega protocol.py con:
        ├─► server_process_hello / build_frame / parse_frame
        ├─► agent_handshake / agent_process_welcome
        └─► NonceCounter, constantes MSG_*

        ├─► P2 (agente) importa: agent_handshake, agent_process_welcome,
        │                        build_frame, parse_frame
        └─► P3 (servidor) importa: server_process_hello, build_frame, parse_frame

P3 (servidor, aiohttp)
  └─► expone API HTTP
        ├─► POST /          → protocolo Nexus (agentes P2)
        ├─► GET  /agents    → P4 CLI/panel
        ├─► POST /agents/{id}/task   → P4
        ├─► GET  /agents/{id}/results → P4
        └─► GET  /          → sirve index.html de P4 (Fase 5)

P4 (operador)
  └─► consume API de P3 con requests
  └─► entrega index.html que P3 sirve en GET /
```

---

> **Cierre.** Cualquier API que un miembro del equipo necesite y no esté aquí: añadirla en la sección correspondiente con el snippet oficial y el link a la fuente — este documento es vivo durante las 24h.
