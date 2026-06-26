import logging
from aiohttp import web
from redirector.redirector import build_app, C2_URL, REDIRECTOR_PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("nexus.redirector")
log.info("Smart Redirector — escuchando en :%d → C2 en %s", REDIRECTOR_PORT, C2_URL)
web.run_app(build_app(), host="0.0.0.0", port=REDIRECTOR_PORT)
