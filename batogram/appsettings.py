import os
from dataclasses import dataclass

from pathlib import Path

from dataclasses_json import Undefined, dataclass_json
from platformdirs import user_data_dir


DEFAULT_COLOUR_MAP = "Kindlmann *"

COLOUR_MAPS = {
    DEFAULT_COLOUR_MAP:         "kindlmann-table-byte-1024.csv",
    "Kindlmann (extended)":     "extended-kindlmann-table-byte-1024.csv",
    "Black body":               "black-body-table-byte-1024.csv",
    "Inferno":                  "inferno-table-byte-1024.csv",
    "Greyscale":                "CET-L01.csv",
    "Black-Red-Yellow-White *":   "CET-L03.csv",
    "Green":                    "CET-L05.csv",
    "Blue":                     "CET-L06.csv",
    "Blue-Pink-Light Pink":     "CET-L07.csv",
    "Blue-Magenta-Yellow":      "CET-L08.csv",
    "Blue-Green-Yellow":        "CET-L09.csv",
    "Black-Blue-Green-Yellow-White": "CET-L16.csv",
    "White-Orange-Red-Blue *":    "CET-L17.csv",
    "White-Yellow-Orange-Red":  "CET-L18.csv",
    "White-Cyan-Magenta-Red":   "CET-L19.csv",
    "Black-Blue-Green-Orange-Yellow": "CET-L20.csv",
}


# Ignore unknown values in the JSON, to help with compatibility:
@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass()
class AppSettings:
    colour_map: str = DEFAULT_COLOUR_MAP
    data_directory: str = str(Path.home())
    # Remember to add new attributes to the _copy_other method.

    def write(self):
        path = self._get_file_path()
        s = self.to_json()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(s)

    def read(self):
        try:
            path = self._get_file_path()
            with open(path, "r") as f:
                s = f.read()
                file_settings: AppSettings = self.from_json(s)
                # Validate some values:
                if file_settings.colour_map not in COLOUR_MAPS:
                    file_settings.colour_map = DEFAULT_COLOUR_MAP

                # Surely there is a neater way to do this?
                self._copy_other(file_settings)

        except FileNotFoundError:
            pass    # There will be no such file the first time around.

    @staticmethod
    def _get_file_path():
        # Hard coded values so there are less likely to change by accident:
        d = user_data_dir("batogram", "fitzharrys")
        return "{}/appsettings.json".format(d)

    def _copy_other(self, other: "AppSettings"):
        self.colour_map = other.colour_map
        self.data_directory = other.data_directory


# The single global instance of this class:
instance: "AppSettings" = AppSettings()

