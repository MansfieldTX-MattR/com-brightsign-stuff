from __future__ import annotations
from typing import TypedDict, cast, TYPE_CHECKING
from loguru import logger
from pathlib import Path
from zoneinfo import ZoneInfo
import importlib.resources
if TYPE_CHECKING:
    from logging import Logger

from aiohttp import web
from aiohttp.web_log import AccessLogger as AiohttpAccessLogger
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
    STATIC_DIRS,
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


logger.level('ACCESS', no=25, color='<green><bold>')
_access_logger = logger


class AccessLogger(AiohttpAccessLogger):
    LOG_FORMAT = '%a "%r" %s %b "%{Referer}i" "%{User-Agent}i"'
    def __init__(self, logger: Logger, log_format: str = LOG_FORMAT) -> None:
        log_format = AccessLogger.LOG_FORMAT
        super().__init__(logger, log_format)

    @property
    def enabled(self) -> bool:
        return True

    def log(self, request: web.Request, response: web.StreamResponse, time: float) -> None:
        try:
            if request.path.startswith('/healthcheck') and response.status == 200:
                return
            fmt_info = self._format_line(request, response, time)
            values = list()
            extra = dict()
            for key, value in fmt_info:
                values.append(value)

                if key.__class__ is str:
                    extra[key] = value
                else:
                    k1, k2 = key  # type: ignore[misc]
                    dct = extra.get(k1, {})  # type: ignore[var-annotated,has-type]
                    dct[k2] = value  # type: ignore[index,has-type]
                    extra[k1] = dct  # type: ignore[has-type,assignment]
            msg = self._log_format % tuple(values)
            _access_logger.log('ACCESS', msg, extra=extra)
        except Exception:
            logger.exception("Error in logging")



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
    assert app[STATIC_URL_PREFIX].strip('/') == static_url_prefix.strip('/'), f'static_url_prefix mismatch: {static_url_prefix} != {app[STATIC_URL_PREFIX]}'
    web.run_app(app, host=host, port=port, access_log_class=AccessLogger)


if __name__ == '__main__':
    load_dotenv()
    cli()
