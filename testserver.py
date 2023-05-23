import os
import asyncio
from pathlib import Path
import aiohttp
from aiohttp import web
from yarl import URL
import jinja2
import aiohttp_jinja2
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
API_KEY = os.environ['OPENWEATHERMAP_APIKEY']

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

async def get_geo_coords() -> tuple[float, float]:
    query = {
        'zip':'76063,US',
        'appid':API_KEY,
    }
    url = URL('http://api.openweathermap.org/geo/1.0/zip').with_query(**query)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            return data['lat'], data['lon']


@routes.get('/weather2')
@aiohttp_jinja2.template('weather2/openweather.html')
async def get_weather_data(request):
    lat, lon = await get_geo_coords()
    query = {
        'lat':lat,
        'lon':lon,
        'units':'imperial',
        'lang':'en',
        'appid':API_KEY,
    }
    url = URL('https://api.openweathermap.org/data/2.5/weather').with_query(**query)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            return {'weather_data':data}


def init_func(argv):
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(HERE))
    routes.static('/static', HERE)
    app.add_routes(routes)
    return app
