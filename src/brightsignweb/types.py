from __future__ import annotations

import datetime

from aiohttp.client import ClientSession
from aiohttp import web


from .localstorage import UpdateTaskGroup

__all__ = (
    'LOCAL_TIMEZONE_KEY', 'UPDATE_TASK_GROUP_KEY', 'AIO_CLIENT_SESSION_KEY',
)


LOCAL_TIMEZONE_KEY = web.AppKey('local_timezone', datetime.tzinfo)
UPDATE_TASK_GROUP_KEY = web.AppKey('update_tasks', UpdateTaskGroup)
AIO_CLIENT_SESSION_KEY = web.AppKey('aio_client_session', ClientSession)
