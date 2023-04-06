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


class FileInfoFrame(DrawableFrame):
    """A Frame that contains a short summary of info relating to the data file being
    displayed."""

    def __init__(self, parent, data_context):
        super().__init__(parent)
        self._dc = data_context

        self._label = tk.Label(self, text="", width=1, anchor=tk.CENTER)
        self._label.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)

    def draw(self, draw_scope: int = DrawableFrame.DRAW_ALL):
        super().draw(draw_scope)
        a = self._dc.afs
        if a is not None:
            md = a.get_metadata()
            channel_text = "channels" if md.channels > 1 else "channel"
            text = "{}: {:.1f} s at {:.1f} kHz, {} {}".format(
                md.file_name, md.length_seconds,  md.sample_rate / 1000.0, md.channels, channel_text)
        else:
            text = ""
        self._label.config(text=text)
