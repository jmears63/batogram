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

from .constants import MAIN_PROFILE_COMPLETER_EVENT, FONT_SIZE
from . import layouts
from .audiofileservice import RawDataReader
from .common import AxisRange
from .frames import GraphFrame, DrawableFrame
from .rendering import ProfilePipelineRequest

PROFILE_WIDTH = 90


class ProfileGraphFrame(GraphFrame):
    """A Frame containing a profile graph for a spectrogram."""

    def __init__(self, parent, root, pipeline, data_context, settings, is_reference):
        super().__init__(parent, root, pipeline, data_context, settings)

        self._canvas = tk.Canvas(self, bg="black", height=1, width=PROFILE_WIDTH)
        self._canvas.grid(row=0, column=0, sticky='nesw')
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._parent = parent
        self._is_reference = is_reference

        self.bind("<Configure>", self._on_canvas_change)
        self.bind(MAIN_PROFILE_COMPLETER_EVENT, self._do_completer)

        # self._pipeline = None   # Temporary, remove this.

    def draw(self, draw_scope: int = DrawableFrame.DRAW_ALL):
        super().draw(draw_scope)

        if not draw_scope & DrawableFrame.DRAW_PROFILE:
            return

        time_range, frequency_range, _ = self._dc.get_ranges()
        profile_range = AxisRange(0, 1)  # Arbitrary, will be overwritten when we know what it is.
        af_data = self._dc.get_afs_data()

        # Allow the canvas to catch up with any pending resizes so that we get the right
        # size below:
        self.update_idletasks()

        width, height = self._canvas.winfo_width(), self._canvas.winfo_height()
        layout = layouts.ProfileLayout(FONT_SIZE, width, height)
        # Draw the graph axes here in the UI thread, as that is fast and provides responsiveness to the user:
        graph_completer, data_area = layout.draw(self._canvas, profile_range, frequency_range,
                                                 self._settings.show_grid, self._settings.zero_based_time)
        if af_data and self._pipeline:
            # Kick off the pipeline which will create a graph in another thread,
            # and complete by generating an event that will finish drawing the grph:
            self._completer = graph_completer
            screen_factors = self._parent.get_screen_factors()
            request = self._get_pipeline_request(self._is_reference, af_data, data_area, time_range, frequency_range, screen_factors,
                                                 self._dc.get_afs())
            self._pipeline.submit(request,
                                  lambda: self.event_generate(MAIN_PROFILE_COMPLETER_EVENT),
                                  self._pipeline_error_handler)
        else:
            # No data, so we can complete drawing the graph right away:
            graph_completer()

    @staticmethod
    def _get_pipeline_request(is_reference: bool, data, data_area, time_range, frequency_range, screen_factors: tuple[float, float], rdr: RawDataReader):
        request = ProfilePipelineRequest(is_reference, data_area, data, time_range, frequency_range, screen_factors, rdr)
        return request

    def _do_completer(self, _):
        # A bit of a hack because tkinter doesn't seem to allow data to be attached to an event:
        completer = self._completer
        if completer:
            memory_limit_hit, request, points, v_range = self._pipeline.get_completion_data()
            completer(memory_limit_hit, points, v_range)
