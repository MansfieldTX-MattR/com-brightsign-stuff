from __future__ import annotations
import datetime

from aiohttp import web

from .types import LOCAL_TIMEZONE_KEY

UTC = datetime.timezone.utc


class TimezoneError(Exception):
    """Base exception for timezone errors.
    """

class TimezoneUnawareError(TimezoneError):
    """Exception raised when a datetime is expected to be timezone-aware but is not.
    """

class TimezoneNotSetError(TimezoneError):
    """Exception raised when a timezone is expected to be set but is not.
    """


def get_timezone(app: web.Application) -> datetime.tzinfo:
    return app[LOCAL_TIMEZONE_KEY]

def get_now_utc() -> datetime.datetime:
    return datetime.datetime.now(UTC)

def get_now(tz: datetime.tzinfo) -> datetime.datetime:
    dt = get_now_utc()
    return dt.astimezone(tz)

def get_now_local(app: web.Application) -> datetime.datetime:
    tz = get_timezone(app)
    return get_now(tz)

def dt_from_timestamp(ts: float, tz: datetime.tzinfo) -> datetime.datetime:
    dt = datetime.datetime.fromtimestamp(ts, UTC)
    return dt.astimezone(tz)

def dt_from_timestamp_local(app: web.Application, ts: float) -> datetime.datetime:
    tz = get_timezone(app)
    return dt_from_timestamp(ts, tz)

def dt_to_timestamp(dt: datetime.datetime) -> float:
    assert_dt_aware(dt)
    return dt.timestamp()

def is_dt_aware(dt: datetime.datetime) -> bool:
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None

def assert_dt_aware(dt: datetime.datetime) -> None:
    if not is_dt_aware(dt):
        raise TimezoneUnawareError('datetime is not timezone aware')

def make_aware(dt: datetime.datetime, tz: datetime.tzinfo) -> datetime.datetime:
    if is_dt_aware(dt):
        return dt.astimezone(tz)
    return dt.replace(tzinfo=tz)

def as_timezone(dt: datetime.datetime, tz: datetime.tzinfo) -> datetime.datetime:
    if not is_dt_aware(dt):
        raise TimezoneUnawareError('dt must be timezone-aware')
    return dt.astimezone(tz)
