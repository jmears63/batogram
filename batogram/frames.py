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
import tkinter.messagebox

from .constants import PROGRAM_NAME


class DrawableFrame(tk.Frame):
    """All frames within a pane are of this type, to allow them to be drawn in the same way."""

    # Flags to pass to the notification methods to limit which graphs will be refreshed:
    DRAW_SPECTROGRAM = 1
    DRAW_PROFILE = 2
    DRAW_AMPLITUDE = 4
    DRAW_ALL = DRAW_SPECTROGRAM | DRAW_PROFILE | DRAW_AMPLITUDE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def draw(self, draw_scope: int = DRAW_ALL):
        pass  # Subclasses may do drawing here, if they want.

    def reset_draw(self, draw_scope: int = DRAW_ALL):
        pass  # Subclasses may use this hint to abandon any pending drawing.


class GraphFrame(DrawableFrame):
    """All frames containing graph data are of this type."""

    def __init__(self, parent, root, pipeline, data_context, settings: "GraphSettings"):
        super().__init__(parent)
        self._completer = None
        self._my_root = root
        self._pipeline = pipeline
        self._dc = data_context
        self._settings: "GraphSettings" = settings
        self._layout = None

    def _on_canvas_change(self, _):
        self.draw()

    @staticmethod
    def _pipeline_error_handler(e):
        tk.messagebox.showerror(PROGRAM_NAME, "Error encountered in processing pipeline: {}".format(e))
        raise e

    def reset_draw(self, draw_scope: int = DrawableFrame.DRAW_ALL):
        super().reset_draw()
        self._completer = None
