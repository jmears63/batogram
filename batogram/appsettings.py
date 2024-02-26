# Copyright (c) 2023 John Mears
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
from typing import Tuple, Optional

import numpy as np

from dataclasses import dataclass
from pathlib import Path
from dataclasses_json import Undefined, dataclass_json
from platformdirs import user_data_dir
from scipy.interpolate import CubicSpline

DEFAULT_COLOUR_MAP = "Kindlmann *"

TD_MAPS = {
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
    main_mic_response_path: str = ""
    ref_mic_response_path: str = ""
    serial_number: int = 0

    def _copy_other(self, other: "AppSettings"):
        # Could we use deep_copy for this?
        self.colour_map = other.colour_map
        self.data_directory = other.data_directory
        self.main_mic_response_path = other.main_mic_response_path
        self.ref_mic_response_path = other.ref_mic_response_path
        self.serial_number += 1


class AppSettingsWrapper(AppSettings):
    """Subclass the data class, so we can have ephemeral fields that aren't streamed as
    JSON etc"""
    main_mic_response_data: Optional[Tuple[CubicSpline, float, float, float, float]]
    ref_mic_response_data: Optional[Tuple[CubicSpline, float, float, float, float]]

    def __init__(self, *args, **nargs):
        super().__init__(*args, **nargs)
        self._reset()

    def write(self):
        path = self._get_file_path()
        s = self.to_json()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(s)

    def read(self):
        self._reset()
        try:
            path = self._get_file_path()
            with open(path, "r") as f:
                s = f.read()
                file_settings: AppSettings = self.from_json(s)
                # Validate some values:
                if file_settings.colour_map not in TD_MAPS:
                    file_settings.colour_map = DEFAULT_COLOUR_MAP

                # Surely there is a neater way to do this?
                self._copy_other(file_settings)

                self.main_mic_response_data = self._read_response_file_data(self.main_mic_response_path)
                self.ref_mic_response_data = self._read_response_file_data(self.ref_mic_response_path)

        except FileNotFoundError:
            pass    # There will be no settings file the first time around.

    def _read_response_file_data(self, path: str):
        if path is not None and path != "":
            try:
                return self._read_mic_response_data(path)
            except BaseException as e:
                print("Unable to read data from {}: {}".format(path, str(e)))
                return None

    def _reset(self):
        self.main_mic_response_data = None
        self.ref_main_mic_response_data = None

    @staticmethod
    def _get_file_path():
        # Hard coded values so there are less likely to change by accident:
        d = user_data_dir("batogram", "fitzharrys")
        return "{}/appsettings.json".format(d)

    def set_main_mic_response_file(self, file: Optional[str]):
        """Attempt to read and parse the file contents, and assign the field if
        it succeeds. If the file is bad, a ValueError or FileNotFound is thrown."""

        self.main_mic_response_path = ""
        self.main_mic_response_data = None

        if file is None or file == "":
            self.main_mic_response_data = None
            self.main_mic_response_path = ""
        else:
            self.main_mic_response_data = self._read_mic_response_data(file)      # Raises an exception if the file is no good.
            self.main_mic_response_path = file

    def set_ref_mic_response_file(self, file: Optional[str]):
        """Attempt to read and parse the file contents, and assign the field if
        it succeeds. If the file is bad, a ValueError or FileNotFound is thrown."""

        self.ref_mic_response_path = ""
        self.ref_mic_response_data = None

        if file is None or file == "":
            self.ref_mic_response_data = None
            self.ref_mic_response_path = ""
        else:
            self.ref_mic_response_data = self._read_mic_response_data(file)      # Raises an exception if the file is no good.
            self.ref_mic_response_path = file

    @staticmethod
    def _read_mic_response_data(file) -> Tuple[CubicSpline, float, float, float, float]:
        # ValueError raised if the file format is bad:
        # print("_read_mic_response_data({})".format(file))
        data: np.ndarray = np.loadtxt(file, delimiter=',', dtype=float)

        # Sanity checking:
        if len(data.shape) != 2 or data.shape[1] < 1:
            raise ValueError("Invalid file format")

        # Make sure it is ascending by frequency:
        sorted_data = data[np.argsort(data[:, 0])]

        # Calculate a cubic spline for use during rendering:
        transposed_data = np.transpose(sorted_data)
        response_frequencies = transposed_data[0]
        response_values = transposed_data[1]
        cs = CubicSpline(response_frequencies, response_values)
        return cs, response_frequencies[0], response_frequencies[-1], response_values[0], response_values[-1]


# The single global instance of this class:
instance: AppSettingsWrapper = AppSettingsWrapper()
