"""
Tests para protocol.py — handshake, frames, crypto, pinning.
Ejecutar con: python -m pytest tests/ -v
"""
import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from protocol import (
    MSG_BEACON, MSG_NOP, MSG_RESULT, MSG_TASK,
    NonceCounter, build_frame, parse_frame,
    pack_clear, unpack_clear,
    agent_handshake, agent_process_welcome,
    server_process_hello, generate_server_keypair, get_pub_bytes,
    encode_beacon, decode_beacon,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def server_keypair():
    priv, pub = generate_server_keypair()
    return priv, pub


@pytest.fixture
def full_session(server_keypair):
    """Handshake completo. Devuelve (srv_chacha, srv_nc, agent_chacha, agent_nc)."""
    srv_priv, srv_pub = server_keypair
    hello, agent_priv, agent_pub = agent_handshake(srv_pub)
    welcome, session_id, _, srv_chacha, srv_nc = server_process_hello(hello, srv_priv)
    _, _, agent_chacha, agent_nc = agent_process_welcome(
        welcome, agent_priv, agent_pub, expected_server_pub=srv_pub
    )
    return srv_chacha, srv_nc, agent_chacha, agent_nc


# ── NonceCounter ──────────────────────────────────────────────────────────────

def test_nonce_counter_server_even():
    nc = NonceCounter(0)
    assert nc.next() == (0).to_bytes(12, "little")
    assert nc.next() == (2).to_bytes(12, "little")
    assert nc.next() == (4).to_bytes(12, "little")


def test_nonce_counter_agent_odd():
    nc = NonceCounter(1)
    assert nc.next() == (1).to_bytes(12, "little")
    assert nc.next() == (3).to_bytes(12, "little")
    assert nc.next() == (5).to_bytes(12, "little")


def test_nonce_parity_never_collides():
    srv = NonceCounter(0)
    agt = NonceCounter(1)
    srv_nonces = {srv.next() for _ in range(100)}
    agt_nonces = {agt.next() for _ in range(100)}
    assert srv_nonces.isdisjoint(agt_nonces)


# ── Handshake ─────────────────────────────────────────────────────────────────

def test_handshake_derives_same_key(full_session):
    srv_chacha, _, agent_chacha, agent_nc = full_session
    frame = build_frame(MSG_BEACON, b"hello", agent_chacha, agent_nc)
    msg_type, plaintext = parse_frame(frame, srv_chacha)
    assert msg_type == MSG_BEACON
    assert plaintext == b"hello"


def test_handshake_session_id_is_32_bytes(server_keypair):
    srv_priv, srv_pub = server_keypair
    hello, agent_priv, agent_pub = agent_handshake(srv_pub)
    _, session_id, _, _, _ = server_process_hello(hello, srv_priv)
    assert len(session_id) == 32


def test_agent_handshake_rejects_wrong_key_length():
    with pytest.raises(ValueError, match="32 bytes"):
        agent_handshake(b"\x00" * 16)


# ── Key pinning ───────────────────────────────────────────────────────────────

def test_key_pinning_rejects_wrong_server_pub(server_keypair):
    srv_priv, srv_pub = server_keypair
    wrong_pub = get_pub_bytes(X25519PrivateKey.generate())
    hello, agent_priv, agent_pub = agent_handshake(srv_pub)
    welcome, _, _, _, _ = server_process_hello(hello, srv_priv)
    with pytest.raises(ValueError, match="mismatch"):
        agent_process_welcome(welcome, agent_priv, agent_pub, expected_server_pub=wrong_pub)


def test_key_pinning_accepts_correct_pub(server_keypair):
    srv_priv, srv_pub = server_keypair
    hello, agent_priv, agent_pub = agent_handshake(srv_pub)
    welcome, _, _, _, _ = server_process_hello(hello, srv_priv)
    session_id, _, _, _ = agent_process_welcome(
        welcome, agent_priv, agent_pub, expected_server_pub=srv_pub
    )
    assert len(session_id) == 32


# ── Frame encrypt/decrypt roundtrip ───────────────────────────────────────────

def test_frame_roundtrip(full_session):
    srv_chacha, _, agent_chacha, agent_nc = full_session
    for msg_type, payload in [
        (MSG_BEACON, b""),
        (MSG_NOP,    b""),
        (MSG_RESULT, b'{"exit_code":0,"stdout":"ok"}'),
        (MSG_TASK,   b'{"cmd":"whoami"}'),
    ]:
        frame = build_frame(msg_type, payload, agent_chacha, agent_nc)
        got_type, got_payload = parse_frame(frame, srv_chacha)
        assert got_type == msg_type
        assert got_payload == payload


# ── AAD protege el byte TYPE ──────────────────────────────────────────────────

def test_tampered_type_rejected(full_session):
    _, _, agent_chacha, agent_nc = full_session
    frame = build_frame(MSG_BEACON, b"data", agent_chacha, agent_nc)
    tampered = bytes([MSG_TASK]) + frame[1:]  # TYPE alterado
    with pytest.raises(InvalidTag):
        parse_frame(tampered, agent_chacha)


def test_tampered_ciphertext_rejected(full_session):
    srv_chacha, _, agent_chacha, agent_nc = full_session
    frame = build_frame(MSG_BEACON, b"secret", agent_chacha, agent_nc)
    tampered = frame[:-1] + bytes([frame[-1] ^ 0xFF])
    with pytest.raises(InvalidTag):
        parse_frame(tampered, srv_chacha)


# ── Validación de longitud mínima ─────────────────────────────────────────────

def test_parse_frame_too_short_raises():
    with pytest.raises(ValueError, match="too short"):
        parse_frame(b"\x03" + b"\x00" * 10, None)


# ── HELLO / WELCOME malformados ───────────────────────────────────────────────

def test_hello_wrong_type(server_keypair):
    srv_priv, _ = server_keypair
    with pytest.raises(ValueError, match="Expected HELLO"):
        server_process_hello(b"\x99" + b"\x00" * 32, srv_priv)


def test_hello_too_short(server_keypair):
    srv_priv, _ = server_keypair
    with pytest.raises(ValueError):
        server_process_hello(b"\x01" + b"\x00" * 16, srv_priv)


def test_hello_too_long(server_keypair):
    srv_priv, _ = server_keypair
    with pytest.raises(ValueError, match="exactly 33"):
        server_process_hello(b"\x01" + b"\x00" * 33, srv_priv)


def test_welcome_too_short(server_keypair):
    srv_priv, srv_pub = server_keypair
    hello, agent_priv, agent_pub = agent_handshake(srv_pub)
    with pytest.raises(ValueError):
        agent_process_welcome(b"\x02" + b"\x00" * 40, agent_priv, agent_pub)


def test_welcome_wrong_type(server_keypair):
    srv_priv, srv_pub = server_keypair
    hello, agent_priv, agent_pub = agent_handshake(srv_pub)
    with pytest.raises(ValueError, match="Expected WELCOME"):
        agent_process_welcome(b"\x99" + b"\x00" * 81, agent_priv, agent_pub)


# ── Clear frames ──────────────────────────────────────────────────────────────

def test_pack_unpack_clear_roundtrip():
    for msg_type in [0x01, 0x03, 0x06, 0x07]:
        payload = b"test payload"
        raw = pack_clear(msg_type, payload)
        got_type, got_payload = unpack_clear(raw)
        assert got_type == msg_type
        assert got_payload == payload


def test_pack_clear_no_payload():
    raw = pack_clear(0x06)
    assert raw == b"\x06"
    t, p = unpack_clear(raw)
    assert t == 0x06
    assert p == b""


# ── Payload helpers ───────────────────────────────────────────────────────────

def test_encode_decode_beacon():
    data = encode_beacon("agent-1", "host1", "Linux-x86_64", ts=1234567890)
    decoded = decode_beacon(data)
    assert decoded["agent_id"] == "agent-1"
    assert decoded["hostname"] == "host1"
    assert decoded["ts"] == 1234567890


# ── NonceCounter monotonicity (base para anti-replay) ────────────────────────

def test_nonce_counter_always_increases():
    nc = NonceCounter(1)
    prev = -1
    for _ in range(50):
        n = int.from_bytes(nc.next(), "little")
        assert n > prev
        prev = n


def test_two_sessions_independent_nonces(server_keypair):
    """Nonce de una sesión no interfiere con otra sesión."""
    srv_priv, srv_pub = server_keypair
    sessions = []
    for _ in range(2):
        hello, agent_priv, agent_pub = agent_handshake(srv_pub)
        welcome, _, _, srv_chacha, srv_nc = server_process_hello(hello, srv_priv)
        _, _, agent_chacha, agent_nc = agent_process_welcome(
            welcome, agent_priv, agent_pub, expected_server_pub=srv_pub
        )
        sessions.append((srv_chacha, agent_chacha, agent_nc))

    # Cada sesión usa sus propios nonces desde 1
    for srv_chacha, agent_chacha, agent_nc in sessions:
        frame = build_frame(MSG_BEACON, b"hello", agent_chacha, agent_nc)
        msg_type, payload = parse_frame(frame, srv_chacha)
        assert payload == b"hello"
