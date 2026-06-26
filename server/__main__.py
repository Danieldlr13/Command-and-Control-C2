from aiohttp import web
from server.broker import build_app

web.run_app(build_app(), host="0.0.0.0", port=8080)
