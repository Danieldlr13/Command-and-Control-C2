# Nexus C2

Framework de Command & Control desarrollado para la **Hackathon Aligo — Defensores Informáticos** (laboratorio cerrado y autorizado).

---

## Descripción

Nexus C2 es un sistema de comando y control que implementa un protocolo binario propio con cifrado de extremo a extremo y forward secrecy. Está diseñado para demostrar una arquitectura C2 sólida, segura y extensible, con énfasis en la capa criptográfica y el diseño de protocolo.

### Características principales

- **Protocolo binario propio** — frame `[TYPE][NONCE][CIPHERTEXT+TAG]` sobre HTTP como portador
- **Forward secrecy por sesión** — intercambio de claves X25519 (ECDH) efímero en cada handshake
- **Cifrado autenticado** — ChaCha20-Poly1305 (AEAD) con gestión de nonce por contador
- **Beaconing con jitter** — patrón de tráfico no determinista
- **Tareas idempotentes** — cada comando lleva un `task_id` único (UUID)
- **Múltiples agentes** — broker async con cola de tareas por agente

---

## Arquitectura

```
  OPERADOR (CLI / panel web)
       |
       | REST/WS  →  GET/POST /agents/*
       ▼
  SERVIDOR C2 — broker async (aiohttp)
       |
       | Protocolo Nexus  →  POST /
       | X-Session-Id en cabecera HTTP
       ├──────────────┬──────────────┐
       ▼              ▼              ▼
   AGENTE 1       AGENTE 2      AGENTE N
```

---

## Estructura del repositorio

```
├── protocol.py          # Codec del protocolo, handshake y criptografía (compartido)
├── server/
│   └── broker.py        # Servidor C2 async (aiohttp)
├── agent/
│   └── agent.py         # Agente: beaconing, ejecución de comandos
├── console/
│   ├── cli.py           # CLI interactiva del operador
│   └── static/
│       └── index.html   # Panel web (Fase 5)
├── docs/
│   ├── Nexus_Documentacion_Tecnica.md   # Referencia técnica completa
│   ├── arquitectura.md                  # Diagrama y decisiones de diseño
│   └── bitacora.md                      # Registro de avance por fases
└── tests/
    └── test_protocol.py  # Tests del codec y la criptografía
```

---

## Instalación

```bash
git clone https://github.com/Danieldlr13/Command-and-Control-C2.git
cd Command-and-Control-C2
pip install -r requirements.txt
```

---

## Uso

### Levantar el servidor C2

```bash
python -m server
```

El servidor escucha en `0.0.0.0:8080`.

### Lanzar un agente

```bash
python -m agent
```

El agente genera su `agent_id` persistente, realiza el handshake y entra en el loop de beaconing.

### CLI del operador

```bash
python -m console
```

Comandos disponibles:

```
nexus> agents                      # lista agentes conectados
nexus> task <agent_id> <comando>   # envía un comando a un agente
nexus> results <agent_id>          # muestra resultados del agente
```

### Panel web

Navegar a `http://localhost:8080` una vez levantado el servidor.

---

## Protocolo

| TYPE | Nombre  | Dirección       | Descripción                              |
|------|---------|-----------------|------------------------------------------|
| 0x01 | HELLO   | agente → server | Inicio de handshake (clave pública X25519) |
| 0x02 | WELCOME | server → agente | Respuesta con clave servidor + salt + session_id |
| 0x03 | BEACON  | agente → server | "Estoy vivo, ¿hay trabajo?"              |
| 0x04 | TASK    | server → agente | Entrega un comando con task_id           |
| 0x05 | RESULT  | agente → server | Devuelve salida del comando              |
| 0x06 | NOP     | server → agente | Sin trabajo pendiente                    |
| 0x07 | ERROR   | ambos           | Error de protocolo o sesión inválida     |

---

## Criptografía

| Primitiva | Uso |
|---|---|
| X25519 (ECDH) | Intercambio de claves con forward secrecy por sesión |
| HKDF-SHA256 | Derivación de `session_key` desde el secreto compartido |
| ChaCha20-Poly1305 | Cifrado autenticado (AEAD) de todos los mensajes |

---

## Documentación

- [`docs/Nexus_Documentacion_Tecnica.md`](docs/Nexus_Documentacion_Tecnica.md) — referencia técnica de APIs y contratos de integración
- [`docs/arquitectura.md`](docs/arquitectura.md) — decisiones de diseño y diagrama de arquitectura
- [`docs/bitacora.md`](docs/bitacora.md) — registro de avance por fases

---

## Contexto

Proyecto desarrollado en el marco de la **Hackathon Aligo — Defensores Informáticos**, en un entorno de laboratorio cerrado y autorizado. El uso de este software fuera de ese contexto es responsabilidad del usuario.
