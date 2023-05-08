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
from typing import Optional

import numpy as np

from . import get_colour_map_path
from .appsettings import COLOUR_MAPS, DEFAULT_COLOUR_MAP


class ColourMap:
    """The colour map is used to render spectrograms in the UI."""

    def __init__(self, map_file: str):
        """
        Don't use this to create instances, instead access
        the single shared instance using get_instance().
        """

        self._cmap = None
        self._num_steps: Optional[int] = None
        self._polyfilla_colour: Optional[str] = None

        self.reload_map(map_file)

    def reload_map(self, map_file: str):
        """
            Read a colour map from a CSV with thee or four columns. The last three columns
            are RGB byte values.
            NB remove the initial row of column headers from files, if present.
        """

        colour_mapping_path = get_colour_map_path(map_file)
        raw_cmap: np.ndarray = np.genfromtxt(colour_mapping_path, delimiter=',', dtype=np.uint8)

        # Some formats have the value in the first column, which is not required:
        if raw_cmap.shape[1] == 4:
            raw_cmap = np.delete(raw_cmap, 0, axis=1)
        self._cmap = raw_cmap
        self._num_steps = len(self._cmap)

        # Calculate the "lowest" colour as a string:
        entry = self._cmap[0]
        self._polyfilla_colour = "#{:02X}{:02X}{:02X}".format(*entry)

    def map(self, inputdata: np.ndarray) -> np.ndarray:
        """Replace each value in the input with an (RGB) tuple.
        The input data values must be in the range 0-1."""

        # Create a new array for the output data, the same shape as the input data:
        outputdata = np.zeros((*inputdata.shape, 3), dtype=np.uint8)  # Allow for RGB layers.
        # Do the mapping: each value in inputdata is replaced with an RGB from
        # cmap, according the input value.

        # ‘clip’ mode means that all indices that are too large are replaced by the index that addresses the last
        # element along that axis. Note that this disables indexing with negative numbers.

        inputdata = (inputdata * self._num_steps).astype(int)
        np.take(self._cmap, inputdata, axis=0, mode='clip', out=outputdata)

        return outputdata

    def get_polyfilla_colour(self) -> str:
        """Get the 'lowest' colour of the spectrum to be used for filling awkward gaps."""
        return self._polyfilla_colour


# The single global instance of the colour map:
instance: ColourMap = ColourMap(COLOUR_MAPS[DEFAULT_COLOUR_MAP])
