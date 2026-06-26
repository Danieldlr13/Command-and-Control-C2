# Nexus C2 — Arquitectura y Decisiones de Diseño

> **Audiencia:** jurado técnico de la Hackathon Aligo — Defensores Informáticos.
> **Propósito:** documentar la arquitectura del sistema, el razonamiento detrás de cada decisión de diseño y el esquema criptográfico implementado.

---

## 1. Resumen ejecutivo

Nexus C2 es un framework de Command & Control que implementa un **protocolo binario propio** sobre HTTP, con **cifrado de extremo a extremo con forward secrecy** y **beaconing con jitter**. A diferencia de soluciones que delegan la seguridad a TLS de librería, Nexus diseña y razona cada primitiva criptográfica desde cero, lo que permite explicar y defender cada decisión ante cualquier auditoría técnica.

El sistema opera en un entorno de laboratorio cerrado y autorizado. Sus tres componentes — servidor, agente y consola de operador — se comunican exclusivamente a través del protocolo Nexus, que actúa como contrato entre los frentes de desarrollo.

---

## 2. Arquitectura general

```
┌─────────────────────────────────────────────────────────────┐
│                     CONSOLA DE OPERADOR                      │
│              CLI interactiva  /  Panel web                   │
└────────────────────────┬────────────────────────────────────┘
                         │  REST HTTP
                         │  GET /agents
                         │  POST /agents/{id}/task
                         │  GET /agents/{id}/results
                         │  GET / → index.html (panel web)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    SERVIDOR C2 — BROKER                      │
│                  aiohttp  ·  asyncio  ·  Python              │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │  Registro   │  │  Colas de    │  │  API del          │  │
│  │  sesiones   │  │  tareas por  │  │  operador         │  │
│  │  + agentes  │  │  agente      │  │  (plano control)  │  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
└────────┬─────────────────┬──────────────────┬───────────────┘
         │                 │                  │
         │  Protocolo Nexus — POST /
         │  X-Session-Id en cabecera HTTP
         │  Frame: [TYPE][NONCE][CIPHERTEXT+TAG]
         ▼                 ▼                  ▼
   ┌──────────┐      ┌──────────┐      ┌──────────┐
   │ AGENTE 1 │      │ AGENTE 2 │      │ AGENTE N │
   │ session  │      │ session  │      │ session  │
   │ key K1   │      │ key K2   │      │ key KN   │
   └──────────┘      └──────────┘      └──────────┘
```

**Separación de planos:**
- **Plano de agentes** (`POST /`): protocolo Nexus binario con cifrado AEAD por sesión. Cada agente tiene su propia `session_key` derivada de un ECDH efímero.
- **Plano de control** (`/agents/*`): API REST HTTP interna para el operador. El servidor orquesta; no ejecuta comandos.

---

## 3. Protocolo Nexus

### 3.1 Formato de frame

```
┌────────┬──────────────────┬──────────────────────────────┐
│  TYPE  │  NONCE (12 B)    │  CIPHERTEXT + TAG (variable) │
│  1 B   │                  │  ChaCha20-Poly1305 output    │
└────────┴──────────────────┴──────────────────────────────┘
```

El frame viaja en el **cuerpo de `POST /`**. HTTP actúa de portador — la semántica del protocolo vive íntegramente en el frame. No hay campo `LEN`: `Content-Length` de HTTP delimita el mensaje.

**Excepción de handshake:** HELLO y WELCOME viajan en claro con formato propio porque la `session_key` aún no existe. El frame cifrado aplica desde el primer BEACON.

### 3.2 Máquina de estados

```
         ┌──────────────────────────────────────┐
         │           HANDSHAKE (una vez)         │
         │                                       │
         │  HELLO ──────────────────► WELCOME   │
         │  agente → server         server → agente │
         └──────────────────────────────────────┘
                          │
                          ▼ canal cifrado establecido
         ┌──────────────────────────────────────┐
         │           LOOP DE BEACONING           │
         │                                       │
         │  BEACON ─────────────────► TASK      │
         │  agente → server         server → agente │
         │                                       │
         │  BEACON ─────────────────► NOP       │
         │  agente → server         server → agente │
         │                                       │
         │  RESULT ─────────────────► (ACK)     │
         │  agente → server                      │
         └──────────────────────────────────────┘
```

### 3.3 Tipos de mensaje

| TYPE | Nombre  | Dirección        | Descripción |
|------|---------|------------------|-------------|
| 0x01 | HELLO   | agente → server  | Inicio de handshake; clave pública X25519 efímera (32 B raw) |
| 0x02 | WELCOME | server → agente  | Respuesta; clave pública servidor + salt + session_id |
| 0x03 | BEACON  | agente → server  | "Estoy vivo, ¿hay trabajo?"; primer beacon incluye `agent_id` |
| 0x04 | TASK    | server → agente  | Comando con `task_id` y `timeout_s` |
| 0x05 | RESULT  | agente → server  | Salida del comando: `exit_code`, `stdout`, `stderr` |
| 0x06 | NOP     | server → agente  | Sin trabajo pendiente |
| 0x07 | ERROR   | ambos            | Error de protocolo o sesión inválida |

### 3.4 Correlación de sesión sobre HTTP sin estado

HTTP es sin estado — cada request puede llegar por una conexión TCP distinta. Para correlacionar cada BEACON/RESULT con su sesión sin socket persistente, el servidor entrega un `session_id` opaco en WELCOME. El agente lo incluye en la cabecera `X-Session-Id` de cada request posterior.

El servidor lee `X-Session-Id` **antes** de descifrar para recuperar la `session_key` asociada. Incluir el `session_id` dentro del ciphertext crearía un problema huevo-y-gallina (habría que saber qué clave usar para saber qué clave usar).

---

## 4. Esquema criptográfico

### 4.1 Visión general

```
Agente                                          Servidor
  │                                                 │
  │  genera par efímero X25519                      │  par estático X25519
  │  (privA_efímera, pubA_efímera)                  │  (privS_static, pubS_static)
  │                                                 │
  │  HELLO [pubA_efímera 32B] ─────────────────►   │
  │                                                 │  ECDH(privS, pubA) → shared
  │                                                 │  salt = random(16B)
  │                                                 │  session_key = HKDF(shared, salt, info)
  │                                                 │  session_id = random(32B)
  │  ◄── WELCOME [pubS 32B][salt 16B][sid] ────────  │
  │                                                 │
  │  ECDH(privA_efímera, pubS) → shared             │
  │  session_key = HKDF(shared, salt, info)         │
  │                                                 │
  │  ══════════ canal cifrado establecido ══════    │
  │                                                 │
  │  BEACON cifrado ────────────────────────────►   │
  │  X-Session-Id: <session_id.hex()>               │
```

### 4.2 X25519 — intercambio de claves

Curve25519 es una curva de Montgomery diseñada para resistir ataques de canal lateral. El agente genera un **par efímero** en cada handshake — la clave privada no sobrevive a la sesión, lo que garantiza **forward secrecy**: comprometer la clave estática del servidor no expone sesiones pasadas.

La clave pública estática del servidor va **embebida en el agente** (pinning). El agente solo acepta comunicarse con ese servidor, eliminando el riesgo de MITM en el laboratorio sin necesidad de una CA.

### 4.3 HKDF-SHA256 — derivación de clave de sesión

El output de X25519 es la coordenada x de un punto de curva — tiene estructura matemática y no es uniformemente aleatorio. Usarlo directamente como clave sería un error criptográfico. HKDF lo convierte en material de clave seguro:

```
session_key = HKDF-SHA256(
    ikm  = shared_secret,          # output de ECDH (32 B)
    salt = salt,                    # 16 B aleatorios del servidor (en WELCOME)
    info = b"nexus-c2-v1-session-key" + agent_pub_bytes + server_pub_bytes,
    len  = 32                       # 256 bits para ChaCha20-Poly1305
)
```

El campo `info` vincula la clave derivada a esta sesión concreta (ambas claves públicas) y al protocolo (`"nexus-c2-v1-session-key"`), previniendo ataques de replay entre sesiones o contextos distintos.

### 4.4 ChaCha20-Poly1305 — cifrado autenticado (AEAD)

Proporciona **confidencialidad + integridad** en una sola primitiva. El tag de Poly1305 (16 B, appended al ciphertext) garantiza que cualquier manipulación del mensaje en tránsito se detecta antes de procesar el payload.

Se eligió ChaCha20 sobre AES-256-GCM por:
- Más simple de implementar sin aceleración de hardware (AES-NI)
- Resistente a timing attacks en software puro
- Estándar moderno: TLS 1.3, WireGuard, Signal Protocol

### 4.5 Gestión de nonce — contador por sesión

ChaCha20-Poly1305 se rompe catastróficamente si se repite un nonce con la misma clave. El nonce aleatorio ofrece unicidad *probabilística*: la probabilidad de colisión con un nonce de 96 bits es ínfima para cualquier volumen de tráfico realista, pero sigue siendo no cero. En criptografía, "probablemente seguro" no es suficiente cuando se puede tener certeza matemática.

Solución: **contador incremental de 12 bytes (little-endian)**, que garantiza unicidad de forma absoluta, con espacio separado por dirección:

| Lado | Nonces | Valores |
|---|---|---|
| Servidor | Pares | 0, 2, 4, 6, … |
| Agente | Impares | 1, 3, 5, 7, … |

Ambos lados comparten la `session_key` sin riesgo de colisión. El contador se incrementa en cada envío físico, incluso en reintentos. La idempotencia (no ejecutar dos veces el mismo comando) la garantiza el `task_id` a nivel de aplicación — capas separadas con responsabilidades separadas.

---

## 5. Decisiones de diseño

### 5.1 HTTP como portador en lugar de TCP crudo

**Elegimos HTTP** porque el tráfico beaconing se mezcla con tráfico web normal. Un detector de intrusiones que filtre por protocolo no distingue un beacon de una petición legítima. TCP crudo con socket persistente es inmediatamente identificable como C2 por su patrón de tráfico.

Implicación: el servidor no puede correlacionar requests con sesiones por el socket (HTTP es sin estado) → necesitamos `X-Session-Id`.

### 5.2 Frame binario propio en lugar de JSON sobre el socket

**Elegimos frame binario** porque nos permite meter el nonce explícitamente en el wire, controlar la serialización al byte, y tener un artefacto técnico propio que argumentar ante el jurado. JSON sobre socket no da control sobre el framing ni permite meter primitivas criptográficas de forma natural.

### 5.3 `agent_id` en el primer BEACON cifrado, no en HELLO

HELLO viaja en claro. Si el `agent_id` viajara en HELLO, quedaría expuesto en el tráfico y sería un identificador enlazable entre sesiones (un observador podría rastrear al agente entre reconexiones). Al mandarlo en el primer BEACON cifrado, el identificador estable del agente nunca aparece en texto claro.

### 5.4 Nonce contador en lugar de nonce aleatorio

El nonce aleatorio en un espacio de 96 bits ofrece probabilidad de colisión negligible para cualquier volumen de tráfico realista. Sin embargo, elegimos un contador porque proporciona **unicidad garantizada matemáticamente**, no estadísticamente: es imposible, no improbable, que dos mensajes compartan nonce en la misma sesión. La separación pares/impares evita colisiones entre las dos direcciones de comunicación que comparten la misma `session_key`.

### 5.5 Clave X25519 efímera por sesión en lugar de clave estática del agente

Una clave estática del agente comprometería todas sus sesiones pasadas si la clave cae. La clave efímera por sesión garantiza forward secrecy: cada sesión tiene su propio `session_key` que no puede reconstruirse aunque se capture la clave estática del servidor o la efímera de otra sesión.

### 5.6 Beaconing con jitter en lugar de intervalo fijo

Un intervalo fijo crea un patrón de tráfico determinista — trivialmente detectable con análisis estadístico de flujo. El jitter aleatoriza el intervalo, rompiendo el patrón. Implementación: `sleep = BASE + uniform(0, JITTER_MAX)`.

---

## 6. Limitaciones conocidas

| Limitación | Descripción | Solución en producción |
|---|---|---|
| Sin autenticación del agente | El servidor acepta cualquier agente que complete el handshake | PSK por agente o firma Ed25519 en HELLO |
| `agent_id` afirmado, no verificado | El agente declara su ID; el servidor lo acepta sin prueba criptográfica | Ligar `agent_id` a una firma Ed25519 con clave pre-registrada |
| Estado en memoria | Si el servidor cae, se pierden sesiones y colas de tareas | Persistir estado en SQLite o Redis |
| Sin rotación de claves de sesión | Una sesión larga usa la misma `session_key` indefinidamente | Renegociar handshake periódicamente |
| Sin protección contra replay a nivel de sesión | Un RESULT capturado podría reenviarse | Añadir timestamp al payload y ventana de aceptación |

---

## 7. Posibles extensiones (Nivel 3-4)

- **Autenticación del agente:** PSK por agente o firma Ed25519 en el frame HELLO para que el servidor solo acepte agentes pre-registrados.
- **Canales no convencionales:** DNS (subtypes TXT/A como canal de datos), ICMP echo payload, o HTTP con headers personalizados para mayor camuflaje.
- **Agentes modulares con plugins:** sistema de extensiones donde el servidor puede desplegar módulos adicionales al agente en tiempo de ejecución.
- **Múltiples saltos / redirectores:** proxy intermedio que reenvía el tráfico al servidor real, ocultando su dirección IP.
- **Serialización binaria (MessagePack/CBOR):** migrar el payload JSON a formato binario compacto para reducir footprint y aumentar ofuscación.
