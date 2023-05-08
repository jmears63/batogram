import pathlib as pl
from . import constants as c

__version__: str = "1.0.7"


def get_asset_path(asset_file: str):
    return pl.Path(__file__).parent / pl.Path(c.ASSETS_PATH) / asset_file


def get_colour_map_path(map_file: str):
    return pl.Path(__file__).parent / pl.Path(c.COLOUR_MAPS_PATH) / map_file
