# Nexus C2 — Bitácora de Avance

> Registro del progreso durante la Hackathon Aligo — Defensores Informáticos (24h).
> Actualizar en cada gate superado, decisión tomada en tiempo real o problema resuelto.

---

## Estado de fases

| Fase | Objetivo | Gate de validación | Estado |
|------|----------|--------------------|--------|
| 0 | Protocolo y cripto definidos en papel | Equipo entiende el frame y el handshake | ✅ Completada |
| 1 | Servidor acepta BEACON en claro, imprime en consola | Se ve el beacon llegar | ✅ Completada |
| 2 | TASK/RESULT en claro: operador manda `whoami`, vuelve la salida | Comando ida y vuelta funciona | ✅ Completada |
| 3 | Handshake ECDH + cifrado AEAD del canal | Mismo flujo cifrado; Wireshark no ve texto | ✅ Completada |
| 4 | Múltiples agentes + cola + reconexión | 2-3 agentes simultáneos estables | ✅ Completada |
| 5 | Panel de operador + jitter en beacon | Demo visual lista | ✅ Completada |
| 6 | Documentación + grabación de video | 4 entregables completos | ⬜ Pendiente |

---

## Decisiones tomadas en tiempo real

> Registrar aquí cualquier decisión que cambie o precise lo definido en el Spec.
> Formato: **fecha/hora — decisión — razón**.

| Hora | Decisión | Razón |
|------|----------|-------|
| Pre-hackathon | Framework servidor: **aiohttp** (no FastAPI) | P3 ya tenía código escrito con aiohttp; FastAPI era referencia de lógica, no del servidor final |
| Pre-hackathon | Carpeta del operador: **`console/`** (no `operator/`) | `operator` es un módulo de la stdlib de Python — conflicto de nombres |
| Pre-hackathon | `info` de HKDF incluye ambas claves públicas | Vincula la `session_key` a la sesión concreta; previene replay |
| Pre-hackathon | HELLO/WELCOME en formato **binario puro** (no JSON) | Consistencia con el resto del protocolo; P3 y P2 deben respetar este formato |
| 2026-06-26 | Agente distribuido vía `NEXUS_SERVER_PUB` (env var) en lugar de copiar `server_pub.hex` | El agente corre en máquina diferente al servidor; intercambio manual de la clave pública hex por canal seguro (fuera de banda) |
| 2026-06-26 | `!persist` corregido para incluir `NEXUS_SERVER` y `NEXUS_SERVER_PUB` en la línea cron | Sin env vars, el agente arrancaba apuntando a `127.0.0.1:8080` y fallaba silenciosamente tras reboot |

---

## Problemas encontrados y resoluciones

> Registrar bloqueos, bugs de integración y cómo se resolvieron.
> Formato: **fase — problema — resolución**.

| Fase | Problema | Resolución |
|------|----------|------------|
| Deploy | `websocket-client` no estaba en `requirements.txt` — ImportError al arrancar el agente | `pip install websocket-client`; pendiente añadir al `requirements.txt` |
| Deploy | El agente necesita la clave pública del servidor (`server_pub.hex`) para el handshake X25519, pero el fichero solo existe donde corre el servidor | El operador comparte el hex por canal fuera de banda; el agente lo recibe como `NEXUS_SERVER_PUB` env var |
| Plugins | `!persist` instalaba crontab sin variables de entorno → el agente no sabía a qué servidor conectar tras reboot | Corregido `persist.py`: la línea `@reboot` incluye `NEXUS_SERVER` y `NEXUS_SERVER_PUB` capturados en tiempo de ejecución |
| Plugins | `!download` confundido con exfiltración — el plugin descarga FROM internet TO el agente, no al revés | Aclarado en docs: `!download <url> <ruta_local>` es dropper. Para exfiltrar usar `cat` + copiar desde panel, o implementar `!upload` |
| Plugins | `!clip write` reportaba exit=1 aunque sí escribía el portapapeles — `wl-copy` bloquea indefinidamente con `subprocess.run` y disparaba `TimeoutExpired` | Cambiado a `subprocess.Popen` para lanzarlo en background; se verifica leyendo el portapapeles de vuelta (`_read_clipboard`) antes de retornar éxito. Fix en `clip.py`. |
| Plugins | `!keylog start` fallaba con mensaje hardcodeado cuando `pynput` no estaba instalado | `_start_listener` ahora intenta auto-instalar `pynput` con pip; si falla propaga el error real. Fix en `keylog.py`. |
| Plugins | **PENDIENTE** `!keylog` en Wayland (Fedora 44 KDE) solo captura teclas especiales (alt, ctrl, shift, enter, backspace) — las letras normales no aparecen | Wayland bloquea por diseño el acceso al teclado entre aplicaciones. Workarounds posibles: (1) arrancar el agente con `XDG_SESSION_TYPE=x11` para forzar XWayland; (2) probar en agente Windows donde pynput captura sin restricciones; (3) investigar uso de `evdev` directo sobre `/dev/input/eventX` (requiere root o grupo `input`). **Asignado a quien tenga acceso a agente Windows o sesión X11.** |

---

## Registro de integración

> Hitos de integración entre componentes — primera vez que dos piezas del equipo funcionan juntas.

| Hito | Descripción | Hora |
|------|-------------|------|
| P3 ↔ P2 Fase 1 | Primer beacon de P2 recibido por el servidor de P3 | — |
| P3 ↔ P2 Fase 2 | Primer comando `whoami` ejecutado de extremo a extremo | — |
| P1 → P3 Fase 3 | `protocol.py` integrado en el servidor — primer beacon cifrado | — |
| P1 → P2 Fase 3 | `protocol.py` integrado en el agente — handshake completo | — |
| P4 ↔ P3 Fase 2 | CLI del operador conectada a la API del servidor | — |
| Demo | Sistema completo con N agentes y panel web funcionando | — |
| **Prueba real** | Agente en Raspberry Pi conectado a servidor remoto vía ngrok (HTTPS) — handshake X25519 completado, sesión cifrada estable | 2026-06-26 ~17:34 |
| **Prueba real** | Plugins probados en producción: `!sysinfo`, `!screenshot`, `!persist` — comandos shell ejecutados desde panel | 2026-06-26 ~17:45 |
| **Prueba real** | Persistencia vía crontab validada (con fix de env vars) — agente sobrevive reboot y reconecta al C2 automáticamente | 2026-06-26 ~18:00 |
| **Reconocimiento** | SSH puerto 22 detectado abierto en la máquina agente — PasswordAuthentication habilitado por defecto (Raspberry Pi OS) | 2026-06-26 |

---

## Mejoras post-hackathon

### 2026-06-26 — Plugin `!screenshot`: captura silenciosa multiplataforma

**Archivos:** `agent/plugins/screenshot.py`

**Por qué se hizo:**
La versión original (`_try_system_tools` + `_try_mss`) tenía tres problemas de campo:

1. **No era silenciosa.** `gnome-screenshot` y `spectacle` sin flags adecuados abren una ventana de previsualización o emiten un sonido del obturador, lo que delata la ejecución ante el usuario del equipo comprometido.
2. **Sin cobertura multiplataforma.** Sólo corría en Linux; no había ruta para Windows ni macOS.
3. **Detección Wayland frágil.** Dependía únicamente de `XDG_SESSION_TYPE`, que en sesiones gráficas remotas o entornos sin systemd puede estar vacía, cayendo silenciosamente en la cadena incorrecta.

**Qué se cambió (primera pasada):**
- Funciones por plataforma separadas: `_linux_wayland`, `_linux_x11`, `_linux_mss`, `_windows`, `_macos`.
- macOS usa `screencapture -x` (suprime sonido y notificación del sistema).
- Windows usa `Pillow.ImageGrab` (Python puro, sin notificación).
- Linux Wayland prioriza `grim` (nativo, completamente silencioso).
- Linux X11 prioriza `scrot` (silencioso por defecto).
- `mss` como último recurso en Linux (Python puro, sin UI).

**Qué se cambió (segunda pasada — refactorización):**
- Se centralizó el manejo de excepciones en `_try(cmd, out_path)` para eliminar el patrón `try/except FileNotFoundError` repetido en cada función.
- `_mss()` y `_pillow()` reciben `out_path` como parámetro en lugar de depender del global `_OUT`, lo que permite reutilizarlas en Windows con ruta distinta.
- Cadena Wayland ampliada: `grim → spectacle -b -n → import (ImageMagick) → mss`.
- Cadena X11 ampliada: `scrot → spectacle -b -n → import → mss → gnome-screenshot` (gnome-screenshot al final porque puede mostrar notificación).
- Fallback `loginctl show-session` para detectar Wayland cuando `XDG_SESSION_TYPE` está vacía (entornos sin D-Bus de usuario o sesiones root).
- Mensaje de error accionable con instrucciones de instalación por OS (`dnf install grim`, `dnf install scrot`, `pip install mss`).

---

### 2026-06-26 — Panel de operador: barra de plugins y dropdown de shell rápido

**Archivos:** `server/broker.py` (sección `_PANEL_HTML`)

**Por qué se hizo:**
El terminal del panel requería que el operador recordara y escribiera manualmente cada nombre de plugin (`!sysinfo`, `!screenshot`, etc.) y cada comando de reconocimiento habitual (`whoami`, `id`, `ps aux`…). Durante una operación bajo presión esto genera fricción, errores tipográficos y retraso.

**Qué se cambió:**

| Componente | Cambio | Razón |
|------------|--------|-------|
| CSS `.plugin-bar` / `.plugin-btn` | Barra de botones de plugins en la parte inferior del terminal | Acceso con un clic a los plugins más usados sin necesidad de recordar la sintaxis |
| CSS `.plugin-btn.needs-arg` | Color ámbar para botones que requieren un argumento adicional | Distinción visual inmediata entre plugins autoejecutables y los que necesitan completar el comando |
| CSS `.cmd-row` / `.cmd-select` | Dropdown de comandos shell frecuentes | Evita reescribir comandos de reconocimiento repetitivos en cada sesión |
| HTML terminal | Barra de plugins con `!sysinfo`, `!screenshot`, `!persist`, `!help`, `!download ···` | Cobertura de los 5 plugins más comunes en el flujo de post-explotación |
| HTML terminal | Dropdown con 15 comandos de reconocimiento | `whoami`, `id`, `ps aux`, `ls -la`, `cat /etc/passwd`, `ip a`, `ss -tlnp`, `env`, `uname -a`, `df -h`, `free -h`, etc. |
| JS `runPlugin(cmd)` | Inserta el comando en el input y llama a `sendCmd()` directamente | Permite ejecutar plugins sin interacción con el teclado |
| JS `fillInput(prefix)` | Pre-rellena el input y posiciona el cursor al final | Para `!download` y otros que necesitan argumento: el operador sólo añade la ruta |
| JS `pickShell(sel_el)` | Toma el valor del dropdown, lo mete en el input y ejecuta | Resetea el dropdown a la opción vacía tras la selección para permitir repetición |

Los IDs del DOM (`term-title`, `term-body`, `term-prompt`, `term-input`) se mantuvieron sin cambios para que todo el JS preexistente siguiera funcionando sin modificaciones.

---

## Equipo

| Persona | Frente | Componente |
|---------|--------|------------|
| P1 | Protocolo + criptografía | `protocol.py` |
| P2 | Agente / implante | `agent/agent.py` |
| P3 | Servidor C2 | `server/broker.py` |
| P4 | Operador + docs + video | `console/cli.py`, `console/static/index.html`, `docs/` |
