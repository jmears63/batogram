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

import math
import tkinter as tk

from .graphsettings import FFT_SAMPLES_OPTIONS, FFT_OVERLAP_PERCENT_OPTIONS, INTERPOLATION_OPTIONS, WINDOW_TYPE_OPTIONS, \
    borderwidth, GraphSettings
from .validatingwidgets import ValidatingMapOptionMenu, ValidatingFrameHelper


class FFTSamplesOptionMenu(ValidatingMapOptionMenu):
    """A drop down menu listing available number of samples per FFT segment."""

    def __init__(self, parent, controlling_frame, container, value_validator=None):
        super().__init__(parent, controlling_frame, container, FFT_SAMPLES_OPTIONS, value_validator)


class FFTOverlapOptionMenu(ValidatingMapOptionMenu):
    """A drop down menu listing available overlaps between FFT segments."""

    def __init__(self, parent, controlling_frame, container, value_validator=None):
        super().__init__(parent, controlling_frame, container, FFT_OVERLAP_PERCENT_OPTIONS, value_validator)


class InterpolationOptionMenu(ValidatingMapOptionMenu):
    """A drop down menu listing available interpolation orders."""
    def __init__(self, parent, controlling_frame, container, value_validator=None):
        super().__init__(parent, controlling_frame, container, INTERPOLATION_OPTIONS, value_validator)


class WindowTypeOptionMenu(ValidatingMapOptionMenu):
    """A drop down menu listing available FFT window types."""
    def __init__(self, parent, controlling_frame, container, value_validator=None):
        super().__init__(parent, controlling_frame, container, WINDOW_TYPE_OPTIONS, value_validator)


class RenderingFrame(tk.Frame, ValidatingFrameHelper):
    """A Frame containing settings relating to rendering the spectrogram."""

    def __init__(self, parent, controlling_frame, settings: GraphSettings, pad):
        super().__init__(parent, borderwidth=borderwidth)
        ValidatingFrameHelper.__init__(self, parent, settings)

        self._settings = settings

        tk.Label(self, text="FFT samples:", anchor="e", padx=pad).grid(row=0, column=0, sticky="EW")
        tk.Label(self, text="FFT overlap:", anchor="e", padx=pad).grid(row=1, column=0, sticky="EW")
        tk.Label(self, text="Window type:", anchor="e", padx=pad).grid(row=0, column=3, sticky="EW")
        tk.Label(self, text="Image interpolation:", anchor="e", padx=pad).grid(row=1, column=3, sticky="EW")

        tk.Label(self, text="%", anchor="e", padx=pad).grid(row=1, column=2, sticky="EW")

        def fft_samples_validator(v):
            log_v = math.log2(v)
            valid = log_v == int(log_v)
            return "FFT sample number must be a power of 2" if not valid else None

        self._samples_listbox = FFTSamplesOptionMenu(self, controlling_frame, self,
                                                     value_validator=fft_samples_validator)
        self._samples_listbox.grid(row=0, column=1, sticky="EW")

        self._overlap_listbox = FFTOverlapOptionMenu(self, controlling_frame, self)
        self._overlap_listbox.grid(row=1, column=1, sticky="EW")

        self._window_type_listbox = WindowTypeOptionMenu(self, controlling_frame, self)
        self._window_type_listbox.grid(row=0, column=4, sticky="EW")

        self._interpolation_order_listbox = InterpolationOptionMenu(self, controlling_frame, self)
        self._interpolation_order_listbox.grid(row=1, column=4, sticky="EW")

        self.copy_settings_to_widgets()

    def copy_settings_to_widgets(self):
        self._samples_listbox.set_value(self._settings.fft_samples)
        self._overlap_listbox.set_value(self._settings.fft_overlap)
        self._window_type_listbox.set_value(self._settings.window_type)
        self._interpolation_order_listbox.set_value(self._settings.zoom_interpolation)

    def copy_widgets_to_settings(self):
        self._settings.fft_samples = self._samples_listbox.get_value()
        self._settings.fft_overlap = self._overlap_listbox.get_value()
        self._settings.window_type = self._window_type_listbox.get_value()
        self._settings.zoom_interpolation = self._interpolation_order_listbox.get_value()
