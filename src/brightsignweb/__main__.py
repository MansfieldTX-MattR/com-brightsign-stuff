import sys
from aiohttp import web

from .main import init_func

web.run_app(init_func(sys.argv))
