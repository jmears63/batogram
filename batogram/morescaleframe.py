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

import tkinter as tk

from .graphsettings import GraphSettings, borderwidth
from .validatingwidgets import ValidatingFrameHelper, DoubleValidatingEntry, ValidatingCheckbutton


class ScaleFrame(tk.Frame, ValidatingFrameHelper):
    """A Frame containing settings relating to spectrogram axis ranges."""

    # Decimal places:
    _TIME_DPS = 4
    _FREQUENCY_DPS = 1
    _FREQUENCY_SCALER = 1000

    def __init__(self, parent, controlling_frame, settings: GraphSettings, pad):
        super().__init__(parent, borderwidth=borderwidth)
        ValidatingFrameHelper.__init__(self, parent, settings)

        self._settings = settings

        tk.Label(self, text="min").grid(row=0, column=1)
        tk.Label(self, text="max").grid(row=0, column=2)

        tk.Label(self, text="Time:", anchor="e").grid(row=1, column=0, sticky="EW", padx=pad)
        tk.Label(self, text="s", anchor="e").grid(row=1, column=3, sticky="W")
        tk.Label(self, text="Frequency:", anchor="e").grid(row=2, column=0, sticky="EW", padx=pad)
        tk.Label(self, text="kHz", anchor="e").grid(row=2, column=3, sticky="W")

        width = 8

        def t_min_validator(v): return self.double_value_validator(v, minimum_value=0,
                                                                   message="The minimum time must be zero or positive.")

        self._t_min = DoubleValidatingEntry(self, controlling_frame, self, width=width, decimal_places=self._TIME_DPS,
                                            value_validator=t_min_validator)
        self._t_min.grid(row=1, column=1, padx=pad)

        def t_max_validator(v): return self.double_value_validator(v, minimum_entry=self._t_min,
                                                                   message="The maximum time must be greater than the minimum.")

        self._t_max = DoubleValidatingEntry(self, controlling_frame, self, width=width, decimal_places=self._TIME_DPS,
                                            value_validator=t_max_validator)
        self._t_max.grid(row=1, column=2, padx=pad)

        def f_min_validator(v): return self.double_value_validator(v, minimum_value=0,
                                                                   message="The minimum frequency must be zero or postive.")

        self._f_min = DoubleValidatingEntry(self, controlling_frame, self, width=width,
                                            decimal_places=self._FREQUENCY_DPS,
                                            scaler=self._FREQUENCY_SCALER, value_validator=f_min_validator)
        self._f_min.grid(row=2, column=1, padx=pad)

        def f_max_validator(v): return self.double_value_validator(v, minimum_entry=self._f_min,
                                                                   message="The maximum frequency must be greater than the minimum.")

        self._f_max = DoubleValidatingEntry(self, controlling_frame, self, width=width,
                                            decimal_places=self._FREQUENCY_DPS,
                                            scaler=self._FREQUENCY_SCALER, value_validator=f_max_validator)
        self._f_max.grid(row=2, column=2, padx=pad)

        self._show_grid_checkbutton = ValidatingCheckbutton(self, controlling_frame, self, "Show grid")
        self._show_grid_checkbutton.grid(row=1, column=4, padx=pad, sticky="W")

        self._zero_based_time_checkbutton = ValidatingCheckbutton(self, controlling_frame, self, "Zero based time")
        self._zero_based_time_checkbutton.grid(row=1, column=5, padx=pad, sticky="W")

        self._show_profile_checkbutton = ValidatingCheckbutton(self, controlling_frame, self, text="Show profile")
        self._show_profile_checkbutton.grid(row=2, column=4, padx=pad, sticky="W")

        self.copy_settings_to_widgets()

    def copy_settings_to_widgets(self):
        # Update the entry values from settings:
        self._t_max.set_value(self._settings.time_range.max)
        self._t_min.set_value(self._settings.time_range.min)
        self._f_max.set_value(self._settings.frequency_range.max)
        self._f_min.set_value(self._settings.frequency_range.min)
        self._show_grid_checkbutton.set_value(self._settings.show_grid)
        self._zero_based_time_checkbutton.set_value(self._settings.zero_based_time)
        self._show_profile_checkbutton.set_value(self._settings.show_profile)

    def copy_widgets_to_settings(self):
        # Update the settings values from the UI:
        self._settings.time_range.max = self._t_max.get_value()
        self._settings.time_range.min = self._t_min.get_value()
        self._settings.frequency_range.max = self._f_max.get_value()
        self._settings.frequency_range.min = self._f_min.get_value()
        self._settings.show_grid = self._show_grid_checkbutton.get_value()
        self._settings.zero_based_time = self._zero_based_time_checkbutton.get_value()
        self._settings.show_profile = self._show_profile_checkbutton.get_value()
