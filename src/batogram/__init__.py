import pathlib as pl
from . import constants as c

__version__: str = "1.0.4"


def get_asset_path(asset_file: str):
    return pl.Path(__file__).parent / pl.Path(c.ASSETS_PATH) / asset_file
