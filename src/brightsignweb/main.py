from typing import TypedDict, cast
from loguru import logger
from pathlib import Path
from zoneinfo import ZoneInfo
import importlib.resources
from aiohttp import web
import jinja2
import aiohttp_jinja2
from dotenv import load_dotenv
import click

from . import feedparser
from . import rss_feeds
from . import weather
from . import requests
from . import civicplus
from .localstorage import UpdateTaskGroup
from .staticfiles import (
    STATIC_DIRS, STATIC_URL_PREFIX,
    collectstatic as staticfiles_collectstatic,
    static_filter,
)
from .types import *

PROJECT_ROOT = cast(Path, importlib.resources.files(__name__.split('.')[0]))

TEMPLATE_DIR = PROJECT_ROOT
LOCAL_TIMEZONE_NAME = 'US/Central'
LOCAL_TIMEZONE = ZoneInfo(LOCAL_TIMEZONE_NAME)

feedparser.set_local_timezone(LOCAL_TIMEZONE)

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




def init_func(
    *args,
    serve_static: bool = True,
    static_url_prefix: str = '/static/'
) -> web.Application:
    static_url_prefix = static_url_prefix.rstrip('/')
    assert static_url_prefix.startswith('/'), 'static_url_prefix must start with /'
    app = web.Application()
    app[LOCAL_TIMEZONE_KEY] = LOCAL_TIMEZONE
    app[STATIC_URL_PREFIX] = static_url_prefix
    jinja_env = aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(TEMPLATE_DIR))
    jinja_env.filters['static'] = static_filter
    if serve_static:
        for p in STATIC_DIRS:
            routes.static(f'{static_url_prefix}/{p.name}', p)
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
@click.argument('out-dir', type=click.Path(file_okay=False, dir_okay=True, path_type=Path))
def collectstatic(out_dir: Path):
    staticfiles_collectstatic(out_dir)


@cli.command()
@click.option('-h', '--host', default='localhost', help='Host to bind the server to.')
@click.option('-p', '--port', default=8080, help='Port to bind the server to.')
@click.option('--serve-static/--no-serve-static', default=True, help='Whether to serve static files.')
@click.option('--static-url-prefix', default='/static/', help='URL prefix for static files.')
def serve(
    host: str = 'localhost',
    port: int = 8080,
    serve_static: bool = True,
    static_url_prefix: str = '/static/'
) -> None:
    app = init_func(serve_static=serve_static, static_url_prefix=static_url_prefix)
    web.run_app(app, host=host, port=port)


if __name__ == '__main__':
    load_dotenv()
    cli()
