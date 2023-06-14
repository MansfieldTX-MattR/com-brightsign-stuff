from aiohttp import web
import aiohttp_jinja2

from .feedparser import MeetingsFeed, CalendarFeed
from . import requests
from .localstorage import get_app_item, set_app_item, update_app_items

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

async def get_rss_feed(request, url):
    session = requests.get_aio_client_session(request.app)
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


@routes.get('/rss/meetings.xml')
async def rss_meetings(request):
    resp_text = await get_rss_feed(request, FEED_INFO['meetings_feed']['url'])
    return web.Response(text=resp_text, content_type='text/xml')

@routes.get('/rss/calendar.xml')
async def rss_calendar(request):
    resp_text = await get_rss_feed(request, FEED_INFO['calendar_feed']['url'])
    return web.Response(text=resp_text, content_type='text/xml')

async def get_rss_tmpl_context(request, storage_key):
    feed_info = FEED_INFO[storage_key]
    resp_text = await get_rss_feed(request, feed_info['url'])
    app_item = await get_app_item(request.app, storage_key)
    if app_item is None:
        feed = feed_info['parser_cls'].from_xml_str(resp_text)
        await set_app_item(app=request.app, key=storage_key, item=feed)
    else:
        feed = app_item.item
        feed.update_from_xml_str(resp_text)
        await update_app_items(request.app)
    max_items = request.query.get('maxItems')

    context = {'rss_feed':feed}
    if max_items is not None:
        context['max_items'] = int(max_items)
    return context

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
