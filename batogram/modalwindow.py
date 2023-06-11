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


class ModalWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)

        # Find the highest level parent window we can:
        ancestor = parent
        while ancestor.master:
            ancestor = ancestor.master

        # Don't prescribe the size, let the window adjust to its contents:
        # self.geometry("+{}+{}".format(
        #     ref.winfo_rootx() + (ref.winfo_width()) // 2,
        #     ref.winfo_rooty() + (ref.winfo_height()) // 2))
        # TODO: figure out how to centre without a flicker as we move it:
        self.geometry("+{}+{}".format(
            ancestor.winfo_rootx() + 100,
            ancestor.winfo_rooty() + 100))

        # self.geometry("{}x{}+{}+{}".format(
        #     width, height,
        #     ref.winfo_rootx() + (ref.winfo_width() - width) // 2,
        #     ref.winfo_rooty() + (ref.winfo_height() - height) // 2))

        # self.update_idletasks()
        # bbox = self.grid_bbox()
        # pass

    def on_cancel(self):
        self.destroy()

    def on_ok(self):
        self.destroy()

