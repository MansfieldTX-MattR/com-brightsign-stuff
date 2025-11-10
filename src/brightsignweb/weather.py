from __future__ import annotations
from typing import Literal, TypedDict, NotRequired, Iterator, cast
import os
import datetime
from collections import Counter
import asyncio
from loguru import logger
from aiohttp import web
from yarl import URL
import aiohttp_jinja2

from .requests import get_aio_client_session
from .localstorage import (
    get_app_item, set_app_item, get_or_create_app_item, AppItem,
)
from .staticfiles import get_static_url
from . import timezone
from .types import *
from .weather_types import *
from .weather_types import (
    weather_data_from_src, forecast_item_from_src,
    weather_forecast_src_from_items,
)


API_KEY = os.environ['OPENWEATHERMAP_APIKEY']
WEATHER_UPDATE_DELTA = datetime.timedelta(minutes=15)
FORECAST_UPDATE_DELTA = datetime.timedelta(minutes=65)

LatLonT = tuple[float, float]

LATLON_KEY = web.AppKey('latlon', LatLonT)
FORECAST_KEY = web.AppKey('weather_forecast', WeatherForecast)
WEATHER_DATA_KEY = web.AppKey('weather_data', WeatherData)

LATLON_KEY_NAME = Literal['latlon']
FORECAST_KEY_NAME = Literal['weather_forecast']
WEATHER_DATA_KEY_NAME = Literal['weather_data']


class ForecastContext(TypedDict):
    weather_forecast: WeatherForecast
    include_json_data: NotRequired[bool]

class WeatherDataContext(TypedDict):
    weather_data: WeatherData
    include_json_data: NotRequired[bool]


class CombinedWeatherContext(ForecastContext, WeatherDataContext): ...


routes = web.RouteTableDef()


_WEATHER_CONDITION_MAP: dict[WeatherConditionName, WeatherCondition[WeatherConditionCodeBase]] = {
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
        'meteocon':'fog-{day}',
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
        'meteocon':'clear-{day}',
        'codes':{
            800:{'desc':'clear sky', 'meteocon':'clear-{day}'},
        },
    },
    'Clouds':{
        'default_icon':'03d',
        'meteocon':'partly-cloudy-{day}',
        'codes':{
            801:{'desc':'few clouds', 'icon':'02d'},
            802:{'desc':'scattered clouds', 'icon':'03d'},
            803:{'desc':'broken clouds', 'icon':'04d'},
            804:{'desc':'overcast clouds', 'icon':'04d', 'meteocon':'overcast-{day}'},
        },
    },
}

WEATHER_CONDITION_MAP: dict[WeatherConditionName, WeatherCondition[WeatherConditionCode]] = {}

WEATHER_CONDITIONS_BY_CODE: dict[int, WeatherConditionCode] = {}

def _build_weather_conditions():
    for group_name, group in _WEATHER_CONDITION_MAP.items():
        icon = group.get('default_icon')
        meteocon = group.get('meteocon')
        out_codes: dict[int, WeatherConditionCode] = {}
        for code, code_data in group['codes'].items():
            out_data = WeatherConditionCode(
                id=code,
                desc=code_data['desc'],
                icon=code_data.get('icon', icon),
                meteocon=code_data.get('meteocon', meteocon),
                group_name=group_name,
            )
            WEATHER_CONDITIONS_BY_CODE[code] = out_data
            out_codes[code] = out_data
        WEATHER_CONDITION_MAP[group_name] = WeatherCondition(
            default_icon=icon,
            meteocon=meteocon,
            codes=out_codes,
        )
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


def _inject_condition(app: web.Application, is_daytime: bool, *items: NowWeatherSrc) -> Iterator[NowWeather]:
    for item in items:
        cond = WEATHER_CONDITIONS_BY_CODE[item['id']].copy()
        meteocon = get_meteocon(cond['meteocon'], is_daytime)
        icon = get_icon(item.get('icon', cond.get('default_icon', '01d')), is_daytime)
        cond['meteocon'] = get_static_url(app, f'weather2/meteocons/fill/all/{meteocon}')
        yield cast(NowWeather, {**item, **cond, 'icon':icon})

def inject_condition_data(
    app: web.Application,
    weather_data: WeatherDataSrc,
) -> WeatherData:
    dt = weather_data['dt']
    sunrise = weather_data['sys']['sunrise']
    sunset = weather_data['sys']['sunset']
    is_daytime = sunrise <= dt <= sunset
    weathers = _inject_condition(app, is_daytime, *weather_data['weather'])
    return weather_data_from_src(weather_data, list(weathers))


def inject_forecast_condition_data(
    app: web.Application,
    forecast_item: ForecastItemSrc,
    sunrise: float,
    sunset: float,
    dt: float
) -> ForecastItem:
    is_daytime = sunrise <= dt <= sunset
    weathers = _inject_condition(app, is_daytime, *forecast_item['weather'])
    return forecast_item_from_src(forecast_item, list(weathers))


def average_forecast_data(
    app: web.Application,
    forecast_data: WeatherForecastSrc[ForecastItem],
) -> dict[datetime.date, DailyForecastItem]:
    # TODO: Rework these nested functions to by more type-friendly
    avg_keys = [
        'main.temp', 'main.feels_like', 'main.pressure', 'main.humidity',
        'clouds.all', 'rain.3h',
    ]
    min_keys = ['main.temp_min']
    max_keys = ['main.temp_max', 'rain.3h']

    def get_item_value(item, key: str, default=0):
        if '.' not in key:
            return item.get(key, default)
        _key = key.split('.')[0]
        next_key = '.'.join(key.split('.')[1:])
        r = item.setdefault(_key, {})
        return get_item_value(r, next_key, default)

    def set_item_value(item, key: str, value):
        if '.' not in key:
            item[key] = value
            return
        _key = key.split('.')[0]
        next_key = '.'.join(key.split('.')[1:])
        d = item.setdefault(_key, {})
        set_item_value(d, next_key, value)

    def build_item(item_data: ForecastItem) -> DailyForecastItem:
        result = {}
        keys = avg_keys + min_keys + max_keys
        keys.append('weather')
        for key in keys:
            value = get_item_value(item_data, key)
            if isinstance(value, list):
                value = [value[0]]
            set_item_value(result, key, value)

        return result # type: ignore

    def handle_item(item_data: ForecastItem, all_data: DailyForecastItem):
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
        weather_list.append(get_item_value(item_data, 'weather')[0]) # type: ignore

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

    daily: dict[datetime.date, DailyForecastItem] = {}
    cur_data: DailyForecastItem|None = None
    cur_date = None
    item_count = 0

    for item in forecast_data['list']:
        dt = timezone.dt_from_timestamp_local(app, item['dt'])
        if cur_date is None or dt.date() != cur_date:
            if item_count != 0:
                assert cur_date is not None
                assert cur_data is not None
                handle_item(item, cur_data)
                finalize_day(cur_data, item_count)
                daily[cur_date] = cur_data
            cur_date = dt.date()
            cur_data = build_item(item)
            cur_data['day_short'] = cur_date.strftime('%a')
            cur_data['day_full'] = cur_date.strftime('%A')
            item_count = 1
            continue
        assert cur_data is not None
        handle_item(item, cur_data)
        item_count += 1
    if cur_date not in daily:
        assert cur_date is not None
        assert cur_data is not None
        finalize_day(cur_data, item_count)
        daily[cur_date] = cur_data
    return daily


@logger.catch(reraise=True)
async def get_geo_coords(app: web.Application) -> LatLonT:
    key: LATLON_KEY_NAME = 'latlon'
    app_item = await get_app_item(app, key, cls=LatLonT)
    if app_item is not None and app_item.item is not None:
        coords = app_item.item
        logger.debug('using cached geo coords')
        return coords
    query = {
        'zip':'76063,US',
        'appid':API_KEY,
    }
    url = URL('http://api.openweathermap.org/geo/1.0/zip').with_query(**query)
    session = get_aio_client_session(app)
    logger.debug('retrieving geo coords')
    async with session.get(url) as response:
        response.raise_for_status()
        data: Coord = await response.json()
        coords: LatLonT = (data['lat'], data['lon'])
        await set_app_item(app, key, coords)
        return coords


@logger.catch(reraise=True)
async def get_forecast_context_data(request) -> ForecastContext:
    key: FORECAST_KEY_NAME = 'weather_forecast'
    app_item, created = await get_or_create_app_item(request.app, key, cls=WeatherForecast)
    async with app_item:
        if created or app_item.expired or app_item.item is None:
            logger.debug(f'trigger update_evt for {app_item.key}')
            app_item.update_evt.set()
            if created or app_item.item is None:
                await app_item.notify.wait()
        else:
            logger.debug('using cached forecast')
        assert app_item.item is not None
        return {'weather_forecast':app_item.item}


@logger.catch(reraise=True)
async def _fetch_forecast_data(app: web.Application, app_item: AppItem[FORECAST_KEY_NAME, WeatherForecast]):
    now = timezone.get_now_local(app)
    logger.info('retreiving forecast data')
    lat, lon = await get_geo_coords(app)
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
    session = get_aio_client_session(app)
    async with session.get(url) as response:
        response.raise_for_status()
        src_data: WeatherForecastSrc = await response.json()
        sunrise, sunset = src_data['city']['sunrise'], src_data['city']['sunset']
        dt = now.replace(hour=12, minute=0, second=0, microsecond=0)
        ts = timezone.dt_to_timestamp(dt)

        items: list[ForecastItem] = []
        for src_item in src_data['list']:
            item = inject_forecast_condition_data(app, src_item, sunrise, sunset, dt=ts)
            items.append(item)

        # Rebuild src_data with typed items
        src_data = weather_forecast_src_from_items(src_data, items)

        daily = average_forecast_data(app, src_data)
        daily = [daily[date] for date in sorted(daily.keys())]
        data = WeatherForecast(
            dt=now.timestamp(),
            cod=src_data['cod'],
            message=src_data['message'],
            cnt=src_data['cnt'],
            daily=daily,
            city=src_data['city'],
        )
        dt = timezone.dt_from_timestamp_local(app, data['dt'])
        await app_item.update(app, item=data, dt=dt, delta=FORECAST_UPDATE_DELTA)


@logger.catch(reraise=True)
async def get_weather_context_data(request) -> WeatherDataContext:
    key: WEATHER_DATA_KEY_NAME = 'weather_data'
    app_item, created = await get_or_create_app_item(request.app, key, cls=WeatherData)
    async with app_item:
        if created or app_item.expired or app_item.item is None:
            logger.debug(f'trigger update_evt for {app_item.key}')
            app_item.update_evt.set()
            if created or app_item.item is None:
                await app_item.notify.wait()
        else:
            logger.debug('using cached weather')
        assert app_item.item is not None
        return {'weather_data':app_item.item}

async def _fetch_weather_data(app: web.Application, app_item: AppItem[WEATHER_DATA_KEY_NAME, WeatherData]):
    logger.info('retreiving weather data')
    lat, lon = await get_geo_coords(app)
    query = {
        'lat':lat,
        'lon':lon,
        'units':'imperial',
        'lang':'en',
        'appid':API_KEY,
    }
    url = URL('https://api.openweathermap.org/data/2.5/weather').with_query(**query)
    session = get_aio_client_session(app)
    async with session.get(url) as response:
        response.raise_for_status()
        src_data: WeatherDataSrc = await response.json()
        data = inject_condition_data(app, src_data)
        dt = timezone.dt_from_timestamp_local(app, data['dt'])
        await app_item.update(app, item=data, dt=dt, delta=WEATHER_UPDATE_DELTA)


async def check_last_modified(
    request: web.Request,
    key: WEATHER_DATA_KEY_NAME|FORECAST_KEY_NAME,
) -> tuple[web.Response|None, datetime.datetime|None]:
    def parse_dt_header(dt_str: str) -> datetime.datetime:
        dt_fmt = '%a, %d %b %Y %H:%M:%S %Z'
        dt = datetime.datetime.strptime(dt_str, dt_fmt)
        return timezone.make_aware(dt, timezone.UTC)

    app_item = await get_app_item(request.app, key)
    if app_item is None or app_item.dt is None:
        return None, None
    last_modified = timezone.as_timezone(app_item.dt, timezone.UTC)
    if 'If-Modified-Since' not in request.headers:
        return None, last_modified
    ims_str = request.headers['If-Modified-Since']
    ims_dt = parse_dt_header(ims_str)
    if last_modified <= ims_dt:
        return web.Response(status=304), last_modified
    return None, last_modified


@logger.catch(reraise=True)
async def get_context_data(request) -> CombinedWeatherContext:
    weather = await get_weather_context_data(request)
    forecast = await get_forecast_context_data(request)
    return CombinedWeatherContext(
        weather_data=weather['weather_data'],
        weather_forecast=forecast['weather_forecast'],
    )

@routes.get('/weather2')
@aiohttp_jinja2.template('weather2/openweather.html')
async def get_weather_data(request) -> CombinedWeatherContext:
    data = await get_context_data(request)
    return data


@routes.get('/weather-data-json')
async def get_weather_data_json(request):
    data = await get_weather_context_data(request)
    return web.json_response(data['weather_data'])

@routes.get('/weather-data-html')
async def get_weather_data_html(request) -> web.Response:
    _resp, last_modified = await check_last_modified(request, key='weather_data')
    if _resp is not None:
        return _resp
    data = await get_weather_context_data(request)
    data['include_json_data'] = True
    resp: web.Response = aiohttp_jinja2.render_template(
        'weather2/includes/weather-current.html',
        request=request,
        context=data,
    )
    resp.last_modified = last_modified
    return resp

@routes.get('/forecast-data-json')
async def get_forecast_data_json(request):
    data = await get_forecast_context_data(request)
    return web.json_response(data['weather_forecast'])

@routes.get('/forecast-data-html')
async def get_forecast_data_html(request) -> web.Response:
    _resp, last_modified = await check_last_modified(request, key='weather_forecast')
    if _resp is not None:
        return _resp
    data = await get_forecast_context_data(request)
    data['include_json_data'] = True
    resp: web.Response = aiohttp_jinja2.render_template(
        'weather2/includes/weather-forecast.html',
        request=request,
        context=data,
    )
    resp.last_modified = last_modified
    return resp

@logger.catch(reraise=True)
async def init_app(app: web.Application):
    logger.debug('weather.init_app()')
    await get_geo_coords(app)
    tg = app[UPDATE_TASK_GROUP_KEY]
    keys = ['weather_data', 'weather_forecast']
    coros = [_fetch_weather_data, _fetch_forecast_data]
    for key, coro in zip(keys, coros):
        app_item, created = await get_or_create_app_item(app, key)
        await tg.add_task(app_item, update_coro=coro)
