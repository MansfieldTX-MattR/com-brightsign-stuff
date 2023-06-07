from loguru import logger
import aiohttp


def get_aio_client_session(app):
    session = app.get('aio_client_session')
    if session is None:
        logger.info('building aio_client_session')
        session = aiohttp.ClientSession()
        app['aio_client_session'] = session
    return session

async def on_cleanup(app):
    session = app.get('aio_client_session')
    if session is not None:
        logger.info('closing aio_client_session')
        await session.close()
