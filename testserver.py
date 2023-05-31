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


WEATHER_CONDITION_MAP = {
    'Thunderstorm':{
        'default_icon':'11d',
        'meteocon':'thunderstorms-{day}-rain',
        'codes':{
            200:{'desc':'thunderstorm with light rain'},
            201:{'desc':'thunderstorm with rain'},
            202:{'desc':'thunderstorm with heavy rain'},
            210:{'desc':'light thunderstorm'},
            211:{'desc':'thunderstorm', 'meteocon':'thunderstorms-{day}'},
            212:{'desc':'heavy thunderstorm', 'meteocon':'thunderstorms-{day}-extreme'},
            221:{'desc':'ragged thunderstorm', 'meteocon':'thunderstorms-{day}-extreme'},
            230:{'desc':'thunderstorm with light drizzle'},
            231:{'desc':'thunderstorm with drizzle'},
            232:{'desc':'thunderstorm with heavy drizzle'},
        },
    },
    'Drizzle':{
        'default_icon':'09d',
        'meteocon':'overcast-{day}-drizzle',
        'codes':{
            300:{'desc':'light intensity drizzle'},
            301:{'desc':'drizzle'},
            302:{'desc':'heavy intensity drizzle'},
            310:{'desc':'light intensity drizzle'},
            311:{'desc':'drizzle rain'},
            312:{'desc':'heavy intensity drizzle rain'},
            313:{'desc':'shower rain and drizzle'},
            314:{'desc':'heavy shower rain and drizzle'},
            321:{'desc':'shower drizzle'},
        },
    },
    'Rain':{
        'default_icon':'10d',
        'meteocon':'overcast-{day}-rain',
        'codes':{
            500:{'desc':'light rain'},
            501:{'desc':'moderate rain'},
            502:{'desc':'heavy intensity rain'},
            503:{'desc':'very heavy rain'},
            504:{'desc':'extreme rain', 'meteocon':'extreme-{day}-rain'},
            511:{'desc':'freezing rain', 'icon':'13d', 'meteocon':'overcast-{day}-sleet'},
            520:{'desc':'light intensity shower rain', 'icon':'09d'},
            521:{'desc':'shower rain', 'icon':'09d'},
            522:{'desc':'heavy intensity shower rain', 'icon':'09d'},
            531:{'desc':'ragged shower rain', 'icon':'09d'},
        },
    },
    'Snow':{
        'default_icon':'13d',
        'meteocon':'overcast-{day}-snow',
        'codes':{
            600:{'desc':'light snow'},
            601:{'desc':'snow'},
            602:{'desc':'heavy snow'},
            611:{'desc':'sleet', 'meteocon':'overcast-{day}-sleet'},
            612:{'desc':'light shower sleet', 'meteocon':'overcast-{day}-sleet'},
            613:{'desc':'shower sleet', 'meteocon':'overcast-{day}-sleet'},
            615:{'desc':'light rain and snow'},
            616:{'desc':'rain and snow'},
            620:{'desc':'light shower snow'},
            621:{'desc':'shower snow'},
            622:{'desc':'heavy shower snow', 'meteocon':'extreme-{day}-snow'},
        },
    },
    'Atmosphere':{
        'default_icon':'50d',
        'codes':{
            701:{'desc':'mist', 'meteocon':'mist'},
            711:{'desc':'smoke', 'meteocon':'overcast-{day}-smoke'},
            721:{'desc':'haze', 'meteocon':'haze-{day}'},
            731:{'desc':'sand/dust whirls', 'meteocon':'dust-wind'},
            741:{'desc':'fog', 'meteocon':'fog-{day}'},
            751:{'desc':'sand', 'meteocon':'dust'},
            761:{'desc':'dust', 'meteocon':'dust'},
            762:{'desc':'volcanic ash', 'meteocon':'dust'},
            771:{'desc':'squalls', 'meteocon':'wind'},
            781:{'desc':'tornado', 'meteocon':'tornado'},
        },
    },
    'Clear':{
        'default_icon':'01d',
        'codes':{
            800:{'desc':'clear sky', 'meteocon':'clear-{day}'},
        },
    },
    'Clouds':{
        'meteocon':'partly-cloudy-{day}',
        'codes':{
            801:{'desc':'few clouds', 'icon':'02d'},
            802:{'desc':'scattered clouds', 'icon':'03d'},
            803:{'desc':'broken clouds', 'icon':'04d'},
            804:{'desc':'overcast clouds', 'icon':'04d', 'meteocon':'overcast-{day}'},
        },
    },
}

WEATHER_CONDITIONS_BY_CODE = {}

def _build_weather_conditions():
    for group_name, group in WEATHER_CONDITION_MAP.items():
        icon = group.get('default_icon')
        meteocon = group.get('meteocon')
        for code, code_data in group['codes'].items():
            code_data.setdefault('icon', icon)
            code_data.setdefault('meteocon', meteocon)
            code_data.update(dict(group_name=group_name, id=code))
            WEATHER_CONDITIONS_BY_CODE[code] = code_data

_build_weather_conditions()

def get_meteocon(meteocon: str, is_daytime: bool) -> str:
    day_str = 'day' if is_daytime else 'night'
    meteocon = '.'.join([meteocon, 'svg'])
    return meteocon.format(day=day_str)

def get_icon(icon: str, is_daytime: bool) -> str:
    if not icon.endswith('d'):
        return icon
    day_str = 'd' if is_daytime else 'n'
    return f'{icon[:2]}{day_str}'

def inject_condition_data(weather_data):
    sunrise = weather_data['sys']['sunrise']
    sunset = weather_data['sys']['sunset']
    is_daytime = sunrise <= weather_data['dt'] <= sunset
    for w in weather_data['weather']:
        cond = WEATHER_CONDITIONS_BY_CODE[w['id']].copy()
        meteocon = get_meteocon(cond['meteocon'], is_daytime)
        cond['meteocon'] = f'/static/weather2/meteocons/line/all/{meteocon}'
        w.update(cond)


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
        inject_condition_data(data)
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

@routes.get('/weather-data-html')
@aiohttp_jinja2.template('weather2/includes/weather-current.html')
async def get_weather_data_html(request):
    data = await get_weather_context_data(request)
    return {'weather_data':data, 'include_json_data':True}


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
