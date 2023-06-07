from loguru import logger
from pathlib import Path
from aiohttp import web
import jinja2
import aiohttp_jinja2
from dotenv import load_dotenv

from .feedparser import Feed, CalendarFeed
from . import weather
from . import requests


TEMPLATE_DIR = Path.cwd()
STATIC_DIR = Path.cwd()

MEETINGS_URL = 'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=Public-Meetings-24'
CALENDAR_URL = 'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml'

routes = web.RouteTableDef()


async def get_rss_feed(request, url):
    session = requests.get_aio_client_session(request.app)
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


@routes.get('/rss/meetings.xml')
async def rss_meetings(request):
    resp_text = await get_rss_feed(request, MEETINGS_URL)
    return web.Response(text=resp_text, content_type='text/xml')

@routes.get('/rss/calendar.xml')
async def rss_calendar(request):
    resp_text = await get_rss_feed(request, CALENDAR_URL)
    return web.Response(text=resp_text, content_type='text/xml')

async def get_rss_tmpl_context(request, url, parser_cls, storage_key):
    resp_text = await get_rss_feed(request, url)
    feed = request.app.get(storage_key)
    if feed is None:
        feed = parser_cls.from_xml_str(resp_text)
        request.app[storage_key] = feed
    else:
        feed.update_from_xml_str(resp_text)
    max_items = request.query.get('maxItems')

    context = {'rss_feed':feed}
    if max_items is not None:
        context['max_items'] = int(max_items)
    return context

@routes.get('/rss/meetings.html')
@aiohttp_jinja2.template('meetings/meetings-tmpl.html')
async def rss_meetings_html(request: web.Request):
    context = await get_rss_tmpl_context(request, MEETINGS_URL, Feed, 'meetings_feed')
    context.update(dict(
        page_title='Upcoming Meetings',
        update_url='/rss/meetings/feed-items',
    ))
    return context

@routes.get('/rss/calendar.html')
@aiohttp_jinja2.template('meetings/meetings-tmpl.html')
async def rss_calendar_html(request: web.Request):
    context = await get_rss_tmpl_context(request, CALENDAR_URL, CalendarFeed, 'calendar_feed')
    context.update(dict(
        page_title='Calendar Events',
        update_url='/rss/calendar/feed-items',
    ))
    return context


@routes.get('/rss/meetings/feed-items')
@aiohttp_jinja2.template('meetings/includes/feed.html')
async def rss_meetings_feed_items(request: web.Request):
    return await get_rss_tmpl_context(request, MEETINGS_URL, Feed, 'meetings_feed')


@routes.get('/rss/calendar/feed-items')
@aiohttp_jinja2.template('meetings/includes/feed.html')
async def rss_calendar_feed_items(request: web.Request):
    return await get_rss_tmpl_context(request, CALENDAR_URL, CalendarFeed, 'calendar_feed')


def static_filter(path: str) -> str:
    path = path.lstrip('/')
    return f'/static/{path}'

def init_func(argv):
    app = web.Application()
    jinja_env = aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(TEMPLATE_DIR))
    jinja_env.filters['static'] = static_filter
    routes.static('/static', STATIC_DIR)
    app.add_routes(routes)
    app.add_routes(weather.routes)
    app.on_cleanup.append(requests.on_cleanup)
    return app
