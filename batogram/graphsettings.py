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

from dataclasses import dataclass
from typing import Optional, NoReturn, Callable

from .common import AxisRange
from .frames import DrawableFrame

borderwidth = 10

SUPPORTED_FFT_SAMPLES = [64, 128, 256, 512, 1024, 2048, 4096, 8192]
DEFAULT_FFT_SAMPLES_INDEX = 3

ADAPTIVE_FFT_SAMPLES = -1  # Note that the range of auto values is defined elsewhere.
FFT_SAMPLES_OPTIONS = {ADAPTIVE_FFT_SAMPLES: "Auto",
                       64: "64", 128: "128", 256: "256",
                       512: "512", 1024: "1024", 2048: "2048", 4096: "4096"}
DEFAULT_FFT_SAMPLES = ADAPTIVE_FFT_SAMPLES
MAX_FFT_SAMPLES = 4096      # Must correspond to the maximum in the dictionary above.

# Note: quadratic interpolation seems a less CPU intensive way to get smoothness
# than a high overlap. So default overlap is not too high, and interpolation defaults to quadratic.

ADAPTIVE_FFT_OVERLAP_PERCENT = -1
FFT_OVERLAP_PERCENT_OPTIONS = {
    ADAPTIVE_FFT_OVERLAP_PERCENT: "Auto",
    0: "0", 25: "25", 50: "50", 75: "75", 90: "90", 95: "95"}
DEFAULT_FFT_OVERLAP_PERCENT = ADAPTIVE_FFT_OVERLAP_PERCENT

INTERPOLATION_OPTIONS = {0: "None", 1: "Linear", 2: "Quadratic", 3: "Cubic"}
DEFAULT_INTERPOLATION = 2       # Linear is fairly smooth and fairly fast,
                                # and avoids edge artifacts that quadratic generates.

# Note: boxcar window blows up in the calculations involving infinity
WINDOW_TYPE_OPTIONS = {"hann": "Hann", "hamming": "Hamming", "blackman": "Blackman", "tukey": "Tukey 0.5",
                       "bartlett": "Bartlett", "flattop": "Flat top", "boxcar": "Rectangular"}
                        # ("kaiser", 3): "Kaiser" is recommended in a paper but results in lots of spread.
DEFAULT_WINDOW_TYPE = "hann"

SPECTROGRAM_TYPE_STANDARD = 0
SPECTROGRAM_TYPE_REASSIGNMENT = 1
SPECTROGRAM_TYPE_ADAPTIVE = 2
SPECTROGRAM_TYPE_OPTIONS = {SPECTROGRAM_TYPE_STANDARD: "Standard",
                            SPECTROGRAM_TYPE_REASSIGNMENT: "Reassignment",
                            SPECTROGRAM_TYPE_ADAPTIVE: "Auto based on zoom"}
DEFAULT_SPECTROGRAM_TYPE = SPECTROGRAM_TYPE_STANDARD

DEFAULT_FFT_WINDOW_PADDING_FACTOR = 1
FFT_WINDOW_PADDING_FACTOR = {DEFAULT_FFT_WINDOW_PADDING_FACTOR: "1", 2: "2", 4: "4", 8: "8"}

BNC_ADAPTIVE_MODE = 0
BNC_MANUAL_MODE = 1
BNC_INTERACTIVE_MODE = 2

MULTICHANNEL_COMBINED_MODE = 0
# MULTICHANNEL_STEREO_MODE = 1
MULTICHANNEL_SINGLE_MODE = 2


@dataclass
class GraphSettings:
    """Settings relating to a specific graph panel."""
    time_range: Optional[AxisRange]
    zero_based_time: bool
    frequency_range: Optional[AxisRange]
    show_grid: bool
    show_profile: bool
    window_samples: int
    window_overlap: int
    window_type: str
    window_padding_factor: int
    zoom_interpolation: int
    colour_mapping_path: str
    colour_mapping_steps: int
    do_histogram_normalization: bool
    bnc_adjust_type: int
    bnc_background_threshold_percent: float
    bnc_manual_min: float  # bnc manual min and max are percentages of the data range.
    bnc_manual_max: float
    show_time_markers: bool
    show_frequency_markers: bool
    multichannel_mode: int
    multichannel_channel: int
    spectrogram_type: int

    def __init__(self,
                 on_app_modified_settings: Callable[[int], NoReturn],
                 on_user_applied_settings: Callable[[int], NoReturn],
                 show_profile=True):
        self.time_range = AxisRange(0, 1)
        self.zero_based_time = True
        self.frequency_range = AxisRange(0, 1)
        self._on_app_modified_settings: Callable[[int], NoReturn] = on_app_modified_settings  # Call this to signal that the UI needs to refresh.
        self._on_user_applied_settings: Callable[[int], NoReturn] = on_user_applied_settings  # Call this to signal that the application needs to refresh.
        self.show_grid = True
        self.show_profile = show_profile
        self.window_samples = DEFAULT_FFT_SAMPLES
        self.window_overlap = DEFAULT_FFT_OVERLAP_PERCENT
        self.window_type = DEFAULT_WINDOW_TYPE
        self.window_padding_factor = DEFAULT_FFT_WINDOW_PADDING_FACTOR
        self.zoom_interpolation = DEFAULT_INTERPOLATION
        self.do_histogram_normalization = False
        self.bnc_adjust_type = BNC_ADAPTIVE_MODE
        self.bnc_background_threshold_percent = 20.0
        self.bnc_manual_min, self.bnc_manual_max = 0.0, 1.0
        self.show_time_markers = False
        self.show_frequency_markers = False
        self.multichannel_mode = MULTICHANNEL_COMBINED_MODE
        self.multichannel_channel = 0
        self.spectrogram_type = SPECTROGRAM_TYPE_STANDARD

    def on_app_modified_settings(self, draw_scope: int = DrawableFrame.DRAW_ALL) -> NoReturn:
        """Signal to the settings UI that the underlying settings values have changed."""
        self._on_app_modified_settings(draw_scope)

    def on_user_applied_settings(self, draw_scope: int = DrawableFrame.DRAW_ALL) -> NoReturn:
        """Signal to the application that the underlying settings values have changed."""
        self._on_user_applied_settings(draw_scope)

    def on_open_new_file(self):
        # Always start with auto BnC, so that the manual range
        # gets initialized to something sensible:
        self.bnc_adjust_type = BNC_ADAPTIVE_MODE
        # Always start with markers disabled: any existing marker positions may be outside
        # the range of view:
        self.show_time_markers = False
        self.show_frequency_markers = False

        # Reset various things for the new file:
        self.spectrogram_type = SPECTROGRAM_TYPE_STANDARD
