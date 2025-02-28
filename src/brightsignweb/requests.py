from loguru import logger
import aiohttp
from aiohttp import web

from .types import *


def get_aio_client_session(app: web.Application) -> aiohttp.ClientSession:
    if AIO_CLIENT_SESSION_KEY not in app:
        logger.info('building aio_client_session')
        session = aiohttp.ClientSession()
        app[AIO_CLIENT_SESSION_KEY] = session
    return app[AIO_CLIENT_SESSION_KEY]


async def on_cleanup(app: web.Application):
    if AIO_CLIENT_SESSION_KEY in app:
        session = app[AIO_CLIENT_SESSION_KEY]
        logger.info('closing aio_client_session')
        await session.close()
