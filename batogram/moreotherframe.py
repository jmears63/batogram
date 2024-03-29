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

from .graphsettings import GraphSettings, borderwidth, MULTICHANNEL_COMBINED_MODE, \
    MULTICHANNEL_SINGLE_MODE
from .morebncframe import ValidatingFrame
from .validatingwidgets import ValidatingFrameHelper, DoubleValidatingEntry, ValidatingCheckbutton, \
    ValidatingRadiobutton, IntegerValidatingEntry


class ValidatingLabelFrame(tk.LabelFrame, ValidatingFrameHelper):
    def __init__(self, parent, settings: GraphSettings, text: str = None):
        super().__init__(parent, text=text)
        ValidatingFrameHelper.__init__(self, parent, settings)


class OtherFrame(tk.Frame, ValidatingFrameHelper):
    """A Frame containing settings relating to spectrogram axis ranges."""

    def __init__(self, parent, button_frame, settings: GraphSettings, pad):
        super().__init__(parent, borderwidth=borderwidth)
        ValidatingFrameHelper.__init__(self, parent, settings)
        self._settings = settings

        multichannel_frame = tk.LabelFrame(self, text="Multichannel data")

        self._multichannel_mode_var = tk.IntVar(value=MULTICHANNEL_COMBINED_MODE)  # Note: can't be a local variable.
        self._combined_channel_radiobutton = ValidatingRadiobutton(multichannel_frame, button_frame, self,
                                                                   "Combine all",
                                                                   self._multichannel_mode_var,
                                                                   MULTICHANNEL_COMBINED_MODE)
        self._combined_channel_radiobutton.grid(row=0, column=0, sticky="W", padx=pad)

        # self._stereo_channel_radiobutton = ValidatingRadiobutton(multichannel_frame, button_frame, self, "Stereo",
        #                                                          self._multichannel_mode_var, MULTICHANNEL_STEREO_MODE)
        # self._stereo_channel_radiobutton.grid(row=1, column=0, sticky="W", padx=pad)

        self._selected_channel_radiobutton = ValidatingRadiobutton(multichannel_frame, button_frame, self, "Select one",
                                                                   self._multichannel_mode_var,
                                                                   MULTICHANNEL_SINGLE_MODE)
        self._selected_channel_radiobutton.grid(row=2, column=0, sticky="W", padx=pad)

        single_channel_frame = ValidatingFrame(multichannel_frame, settings)

        def channel_validator(v):
            return self.generic_value_validator(
                v, minimum_value=0, maximum_value=3, message="The channel must be in the range 0 to 3.")

        self._auto_label1 = tk.Label(single_channel_frame, text="Channel:", anchor=tk.W)
        self._auto_label1.grid(row=0, column=0, sticky="W")
        self._channel = IntegerValidatingEntry(single_channel_frame, button_frame, self, width=7,
                                               value_validator=channel_validator)
        self._channel.grid(row=0, column=1, sticky="W")

        self._combined_channel_radiobutton.register_dependent_widgets(
            lambda v: v == MULTICHANNEL_SINGLE_MODE, [self._channel, self._auto_label1])

        single_channel_frame.grid(row=3, column=0, padx=(40, pad), pady=(0, pad))

        multichannel_frame.grid(row=0, column=0)

        batgizmo_frame = tk.LabelFrame(self, text="BatGizmo Settings")
        self._frame_data_checkbutton = ValidatingCheckbutton(batgizmo_frame, button_frame, self, "Use frame data")
        self._frame_data_checkbutton.grid(row=0, column=0, padx=pad, sticky="W")
        batgizmo_frame.grid(row=0, column=1, sticky="NS", padx=pad)

        # misc_frame = tk.LabelFrame(self, text="Misc", text="Misc")
        misc_frame = ValidatingLabelFrame(self, settings, text="Misc")
        tk.Label(misc_frame, text="Sample rate:", anchor="e").grid(row=0, column=0, sticky="EW", padx=pad)
        tk.Label(misc_frame, text="Hz", anchor="w").grid(row=0, column=2, sticky="EW", padx=pad)

        permitted_range = 1000, 768000

        def sample_rate_validator(v): return self.generic_value_validator(
            v, minimum_value=permitted_range[0], maximum_value=permitted_range[1],
            message="The sample rate must be in the range {} to {}".format(*permitted_range))

        self._sample_rate = DoubleValidatingEntry(misc_frame, button_frame, self, width=7, decimal_places=1,
                                                  value_validator=sample_rate_validator)
        self._sample_rate.grid(row=0, column=1, padx=pad)

        misc_frame.grid(row=0, column=2, sticky="NS", padx=pad)

        self.copy_settings_to_widgets()

    def copy_settings_to_widgets(self):
        # Update the entry values from settings:
        self._combined_channel_radiobutton.set_value(self._settings.multichannel_mode)
        self._selected_channel_radiobutton.set_value(self._settings.multichannel_mode)
        # self._stereo_channel_radiobutton.set_value(self._settings.multichannel_mode)
        self._channel.set_value(self._settings.multichannel_channel)
        self._frame_data_checkbutton.set_value(self._settings.use_frame_data)
        self._sample_rate.set_value(self._settings.settings_sample_rate)

    def copy_widgets_to_settings(self):
        # Update the settings values from the UI:
        self._settings.multichannel_mode = self._combined_channel_radiobutton.get_value()
        self._settings.multichannel_channel = self._channel.get_value()
        self._settings.use_frame_data = self._frame_data_checkbutton.get_value()
        self._settings.settings_sample_rate = self._sample_rate.get_value()
