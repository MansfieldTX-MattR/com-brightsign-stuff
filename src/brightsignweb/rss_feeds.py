from __future__ import annotations
from typing import TypedDict, NotRequired, Iterable
import datetime
from aiohttp import web
import aiohttp_jinja2
from loguru import logger

from .feedparser import (
    Feed, MeetingsFeed, CalendarFeed, LegistarFeed, CustomFeedItem,
    FeedItem, MeetingsFeedItem, CalendarFeedItem, LegistarFeedItem,
)
from . import requests

from . import timezone
from .localstorage import get_or_create_app_item, AppItem
from .types import FeedName, FeedNames, UPDATE_TASK_GROUP_KEY


UPDATE_DELTA = datetime.timedelta(minutes=5)

class _FeedInfo[T: Feed](TypedDict):
    url: str
    parser_cls: type[T]


FEED_INFO: dict[FeedName, _FeedInfo] = {
    'meetings_feed':{
        'url':'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=Public-Meetings-24',
        'parser_cls':MeetingsFeed,
    },
    'calendar_feed':{
        'url':'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml',
        'parser_cls':CalendarFeed,
    },
    'legistar_feed':{
        'url':'https://mansfield.legistar.com/Feed.ashx?M=Calendar&ID=22493777&GUID=82450362-860b-42da-8966-b30a0ceada48&Mode=This%20Week&Title=CITY+OF+MANSFIELD+-+Calendar+(This+Week)',
        'parser_cls':LegistarFeed,
    }
}

routes = web.RouteTableDef()

async def get_rss_feed(app: web.Application, url: str) -> str:
    session = requests.get_aio_client_session(app)
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


@routes.get('/rss/meetings.xml')
async def rss_meetings(request):
    resp_text = await get_rss_feed(request.app, FEED_INFO['meetings_feed']['url'])
    return web.Response(text=resp_text, content_type='text/xml')

@routes.get('/rss/calendar.xml')
async def rss_calendar(request):
    resp_text = await get_rss_feed(request.app, FEED_INFO['calendar_feed']['url'])
    return web.Response(text=resp_text, content_type='text/xml')

@routes.get('/rss/legistar.xml')
async def rss_legistar(request):
    resp_text = await get_rss_feed(request.app, FEED_INFO['legistar_feed']['url'])
    return web.Response(text=resp_text, content_type='text/xml')



class TemplateContextBase[Ft: (Feed), It: (FeedItem)](TypedDict):
    rss_feed: Ft
    max_items: NotRequired[int]|None
    item_iter: Iterable[It|CustomFeedItem]
    page_title: NotRequired[str]
    update_url: NotRequired[str]

class TemplateContext[Ft: (Feed), It: (FeedItem)](TemplateContextBase[Ft, It]):
    page_title: str
    update_url: str



async def get_rss_tmpl_context[
    Ft: (Feed), It: (FeedItem)
](
    request: web.Request,
    storage_key: FeedName,
    cls: type[Ft],
    item_cls: type[It]
) -> TemplateContextBase[Ft, It]:
    app_item, created = await get_or_create_app_item(request.app, storage_key, cls)
    async with app_item:
        if app_item.delta is None:
            app_item.delta = UPDATE_DELTA
            app_item.dt = timezone.get_now_utc()
        if app_item.item is None or app_item.delta is None or app_item.expired:
            logger.debug(f'trigger update_evt for {app_item.key}')
            app_item.update_evt.set()
            if app_item.item is None:
                await app_item.notify.wait()
                assert app_item.item is not None
        else:
            logger.debug(f'using cache for {storage_key}')
    max_items = request.query.get('maxItems')
    assert app_item.item is not None
    feed = app_item.item
    item_iter: Iterable[It|CustomFeedItem]
    if max_items is not None:
        max_items = int(max_items)
        item_iter = feed.iter_limited(max_items)
    else:
        item_iter = feed
    return {
        'rss_feed':feed,
        'max_items':max_items,
        'item_iter':item_iter,
    }


async def _fetch_rss_feed(app: web.Application, app_item: AppItem[FeedName, Feed]) -> None:
    logger.info(f'retrieving {app_item.key}')
    key = str(app_item.key)
    assert key in FeedNames
    feed_info = FEED_INFO[key]
    resp_text = await get_rss_feed(app, feed_info['url'])
    if app_item.item is None:
        feed = feed_info['parser_cls'].from_xml_str(resp_text)
        app_item.item = feed
    else:
        feed = app_item.item
        feed.update_from_xml_str(resp_text)
    now = timezone.get_now_utc()
    await app_item.update(app, dt=now, delta=UPDATE_DELTA)


@routes.get('/rss/meetings.html')
@aiohttp_jinja2.template('meetings/meetings-tmpl.html')
async def rss_meetings_html(
    request: web.Request
) -> TemplateContext[MeetingsFeed, MeetingsFeedItem]:
    context = await get_rss_tmpl_context(request, 'meetings_feed', MeetingsFeed, MeetingsFeedItem)
    return {
        'page_title':'Upcoming Meetings',
        'update_url':'/rss/meetings/feed-items',
        **context,
    }

@routes.get('/rss/calendar.html')
@aiohttp_jinja2.template('meetings/meetings-tmpl.html')
async def rss_calendar_html(
    request: web.Request
) -> TemplateContext[CalendarFeed, CalendarFeedItem]:
    context = await get_rss_tmpl_context(request, 'calendar_feed', CalendarFeed, CalendarFeedItem)
    return {
        'page_title':'Calendar Events',
        'update_url':'/rss/calendar/feed-items',
        **context,
    }

@routes.get('/rss/legistar.html')
@aiohttp_jinja2.template('meetings/meetings-tmpl.html')
async def rss_legistar_html(
    request: web.Request
) -> TemplateContext[LegistarFeed, LegistarFeedItem]:
    context = await get_rss_tmpl_context(request, 'legistar_feed', LegistarFeed, LegistarFeedItem)
    return {
        'page_title':'Legistar Calendar',
        'update_url':'/rss/legistar/feed-items',
        **context,
    }

@routes.get('/rss/meetings/feed-items')
@aiohttp_jinja2.template('meetings/includes/feed.html')
async def rss_meetings_feed_items(
    request: web.Request
) -> TemplateContextBase[MeetingsFeed, MeetingsFeedItem]:
    return await get_rss_tmpl_context(request, 'meetings_feed', MeetingsFeed, MeetingsFeedItem)


@routes.get('/rss/calendar/feed-items')
@aiohttp_jinja2.template('meetings/includes/feed.html')
async def rss_calendar_feed_items(
    request: web.Request
) -> TemplateContextBase[CalendarFeed, CalendarFeedItem]:
    return await get_rss_tmpl_context(request, 'calendar_feed', CalendarFeed, CalendarFeedItem)


@routes.get('/rss/legistar/feed-items')
@aiohttp_jinja2.template('meetings/includes/feed.html')
async def rss_legistar_feed_items(
    request: web.Request
) -> TemplateContextBase[LegistarFeed, LegistarFeedItem]:
    return await get_rss_tmpl_context(request, 'legistar_feed', LegistarFeed, LegistarFeedItem)

@routes.get('/{feed_name}/custom-feed-item')
@aiohttp_jinja2.template('meetings/custom-feed-item-form.html')
async def custom_feed_item_get(request: web.Request):
    feed_name = request.match_info['feed_name']
    assert feed_name in ['meetings_feed', 'calendar_feed', 'legistar_feed']
    context = {}
    return context


@routes.post('/{feed_name}/custom-feed-item')
async def custom_feed_item_post(request: web.Request):
    post = await request.post()
    keys = ['title', 'description', 'start_time', 'end_time', 'index', 'html_content']
    data = {key:post.get(key) for key in keys}
    dt_fmt = '%Y-%m-%dT%H:%M'
    kw = {
        'title':data['title'],
        'description':data['description'] if data['description'] else '',
        'index':int(data['index']),         # type: ignore
        'pub_date':timezone.get_now_local(request.app),
    }
    for key in ['start_time', 'end_time']:
        s = data[key]
        assert isinstance(s, str)
        dt = datetime.datetime.strptime(s, dt_fmt)
        dt = timezone.make_aware(dt, timezone.get_timezone(request.app))
        kw[key] = dt

    h = data['html_content']
    if h:
        if isinstance(h, bytes):
            h = h.decode('UTF-8')
        assert isinstance(h, str)
        kw['html_content'] = h

    feed_item = CustomFeedItem(**kw)
    feed_name = request.match_info['feed_name']
    assert feed_name in FeedNames
    app_item, created = await get_or_create_app_item(request.app, feed_name, cls=Feed)

    async with app_item:
        assert app_item.item is not None
        feed: Feed = app_item.item
        try:
            feed.add_custom_item(feed_item)
        except Exception as exc:
            import traceback
            return web.Response(
                text=traceback.format_exc()
            )
        await app_item.store(request.app)
    return web.Response(text='ok')


@logger.catch(reraise=True)
async def init_app(app: web.Application):
    logger.debug('weather.init_app()')
    tg = app[UPDATE_TASK_GROUP_KEY]
    for key in ['meetings_feed']:
        app_item, created = await get_or_create_app_item(app, key)
        if app_item.delta is None:
            app_item.delta = UPDATE_DELTA
        await tg.add_task(app_item, update_coro=_fetch_rss_feed)
