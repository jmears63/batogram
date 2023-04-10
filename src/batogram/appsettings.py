import os
from dataclasses import dataclass
from pathlib import Path

from dataclasses_json import Undefined, dataclass_json
from platformdirs import user_data_dir


# Ignore unknown values in the JSON, to help with compatibility:
@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass()
class AppSettings:
    colour_scale: str = "kindlmann-table-byte-1024.csv"
    data_directory: str = Path.home()
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
                file_settings = self.from_json(s)
                # Surely there is a neater way to do this?
                self._copy_other(file_settings)

        except FileNotFoundError:
            pass    # There will be no such file the first time around.

    @staticmethod
    def _get_file_path():
        # Hard coded values so there are less likely to change by accident:
        d = user_data_dir("batogram", "fitzharrys")
        return "{}/appsettings.py".format(d)

    def _copy_other(self, other: "AppSettings"):
        self.colour_scale = other.colour_scale
        self.data_directory = other.data_directory


