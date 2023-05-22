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
from typing import Tuple, Optional, Callable

from .constants import MAIN_SPECTROGAM_COMPLETER_EVENT, FONT_SIZE, MIN_F_RANGE, MIN_T_RANGE
from . import layouts
from .audiofileservice import RawDataReader, AudioFileService
from .common import AxisRange
from .frames import GraphFrame, DrawableFrame
from .spectrogrammouseservice import SpectrogramMouseService, CursorMode
from .rendering import SpectrogramPipelineRequest
from .moreframe import HistogramInterface


class TimeMarker:
    _DRAG_CURSOR = "sb_h_double_arrow"
    _MARKER_COLOUR = "#808000"
    _MARKER_DRAGGER_COLOUR = "#FFFF00"

    def __init__(self, canvas: "SpectrogramCanvas", pair: "TimeMarkerPair", sgf: "SpectrogramGraphFrame",
                 time_value: Optional[float], tag_name: str):
        self._pair = pair
        self._sgf = sgf
        self._time_value: Optional[float] = time_value
        self._pixel_value: Optional[int] = None
        self._tag_name: str = tag_name
        self._canvas: "SpectrogramCanvas" = canvas
        self._start_event = None
        self._saved_cursor = None
        self._polygon_id = None
        self._line = None
        self._moved: Optional[int] = None

        canvas.tag_bind(self._tag_name, "<Enter>", lambda event: self.mouse_enters_dragger(event))
        canvas.tag_bind(self._tag_name, "<Leave>", lambda event: self.mouse_leaves_dragger(event))
        canvas.tag_bind(self._tag_name, "<Button-1>", lambda event: self._on_click(event))
        canvas.tag_bind(self._tag_name, "<B1-Motion>", lambda event: self._on_move(event))
        canvas.tag_bind(self._tag_name, "<ButtonRelease-1>", lambda event: self._on_release(event))

    def get_pixel_value(self) -> Optional[int]:
        return self._pixel_value

    def draw(self, marker_rect: Tuple[int, int, int, int], data_rect: Tuple[int, int, int, int],
             margin: int, axis_range: AxisRange) -> Tuple[Callable, int, int]:
        """Draw the marker, and return the coordinates of the end of the connecting band."""

        l, t, r, b = data_rect

        # Draw the line:
        x_pixels = int((self._time_value - axis_range.min) / (axis_range.max - axis_range.min) * (r - l) + l)
        self._line = self._canvas.create_line(x_pixels, b, x_pixels, t, fill=self._MARKER_COLOUR, width=1, dash=(2, 2))

        # Draw the dragger:
        l, t, r, b = marker_rect
        h = int(margin / 2)
        tan60: float = 1.73
        w = int(h / tan60)
        self._pixel_value = x_pixels

        # The caller will call this closure to actually draw the marker:
        def drawer():
            self._polygon_id = self._canvas.create_polygon(x_pixels, b, x_pixels + w, b - h, x_pixels - w, b - h,
                                                           fill=self._MARKER_DRAGGER_COLOUR,
                                                           outline=self._MARKER_DRAGGER_COLOUR,
                                                           tags=[self._tag_name])
            return self._polygon_id

        return drawer, b, b - h

    def mouse_enters_dragger(self, _):
        # Only if we aren't currently dragging - avoids cursor flicker during the drag.
        if self._start_event is None:
            self._saved_cursor = self._canvas.config('cursor')[-1]
            self._canvas.config(cursor=self._DRAG_CURSOR)

    def mouse_leaves_dragger(self, _):
        # Only if we aren't currently dragging - avoids cursor flicker during the drag.
        if self._start_event is None and self._saved_cursor is not None:
            self._canvas.config(cursor=self._saved_cursor)
            self._saved_cursor = None

    def _on_click(self, event):
        # print("_on_click: {}".format(event))
        self._start_event = event
        self._moved = self._pixel_value

        # # Ask the line (which knows about the other dragger) what our allowed positions are:
        # self._allowed_x_range = self._line.get_allowed_range(self._which)
        # Set the cursor at the canvas level so it doesn't flicker during dragging:
        self._canvas.config(cursor=self._DRAG_CURSOR)

        # Take control of the mouse away from the canvas:
        self._canvas.preempt_mouse(True)

    def _on_move(self, event):
        # print("TimeMarker._on_move: {}".format(event))

        # This is a little more complex that you might hope as we have
        # to convert between deltas and totals.
        x_resulting = self._calc_dragged(event)
        self.do_move(x_resulting)

    def do_move(self, x: int):
        # Move the dragger object in the canvas, using the intrinsic move method
        # which presumably is the most efficient way:
        x_last = self._moved
        dx, dy = x - x_last, 0
        self._canvas.move(self._polygon_id, dx, dy)
        self._canvas.move(self._line, dx, dy)
        self._moved = x

    def _on_release(self, event):
        # print("_on_release: {}".format(event))

        # Move to the release point just in case we somehow didn't get a move event:
        self._calc_dragged(event)

        # Reset ready for another drag:
        self._pos = self._moved
        self._pixel_value = self._moved
        self._allowed_x_range = None
        self._start_event = None

        # Return control of the mouse to the canvas:
        self._canvas.preempt_mouse(False)

    def _calc_dragged(self, event) -> int:
        """Figure out by how far they have dragged, clipping that to the allowed range."""

        # Note that the event x is not dragger position, it is where
        # the user clicked in the dragger, so most likely off centre:
        x, x0 = event.x, self._start_event.x

        # How far have we dragged from the start?
        x_dragged = x - x0
        x_resulting = self._pixel_value + x_dragged
        # x_min_allowed, x_max_allowed = self._allowed_x_range
        # x_resulting = clip_to_range(x_resulting, x_min_allowed, x_max_allowed)

        return x_resulting


class LeftTimeMarker(TimeMarker):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "TimeMarkerPair", sgf: "SpectrogramGraphFrame",
                 time_value: Optional[float]):
        super().__init__(canvas, pair, sgf, time_value, "left_time_marker")

    def do_move(self, x: int):
        super().do_move(x)
        # Notify the pair to redraw the band before we move the marker:
        self._pair.do_move_left(x)


class RightTimeMarker(TimeMarker):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "TimeMarkerPair", sgf: "SpectrogramGraphFrame",
                 time_value: Optional[float]):
        super().__init__(canvas, pair, sgf, time_value, "right_time_marker")

    def do_move(self, x: int):
        super().do_move(x)
        # Notify the pair to redraw the band before we move the marker:
        self._pair.do_move_right(x)


class TimeMarkerPair:
    _BAND_COLOUR = "#808000"
    _tag_name = "band"

    def __init__(self, canvas: "SpectrogramCanvas", sgf: "SpectrogramGraphFrame", left_time: Optional[float],
                 right_time: Optional[float]):
        self._left_marker = LeftTimeMarker(canvas, self, sgf, left_time)
        self._right_marker = RightTimeMarker(canvas, self, sgf, right_time)
        self._sgf = sgf
        self._canvas = canvas
        self._band_rect: Optional[Tuple[int, int, int, int]] = None
        self._band_id = None
        self._left_id = self._right_id = None

    def draw(self, marker_rect: Tuple[int, int, int, int], data_rect: Tuple[int, int, int, int],
             margin: int, axis_range: AxisRange):
        # Draw the markers:
        left_drawer, bottom, top = self._left_marker.draw(marker_rect, data_rect, margin, axis_range)
        right_drawer, _, _ = self._right_marker.draw(marker_rect, data_rect, margin, axis_range)

        # Draw a connecting band between them:
        self._band_rect = self._left_marker.get_pixel_value(), top, self._right_marker.get_pixel_value(), bottom
        self._band_id = self._draw_band(*self._band_rect)

        # Finally, draw the markers, so that they overlap the band on top of it:
        self._left_id = left_drawer()
        self._right_id = right_drawer()

    def do_move_left(self, x: int):
        if self._band_rect is not None:
            l, t, r, b = self._band_rect
            self._band_rect = x, t, r, b
            self._redraw_band(*self._band_rect)

    def do_move_right(self, x: int):
        if self._band_rect is not None:
            l, t, r, b = self._band_rect
            self._band_rect = l, t, x, b
            self._redraw_band(*self._band_rect)

    def _draw_band(self, left, top, right, bottom):
        return self._canvas.create_rectangle(left, top, right, bottom,
                                             fill=self._BAND_COLOUR,
                                             outline=self._BAND_COLOUR,
                                             stipple='gray25',
                                             tags=[self._tag_name])

    def _redraw_band(self, left, top, right, bottom):
        new_band_id = self._draw_band(left, top, right, bottom)

        # Move it beneath any existing band, before we delete the existing one, to preserve layering order:
        if self._band_id is not None:
            self._canvas.tag_lower(new_band_id, self._band_id)
            self._canvas.delete(self._band_id)
        self._band_id = new_band_id


class SpectrogramCanvas(tk.Canvas):
    """A Canvas containing a spectrogram."""

    def __init__(self, parent, width, height, initial_cursor_mode):
        super().__init__(parent, height=height, width=width, cursor="cross", bg="black")

        self._mouse_service = SpectrogramMouseService(self, initial_cursor_mode, parent)

    def set_cursor_mode(self, mode):
        self._mouse_service.set_cursor_mode(mode)

    def notify_draw_complete(self):
        self._mouse_service.notify_draw_complete()

    def preempt_mouse(self, preempt: bool):
        self._mouse_service.preempt_mouse(preempt)


class SpectrogramGraphFrame(GraphFrame):
    """A graph frame containing a spectrogram."""

    def __init__(self, parent: "PanelFrame", root, pipeline, data_context, settings, initial_cursor_mode, is_reference):
        super().__init__(parent, root, pipeline, data_context, settings)

        self._is_reference = is_reference
        self._canvas = SpectrogramCanvas(self, height=100, width=100, initial_cursor_mode=initial_cursor_mode)
        self._canvas.grid(row=0, column=0, sticky='nesw')
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._layout = None
        self._histogram_interface: Optional[HistogramInterface] = None

        # Scrollers are (individually) optional:
        self._scroller_t = None
        self._scroller_f = None

        self._parent = parent

        # Optional time marker pair, depends whether the user has enable time markers or not:
        self._time_marker_pair: Optional[TimeMarkerPair] = TimeMarkerPair(self._canvas, self, 0.3333, 2.6666)

        self.bind("<Configure>", self._on_canvas_change)
        self.bind(MAIN_SPECTROGAM_COMPLETER_EVENT, self._do_completer)

    def set_histogram_interface(self, interface: HistogramInterface):
        self._histogram_interface = interface

    def set_scroller_t(self, time_scroller):
        time_scroller.configure(command=self.tview)
        self._scroller_t = time_scroller

    def set_scroller_f(self, frequency_scroller):
        frequency_scroller.configure(command=self.fview)
        self._scroller_f = frequency_scroller

    def tview(self, *args):
        """The time scroller calls this method to request scrolling.

            command can be one of: tk.SCROLL, tk.MOVETO
            delta depends on the command (+/-1, or a float 0-1.0 respectively).
            size is one of tk.UNITS, tk.PAGES

            TODO: the internet suggests that this method should return start,end
            if called with no args, or perhaps, always.
        """

        cmd, *_ = args
        if cmd == tk.MOVETO:
            cmd, f, = args
            self._scroll_move_time(float(f))
        elif cmd == tk.SCROLL:
            cmd, delta, size, = args
            self._scroll_delta_time(delta, size)

    def fview(self, *args):
        cmd, *_ = args
        if cmd == tk.MOVETO:
            cmd, f, = args
            self._scroll_move_frequency(float(f))
        elif cmd == tk.SCROLL:
            cmd, delta, size, = args
            self._scroll_delta_frequency(delta, size)

    def draw(self, draw_scope: int = DrawableFrame.DRAW_ALL):
        super().draw(draw_scope)

        if not draw_scope & DrawableFrame.DRAW_SPECTROGRAM:
            return

        time_range, frequency_range = self._dc.time_range, self._dc.frequency_range
        afs_data = self._dc.get_afs_data()

        # Allow the canvas to catch up with any pending resizes so that we get the right
        # size below:        self._parent = parent
        self.update_idletasks()

        width, height = self.get_canvas_size()
        self._layout = layouts.SpectrogramLayout(FONT_SIZE, width, height, self._time_marker_pair)
        # Draw the graph axes here in the UI thread, as that is fast and provides responsiveness to the user:
        graph_completer, data_area = self._layout.draw(self._canvas, time_range, frequency_range,
                                                       self._settings.show_grid,
                                                       self._settings.zero_based_time)

        if afs_data:
            self._update_time_scroller(time_range, afs_data.time_range)
            self._update_frequency_scroller(frequency_range, afs_data.frequency_range)
            if self._pipeline:
                # Kick off the pipeline which will create a spectrogram in another thread,
                # and complete by generating an event that will finish drawing the graph in
                # this thread.
                self._completer = graph_completer
                screen_factors = self._parent.get_screen_factors()
                request = self._get_pipeline_request(self._is_reference, afs_data, data_area, time_range,
                                                     frequency_range, screen_factors,
                                                     self._dc.get_afs())
                self._pipeline.submit(request,
                                      lambda: self.event_generate(MAIN_SPECTROGAM_COMPLETER_EVENT),
                                      self._pipeline_error_handler)
        else:
            # No data, make the sliders full length:
            self._update_time_scroller(AxisRange(0, 1), AxisRange(0, 1))
            self._update_frequency_scroller(AxisRange(0, 1), AxisRange(0, 1))

            # No data, so clear the histogram:
            self._histogram_interface.hide_histogram()

            # No data, so we can complete drawing the graph right away:
            graph_completer()

        # Allow the screen update to happen:
        self.update()

        self._canvas.notify_draw_complete()

    def set_cursor_mode(self, mode):
        if mode == CursorMode.CURSOR_ZOOM:
            self._canvas.config(cursor="cross")
        elif mode == CursorMode.CURSOR_PAN:
            self._canvas.config(cursor="fleur")
        else:
            self._canvas.config(cursor="")

        self._canvas.set_cursor_mode(mode)

    @staticmethod
    def _get_pipeline_request(is_reference: bool, data, data_area, time_range, frequency_range,
                              screen_factors: tuple[float, float],
                              raw_data_reader: RawDataReader):
        request = SpectrogramPipelineRequest(is_reference, data_area, data, time_range, frequency_range, screen_factors,
                                             raw_data_reader)
        return request

    def _do_completer(self, _):
        # A bit of a hack because tkinter doesn't seem to allow data to be attached to an event:
        completer = self._completer
        if completer:
            memory_limit_hit, request, image, histogram, auto_vrange = self._pipeline.get_completion_data()  # Can be None.
            completer(memory_limit_hit, image)
            if not memory_limit_hit:
                # Update the graph parameters to the readout frame:
                params = self._pipeline.get_graph_parameters()
                self._parent.update_readout_params(params)
                # Update the manual BnC range to the settings and settings UI:
                if auto_vrange is not None:
                    self._settings.bnc_manual_min, self._settings.bnc_manual_max = auto_vrange
                    self._settings.on_app_modified_settings()
                # Update the BnC histogram from the range discovered.
                self._histogram_interface.show_histogram(histogram)

    def on_zoom_to_rect(self, rect: Tuple[int, int, int, int]):
        """Rescale to the pixel rectangle provided."""
        if self._layout is None:
            return  # No layout, we can't do anything.

        # Convert the canvas coords to axes values:
        r_values = self._layout.rect_to_values(rect)

        # print("Rescaling graph to r_values {}".format(r_values))

        l, t, r, b = r_values
        # Sanity, avoid divisions by zero. Shouldn't ever happen...
        if not l < r:
            r = l + 1
        if not b < t:
            t = b + 1

        # Don't allow them to zoom in excessively:
        f_delta, t_delta = t - b, r - l
        if f_delta < MIN_F_RANGE or t_delta < MIN_T_RANGE:
            print("Ignoring insane zoom.")
            return  # Insane zoom requested, ignore it.

        # Notify news of this rescale back to the main window so that it can redraw widgets affected:
        # news to widgets that need to know.
        self._parent.on_rescale_handler(AxisRange(l, r), AxisRange(b, t))

    def on_pan(self, rect):
        """This is called in response to the user dragging a pan line with the mouse."""
        if self._layout is None:
            return  # No layout, we can't do anything.

        # The following will clip pan line to the range of the axes:
        t1, f1, t2, f2 = self._layout.rect_to_values(rect)
        dt_value, df_value = t2 - t1, f2 - f1

        # print("Panning graph by {}, {}".format(dt_value, df_value))

        # Apply the pan:
        t_range, f_range = self._layout.get_data_ranges()
        (l, r), (b, t) = t_range.get_tuple(), f_range.get_tuple()
        l, r, b, t = l - dt_value, r - dt_value, b - df_value, t - df_value

        self._parent.on_rescale_handler(AxisRange(l, r), AxisRange(b, t))

    def on_zoom_about_centre(self, position, factor, frequency_clamped: bool) -> bool:
        """
        Optionally pan so that pixel position is centered, then apply the zoom factor.
        Return True if the new range was sane and we applied it, otherwise false.
        """

        # If a position is provided, we apply an offset so that that position
        # becomes the centre of the axis ranges:
        if position:
            position_t_v, position_f_v = self._layout.canvas_to_axis(position)
            time_range, frequency_range = self._layout.get_data_ranges()
            centre_t_v, centre_f_v = (time_range.min + time_range.max) / 2, (
                    frequency_range.min + frequency_range.max) / 2
            offset_t_v, offset_f_v = centre_t_v - position_t_v, centre_f_v - position_f_v
            axis_ranges = AxisRange(time_range.min - offset_t_v, time_range.max - offset_t_v), \
                AxisRange(frequency_range.min - offset_f_v, frequency_range.max - offset_f_v)
        else:
            axis_ranges = self._layout.get_data_ranges()

        # We need to zoom the axis ranges in or out relative to the centres of their ranges:
        time_range, frequency_range = axis_ranges

        (l, r), (b, t) = time_range.get_tuple(), frequency_range.get_tuple()

        if t - b < MIN_F_RANGE or r - l < MIN_T_RANGE:
            # Allow them to zoom back out again, to avoid getting stuck.
            if factor < 1.0:
                print("Ignoring insane zoom in.")
                return False  # Insane zoom requested, ignore it.

        # Offset to the centre of the axis ranges:
        centre_t_v, centre_f_v = (l + r) / 2, (t + b) / 2
        l, t, r, b = l - centre_t_v, t - centre_f_v, r - centre_t_v, b - centre_f_v
        # Apply the zoom:
        l, t, r, b = l * factor, t * factor, r * factor, b * factor
        # Reverse the offset we applied:
        l, t, r, b = l + centre_t_v, t + centre_f_v, r + centre_t_v, b + centre_f_v

        if frequency_clamped:
            _, frequency_range = self._layout.get_data_ranges()
            self._parent.on_rescale_handler(AxisRange(l, r), frequency_range)
        else:
            self._parent.on_rescale_handler(AxisRange(l, r), AxisRange(b, t))

        return True

    def on_mouse_move(self, p_canvas):
        # print("on mouse move")

        if p_canvas is None or self._layout is None:
            self._parent.update_readout_coords(None, None)
        else:
            # Convert to axis coords for t and f:
            p_axis = self._layout.canvas_to_axis(p_canvas)
            p_data_area = self._layout.canvas_to_data_area(p_canvas)
            self._parent.update_readout_coords(p_axis, p_data_area)

    def _scroll_move_time(self, _):
        # Scroll time to position f which is in the range 0 to 1.0.

        data: AudioFileService.RenderingData = self._dc.get_afs_data()
        if data is None:
            return

        # Weirdly, f seems to refer to one end of the slider, not the centre.
        # We call get to get the ends, avoiding using f.

        new_tmin, new_tmax = self._scroller_t.get()

        file_tmin, file_tmax = data.time_range.get_tuple()
        _, range_f = self._layout.get_data_ranges()
        axis_fmin, axis_fmax = range_f.get_tuple()

        # The total time range available is the data file range minus the time axis range:
        resultant_tmin = (file_tmax - file_tmin) * new_tmin + file_tmin
        resultant_tmax = (file_tmax - file_tmin) * new_tmax + file_tmin

        self._parent.on_rescale_handler(AxisRange(resultant_tmin, resultant_tmax), AxisRange(axis_fmin, axis_fmax))

    def _scroll_move_frequency(self, _):
        # Scroll frequency to position f which is in the range 0 to 1.0.

        data: AudioFileService.RenderingData = self._dc.get_afs_data()
        if data is None:
            return

        new_fmin, new_fmax = self._scroller_f.get()
        # Vertical scroll bars increase downwards:
        new_fmin, new_fmax = 1.0 - new_fmax, 1.0 - new_fmin

        file_fmin, file_fmax = data.frequency_range.get_tuple()
        range_t, _ = self._layout.get_data_ranges()
        axis_tmin, axis_tmax = range_t.get_tuple()
        # The total time range available is the data file range minus the time axis range:
        resultant_fmin = (file_fmax - file_fmin) * new_fmin + file_fmin
        resultant_fmax = (file_fmax - file_fmin) * new_fmax + file_fmin

        self._parent.on_rescale_handler(AxisRange(axis_tmin, axis_tmax), AxisRange(resultant_fmin, resultant_fmax))

    def _scroll_delta_time(self, sign_s, size):
        # Apply a step to the scroll f which is in the range 0 to 1.0.

        data = self._dc.get_afs()
        if data is None:
            return

        range_t, range_f = self._layout.get_data_ranges()
        axis_t_span = range_t.max - range_t.min

        sign = int(sign_s)
        if size == tk.UNITS:
            delta_t = axis_t_span * 0.05 * sign
        elif size == tk.PAGES:
            delta_t = axis_t_span * 0.8 * sign
        else:
            return

        self._parent.on_scroll_handler(delta_t, 0, range_t, range_f)

    def _scroll_delta_frequency(self, sign_s, size):
        # Apply a step to the scroll f which is in the range 0 to 1.0.

        data = self._dc.get_afs()
        if data is None:
            return

        range_t, range_f = self._layout.get_data_ranges()
        axis_f_span = range_f.max - range_f.min

        sign = int(sign_s)
        # Vertical scrollers increase downward:
        sign = sign * -1.0
        if size == tk.UNITS:
            delta_f = axis_f_span * 0.05 * sign
        elif size == tk.PAGES:
            delta_f = axis_f_span * 0.9 * sign
        else:
            return

        self._parent.on_scroll_handler(0, delta_f, range_t, range_f)

    def set_preset_time_range(self, sign: int):
        """Zoom the time range in or out, centered on the current range.
        Positive sign increases the axis range, ie zoom out.
        """

        new_time_range: AxisRange = self._layout.calc_preferred_time_range(sign)

        if new_time_range.max - new_time_range.min < MIN_T_RANGE:
            # Allow them to zoom back out again, to avoid getting stuck.
            if sign < 0:
                print("Ignoring insane zoom in.")
                return False  # Insane zoom requested, ignore it.

        _, frequency_range = self._layout.get_data_ranges()
        self._parent.on_rescale_handler(new_time_range, frequency_range)

    def _update_time_scroller(self, axis_range, file_range):
        if self._scroller_t is None:
            return

        # Set the time scroller so that the bar represents the visible part of the data,
        # scaled to the range 0 to 1.0.

        file_tmin, file_tmax = file_range.get_tuple()
        axis_tmin, axis_tmax = axis_range.get_tuple()
        if file_tmax == file_tmin:
            return

        start = (axis_tmin - file_tmin) / (file_tmax - file_tmin)
        end = (axis_tmax - file_tmin) / (file_tmax - file_tmin)

        # print("set {} {}".format(start, end))
        self._scroller_t.set(start, end)

    def _update_frequency_scroller(self, axis_range, file_range):

        if self._scroller_f is None:
            return

        # Set the time scroller so that the bar represents the visible part of the data,
        # scaled to the range 0 to 1.0.

        file_fmin, file_fmax = file_range.get_tuple()
        axis_fmin, axis_fmax = axis_range.get_tuple()
        if file_fmax == file_fmin:
            return

        start = (axis_fmin - file_fmin) / (file_fmax - file_fmin)
        end = (axis_fmax - file_fmin) / (file_fmax - file_fmin)

        # Vertical scrollers increase downward:
        start, end = 1.0 - end, 1.0 - start

        # print("set {} {}".format(start, end))
        self._scroller_f.set(start, end)

    def get_canvas_size(self):
        return self._canvas.winfo_width(), self._canvas.winfo_height()

    def calculate_screen_factors(self) -> tuple[float, float]:
        """
        Calculate:
         * the screen aspect factor in s/Hz that will be used for adaptive window
            length calculations,
         * The number of x pixels per second that will be used for adaptive
            overlap calculations.
        """

        def delta(axis_range: AxisRange):
            return axis_range.max - axis_range.min

        width, height = self.get_canvas_size()
        dt, df = delta(self._dc.time_range), delta(self._dc.frequency_range)
        window_factor = (height * dt) / (width * df)

        pixels_per_second = width / dt

        return window_factor, pixels_per_second
