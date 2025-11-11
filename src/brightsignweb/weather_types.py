from __future__ import annotations
from typing import TypedDict, NotRequired, Unpack, Literal

__all__ = (
    'WeatherConditionName', 'WeatherConditionCodeBase', 'WeatherConditionCode',
    'WeatherCondition', 'WeatherDataSrc', 'WeatherData', 'WeatherForecastSrc',
    'WeatherForecast', 'ForecastItemSrc', 'ForecastItem', 'NowWeatherSrc',
    'NowWeather', 'DailyForecastItem', 'Coord',
)


type InternalParam[T] = T

type WeatherConditionName = Literal[
    'Thunderstorm', 'Drizzle', 'Rain', 'Snow',
    'Atmosphere', 'Clear', 'Clouds'
]


class WeatherConditionCodeBase(TypedDict):
    """Weather condition code information from the OpenWeatherMap API"""
    desc: str                       #: Description of the weather condition
    icon: NotRequired[str]          #: Icon ID
    meteocon: NotRequired[str]      #: Meteocon icon ID


class WeatherConditionCode(WeatherConditionCodeBase):
    """Weather condition code information with additional fields"""
    id: int                         #: Weather condition code ID
    group_name: str                 #: Group name (e.g., 'Clear', 'Clouds', 'Rain', etc.)
    icon: str                       #: Icon ID
    meteocon: str                   #: Meteocon icon ID


class WeatherCondition[T: (WeatherConditionCodeBase, WeatherConditionCode)](TypedDict):
    """Mapping of weather condition codes to their information"""
    default_icon: str               #: Default icon ID
    meteocon: str                   #: Default Meteocon icon ID
    codes: dict[int, T]             #: Mapping of weather condition codes to their information




class Coord(TypedDict):
    """Coordinate information."""
    lon: float #: Longitude
    lat: float #: Latitude


class NowWeatherSrc(TypedDict):
    """Current weather information from the OpenWeatherMap API"""
    id: int                     #: Weather condition id
    main: str                   #: Group of weather parameters (Rain, Snow, Extreme etc.)
    description: str            #: Weather condition within the group
    icon: str                   #: Weather icon id


class _NowWeatherExtra(TypedDict):
    desc: str
    metocon: str
    group_name: str

class NowWeather(NowWeatherSrc):
    """Current weather information with additional fields"""
    desc: str                   #: Additional description
    metocon: str                #: Metocon icon url
    group_name: str             #: Group name (e.g., 'Clear', 'Clouds', 'Rain', etc.)


def now_weather_from_src(data: NowWeatherSrc, **kwargs: Unpack[_NowWeatherExtra]) -> NowWeather:
    """Convert :class:`NowWeatherSrc` to :class:`NowWeather` by injecting additional fields."""
    return NowWeather(
        **data,
        **kwargs,
    )


class WMain(TypedDict):
    """Main weather parameters"""
    temp: float                 #: Current temperature
    feels_like: float           #: Temperature accounting for human perception
    temp_min: float             #: Minimum temperature at the moment
    temp_max: float             #: Maximum temperature at the moment
    pressure: float             #: Atmospheric pressure
    humidity: float             #: Humidity percentage
    sea_level: float            #: Atmospheric pressure at sea level
    grnd_level: float           #: Atmospheric pressure at ground level
    temp_kf: NotRequired[float] #: Temperature correction factor


class Wind(TypedDict):
    """Wind information"""
    speed: float                #: Wind speed
    deg: int                    #: Wind direction
    gust: NotRequired[float]    #: Wind gusts


class WSys(TypedDict):
    """System information"""
    type: InternalParam[int]    #: Internal parameter
    id: InternalParam[int]      #: Internal parameter
    country: str                #: Country code
    sunrise: int                #: Sunrise time (unix timestamp)
    sunset: int                 #: Sunset time (unix timestamp)


class Clouds(TypedDict):
    """Cloudiness information"""
    all: int                    #: Cloudiness percentage


class WeatherDataBase[T: (NowWeatherSrc, NowWeather)](TypedDict):
    """Current weather data base class"""
    coord: Coord                #: Coordinate information
    weather: list[T]            #: List of weather conditions
    base: InternalParam[Literal['stations']]
    main: WMain                 #: Main weather parameters
    visibility: int             #: Visibility in meters
    wind: Wind                  #: Wind information
    clouds: Clouds              #: Cloudiness information
    dt: float                   #: Data calculation time
    sys: WSys                   #: System information
    timezone: int               #: Timezone offset in seconds
    id: int                     #: City ID
    name: str                   #: City name
    cod: InternalParam[int]     #: Response code


class WeatherDataSrc(WeatherDataBase[NowWeatherSrc]):
    """Current weather data from the OpenWeatherMap API"""
    pass


class WeatherData(WeatherDataBase[NowWeather]):
    """Current weather data with additional fields"""
    next_update_iso: NotRequired[str]       #: Next update time in ISO format


def weather_data_from_src(data: WeatherDataSrc, weather: list[NowWeather]) -> WeatherData:
    """Convert :class:`WeatherDataSrc` to :class:`WeatherData` by injecting additional weather fields."""
    return WeatherData(
        coord=data['coord'],
        weather=weather,
        base=data['base'],
        main=data['main'],
        visibility=data['visibility'],
        wind=data['wind'],
        clouds=data['clouds'],
        dt=data['dt'],
        sys=data['sys'],
        timezone=data['timezone'],
        id=data['id'],
        name=data['name'],
        cod=data['cod'],
    )



class ForecastSys(TypedDict):
    """Forecast system information"""
    pod: str                    #: Part of the day (n: night, d: day)


class ForecastCity(TypedDict):
    """Forecast city information"""
    id: int                     #: City ID
    name: str                   #: City name
    coord: Coord                #: Coordinate information
    country: str                #: Country code
    population: int             #: City population
    timezone: int               #: Timezone offset in seconds
    sunrise: int                #: Sunrise time (unix timestamp)
    sunset: int                 #: Sunset time (unix timestamp)


class ForecastItemBase[T](TypedDict):
    """Forecast item information base class"""
    dt: int                                         #: Forecast time (unix timestamp)
    main: WMain                                     #: Main weather parameters
    weather: T                                      #: List of weather conditions
    clouds: Clouds                                  #: Cloudiness information
    wind: Wind                                      #: Wind information
    visibility: int                                 #: Visibility in meters
    pop: float                                      #: Probability of precipitation
    sys: dict[Literal['pod'], Literal['n', 'd']]    #: Part of the day (n: night, d: day)
    dt_txt: str                                     #: Date and time in text format
    rain: NotRequired[dict[Literal['3h'], float]]   #: Rain volume for the last 3 hours
    snow: NotRequired[dict[Literal['3h'], float]]   #: Snow volume for the last 3 hours


class ForecastItemSrc(ForecastItemBase[list[NowWeatherSrc]]):
    """Forecast item information from the OpenWeatherMap API"""
    pop: float                                     #: Probability of precipitation


class ForecastItem(ForecastItemBase[list[NowWeather]]):
    """Forecast item information"""
    pop: float                                     #: Probability of precipitation


class DailyForecastItem(ForecastItem):
    """Daily forecast item information with additional fields"""
    day_short: str                  #: Short day string (e.g., 'Mon', 'Tue', etc.)
    day_full: str                   #: Full day string (e.g., 'Monday', 'Tuesday', etc.)


def forecast_item_from_src(forecast_item: ForecastItemSrc, weather: list[NowWeather]) -> ForecastItem:
    """Convert :class:`ForecastItemSrc` to :class:`ForecastItem` with additional weather fields"""
    return ForecastItem(
        dt=forecast_item['dt'],
        main=forecast_item['main'],
        weather=weather,
        clouds=forecast_item['clouds'],
        wind=forecast_item['wind'],
        visibility=forecast_item['visibility'],
        pop=forecast_item['pop'],
        sys=forecast_item['sys'],
        dt_txt=forecast_item['dt_txt'],
        rain=forecast_item.get('rain', {}),
        snow=forecast_item.get('snow', {}),
    )


class WeatherForecastBase(TypedDict):
    """Daily (5-day, 3-hour) weather forecast data base class"""
    cod: InternalParam[str]         #: Response code
    message: InternalParam[int]     #: Response message
    cnt: int                        #: Number of forecast items
    city: ForecastCity              #: City information


class WeatherForecastSrc[T: (ForecastItemSrc | ForecastItem)](WeatherForecastBase):
    """Weather forecast data from the OpenWeatherMap API"""
    list: list[T]                   #: List of forecast items


def weather_forecast_src_from_items[T: (ForecastItemSrc|ForecastItem)](
    forecast: WeatherForecastBase,
    items: list[T]
) -> WeatherForecastSrc[T]:
    """Convert :class:`WeatherForecastBase` and items to :class:`WeatherForecastSrc`

    The *items* may be either :class:`ForecastItemSrc` or :class:`ForecastItem`
    and will be assigned to the :attr:`WeatherForecastSrc.list` attribute.

    .. note::

        This is mainly a helper function to make type checking a bit easier.

    """
    return WeatherForecastSrc(
        cod=forecast['cod'],
        message=forecast['message'],
        cnt=forecast['cnt'],
        city=forecast['city'],
        list=items
    )

class WeatherForecast(WeatherForecastBase):
    """Weather forecast data with additional fields"""
    dt: float                           #: Data calculation time
    daily: list[DailyForecastItem]      #: List of daily forecast items
    next_update_iso: NotRequired[str]   #: Next update time in ISO format


def weather_forecast_from_src(
    forecast: WeatherForecastSrc,
    dt: float,
    daily: list[DailyForecastItem],
) -> WeatherForecast:
    """Convert :class:`WeatherForecastSrc` to :class:`WeatherForecast`"""
    return WeatherForecast(
        cod=forecast['cod'],
        message=forecast['message'],
        cnt=forecast['cnt'],
        city=forecast['city'],
        dt=dt,
        daily=daily,
    )
