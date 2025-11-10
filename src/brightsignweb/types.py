from __future__ import annotations
from typing import Literal, get_args
import datetime

from aiohttp.client import ClientSession
from aiohttp import web


from .localstorage import UpdateTaskGroup

__all__ = (
    'LOCAL_TIMEZONE_KEY', 'UPDATE_TASK_GROUP_KEY', 'AIO_CLIENT_SESSION_KEY',
    'STATIC_URL_PREFIX', 'FeedName', 'FeedNames',
)

FeedName = Literal['legistar_feed', 'calendar_feed', 'meetings_feed']
FeedNames: tuple[FeedName, ...] = get_args(FeedName)


LOCAL_TIMEZONE_KEY = web.AppKey('local_timezone', datetime.tzinfo)
UPDATE_TASK_GROUP_KEY = web.AppKey('update_tasks', UpdateTaskGroup)
AIO_CLIENT_SESSION_KEY = web.AppKey('aio_client_session', ClientSession)
STATIC_URL_PREFIX = web.AppKey[str]('static_url_prefix')
