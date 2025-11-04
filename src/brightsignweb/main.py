from typing import cast
from loguru import logger
from pathlib import Path
from zoneinfo import ZoneInfo
import importlib.resources
from aiohttp import web
import jinja2
import aiohttp_jinja2
from dotenv import load_dotenv
import click

from . import rss_feeds
from . import weather
from . import requests
from . import civicplus
from .localstorage import UpdateTaskGroup
from .types import *

PROJECT_ROOT = cast(Path, importlib.resources.files(__name__.split('.')[0]))

TEMPLATE_DIR = PROJECT_ROOT
STATIC_ROOT = PROJECT_ROOT
STATIC_DIRS = [STATIC_ROOT / s for s in ['meetings', 'weather2']]
LOCAL_TIMEZONE_NAME = 'US/Central'
LOCAL_TIMEZONE = ZoneInfo(LOCAL_TIMEZONE_NAME)

routes = web.RouteTableDef()

@routes.get('/healthcheck')
async def healthcheck(request: web.Request) -> web.Response:
    return web.Response(text='OK')


@routes.get('/signage')
@aiohttp_jinja2.template('meetings/signage.html')
async def signage_handler(request: web.Request) -> dict:
    return {
        'title': 'BrightSign Web Signage',
    }


def static_filter(path: str) -> str:
    path = path.lstrip('/')
    return f'/static/{path}'

def init_func(argv):
    app = web.Application()
    app[LOCAL_TIMEZONE_KEY] = LOCAL_TIMEZONE
    jinja_env = aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(TEMPLATE_DIR))
    jinja_env.filters['static'] = static_filter
    for p in STATIC_DIRS:
        routes.static(f'/static/{p.name}', p)
    for r in [routes, rss_feeds.routes, weather.routes, civicplus.routes]:
        app.add_routes(r)
    app.on_cleanup.append(requests.on_cleanup)
    app[UPDATE_TASK_GROUP_KEY] = t = UpdateTaskGroup(app)
    app.cleanup_ctx.append(t.cleanup_ctx)
    app.on_startup.append(weather.init_app)
    app.on_startup.append(rss_feeds.init_app)
    return app


@click.group()
def cli():
    pass


@cli.command()
@click.option('-h', '--host', default='localhost', help='Host to bind the server to.')
@click.option('-p', '--port', default=8080, help='Port to bind the server to.')
def serve(host: str = 'localhost', port: int = 8080):
    app = init_func()
    web.run_app(app, host=host, port=port)


if __name__ == '__main__':
    load_dotenv()
    cli()
