from loguru import logger
from pathlib import Path
from aiohttp import web
import jinja2
import aiohttp_jinja2
from dotenv import load_dotenv

from . import rss_feeds
from . import weather
from . import requests


TEMPLATE_DIR = Path.cwd()
STATIC_DIR = Path.cwd()

routes = web.RouteTableDef()


def static_filter(path: str) -> str:
    path = path.lstrip('/')
    return f'/static/{path}'

def init_func(argv):
    app = web.Application()
    jinja_env = aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(TEMPLATE_DIR))
    jinja_env.filters['static'] = static_filter
    routes.static('/static', STATIC_DIR)
    for r in [routes, rss_feeds.routes, weather.routes]:
        app.add_routes(r)
    app.on_cleanup.append(requests.on_cleanup)
    return app
