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

from .frames import DrawableFrame
from .renderingservice import GraphParams
from .graphsettings import WINDOW_TYPE_OPTIONS


class SettingsButton(tk.Button):
    """A Frame allowing the user to show or hide the settings for a given pane."""

    _SHOW_TEXT = "Show more"
    _HIDE_TEXT = "Show less"

    def __init__(self, parent):
        self._btn_text: tk.StringVar = tk.StringVar()
        super().__init__(parent, textvariable=self._btn_text)

    def update_button_appearance(self, is_shown: bool, other_shown: bool):
        if is_shown:
            self["state"] = tk.NORMAL
            self._btn_text.set(self._HIDE_TEXT)
        elif other_shown:
            self["state"] = tk.DISABLED
            self._btn_text.set(self._SHOW_TEXT)
        else:
            self["state"] = tk.NORMAL
            self._btn_text.set(self._SHOW_TEXT)


class ReadoutFrame(DrawableFrame):
    """A Frame containing data readout for a given pane."""

    def __init__(self, parent):
        super().__init__(parent)

        self._parent = parent

        self._settings_button: SettingsButton = SettingsButton(self)
        self._settings_button.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        self._parameters_variable = tk.StringVar(value="")
        self._parameters_label = tk.Label(self, textvariable=self._parameters_variable, width=40, anchor=tk.W)
        self._parameters_label.grid(row=0, column=1, sticky="nsew")

        self._coords_variable = tk.StringVar(value="")
        self._coords_label = tk.Label(self, textvariable=self._coords_variable, width=20, anchor=tk.E)
        self._coords_label.grid(row=0, column=2, sticky="nsew")

        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)

    def update_readout_coords(self, position, power):
        text = ""
        if position is not None:
            t, f = position
            text = "{:.4} s, {:.1f} kHz".format(t, f / 1000.0, power)
        if power is not None:
            text += ", {:.1f} dB".format(power)
        self._coords_variable.set(text)

    def update_graph_parameters(self, params: GraphParams):
        if params.specific_channel is None:
            if params.num_channels == 1:
                channel_text = "1 channel"
            else:
                channel_text = "{} channels combined".format(params.num_channels)
        else:
            channel_text = "channel {} only".format(params.specific_channel)

        self._parameters_variable.set("{} {}, {}% overlap, {}x window padding, {}".format(
            WINDOW_TYPE_OPTIONS[params.window_type], params.window_samples, params.window_overlap,
            params.window_padding_factor, channel_text))

    def get_settings_button(self) -> SettingsButton:
        return self._settings_button
