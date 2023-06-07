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

from .feedparser import Feed, CalendarFeed
from . import weather


TEMPLATE_DIR = Path.cwd()
STATIC_DIR = Path.cwd()
API_KEY = os.environ['OPENWEATHERMAP_APIKEY']

WEATHER_UPDATE_DELTA = datetime.timedelta(minutes=10)
FORECAST_UPDATE_DELTA = datetime.timedelta(minutes=60)

MEETINGS_URL = 'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=Public-Meetings-24'
CALENDAR_URL = 'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml'

routes = web.RouteTableDef()


async def get_rss_feed(request, url):
    session = get_aio_client_session(request.app)
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

@logger.catch
async def get_forecast_context_data(request):
    now = datetime.datetime.now()
    data = request.app.get('weather_forecast')
    if data is not None:
        ts = data['dt']
        dt = datetime.datetime.fromtimestamp(ts)
        next_update = dt + FORECAST_UPDATE_DELTA
        if now < next_update:
            logger.debug('using cached forecast')
            return {'weather_forecast':data}

    logger.info('retreiving forecast data')
    lat, lon = await get_geo_coords(request)
    num_days = 5
    num_hours = num_days * 24
    query = {
        'lat':lat,
        'lon':lon,
        'cnt':num_hours // 3,
        'units':'imperial',
        'lang':'en',
        'appid':API_KEY,
    }
    url = URL('https://api.openweathermap.org/data/2.5/forecast').with_query(**query)
    session = get_aio_client_session(request.app)
    async with session.get(url) as response:
        response.raise_for_status()
        data = await response.json()
        sunrise, sunset = data['city']['sunrise'], data['city']['sunset']
        dt = datetime.datetime.now().replace(hour=12, minute=0)

        for item in data['list']:
            weather.inject_condition_data(item, sunrise, sunset, dt=dt.timestamp())
        daily = weather.average_forecast_data(data)
        data['daily'] = [daily[date] for date in sorted(daily.keys())]
        data['dt'] = now.timestamp()
        request.app['weather_forecast'] = data
        return {'weather_forecast':data}

async def get_weather_context_data(request):
    now = datetime.datetime.now()
    weather_data = request.app.get('weather_data')
    if weather_data is not None:
        ts = weather_data['dt']
        dt = datetime.datetime.fromtimestamp(ts)
        next_update = dt + WEATHER_UPDATE_DELTA
        if now < next_update:
            logger.debug('using cached weather')
            return {'weather_data':weather_data}

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
        weather.inject_condition_data(data)
        request.app['weather_data'] = data
        return {'weather_data':data}

async def get_context_data(request):
    coros = [
        get_weather_context_data(request),
        get_forecast_context_data(request),
    ]
    result = {}
    for fut in asyncio.as_completed(coros):
        r = await fut
        result.update(r)
    return result

@routes.get('/weather2')
@aiohttp_jinja2.template('weather2/openweather.html')
async def get_weather_data(request):
    data = await get_context_data(request)
    return data


@routes.get('/weather-data-json')
async def get_weather_data_json(request):
    data = await get_weather_context_data(request)
    return web.json_response(data['weather_data'])

@routes.get('/weather-data-html')
@aiohttp_jinja2.template('weather2/includes/weather-current.html')
async def get_weather_data_html(request):
    data = await get_weather_context_data(request)
    data['include_json_data'] = True
    return data

@routes.get('/forecast-data-json')
async def get_forecast_data_json(request):
    data = await get_forecast_context_data(request)
    return web.json_response(data['weather_forecast'])

@routes.get('/forecast-data-html')
@aiohttp_jinja2.template('weather2/includes/weather-forecast.html')
async def get_forecast_data_html(request):
    data = await get_forecast_context_data(request)
    data['include_json_data'] = True
    return data

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
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(TEMPLATE_DIR))
    routes.static('/static', STATIC_DIR)
    app.add_routes(routes)
    app.on_cleanup.append(on_cleanup)
    return app
