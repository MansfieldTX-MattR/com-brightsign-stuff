from typing import TypedDict, cast
from pathlib import Path
import importlib.resources
import shutil
from aiohttp import web
import jinja2
import click


PROJECT_ROOT = cast(Path, importlib.resources.files(__name__.split('.')[0]))

STATIC_URL_PREFIX = web.AppKey[str]('static_url_prefix')
STATIC_ROOT = PROJECT_ROOT
STATIC_DIRS = [STATIC_ROOT / s for s in ['meetings', 'weather2']]


class JinjaFilterContext(TypedDict):
    app: web.Application


@jinja2.pass_context
def static_filter(ctx: JinjaFilterContext, path: str) -> str:
    app = ctx['app']
    return get_static_url(app, path)

def get_static_url(app: web.Application, path: str) -> str:
    path = path.lstrip('/')
    prefix = app[STATIC_URL_PREFIX]
    return f'{prefix}/{path}'


def collectstatic(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    static_suffixes = [
        '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg',
        '.woff', '.woff2', '.ttf', '.eot', '.otf', '.ico',
    ]
    def iter_static_files(cur_dir: Path):
        for p in cur_dir.iterdir():
            if p.is_dir():
                yield from iter_static_files(p)
            else:
                if p.suffix in static_suffixes:
                    yield p

    for f in iter_static_files(STATIC_ROOT):
        dest_f = out_dir / f.relative_to(STATIC_ROOT)
        click.echo(f'cp {f} {dest_f}')
        dest_f.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dest_f)
