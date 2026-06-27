#!/bin/bash
# Arma el paquete del agente listo para copiar a la máquina vulnerable.
#
# ANTES de correr este script:
#   1. Edita deploy/config.env con la IP de tu laptop
#   2. Inicia el servidor: python3 -m server
#
# Uso (desde la raíz del repositorio):
#   chmod +x deploy/build_package.sh
#   ./deploy/build_package.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT="$ROOT/nexus-agent"
CONFIG="$SCRIPT_DIR/config.env"

# ── Leer config.env ───────────────────────────────────────────────────────────
if [ ! -f "$CONFIG" ]; then
    echo "[!] ERROR: deploy/config.env no encontrado."
    exit 1
fi
source "$CONFIG"

echo "============================================"
echo "  Nexus C2 — Construyendo paquete agente"
echo "  Servidor : $NEXUS_SERVER"
echo "  Transporte: $NEXUS_TRANSPORT"
echo "============================================"
echo ""

# ── Verificar server_pub.hex ──────────────────────────────────────────────────
if [ ! -f "$ROOT/server_pub.hex" ]; then
    echo "[!] ERROR: server_pub.hex no encontrado."
    echo "    Inicia el servidor primero: python3 -m server"
    exit 1
fi

# ── Limpiar y crear carpeta de salida ─────────────────────────────────────────
rm -rf "$OUT"
mkdir -p "$OUT"

# ── Copiar archivos del agente ────────────────────────────────────────────────
cp -r "$ROOT/agent"       "$OUT/agent"
cp    "$ROOT/protocol.py" "$OUT/protocol.py"
cp    "$ROOT/server_pub.hex" "$OUT/server_pub.hex"
cp    "$SCRIPT_DIR/requirements-agent.txt" "$OUT/requirements.txt"
cp    "$SCRIPT_DIR/install.sh" "$OUT/install.sh"
chmod +x "$OUT/install.sh"

# ── Embeber configuración en el paquete ───────────────────────────────────────
cat > "$OUT/config.env" <<EOF
NEXUS_SERVER=$NEXUS_SERVER
NEXUS_TRANSPORT=$NEXUS_TRANSPORT
EOF

# ── Limpiar __pycache__ ───────────────────────────────────────────────────────
find "$OUT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "[+] Paquete listo en: $OUT"
echo ""
echo "Siguiente paso — copiar a la Raspberry Pi:"
echo ""
echo "   scp -r $OUT pi@<IP_RASPBERRY>:~/nexus-agent"
echo ""
echo "Luego en la Raspberry:"
echo ""
echo "   cd ~/nexus-agent && ./install.sh"
