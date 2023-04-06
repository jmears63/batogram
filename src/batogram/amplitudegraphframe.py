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

from .constants import MAIN_AMPLITUDE_COMPLETER_EVENT, FONT_SIZE
from . import layouts
from .audiofileservice import AudioFileService, RawDataReader
from .common import AxisRange
from .frames import GraphFrame, DrawableFrame
from .rendering import AmplitudePipelineRequest

AMPLITUDE_HEIGHT = 60


class AmplitudeGraphFrame(GraphFrame):
    """A Frame the contains an amplitude graph."""

    def __init__(self, parent, root, pipeline, data_context, settings, is_reference=False):
        super().__init__(parent, root, pipeline, data_context, settings)

        self._is_reference = is_reference
        self._parent = parent

        self._canvas = tk.Canvas(self, bg="black", height=AMPLITUDE_HEIGHT, width=1)
        self._canvas.grid(row=0, column=0, sticky='nesw')
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.bind("<Configure>", self._on_canvas_change)
        self.bind(MAIN_AMPLITUDE_COMPLETER_EVENT, self._do_completer)

    def draw(self, draw_scope: int = DrawableFrame.DRAW_ALL):
        super().draw(draw_scope)

        if not draw_scope & DrawableFrame.DRAW_AMPLITUDE:
            return

        time_range, frequency_range, amplitude_range = self._dc.get_ranges()
        afs: AudioFileService = self._dc.get_afs()

        # Allow the canvas to catch up with any pending resizes so that get the right
        # size below:
        self.update_idletasks()

        width, height = self._canvas.winfo_width(), self._canvas.winfo_height()
        layout = layouts.AmplitudeLayout(FONT_SIZE, width, height, is_reference=self._is_reference)
        # Draw the graph axes here in the UI thread, as that is fast and provides responsiveness to the user:
        graph_completer, data_area = layout.draw(self._canvas, time_range, amplitude_range, self._settings.show_grid)

        if afs and self._pipeline:
            # Kick off the pipeline which will create a spectrogram in another thread,
            # and complete by generating an event that will finish drawing the graph in
            # this thread.
            self._completer = graph_completer
            screen_factors = self._parent.get_screen_factors()
            request = self._get_pipeline_request(afs.get_rendering_data(), data_area, time_range, frequency_range,
                                                 amplitude_range,
                                                 screen_factors, afs)

            self._pipeline.submit(request,
                                  lambda: self.event_generate(MAIN_AMPLITUDE_COMPLETER_EVENT),
                                  self._pipeline_error_handler)
        else:
            # No data, so we can complete drawing the graph right away:
            graph_completer()

    @staticmethod
    def _get_pipeline_request(data, data_area, time_range: AxisRange, frequency_range: AxisRange,
                              amplitude_range: AxisRange, screen_factors: tuple[float, float], rdr: RawDataReader):

        request = AmplitudePipelineRequest(data_area, data, time_range, frequency_range,
                                           amplitude_range, screen_factors, rdr)
        return request

    def _do_completer(self, _):
        # A bit of a hack because tkinter doesn't seem to allow data to be attached to an event:
        completer = self._completer
        if completer:
            is_memory_limit_hit, request, completion_data = self._pipeline.get_completion_data()
            completer(is_memory_limit_hit, completion_data)
