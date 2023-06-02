import os
import asyncio
import datetime
from collections import Counter
from loguru import logger
from pathlib import Path
import aiohttp
from aiohttp import web
from yarl import URL
import jinja2
import aiohttp_jinja2
from dotenv import load_dotenv

from feedparser import Feed, CalendarFeed


HERE = Path(__file__).resolve().parent
API_KEY = os.environ['OPENWEATHERMAP_APIKEY']

WEATHER_UPDATE_DELTA = datetime.timedelta(minutes=10)
FORECAST_UPDATE_DELTA = datetime.timedelta(minutes=60)

MEETINGS_URL = 'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=Public-Meetings-24'
CALENDAR_URL = 'https://www.mansfieldtexas.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml'

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
        'meteocon':'partly-cloudy-{day}-drizzle',
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
        'meteocon':'partly-cloudy-{day}-rain',
        'codes':{
            500:{'desc':'light rain'},
            501:{'desc':'moderate rain'},
            502:{'desc':'heavy intensity rain'},
            503:{'desc':'very heavy rain'},
            504:{'desc':'extreme rain', 'meteocon':'extreme-{day}-rain'},
            511:{'desc':'freezing rain', 'icon':'13d', 'meteocon':'partly-cloudy-{day}-sleet'},
            520:{'desc':'light intensity shower rain', 'icon':'09d'},
            521:{'desc':'shower rain', 'icon':'09d'},
            522:{'desc':'heavy intensity shower rain', 'icon':'09d'},
            531:{'desc':'ragged shower rain', 'icon':'09d'},
        },
    },
    'Snow':{
        'default_icon':'13d',
        'meteocon':'partly-cloudy-{day}-snow',
        'codes':{
            600:{'desc':'light snow'},
            601:{'desc':'snow'},
            602:{'desc':'heavy snow'},
            611:{'desc':'sleet', 'meteocon':'partly-cloudy-{day}-sleet'},
            612:{'desc':'light shower sleet', 'meteocon':'partly-cloudy-{day}-sleet'},
            613:{'desc':'shower sleet', 'meteocon':'partly-cloudy-{day}-sleet'},
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

def inject_condition_data(weather_data, sunrise=None, sunset=None):
    if sunrise is None:
        sunrise = weather_data['sys']['sunrise']
    if sunset is None:
        sunset = weather_data['sys']['sunset']
    is_daytime = sunrise <= weather_data['dt'] <= sunset
    for w in weather_data['weather']:
        cond = WEATHER_CONDITIONS_BY_CODE[w['id']].copy()
        meteocon = get_meteocon(cond['meteocon'], is_daytime)
        cond['meteocon'] = f'/static/weather2/meteocons/line/all/{meteocon}'
        w.update(cond)

def average_forecast_data(forecast_data):

    avg_keys = [
        'main.temp', 'main.feels_like', 'main.pressure', 'main.humidity',
        'clouds.all', 'rain.3h',
    ]
    min_keys = ['main.temp_min']
    max_keys = ['main.temp_max', 'rain.3h']

    def get_item_value(item: dict, key: str, default=0):
        if '.' not in key:
            return item.get(key, default)
        _key = key.split('.')[0]
        next_key = '.'.join(key.split('.')[1:])
        r = item.setdefault(_key, {})
        return get_item_value(r, next_key, default)

    def set_item_value(item: dict, key: str, value):
        if '.' not in key:
            item[key] = value
            return
        _key = key.split('.')[0]
        next_key = '.'.join(key.split('.')[1:])
        d = item.setdefault(_key, {})
        set_item_value(d, next_key, value)

    def build_item(item_data):
        result = {}
        keys = avg_keys + min_keys + max_keys
        keys.append('weather')
        for key in keys:
            value = get_item_value(item_data, key)
            if isinstance(value, list):
                value = [value[0]]
            set_item_value(result, key, value)

        return result

    def handle_item(item_data, all_data):
        for key in avg_keys:
            value = get_item_value(all_data, key)
            value += get_item_value(item_data, key)
            set_item_value(all_data, key, value)
        for key in min_keys:
            values = [get_item_value(d, key) for d in [item_data, all_data]]
            set_item_value(all_data, key, min(values))
        for key in max_keys:
            values = [get_item_value(d, key) for d in [item_data, all_data]]
            set_item_value(all_data, key, max(values))

        weather_list = get_item_value(all_data, 'weather')
        weather_list.append(get_item_value(item_data, 'weather')[0])

    def finalize_day(data, item_count):
        for key in avg_keys:
            value = get_item_value(data, key)
            value /= item_count
            set_item_value(data, key, value)

        weather_list = get_item_value(data, 'weather')
        d = {w['id']:w for w in weather_list}
        c = Counter([w['id'] for w in weather_list])
        w_id = c.most_common(1)[0][0]
        set_item_value(data, 'weather', d[w_id])

    daily = {}
    cur_data = {}
    cur_date = None
    item_count = 0

    for item in forecast_data['list']:
        dt = datetime.datetime.fromtimestamp(item['dt'])
        if cur_date is None or dt.date() != cur_date:
            if item_count != 0:
                assert cur_date is not None
                handle_item(item, cur_data)
                finalize_day(cur_data, item_count)
                daily[cur_date] = cur_data
            cur_date = dt.date()
            cur_data = build_item(item)
            cur_data['day_short'] = cur_date.strftime('%a')
            cur_data['day_full'] = cur_date.strftime('%A')
            item_count = 1
            continue
        handle_item(item, cur_data)
        item_count += 1
    if cur_date not in daily:
        assert cur_date is not None
        finalize_day(cur_data, item_count)
        daily[cur_date] = cur_data
    return daily


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

        for item in data['list']:
            inject_condition_data(item, sunrise, sunset)
        daily = average_forecast_data(data)
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
        inject_condition_data(data)
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
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(HERE))
    routes.static('/static', HERE)
    app.add_routes(routes)
    app.on_cleanup.append(on_cleanup)
    return app
