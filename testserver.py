import os
import asyncio
import datetime
from loguru import logger
from pathlib import Path
import aiohttp
from aiohttp import web
from yarl import URL
import jinja2
import aiohttp_jinja2
from dotenv import load_dotenv


HERE = Path(__file__).resolve().parent
API_KEY = os.environ['OPENWEATHERMAP_APIKEY']

WEATHER_UPDATE_DELTA = datetime.timedelta(minutes=10)

routes = web.RouteTableDef()


async def get_rss_feed(request, url):
    session = get_aio_client_session(request.app)
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


@routes.get('/rss/meetings.xml')
async def rss_meetings(request):
    url = 'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=Public-Meetings-24'
    resp_text = await get_rss_feed(request, url)
    return web.Response(text=resp_text, content_type='text/xml')

@routes.get('/rss/calendar.xml')
async def rss_calendar(request):
    url = 'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml'
    resp_text = await get_rss_feed(request, url)
    return web.Response(text=resp_text, content_type='text/xml')


async def get_geo_coords(request) -> tuple[float, float]:
    coords = request.app.get('latlon')
    if coords is not None:
        return coords
    query = {
        'zip':'76063,US',
        'appid':API_KEY,
    }
    url = URL('http://api.openweathermap.org/geo/1.0/zip').with_query(**query)
    session = get_aio_client_session(request.app)
    async with session.get(url) as response:
        response.raise_for_status()
        data = await response.json()
        coords = (data['lat'], data['lon'])
        request.app['latlon'] = coords
        return coords


async def get_weather_context_data(request):
    now = datetime.datetime.now()
    weather_data = request.app.get('weather_data')
    if weather_data is not None:
        ts = weather_data['dt']
        dt = datetime.datetime.fromtimestamp(ts)
        next_update = dt + WEATHER_UPDATE_DELTA
        if now < next_update:
            logger.debug('using cached weather')
            return weather_data

    logger.info('retreiving weather data')
    lat, lon = await get_geo_coords(request)
    query = {
        'lat':lat,
        'lon':lon,
        'units':'imperial',
        'lang':'en',
        'appid':API_KEY,
    }
    url = URL('https://api.openweathermap.org/data/2.5/weather').with_query(**query)
    session = get_aio_client_session(request.app)
    async with session.get(url) as response:
        response.raise_for_status()
        data = await response.json()
        request.app['weather_data'] = data
        return data


@routes.get('/weather2')
@aiohttp_jinja2.template('weather2/openweather.html')
async def get_weather_data(request):
    data = await get_weather_context_data(request)
    return {'weather_data':data}


@routes.get('/weather-data-json')
async def get_weather_data_json(request):
    data = await get_weather_context_data(request)
    return web.json_response(data)



def get_aio_client_session(app):
    session = app.get('aio_client_session')
    if session is None:
        logger.info('building aio_client_session')
        session = aiohttp.ClientSession()
        app['aio_client_session'] = session
    return session

async def on_cleanup(app):
    session = app.get('aio_client_session')
    if session is not None:
        logger.info('closing aio_client_session')
        await session.close()

def init_func(argv):
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(HERE))
    routes.static('/static', HERE)
    app.add_routes(routes)
    app.on_cleanup.append(on_cleanup)
    return app
