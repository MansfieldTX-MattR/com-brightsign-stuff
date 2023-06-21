from __future__ import annotations
from typing import Any, Container
import asyncio
from pathlib import Path
import datetime
from dataclasses import dataclass
from loguru import logger

from aiohttp import web

import aiofiles
import jsonfactory

from .serialization import DataclassSerialize

STORAGE_FILE = Path.home() / '.config' / 'brightsignweb' / 'localstorage.json'

async def _read() -> dict[str, AppItem]:
    if not STORAGE_FILE.exists():
        return {}
    async with aiofiles.open(STORAGE_FILE, 'r') as f:
        s = await f.read()
    return jsonfactory.loads(s)

async def _write(app_items: dict[str, AppItem]):
    STORAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    s = jsonfactory.dumps(app_items, indent=2)
    async with aiofiles.open(STORAGE_FILE, 'w') as f:
        await f.write(s)

def _get_lock(app: web.Application) -> asyncio.Lock:
    lock = app.get('localstorage_lock')
    if lock is None:
        app['localstorage_lock'] = lock = asyncio.Lock()
    return lock

async def _get_app_items(app: web.Application) -> dict[str, AppItem]:
    items = app.get('localstorage_items')
    if items is not None:
        return items
    async with _get_lock(app):
        items = app.get('localstorage_items')
        if items is not None:
            return items
        app['localstorage_items'] = items = await _read()
    return items


@dataclass
class AppItem(DataclassSerialize):
    key: str
    item: Any
    dt: datetime.datetime|None = None
    delta: datetime.timedelta|None = None
    dt_key: str|None = None

    def __post_init__(self, **kwargs):
        self._lock = asyncio.Lock()
        self.notify = asyncio.Condition(self._lock)
        self.update_evt = asyncio.Event()

    def locked(self) -> bool:
        return self._lock.locked()

    async def __aenter__(self):
        await self._lock.acquire()
        return self

    async def __aexit__(self, *args):
        self._lock.release()

    async def store(self, app: web.Application):
        assert self.locked()
        await update_app_items(app)

    async def update(self, app: web.Application, **kwargs):
        assert self.locked()
        for key, val in kwargs.items():
            setattr(self, key, val)
        await self.store(app)

    @property
    def expired(self) -> bool:
        if self.delta is None:
            return False
        dt = self.dt
        if dt is None:
            return True
        now = datetime.datetime.now()
        next_update = dt + self.delta
        return now >= next_update

    @classmethod
    def from_json(cls, s: str) -> AppItem:
        return jsonfactory.loads(s)

    def to_json(self) -> dict:
        return jsonfactory.dumps(self._serialize())


class UpdateTaskGroup:
    def __init__(self, app: web.Application) -> None:
        self.app = app
        self.tasks = {}
        self._lock = asyncio.Lock()
        self._running = False

    async def open(self):
        logger.debug(f'open({self})')
        async with self._lock:
            assert not self._running
            self._running = True
            coros = [t.open() for t in self]
            await asyncio.gather(*coros)

    async def close(self):
        logger.debug(f'close({self})')
        async with self._lock:
            self._running = False
            coros = [t.close() for t in self]
            await asyncio.gather(*coros)

    async def cleanup_ctx(self, app):
        await self.open()
        yield
        await self.close()

    async def add_task(self, app_item: AppItem, update_coro):
        key = app_item.key
        async with self._lock:
            if key in self:
                logger.warning(f'key "{key}" already exists')
                return
            t = UpdateTask(app=self.app, app_item=app_item, update_coro=update_coro)
            if self._running:
                await t.open()

    def __getitem__(self, key: str) -> UpdateTask:
        return self.tasks[key]

    def __contains__(self, key: str) -> bool:
        return key in self.tasks

    def __iter__(self):
        yield from self.tasks.values()


class UpdateTask:
    def __init__(self, app: web.Application, app_item: AppItem, update_coro) -> None:
        self.app = app
        self.app_item = app_item
        self.update_coro = update_coro
        self.update_evt = app_item.update_evt
        self.notify = app_item.notify
        self._running = False
        self._task = None

    @property
    def key(self) -> str:
        return self.app_item.key

    async def open(self):
        logger.debug(f'open({self!r})')
        assert not self._running
        self._running = True
        assert self._task is None
        self._task = asyncio.create_task(self._loop())

    async def close(self):
        logger.debug(f'close({self!r})')
        self._running = False
        t = self._task
        self._task = None
        if t is not None:
            self.update_evt.set()
            await t

    @logger.catch
    async def _loop(self):
        while self._running:
            await self.update_evt.wait()
            self.update_evt.clear()
            if not self._running:
                break
            async with self.app_item:
                logger.debug(f'update({self!r})')
                await self.update_coro(app=self.app, app_item=self.app_item)
                self.notify.notify_all()

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}: "{self}" (running={self._running})>'

    def __str__(self) -> str:
        return self.key



async def get_app_item(
    app: web.Application,
    key: str,
    dt: datetime.datetime|None = None,
    delta: datetime.timedelta|None = None
) -> AppItem|None:
    item_dict = await _get_app_items(app)
    return item_dict.get(key)

async def get_or_create_app_item(app: web.Application, key: str) -> tuple[AppItem, bool]:
    item_dict = await _get_app_items(app)
    created = False
    async with _get_lock(app):
        app_item = item_dict.get(key)
        if app_item is None:
            app_item = AppItem(key=key, item=None)
            item_dict[key] = app_item
            created = True
    return app_item, created

async def set_app_item(
    app: web.Application,
    key: str,
    item: Any,
    dt: datetime.datetime|None = None,
    delta: datetime.timedelta|None = None,
    dt_key: str|None = None
):
    if dt is None:
        dt = datetime.datetime.now()
    item_dict = await _get_app_items(app)
    app_item = AppItem(key=key, dt=dt, delta=delta, item=item, dt_key=dt_key)
    async with _get_lock(app):
        item_dict[key] = app_item
        await _write(item_dict)

async def update_app_items(app: web.Application):
    item_dict = await _get_app_items(app)
    async with _get_lock(app):
        await _write(item_dict)
