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
| 5 | Panel de operador + jitter en beacon | Demo visual lista | ⬜ Pendiente |
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

---

## Problemas encontrados y resoluciones

> Registrar bloqueos, bugs de integración y cómo se resolvieron.
> Formato: **fase — problema — resolución**.

| Fase | Problema | Resolución |
|------|----------|------------|
| — | — | — |

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

---

## Equipo

| Persona | Frente | Componente |
|---------|--------|------------|
| P1 | Protocolo + criptografía | `protocol.py` |
| P2 | Agente / implante | `agent/agent.py` |
| P3 | Servidor C2 | `server/broker.py` |
| P4 | Operador + docs + video | `console/cli.py`, `console/static/index.html`, `docs/` |
