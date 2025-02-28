from __future__ import annotations
from typing import (
    NewType, ClassVar, Any, Iterator,
    TypedDict, NotRequired, Self, cast,
)
from abc import ABC, abstractmethod

from pathlib import Path
from os import PathLike
from dataclasses import dataclass, field
import datetime
from zoneinfo import ZoneInfo
import calendar
import enum
import asyncio
from urllib.parse import quote

from loguru import logger
from aiohttp.client import ClientSession
from aiohttp import web
import aiohttp_jinja2
from yarl import URL
import jsonfactory

from .serialization import DataclassSerialize
from .requests import get_aio_client_session
from .types import *



EventId = NewType('EventId', int)
EventCategory = NewType('EventCategory', str)
EventCategoryId = NewType('EventCategoryId', int)
AgendaId = NewType('AgendaId', int)


EVENTS_URL = URL('https://mansfieldtx.v8.civicclerk.com/public-api/Events')
EPOCH_UTC = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

routes = web.RouteTableDef()


class TimezoneError(Exception):
    pass

class TimezoneUnawareError(TimezoneError):
    pass

class TimezoneNotSetError(TimezoneError):
    pass


class Timespan(enum.Enum):
    DAY = 1
    WEEK = 7
    MONTH = 30

    @classmethod
    def from_str(cls, s: str) -> Timespan:
        if s.upper() in cls.__members__:
            return cls[s.upper()]
        raise KeyError(f'Invalid Timespan: {s}')


def get_now(tz: datetime.tzinfo = datetime.UTC) -> datetime.datetime:
    return datetime.datetime.now().astimezone(tz)

def is_aware(dt: datetime.datetime) -> bool:
    return dt.tzinfo is not None and dt.utcoffset() is not None

def make_aware(dt: datetime.datetime, tz: datetime.tzinfo) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)

def as_timezone(dt: datetime.datetime, tz: datetime.tzinfo) -> datetime.datetime:
    if not is_aware(dt):
        raise TimezoneUnawareError('dt must be timezone-aware')
    return dt.astimezone(tz)


def get_timespan(
    span: Timespan,
    start_dt: datetime.datetime|None = None,
    span_count: int = 1,
    start_day_of_week: calendar.Day = calendar.SUNDAY,
) -> tuple[datetime.datetime, datetime.datetime]:
    local_tz = CivicPlusItem.LOCAL_TZ
    if local_tz is None:
        raise TimezoneNotSetError('LOCAL_TZ must be set before getting timespan')
    if start_dt is None:
        start_dt = get_now(local_tz)
    else:
        # if not is_aware(start_dt):
        #     raise TimezoneUnawareError('start_dt must be timezone-aware')
        start_dt = as_timezone(start_dt, local_tz)
    if span == Timespan.DAY:
        start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = start_dt + datetime.timedelta(days=span_count)
    elif span == Timespan.WEEK:
        start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        dow = start_dt.weekday()
        # start_dow = getattr(calendar, start_day_of_week.upper())
        start_dow = start_day_of_week.value
        start_dt -= datetime.timedelta(days=(dow - start_dow) % 7)
        end_dt = start_dt + datetime.timedelta(days=7 * span_count)
    elif span == Timespan.MONTH:
        start_dt = start_dt.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_month = start_dt.month + span_count - 1
        if end_month > 12:
            end_month -= 12
            end_year = start_dt.year + 1
        else:
            end_year = start_dt.year
        end_day = calendar.monthrange(end_year, end_month)[1]
        end_dt = start_dt.replace(year=end_year, month=end_month, day=end_day)
    else:
        raise ValueError('Invalid timespan')
    return start_dt, end_dt



@dataclass
class CivicPlusItem(DataclassSerialize):
    id: EventId
    title: str
    pub_date: datetime.datetime
    description: str
    address: str
    city: str

    # event_date is the start datetime, but given in what I'm assuming to be
    # the local timezone
    event_date: datetime.datetime

    # these two fields are not correct.
    # start_time holds the time portion, but the date is not correct
    # end_time doesn't actually exist in the json data
    start_time: datetime.datetime
    end_time: datetime.datetime

    is_published: bool
    category_name: EventCategory
    category_id: EventCategoryId
    agenda_id: AgendaId
    agenda_name: str
    show_in_upcoming: bool
    is_live_event: bool
    is_ondemand_event: bool
    duration_hours: int
    duration_minutes: int
    publish_start: datetime.datetime
    live_start_time: datetime.datetime
    live_end_time: datetime.datetime
    live_is_currently_streaming: bool
    is_live: bool
    raw_json: dict[str, Any]

    use_description: ClassVar[bool] = False
    date_fmt_naive: ClassVar = '%Y-%m-%dT%H:%M:%S'
    # dt_fmt: ClassVar = '%Y-%m-%dT%H:%M:%S%z'
    LOCAL_TZ: ClassVar[datetime.tzinfo]|None = None

    @classmethod
    def set_local_tz(cls, tz: datetime.tzinfo|str) -> None:
        if isinstance(tz, str):
            tz = ZoneInfo(tz)
        cls.LOCAL_TZ = tz

    @classmethod
    def get_local_tz(cls) -> datetime.tzinfo:
        if cls.LOCAL_TZ is None:
            raise TimezoneNotSetError('LOCAL_TZ must be set before getting it')
        return cls.LOCAL_TZ

    @property
    def html_elem_id(self) -> str:
        return f'civicplus-event-{self.id}'

    @property
    def start_datetime(self) -> datetime.datetime:
        if self.start_time < self.event_date:
            return self.event_date
        return self.start_time

    @property
    def end_datetime(self) -> datetime.datetime:
        if self.end_time >= self.event_date:
            return self.end_time
        td = self.end_time - self.start_time
        return self.start_datetime + td

    @property
    def duration(self) -> datetime.timedelta:
        h, m = self.duration_hours, self.duration_minutes
        if h == m == 0:
            return self.end_datetime - self.start_datetime
        return datetime.timedelta(hours=h, minutes=m)

    def is_hidden(self, now: datetime.datetime|None = None) -> bool:
        if not self.is_published:
            return True
        if self.is_live:
            return False
        if now is None:
            now = get_now()
        return now > self.end_datetime

    def _is_valid_dt(self, dt: datetime.datetime) -> bool:
        if not is_aware(dt):
            raise TimezoneUnawareError('dt must be timezone-aware')
        return dt > EPOCH_UTC

    @classmethod
    def from_json(cls, json_data: dict[str, Any]) -> Self:

        def parse_dt_str(s: str) -> datetime.datetime:
            if '+' not in s and '-' not in s:
                # if no timezone info, assume it's in local timezone
                dt = datetime.datetime.strptime(s, cls.date_fmt_naive)
            else:
                dt = datetime.datetime.fromisoformat(s)

            if cls.LOCAL_TZ is None:
                raise TimezoneNotSetError('LOCAL_TZ must be set before parsing datetime strings')
            if not is_aware(dt):
                dt = dt.replace(tzinfo=cls.LOCAL_TZ)
            return dt.astimezone(datetime.UTC)


        start_time = parse_dt_str(json_data['startDateTime'])

        # TODO: determine where the actual end time is
        end_time = start_time + datetime.timedelta(hours=1)

        return cls(
            id=EventId(json_data['id']),
            title=json_data['eventName'],
            pub_date=parse_dt_str(json_data['createdOn']),
            description=json_data['eventDescription'],
            address=json_data['eventLocation']['address1'],
            city=json_data['eventLocation']['city'],
            event_date=parse_dt_str(json_data['eventDate']),
            start_time=start_time,
            end_time=end_time,
            is_published=json_data['isPublished'] == 'published',
            category_name=EventCategory(json_data['categoryName']),
            category_id=EventCategoryId(json_data['eventCategoryId']),
            agenda_id=AgendaId(json_data['agendaId']),
            agenda_name=json_data['agendaName'],
            show_in_upcoming=json_data['showInUpcomingEvents'],
            is_live_event=json_data['isLiveEvent'],
            is_ondemand_event=json_data['isOnDemandEvent'],
            duration_hours=json_data['durationHrs'],
            duration_minutes=json_data['durationMin'],
            publish_start=parse_dt_str(json_data['publishStart']),
            live_start_time=parse_dt_str(json_data['liveStartTime']),
            live_end_time=parse_dt_str(json_data['liveEndTime']),
            live_is_currently_streaming=json_data['liveIsCurrentlyStreaming'],
            is_live=json_data['isLive'],
            raw_json=json_data,
        )

    def _serialize(self) -> dict[str, Any]:
        return self.raw_json

    @classmethod
    def _get_deserialize_kwargs(cls, data: dict) -> dict[str, Any]:
        raise NotImplementedError('This should not be called')

    @classmethod
    def _deserialize(cls, data: dict) -> Self:
        return cls.from_json(data)

    # def get_date_str(self) -> str:
    #     date_fmt = '%a, %b %d, %Y'
    #     time_fmt = '%I:%M %p'
    #     return f'{self.start_time.strftime(date_fmt)}: {self.start_time.strftime(time_fmt)} to {self.end_time.strftime(time_fmt)}'


CPItemDict = dict[EventId, CivicPlusItem]

@dataclass
class CivicPlusItems(DataclassSerialize):
    items: list[CivicPlusItem]
    build_date: datetime.datetime
    items_by_id: CPItemDict = field(init=False)
    items_by_dt: dict[datetime.datetime, CPItemDict] = field(init=False)
    enabled_categories: ClassVar[list[EventCategory]] = [
        EventCategory('City Council'),
        EventCategory('Planning and Zoning Commission'),
        EventCategory('Historic Landmark Commission'),
        EventCategory('Mansfield Economic Development Corporation'),
        EventCategory('Mansfield Park Facilities Development Corporation'),
    ]

    def __post_init__(self):
        self.items_by_id = {item.id: item for item in self.items}
        self.items_by_dt = {}
        for item in self.items:
            d = self.items_by_dt.setdefault(item.start_datetime, {})
            d[item.id] = item

    def save(self, filename: PathLike) -> None:
        if not isinstance(filename, Path):
            filename = Path(filename)
        filename.write_text(jsonfactory.dumps(self._serialize(), indent=2))

    @classmethod
    def load(cls, filename: PathLike) -> Self:
        if not isinstance(filename, Path):
            filename = Path(filename)
        data = jsonfactory.loads(filename.read_text())
        return cls._deserialize(data)

    def _serialize(self) -> dict[str, Any]:
        return {
            'build_date': self.build_date,
            'items':[item._serialize() for item in self.items]
        }

    @classmethod
    def _get_deserialize_kwargs(cls, data: dict) -> dict[str, Any]:
        return {
            'build_date': data['build_date'],
            'items':data['items'],
        }

    def iter_sorted_dts(self) -> Iterator[datetime.datetime]:
        yield from sorted(self.items_by_dt.keys())

    def iter_sorted(self) -> Iterator[CivicPlusItem]:
        for dt in self.iter_sorted_dts():
            yield from self.items_by_dt[dt].values()

    def iter_filtered(self, max_items: int|None = None) -> Iterator[CivicPlusItem]:
        now = datetime.datetime.now().astimezone(datetime.UTC)
        i = 0
        for item in self.iter_sorted():
            if max_items is not None and i >= max_items:
                break
            if item.is_hidden(now):
                continue
            if item.category_name not in self.enabled_categories:
                continue
            yield item
            i += 1

    def __getitem__(self, key: EventId) -> CivicPlusItem:
        return self.items_by_id[key]

    def __contains__(self, key: EventId) -> bool:
        return key in self.items_by_id

    def __len__(self) -> int:
        return len(self.items)



async def get_civicplus_events(
    app: web.Application,
    start_dt: datetime.datetime,
    end_dt: datetime.datetime,
) -> list[CivicPlusItem]:
    if CivicPlusItem.LOCAL_TZ is None:
        tz = app[LOCAL_TIMEZONE_KEY]
        CivicPlusItem.set_local_tz(tz)
    session = get_aio_client_session(app)
    return await _get_civicplus_events(session, start_dt, end_dt)


async def _get_civicplus_events(
    session: ClientSession,
    start_dt: datetime.datetime,
    end_dt: datetime.datetime,
) -> list[CivicPlusItem]:
    def quote_iso_str(s: str) -> str:
        # return s.replace(':', '%3A')
        return quote(s)
    if start_dt.tzinfo is None or end_dt.tzinfo is None:
        raise TimezoneUnawareError('start_dt and end_dt must be timezone-aware')
    start_dt = start_dt.astimezone(datetime.timezone.utc)
    end_dt = end_dt.astimezone(datetime.timezone.utc)
    params = {
        'startDate': quote_iso_str(start_dt.isoformat()),
        'endDate': quote_iso_str(end_dt.isoformat()),
    }
    # logger.debug(f'{params=}')
    param_qs = '&'.join(f'{k}={v}' for k, v in params.items())
    q_url = URL(f'{EVENTS_URL}?{param_qs}', encoded=True)
    # logger.debug(f'{q_url=}')
    async with session.get(q_url) as resp:
        resp.raise_for_status()
        # logger.debug(f'{resp.url=}, {resp.real_url=}')
        json_data = await resp.json()
        # logger.debug(f'{resp.headers=}')
    return [CivicPlusItem.from_json(item) for item in json_data]


class TimespanParams[St](TypedDict):
    start_dt: datetime.datetime
    end_dt: datetime.datetime
    span: St
    span_count: int
    use_span: bool


class BaseViewContext(TypedDict):
    page_title: str
    timezone: datetime.tzinfo

class EventListContext(BaseViewContext):
    items: CivicPlusItems
    rss_feed: CivicPlusItems
    item_iter: Iterator[CivicPlusItem]
    span_params: TimespanParams[str]
    feed_template: NotRequired[str]
    feed_item_template: str


class EventMeetingsContext(EventListContext):
    update_url: URL
    update_interval: int



class CPViewBase[Ct: (BaseViewContext)](web.View, ABC):
    template_name: ClassVar[str]
    page_tile: ClassVar[str]

    @classmethod
    def get_template_name(cls) -> str:
        return cls.template_name

    def get_page_title(self) -> str:
        return self.page_tile

    @abstractmethod
    async def get_context_data(self) -> Ct: ...

    async def render_to_response(self, context: Ct) -> web.Response:
        tmpl = self.get_template_name()
        return aiohttp_jinja2.render_template(tmpl, self.request, context)

    async def get(self) -> web.Response:
        context = await self.get_context_data()
        return await self.render_to_response(context)



class CPEventListViewBase[
    Ct: (EventListContext, EventMeetingsContext)
](CPViewBase[Ct], ABC):

    max_items: int|None = None

    @abstractmethod
    def get_span_params(self) -> TimespanParams[Timespan]: ...

    async def get_cp_items(
        self,
        span_params: TimespanParams[Timespan],
        now: datetime.datetime|None = None,
    ) -> CivicPlusItems:
        start_dt, end_dt = span_params['start_dt'], span_params['end_dt']
        assert CivicPlusItem.LOCAL_TZ is not None
        if now is None:
            now = get_now(CivicPlusItem.get_local_tz())
        else:
            now = now.astimezone(CivicPlusItem.get_local_tz())
        item_list = await get_civicplus_events(
            self.request.app, start_dt, end_dt,
        )
        return CivicPlusItems(build_date=now, items=item_list)

    async def get_base_context_data(self) -> EventListContext:
        request = self.request
        if CivicPlusItem.LOCAL_TZ is None:
            tz = request.app[LOCAL_TIMEZONE_KEY]
            CivicPlusItem.set_local_tz(tz)
        span_params = self.get_span_params()
        start_dt, end_dt = span_params['start_dt'], span_params['end_dt']

        items = await self.get_cp_items(span_params)
        return {
            'page_title': self.get_page_title(),
            'items': items,
            'rss_feed': items,
            'item_iter': items.iter_filtered(max_items=self.max_items),
            'span_params': {
                'start_dt': start_dt,
                'end_dt': end_dt,
                'span': span_params['span'].name.lower(),
                'span_count': span_params['span_count'],
                'use_span': span_params['use_span'],
            },
            # 'feed_template': 'meetings/includes/civicplus-feed.html',
            'feed_item_template': 'meetings/includes/civicplus-feed-item.html',
            'timezone': CivicPlusItem.get_local_tz(),
        }


@routes.view('/civicplus/events')
class CPEventListView(CPEventListViewBase['EventListContext']):
    template_name = 'meetings/civicplus-events.html'
    page_tile = 'CivicPlus Events'

    def get_span_params(self) -> TimespanParams[Timespan]:
        params = self.request.query
        start_dt_str = params.get('start_dt')
        end_dt_str = params.get('end_dt')
        span_str = params.get('time_span', 'WEEK')
        span_count = int(params.get('span_count', '1'))
        start_dt, end_dt = None, None
        if start_dt_str is not None:
            start_dt = datetime.datetime.fromisoformat(start_dt_str)
        if end_dt_str is not None:
            end_dt = datetime.datetime.fromisoformat(end_dt_str)
        span = Timespan.from_str(span_str)
        use_span = params.get('use_span', 'false').lower() == 'true'
        if use_span or start_dt is None or end_dt is None:
            start_dt, end_dt = get_timespan(
                span, start_dt=start_dt, span_count=span_count,
            )
            use_span = True

        return {
            'start_dt': start_dt,
            'end_dt': end_dt,
            'span': span,
            'span_count': span_count,
            'use_span': use_span,
        }

    async def get_context_data(self) -> EventListContext:
        base = await self.get_base_context_data()
        return base



class CPMeetingsViewBase(CPEventListViewBase['EventMeetingsContext']):
    template_name = 'meetings/meetings-tmpl.html'
    page_tile = 'Upcoming Events'
    update_url = URL('/civicplus/meetings/feed-items')
    _cached_items: ClassVar[CivicPlusItems]|None = None
    _cache_expiry: ClassVar[datetime.timedelta] = datetime.timedelta(minutes=5)

    def get_span_params(self) -> TimespanParams[Timespan]:
        params = self.request.query
        max_items = params.get('max_items', None)
        span = Timespan.WEEK
        span_count = int(params.get('span_count', '3'))
        if max_items is not None:
            max_items = int(max_items)
        self.max_items = max_items
        start_dt, end_dt = get_timespan(span, span_count=span_count)
        return {
            'start_dt': start_dt,
            'end_dt': end_dt,
            'span': span,
            'span_count': span_count,
            'use_span': True,
        }

    async def get_cp_items(
        self,
        span_params: TimespanParams[Timespan],
        now: datetime.datetime|None = None,
    ) -> CivicPlusItems:
        if now is None:
            now = get_now()
        if self._cached_items is not None:
            td = now - self._cached_items.build_date
            if td < self._cache_expiry:
                logger.debug(f'Using cached items: {self._cached_items.build_date=}')
                return self._cached_items
        items = await super().get_cp_items(span_params, now)
        self.__class__._cached_items = items
        logger.debug(f'{items.build_date=}')
        return items

    async def get_context_data(self) -> EventMeetingsContext:
        base = await self.get_base_context_data()
        base = cast(EventMeetingsContext, base)
        base['update_url'] = self.update_url.with_query(self.request.query)
        params = self.request.query
        base['update_interval'] = int(params.get('update_interval', '60000'))
        return base


@routes.view('/civicplus/meetings')
class CPMeetingsView(CPMeetingsViewBase):
    pass


@routes.view('/civicplus/meetings/feed-items')
class CPMeetingsRssView(CPMeetingsViewBase):
    template_name = 'meetings/includes/feed.html'


# async def log_events(base_path: PathLike):
#     tz = ZoneInfo('US/Central')
#     CivicPlusItem.set_local_tz(tz)
#     now = get_now(tz)
#     start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
#     end_dt = start_dt + datetime.timedelta(days=1)
#     async with ClientSession() as session:
#         item_list = await _get_civicplus_events(session, start_dt, end_dt)
#     items = CivicPlusItems(items=item_list, build_date=now)
#     dt_fmt = '%Y%m%d_%H%M%S'
#     filename = Path(base_path) / f'events-{now.strftime(dt_fmt)}.json'
#     items.save(filename)

# if __name__ == '__main__':
#     base_path = Path.cwd() / 'civicplus_events'
#     base_path.mkdir(exist_ok=True)
#     asyncio.run(log_events(base_path))
