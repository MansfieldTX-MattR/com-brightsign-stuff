import asyncio
from pathlib import Path
import aiohttp
from aiohttp import web

HERE = Path(__file__).resolve().parent

routes = web.RouteTableDef()

async def get_rss_feed(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.text()


@routes.get('/rss/meetings.xml')
async def rss_meetings(request):
    url = 'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=Public-Meetings-24'
    resp_text = await get_rss_feed(url)
    return web.Response(text=resp_text, content_type='text/xml')

@routes.get('/rss/calendar.xml')
async def rss_calendar(request):
    url = 'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml'
    resp_text = await get_rss_feed(url)
    return web.Response(text=resp_text, content_type='text/xml')

def init_func(argv):
    app = web.Application()
    routes.static('/static', HERE)
    app.add_routes(routes)
    return app
