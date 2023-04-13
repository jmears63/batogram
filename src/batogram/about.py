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

from PIL import ImageTk, Image
from . import get_asset_path, __version__
from .modalwindow import ModalWindow


class AboutWindow(ModalWindow):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("About Batogram")

        pad = 5

        # We must assign the image to a member variable to prevent the GC getting rid of it
        # too soon:
        self._img = ImageTk.PhotoImage(Image.open(get_asset_path("batogram.png")))
        label = tk.Label(self, image=self._img)
        label.grid(row=0, column=0, padx=pad, pady=pad)

        label = tk.Label(self, text="Version: {}".format(__version__))
        label.grid(row=1, column=0, padx=pad, pady=pad)

        label = tk.Label(self, text="Author: John Mears")
        label.grid(row=2, column=0, padx=pad, pady=pad)

        btn = tk.Button(self, text="Close", underline=0, command=self.on_cancel)
        self.bind('c', lambda event: self.on_cancel())
        btn.grid(row=3, column=0, padx=pad, pady=pad)

        self.columnconfigure(0, weight=1, pad=100)   # Expand to use the width.
