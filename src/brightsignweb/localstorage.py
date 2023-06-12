from __future__ import annotations
from typing import Any, Container
import asyncio
from pathlib import Path
import datetime
from dataclasses import dataclass

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
    dt: datetime.datetime
    delta: datetime.timedelta|None
    dt_key: str|None = None

    @property
    def expired(self) -> bool:
        if self.delta is None:
            return False
        dt = self.dt
        now = datetime.datetime.now()
        next_update = dt + self.delta
        return now >= next_update

    @classmethod
    def from_json(cls, s: str) -> AppItem:
        return jsonfactory.loads(s)

    def to_json(self) -> dict:
        return jsonfactory.dumps(self._serialize())



async def get_app_item(
    app: web.Application,
    key: str,
    dt: datetime.datetime|None = None,
    delta: datetime.timedelta|None = None
) -> AppItem|None:
    item_dict = await _get_app_items(app)
    return item_dict.get(key)


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
