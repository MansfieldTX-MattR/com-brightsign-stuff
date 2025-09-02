from __future__ import annotations
from typing import Self, Any
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

type _AppItemKey = str | web.AppKey

LS_LOCK_KEY = web.AppKey('localstorage_lock', asyncio.Lock)
LS_ITEMS_KEY = web.AppKey('localstorage_items', dict[_AppItemKey, 'AppItem'])


@logger.catch(reraise=True)
async def _read() -> dict[_AppItemKey, AppItem]:
    if not STORAGE_FILE.exists():
        return {}
    async with aiofiles.open(STORAGE_FILE, 'r') as f:
        s = await f.read()
    return jsonfactory.loads(s)

@logger.catch(reraise=True)
async def _write(app_items: dict[_AppItemKey, AppItem]):
    STORAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    s = jsonfactory.dumps(app_items, indent=2)
    async with aiofiles.open(STORAGE_FILE, 'w') as f:
        await f.write(s)

def _get_lock(app: web.Application) -> asyncio.Lock:
    lock = app.get(LS_LOCK_KEY)
    if lock is None:
        app[LS_LOCK_KEY] = lock = asyncio.Lock()
    return lock

async def _get_app_items(app: web.Application) -> dict[_AppItemKey, AppItem]:
    items = app.get(LS_ITEMS_KEY)
    if items is not None:
        return items
    async with _get_lock(app):
        items = app.get(LS_ITEMS_KEY)
        if items is not None:
            return items
        app[LS_ITEMS_KEY] = items = await _read()
    return items


@dataclass
class AppItem[_AppItemKey, T](DataclassSerialize):
    key: _AppItemKey
    item: T|None
    dt: datetime.datetime|None = None
    delta: datetime.timedelta|None = None
    dt_key: str|None = None

    def __post_init__(self, **kwargs):
        self._lock = asyncio.Lock()
        self.notify = asyncio.Condition(self._lock)
        self.update_evt = asyncio.Event()

    def locked(self) -> bool:
        return self._lock.locked()

    async def __aenter__(self) -> Self:
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

    @property
    def next_update(self) -> datetime.datetime|None:
        if self.delta is None:
            return None
        if self.dt is None:
            return datetime.datetime.now()
        return self.dt + self.delta

    @property
    def next_update_seconds(self) -> float|None:
        dt = self.next_update
        if dt is None:
            return None
        now = datetime.datetime.now()
        td = dt - now
        return td.total_seconds()

    async def wait_for_next_update(self):
        evt_triggered = False
        num_seconds = self.next_update_seconds
        logger.info(f'AppItem "{self.key}" wait_for_next_update: {num_seconds=}')
        try:
            if num_seconds is None:
                await self.update_evt.wait()
                evt_triggered = True
            else:
                try:
                    await asyncio.wait_for(self.update_evt.wait(), timeout=num_seconds)
                    evt_triggered = True
                except asyncio.TimeoutError:
                    pass
        finally:
            self.update_evt.clear()
        if evt_triggered:
            logger.success(f'AppItem "{self.key}" updating via event trigger')
        else:
            logger.success(f'AppItem "{self.key}" updating without request')

    @classmethod
    def from_json(cls, s: str) -> Self:
        return jsonfactory.loads(s)

    def to_json(self) -> str:
        return jsonfactory.dumps(self._serialize())

    def _serialize(self) -> dict[str, Any]:
        r = super()._serialize()
        r['key'] = str(self.key)
        return r


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


class UpdateTask[_AppItemKey, T]:
    def __init__(self, app: web.Application, app_item: AppItem[_AppItemKey, T], update_coro) -> None:
        self.app = app
        self.app_item = app_item
        self.update_coro = update_coro
        self.update_evt = app_item.update_evt
        self.notify = app_item.notify
        self._running = False
        self._task = None

    @property
    def key(self) -> _AppItemKey:
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

    @logger.catch(reraise=True)
    async def _loop(self):
        while self._running:
            await self.app_item.wait_for_next_update()
            self.update_evt.clear()
            if not self._running:
                break
            async with self.app_item:
                logger.debug(f'update({self!r})')
                try:
                    await self.update_coro(app=self.app, app_item=self.app_item)
                except Exception as exc:
                    logger.exception(exc)
                    await asyncio.sleep(10)
                    continue
                self.notify.notify_all()

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}: "{self}" (running={self._running})>'

    def __str__(self) -> str:
        return str(self.key)



async def get_app_item[Kt: _AppItemKey, T](
    app: web.Application,
    key: Kt,
    dt: datetime.datetime|None = None,
    delta: datetime.timedelta|None = None,
    cls: type[T]|None = None
) -> AppItem[Kt, T]|None:
    item_dict = await _get_app_items(app)
    return item_dict.get(key)

async def get_or_create_app_item[Kt: _AppItemKey, T](
    app: web.Application,
    key: Kt,
    cls: type[T]|None = None
) -> tuple[AppItem[Kt, T], bool]:
    item_dict = await _get_app_items(app)
    created = False
    async with _get_lock(app):
        app_item = item_dict.get(key)
        if app_item is None:
            app_item = AppItem[Kt, T](key=key, item=None)
            item_dict[key] = app_item
            created = True
    return app_item, created

async def set_app_item[Kt: _AppItemKey, T](
    app: web.Application,
    key: Kt,
    item: T,
    dt: datetime.datetime|None = None,
    delta: datetime.timedelta|None = None,
    dt_key: str|None = None
) -> AppItem[Kt, T]:
    if dt is None:
        dt = datetime.datetime.now()
    item_dict = await _get_app_items(app)
    app_item = AppItem[Kt, T](key=key, dt=dt, delta=delta, item=item, dt_key=dt_key)
    async with _get_lock(app):
        item_dict[key] = app_item
        await _write(item_dict)
    return app_item

async def update_app_items(app: web.Application):
    item_dict = await _get_app_items(app)
    async with _get_lock(app):
        await _write(item_dict)
