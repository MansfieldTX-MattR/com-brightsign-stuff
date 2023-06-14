from loguru import logger
from pathlib import Path
from aiohttp import web
import jinja2
import aiohttp_jinja2
from dotenv import load_dotenv

from . import rss_feeds
from . import weather
from . import requests
from .localstorage import UpdateTaskGroup


TEMPLATE_DIR = Path.cwd()
STATIC_ROOT = Path.cwd()
STATIC_DIRS = [STATIC_ROOT / s for s in ['meetings', 'weather2']]

routes = web.RouteTableDef()


def static_filter(path: str) -> str:
    path = path.lstrip('/')
    return f'/static/{path}'

def init_func(argv):
    app = web.Application()
    jinja_env = aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(TEMPLATE_DIR))
    jinja_env.filters['static'] = static_filter
    for p in STATIC_DIRS:
        routes.static(f'/static/{p.name}', p)
    for r in [routes, rss_feeds.routes, weather.routes]:
        app.add_routes(r)
    app.on_cleanup.append(requests.on_cleanup)
    app['update_tasks'] = t = UpdateTaskGroup(app)
    app.cleanup_ctx.append(t.cleanup_ctx)
    app.on_startup.append(weather.init_app)
    app.on_startup.append(rss_feeds.init_app)
    return app
