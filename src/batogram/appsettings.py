import os
from dataclasses import dataclass
from dataclasses_json import Undefined, dataclass_json
from platformdirs import user_data_dir


# Ignore unknown values in the JSON, to help with compatibility:
@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass()
class AppSettings:
    colour_scale: str = "kindlmann-table-byte-1024.csv"
    data_path: str = "."

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
                self.from_json(s)
        except FileNotFoundError:
            pass    # There will be no such file the first time around.

    @staticmethod
    def _get_file_path():
        # Hard coded values so there are less likely to change by accident:
        d = user_data_dir("batogram", "fitzharrys")
        return "{}/appsettings.py".format(d)

