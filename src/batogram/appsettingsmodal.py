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
from dataclasses import dataclass

from batogram.modalwindow import ModalWindow
from dataclasses_json import Undefined, dataclass_json


@dataclass_json(undefined=Undefined.EXCLUDE)
@dataclass()
class AppSettings:
    colour_scale: str = "kindlmann-table-byte-1024.csv"
    data_path: str = "."


class AppSettingsWindow(ModalWindow):
    def __init__(self, parent, app_settings: AppSettings):
        super().__init__(parent)
        self._app_settings: AppSettings = app_settings

        self.title("Settings")

        pad = 5
        margin = 30

        settings_frame = tk.Frame(self)

        label = tk.Label(settings_frame, text="Initial data directory:")
        label.grid(row=0, column=0, padx=pad, pady=pad)
        label = tk.Entry(settings_frame, width=30)
        label.grid(row=0, column=1, padx=pad, pady=pad)

        label = tk.Label(settings_frame, text="Colour scale:")
        label.grid(row=1, column=0, padx=pad, pady=pad)
        label = tk.Entry(settings_frame, width=30)
        label.grid(row=1, column=1, padx=pad, pady=pad)

        settings_frame.grid(row=0, columnspan=1)

        okcancel_frame = tk.Frame(self)
        btn = tk.Button(okcancel_frame, text="OK", command=self.on_ok)
        btn.grid(row=0, column=0, padx=pad, pady=pad, sticky="EW")
        btn = tk.Button(okcancel_frame, text="Cancel", command=self.on_cancel)
        btn.grid(row=0, column=1, padx=pad, pady=pad, sticky="EW")
        okcancel_frame.columnconfigure(0, weight=1)
        okcancel_frame.columnconfigure(1, weight=1)
        okcancel_frame.grid(row=1, column=0)

        self.rowconfigure(0, weight=1, pad=margin)
        self.rowconfigure(0, weight=0, pad=margin)
        self.columnconfigure(0, weight=1, pad=margin)

