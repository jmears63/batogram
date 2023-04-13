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
from tkinter import filedialog
from typing import List, Callable

from pathlib import Path

from batogram import colourmap
from batogram.appsettings import AppSettings, COLOUR_MAPS, DEFAULT_COLOUR_MAP
from batogram.modalwindow import ModalWindow


class ColourMapOptionMenu(tk.OptionMenu):
    def __init__(self, parent, var):
        options: List[str] = list(COLOUR_MAPS.keys())
        options.sort()
        # Force the preselect value to be valid. Perhaps an obselete value
        # was stored in JSON?
        if var.get() not in options:
            var.set(DEFAULT_COLOUR_MAP)
        super().__init__(parent, var, *options)


class AppSettingsWindow(ModalWindow):
    def __init__(self, parent, app_settings: AppSettings, apply_updates: Callable):
        super().__init__(parent)
        self._app_settings: AppSettings = app_settings
        self._apply_updates: Callable = apply_updates

        self.title("Settings")

        self._data_directory_var: tk.StringVar = tk.StringVar()
        self._colour_scale_var: tk.StringVar = tk.StringVar()

        self._settings_to_vars()

        pad = 5
        margin = 30
        button_width = 7

        settings_frame = tk.Frame(self)

        label = tk.Label(settings_frame, text="Initial data directory:", anchor=tk.E)
        label.grid(row=0, column=0, padx=pad, pady=pad, sticky=tk.E)
        label = tk.Label(settings_frame, textvariable=self._data_directory_var, width=20, anchor=tk.W)
        label.grid(row=0, column=1, padx=pad, pady=pad, sticky=tk.EW)
        button = tk.Button(settings_frame, text="Select", width = button_width, command=self._select_data_directory)
        button.grid(row=0, column=2, padx=pad, pady=pad)

        label = tk.Label(settings_frame, text="Colour scale:", anchor=tk.E)
        label.grid(row=1, column=0, padx=pad, pady=pad, sticky=tk.E)
        menu = ColourMapOptionMenu(settings_frame, self._colour_scale_var)
        menu.grid(row=1, column=1, padx=pad, pady=pad, sticky=tk.EW)

        settings_frame.columnconfigure(1, weight=1)
        settings_frame.grid(row=0, column=0, sticky=tk.EW)

        okcancel_frame = tk.Frame(self)
        btn = tk.Button(okcancel_frame, text="OK", underline=0,  width=button_width, command=self.on_ok)
        self.bind('o', lambda event: self.on_ok())
        btn.grid(row=0, column=1, padx=pad, pady=pad)
        btn = tk.Button(okcancel_frame, text="Apply", underline=0, width=button_width, command=self.on_apply)
        self.bind('a', lambda event: self.on_apply)
        btn.grid(row=0, column=2, padx=pad, pady=pad)
        btn = tk.Button(okcancel_frame, text="Cancel", underline=0, width=button_width, command=self.on_cancel)
        self.bind('c', lambda event: self.on_cancel())
        btn.grid(row=0, column=3, padx=pad, pady=pad)
        okcancel_frame.columnconfigure(0, weight=1)
        okcancel_frame.grid(row=1, column=0, sticky=tk.EW)

        self.rowconfigure(0, weight=1, pad=margin)
        self.rowconfigure(1, weight=0, pad=margin)
        self.columnconfigure(0, weight=1, pad=margin)

        self.data_directory_var = tk.StringVar()

    def on_ok(self):
        self.on_apply()
        super().on_ok()

    def on_apply(self):
        self._vars_to_settings()
        # Write the new values to file:
        self._app_settings.write()
        # Apply the settings:
        self._apply_updates()

    def _settings_to_vars(self):
        self._data_directory_var.set(self._app_settings.data_directory)
        self._colour_scale_var.set(self._app_settings.colour_map)

    def _vars_to_settings(self):
        self._app_settings.data_directory = self._data_directory_var.get()
        self._app_settings.colour_map = self._colour_scale_var.get()

    def _select_data_directory(self):
        initial = self._app_settings.data_directory if self._app_settings.data_directory != "" else Path.home()
        directory_selected = filedialog.askdirectory(parent=self, mustexist=True, initialdir=initial)
        if directory_selected is not None:
            self._app_settings.data_directory = directory_selected
            self._data_directory_var.set(directory_selected)
