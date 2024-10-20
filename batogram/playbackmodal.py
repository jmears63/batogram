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
from enum import Enum, IntEnum
from tkinter import filedialog, messagebox
from typing import List, Callable, Literal, Optional

from pathlib import Path

from batogram.appsettings import AppSettingsWrapper
from batogram.modalwindow import ModalWindow

DEFAULT_TD_MAP = "8x"
TD_MAP = {"4x": 4, DEFAULT_TD_MAP: 8, "12x": 12, "16x": 16, "20x": 20, "24x": 24}
TD_INVERSE_MAP = {v: k for k, v in TD_MAP.items()}


class PlaybackMethod(IntEnum):
    PLAYBACK_HETERODYNE_METHOD = 0
    PLAYBACK_TD_METHOD = 1
    PLAYBACK_DIRECT_METHOD = 2


class PlaybackSettings:
    method: int = PlaybackMethod.PLAYBACK_HETERODYNE_METHOD.value
    reference_khz: int = int(50)
    td_factor: int = TD_MAP[DEFAULT_TD_MAP]
    repeat: bool = False
    autoscale: bool = True
    write_to_file: bool = False
    file_name: Optional[str] = None
    settings_sample_rate: int       # A hidden setting that we use to pass a value through from the main settings.


class TDOptionMenu(tk.OptionMenu):
    def __init__(self, parent, var):
        # Sort by integer values, but populate with the corresponding strings:
        options = [TD_INVERSE_MAP[i] for i in sorted(list(TD_INVERSE_MAP.keys()))]
        super().__init__(parent, var, *options)


class PlaybackModal(ModalWindow):
    def __init__(self, parent, playback_settings: PlaybackSettings, on_ok: Callable):
        super().__init__(parent)
        self._playback_settings: PlaybackSettings = playback_settings
        self._on_ok = on_ok

        self.title("Playback")

        self._method_var = tk.IntVar()
        self._reference_var: tk.StringVar = tk.StringVar()
        self._repeat_var: tk.IntVar = tk.IntVar()
        self._td_factor_var: tk.StringVar = tk.StringVar()
        self._autoscale_var: tk.IntVar = tk.IntVar()
        self._file_var: tk.IntVar = tk.IntVar()

        registered_reference_validator = self.register(self._is_valid_reference)

        pad = 5
        margin = 30
        button_width = 7

        settings_frame = tk.Frame(self)

        self._heterodyne_radiobutton = tk.Radiobutton(settings_frame, text="Heterodyne", variable=self._method_var,
                                                      value=PlaybackMethod.PLAYBACK_HETERODYNE_METHOD.value)
        self._heterodyne_radiobutton.grid(row=0, column=0, sticky="W")

        self._heterodyne_label1 = tk.Label(settings_frame, text="Reference:", anchor=tk.W)
        self._heterodyne_label1.grid(row=0, column=1, sticky="W")
        self._reference_entry = tk.Entry(settings_frame, width=7, textvariable=self._reference_var,
                                         validate='all',
                                         validatecommand=(registered_reference_validator, '%d', '%P'))
        self._reference_entry.grid(row=0, column=2, sticky="W")
        self._heterodyne_label2 = tk.Label(settings_frame, text="kHz", anchor="e")
        self._heterodyne_label2.grid(row=0, column=3, sticky="W")

        self._td_radiobutton = tk.Radiobutton(settings_frame, text="Time Division", variable=self._method_var,
                                              value=PlaybackMethod.PLAYBACK_TD_METHOD.value)
        self._td_radiobutton.grid(row=1, column=0, sticky="W")

        self._td_label1 = tk.Label(settings_frame, text="Factor:", anchor=tk.W)
        self._td_label1.grid(row=1, column=1, sticky="W")
        self._factor_listbox = TDOptionMenu(settings_frame, self._td_factor_var)
        self._factor_listbox.grid(row=1, column=2, sticky="W")
        self._td_label2 = tk.Label(settings_frame, text="", anchor="e")
        self._td_label2.grid(row=1, column=3, sticky="W")

        self._direct_radiobutton = tk.Radiobutton(settings_frame, text="Direct", variable=self._method_var,
                                                  value=PlaybackMethod.PLAYBACK_DIRECT_METHOD.value)

        self._direct_radiobutton.grid(row=2, column=0, sticky="W")

        self._repeat_cb = tk.Checkbutton(settings_frame, text="Repeat", variable=self._repeat_var)
        self._repeat_cb.grid(row=3, column=0, sticky="W")

        self._repeat_cb = tk.Checkbutton(settings_frame, text="Auto volume control", variable=self._autoscale_var)
        self._repeat_cb.grid(row=3, column=1, sticky="W")

        self._file_cb = tk.Checkbutton(settings_frame, text="Write to file", variable=self._file_var)
        self._file_cb.grid(row=4, column=0, sticky="W")

        settings_frame.rowconfigure(0, weight=0, pad=pad)
        settings_frame.rowconfigure(1, weight=0, pad=pad)
        settings_frame.rowconfigure(2, weight=0, pad=pad)
        settings_frame.rowconfigure(3, weight=0, pad=pad * 5)
        settings_frame.columnconfigure(0, pad=margin)
        settings_frame.grid(row=0, column=0)

        okcancel_frame = tk.Frame(self)
        btn = tk.Button(okcancel_frame, text="Play", underline=0, width=button_width, command=self.on_ok)
        self.bind('p', lambda event: self.on_ok())
        btn.grid(row=0, column=1, padx=pad, pady=pad)

        btn = tk.Button(okcancel_frame, text="Cancel", underline=0, width=button_width, command=self.on_cancel)
        self.bind('c', lambda event: self.on_cancel())
        btn.grid(row=0, column=3, padx=pad, pady=pad)

        okcancel_frame.columnconfigure(0, weight=1)
        okcancel_frame.grid(row=1, column=0, sticky=tk.EW)

        self.rowconfigure(0, weight=1, pad=margin)
        self.rowconfigure(1, weight=0, pad=margin)
        self.columnconfigure(0, weight=1, pad=margin)

        self.data_directory_var = tk.StringVar()

        self._method_var.trace("w", self._on_method_selected)
        self._settings_to_vars()

    def _is_valid_reference(self, action: str, result):
        if int(action) == 1:        # Inserting a character
            try:
                _ = int(result)
                return True
            except ValueError as e:
                return False

        return True

    @staticmethod
    def _state_literal(enabled: bool) -> Literal["normal", "active", "disabled"]:
        return "normal" if enabled else "disabled"  # Don't know why type hints wanrs.

    def _on_method_selected(self, *args):
        selected: int = self._method_var.get()
        self._heterodyne_label1.configure(
            state=self._state_literal(selected == PlaybackMethod.PLAYBACK_HETERODYNE_METHOD.value))
        self._reference_entry.configure(
            state=self._state_literal(selected == PlaybackMethod.PLAYBACK_HETERODYNE_METHOD.value))
        self._heterodyne_label2.configure(
            state=self._state_literal(selected == PlaybackMethod.PLAYBACK_HETERODYNE_METHOD.value))

        self._td_label1.configure(state=self._state_literal(selected == PlaybackMethod.PLAYBACK_TD_METHOD.value))
        self._factor_listbox.configure(state=self._state_literal(selected == PlaybackMethod.PLAYBACK_TD_METHOD.value))
        self._td_label2.configure(state=self._state_literal(selected == PlaybackMethod.PLAYBACK_TD_METHOD.value))

    def on_ok(self):
        # Basic validation:
        try:
            reference = int(self._reference_var.get())
        except BaseException as e:
            messagebox.showerror(title="Error", message=e, parent=self)
            return

        allowed = 10, 150
        if not allowed[0] <= int(self._reference_var.get()) <= allowed[1]:
            messagebox.showerror(title="Error",
                                 message="The heterodyne frequency must be in the range {} to {}."
                                 .format(allowed[0], allowed[1]),
                                 parent=self)
            return

        self._vars_to_settings()
        self._on_ok()
        super().on_ok()

    def _settings_to_vars(self):
        self._method_var.set(self._playback_settings.method)
        self._reference_var.set(str(self._playback_settings.reference_khz))
        self._repeat_var.set(1 if self._playback_settings.repeat else 0)
        self._td_factor_var.set(TD_INVERSE_MAP[self._playback_settings.td_factor])
        self._autoscale_var.set(1 if self._playback_settings.autoscale else 0)
        self._file_var.set(1 if self._playback_settings.write_to_file else 0)

    def _vars_to_settings(self):
        self._playback_settings.method = self._method_var.get()
        self._playback_settings.reference_khz = int(self._reference_var.get())
        self._playback_settings.repeat = False if self._repeat_var.get() == 0 else True
        self._playback_settings.td_factor = TD_MAP[self._td_factor_var.get()]
        self._playback_settings.autoscale = False if self._autoscale_var.get() == 0 else True
        self._playback_settings.write_to_file = False if self._file_var.get() == 0 else True
