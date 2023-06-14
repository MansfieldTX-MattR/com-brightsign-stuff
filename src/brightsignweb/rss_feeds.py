import datetime
from aiohttp import web
import aiohttp_jinja2
from loguru import logger

from .feedparser import MeetingsFeed, CalendarFeed
from . import requests
from .localstorage import get_or_create_app_item, AppItem

UPDATE_DELTA = datetime.timedelta(minutes=5)

FEED_INFO = {
    'meetings_feed':{
        'url':'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=Public-Meetings-24',
        'parser_cls':MeetingsFeed,
    },
    'calendar_feed':{
        'url':'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml',
        'parser_cls':CalendarFeed,
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

async def get_rss_tmpl_context(request, storage_key):
    app_item, created = await get_or_create_app_item(request.app, storage_key)
    async with app_item:
        if app_item.delta is None:
            app_item.delta = UPDATE_DELTA
            app_item.dt = datetime.datetime.now()
        if created or app_item.delta is None or app_item.expired:
            logger.debug(f'trigger update_evt for {app_item.key}')
            app_item.update_evt.set()
            if created:
                await app_item.notify.wait()
        else:
            logger.debug(f'using cache for {storage_key}')
    max_items = request.query.get('maxItems')
    context = {'rss_feed':app_item.item}
    if max_items is not None:
        context['max_items'] = int(max_items)
    return context

async def _fetch_rss_feed(app: web.Application, app_item: AppItem):
    logger.info(f'retrieving {app_item.key}')
    feed_info = FEED_INFO[app_item.key]
    resp_text = await get_rss_feed(app, feed_info['url'])
    if app_item.item is None:
        feed = feed_info['parser_cls'].from_xml_str(resp_text)
        app_item.item = feed
    else:
        feed = app_item.item
        feed.update_from_xml_str(resp_text)
    now = datetime.datetime.now()
    await app_item.update(app, dt=now, delta=UPDATE_DELTA)


@routes.get('/rss/meetings.html')
@aiohttp_jinja2.template('meetings/meetings-tmpl.html')
async def rss_meetings_html(request: web.Request):
    context = await get_rss_tmpl_context(request, 'meetings_feed')
    context.update(dict(
        page_title='Upcoming Meetings',
        update_url='/rss/meetings/feed-items',
    ))
    return context

@routes.get('/rss/calendar.html')
@aiohttp_jinja2.template('meetings/meetings-tmpl.html')
async def rss_calendar_html(request: web.Request):
    context = await get_rss_tmpl_context(request, 'calendar_feed')
    context.update(dict(
        page_title='Calendar Events',
        update_url='/rss/calendar/feed-items',
    ))
    return context


@routes.get('/rss/meetings/feed-items')
@aiohttp_jinja2.template('meetings/includes/feed.html')
async def rss_meetings_feed_items(request: web.Request):
    return await get_rss_tmpl_context(request, 'meetings_feed')


@routes.get('/rss/calendar/feed-items')
@aiohttp_jinja2.template('meetings/includes/feed.html')
async def rss_calendar_feed_items(request: web.Request):
    return await get_rss_tmpl_context(request, 'calendar_feed')


async def init_app(app: web.Application):
    logger.debug('weather.init_app()')
    tg = app['update_tasks']
    for key in ['meetings_feed', 'calendar_feed']:
        app_item, created = await get_or_create_app_item(app, key)
        if app_item.delta is None:
            app_item.delta = UPDATE_DELTA
        await tg.add_task(app_item, update_coro=_fetch_rss_feed)
