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

import numpy as np
import pathlib as pl


class ColourMap:
    """The colour map is used to render spectrograms in the UI."""

    def __init__(self):
        self._cmap = None
        self._num_steps: int | None = None

    def load_map(self, colour_mapping_path: pl.Path):
        """Read a colour map from a CSV with four columns like this:
            0.0,0,0,0
            0.0009775171065493646,1,0,1
            ...
            0.9990224828934506,255,255,255
            1.0,255,255,255
        """

        raw_cmap = np.genfromtxt(colour_mapping_path, delimiter=',', dtype=np.uint8)  # Rows are: value, R, G, B
        # The first column is not required, the remaining 3 are RGB:
        self._cmap = np.delete(raw_cmap, 0, axis=1)
        self._num_steps = len(self._cmap)

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
