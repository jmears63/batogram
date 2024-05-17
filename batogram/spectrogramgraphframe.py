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
from typing import Tuple, Optional

from .constants import SPECTROGAM_COMPLETER_EVENT, MIN_F_RANGE, MIN_T_RANGE, AXIS_FONT_HEIGHT
from . import layouts
from .audiofileservice import RawDataReader, AudioFileService
from .common import AxisRange
from .frames import GraphFrame, DrawableFrame
from .markers import TimeMarkerPair, FrequencyMarkerPair, AbstractMarkerPair
from .playbackservice import PlaybackCursorEventHandler
from .spectrogrammouseservice import SpectrogramMouseService, CursorMode, DragMode
from .renderingservice import SpectrogramPipelineRequest
from .moreframe import HistogramInterface


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


class RightMouseMenu(tk.Menu):
    def __init__(self, parent: "SpectrogramGraphFrame", screen_end_pos: Tuple[int, int],
                 canvas_end_pos: Tuple[int, int], region: Tuple[int, int, int, int],
                 settings: "GraphSettings", drag_mode: DragMode):
        super().__init__(parent, tearoff=0)

        self._screen_pos = screen_end_pos

        # If drag mode is undefined, a point was clicked:
        is_region: bool = True if drag_mode else False

        region_option_state = tk.ACTIVE if is_region else tk.DISABLED
        position_option_state = tk.DISABLED if is_region else tk.ACTIVE

        # Submenu for placing markers:
        placement_menu = tk.Menu(self, tearoff=0)

        # Adding Menu Items
        self.add_command(label="Zoom to region", state=region_option_state,
                         command=lambda: parent.on_zoom_to_rect(region))
        self.add_command(label="Centre on position", state=position_option_state,
                         # Centering is special case of zooming about centre:
                         command=lambda: parent.on_zoom_about_centre(canvas_end_pos, 1.0, False))
        self.add_command(label="Mark selected region", state=region_option_state,
                         command=lambda: parent.mark_region(region, drag_mode))
        self.add_cascade(label="Place...", menu=placement_menu)
        placement_menu.add_command(label="left marker", state=position_option_state,
                                   command=lambda: parent.on_place_left_marker(canvas_end_pos))
        placement_menu.add_command(label="top marker", state=position_option_state,
                                   command=lambda: parent.on_place_top_marker(canvas_end_pos))
        placement_menu.add_command(label="right marker", state=position_option_state,
                                   command=lambda: parent.on_place_right_marker(canvas_end_pos))
        placement_menu.add_command(label="bottom marker", state=position_option_state,
                                   command=lambda: parent.on_place_bottom_marker(canvas_end_pos))
        self.add_command(label="Hide markers",
                         state=tk.ACTIVE if (
                                                    settings.show_time_markers or settings.show_frequency_markers) and not is_region else tk.DISABLED,
                         command=lambda: parent.on_hide_markers())
        self.add_command(label="Close menu")

    def show(self):
        try:
            # Locate relative to the entire screen:
            self.tk_popup(*self._screen_pos, 0)  # Locate menu entry zero at the point provided.
        finally:
            # Release the grab
            self.grab_release()


class SpectrogramGraphFrame(GraphFrame, PlaybackCursorEventHandler):
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
        self._data_area: Optional[Tuple[int, int, int, int]] = None

        # Scrollers are (individually) optional:
        self._scroller_t = None
        self._scroller_f = None

        self._parent = parent

        self._playback_line_id: Optional[int] = None

        # Optional time marker pair, depends whether the user has enabled time markers or not:
        self._time_marker_pair: Optional[TimeMarkerPair] = None
        self._frequency_marker_pair: Optional[FrequencyMarkerPair] = None
        # Any pending marker positions to be applied:
        self._pending_time_marker_positions: Tuple[Optional[float], Optional[float]] = None, None
        self._pending_frequency_marker_positions: Tuple[Optional[float], Optional[float]] = None, None

        self.bind("<Configure>", self._on_canvas_change)
        self.bind(SPECTROGAM_COMPLETER_EVENT, self._do_completer)

    def set_spectrogram_focus(self):
        # Invoked by a child widget to signal upwards that this spectrogram should
        # grab the focus.

        self._parent.set_spectrogram_focus()

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
        # print("SpectrogramGraphFrame.draw()")
        super().draw(draw_scope)

        if not draw_scope & DrawableFrame.DRAW_SPECTROGRAM:
            return

        time_range, frequency_range = self._dc.time_range, self._dc.frequency_range
        afs_data = self._dc.get_afs_data()

        # Allow the canvas to catch up with any pending resizes so that we get the right
        # size below:
        self.update_idletasks()

        self._show_hide_markers(time_range, frequency_range)

        width, height = self.get_canvas_size()
        self._layout = layouts.SpectrogramLayout(AXIS_FONT_HEIGHT, width, height,
                                                 self._time_marker_pair, self._frequency_marker_pair)

        # Draw the graph axes here in the UI thread, as that is fast and provides responsiveness to the user:
        graph_completer, data_area = self._layout.draw(self._canvas, time_range, frequency_range,
                                                       self._settings.show_grid,
                                                       self._settings.zero_based_time)
        self._data_area = data_area

        if afs_data:
            self._update_time_scroller(time_range, self._settings.calc_time_range(afs_data))
            self._update_frequency_scroller(frequency_range, self._settings.calc_frequency_range())
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
                                      lambda: self.event_generate(SPECTROGAM_COMPLETER_EVENT),
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
        self.update_idletasks()

        self._canvas.notify_draw_complete()

    def _show_hide_markers(self, time_range: AxisRange, frequency_range: AxisRange):
        """Create or destroy markers depending on the settings."""

        if self._settings.show_time_markers:
            self._time_marker_pair = self._create_or_update_marker(axis_range=time_range,
                                                                   marker_pair=self._time_marker_pair,
                                                                   pending_marker_positions=self._pending_time_marker_positions,
                                                                   marker_class=TimeMarkerPair)
        else:
            self._time_marker_pair = None
        self._pending_time_marker_positions = None, None  # We've consumed any pending values now.

        if self._settings.show_frequency_markers:
            self._frequency_marker_pair = self._create_or_update_marker(axis_range=frequency_range,
                                                                        marker_pair=self._frequency_marker_pair,
                                                                        pending_marker_positions=self._pending_frequency_marker_positions,
                                                                        marker_class=FrequencyMarkerPair)
        else:
            self._frequency_marker_pair = None
        self._pending_frequency_marker_positions = None, None  # We've consumed any pending values now.

    def _create_or_update_marker(self, marker_pair: AbstractMarkerPair, axis_range: AxisRange,
                                 pending_marker_positions: Tuple[Optional[float], Optional[float]],
                                 marker_class) -> AbstractMarkerPair:
        if marker_pair is None:
            # Default positions are visible in the current scaling:
            delta = axis_range.max - axis_range.min
            # Handle the case where a marker is placed the wrong side of the other marker.
            # We need to adjust the marker that is *not* currently being placed.
            min_value, max_value = self._adjust_marker_range(
                (axis_range.min + delta / 3, axis_range.max - delta / 3),
                pending_marker_positions, axis_range)
            marker_pair = marker_class(self._canvas, self, min_value, max_value)
        else:
            existing_min, existing_max = marker_pair.get_positions()
            min_value, max_value = self._adjust_marker_range((
                existing_min, existing_max),
                pending_marker_positions, axis_range)
            marker_pair.set_positions((min_value, max_value))

        return marker_pair

    @staticmethod
    def _adjust_marker_range(existing_range: Tuple[float, float],
                             pending_marker_positions: Tuple[Optional[float], Optional[float]],
                             axis_range: AxisRange) -> Tuple[float, float]:
        """Create a suitable range for markers, respecting:
            * Update one marker, leaving the other at its existing position.
            * However, if that leaves them in the wrong order, move the other marker.
        """

        resulting_min, resulting_max = existing_range
        if pending_marker_positions[0] is not None:
            # We are placing the lower marker.
            resulting_min = pending_marker_positions[0]
        if pending_marker_positions[1] is not None:
            # We are placing the upper marker.
            resulting_max = pending_marker_positions[1]

        # Keep min and max in the right order:
        if resulting_max <= resulting_min:
            resulting_max = (resulting_min + axis_range.max) / 2
        if resulting_min >= resulting_max:
            resulting_min = (resulting_max + axis_range.min) / 2

        return resulting_min, resulting_max

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
                              screen_factors: Tuple[float, float],
                              raw_data_reader: RawDataReader):
        request = SpectrogramPipelineRequest(is_reference, data_area, data, time_range, frequency_range, screen_factors,
                                             raw_data_reader)
        return request

    def _do_completer(self, _):
        # A bit of a hack because tkinter doesn't seem to allow data to be attached to an event.
        # Possibly, using a queue would be slightly more elegant, but this slightly hacky approach
        # is actually fine.
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

    def calculate_screen_factors(self) -> Tuple[float, float]:
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

    def do_mouse_menu(self, end_pos: Tuple[int, int],
                      region: Tuple[int, int, int, int],
                      drag_mode: DragMode):
        end_screen_pos = self._canvas.winfo_rootx() + end_pos[0], self._canvas.winfo_rooty() + end_pos[1]
        menu = RightMouseMenu(self, end_screen_pos, end_pos, region, self._settings, drag_mode)
        menu.show()

    def on_place_left_marker(self, canvas_pos: Tuple[int, int]):
        self._settings.show_time_markers = True
        self._settings.on_app_modified_settings()
        axis_time, _ = self._layout.canvas_to_axis(canvas_pos)
        self._pending_time_marker_positions = axis_time, None
        self.draw()

    def on_place_right_marker(self, canvas_pos: Tuple[int, int]):
        self._settings.show_time_markers = True
        self._settings.on_app_modified_settings()
        axis_time, _ = self._layout.canvas_to_axis(canvas_pos)
        self._pending_time_marker_positions = None, axis_time
        self.draw()

    def on_place_top_marker(self, canvas_pos: Tuple[int, int]):
        self._settings.show_frequency_markers = True
        self._settings.on_app_modified_settings()
        _, axis_frequency = self._layout.canvas_to_axis(canvas_pos)
        self._pending_frequency_marker_positions = None, axis_frequency
        self.draw()

    def on_place_bottom_marker(self, canvas_pos: Tuple[int, int]):
        self._settings.show_frequency_markers = True
        self._settings.on_app_modified_settings()
        _, axis_frequency = self._layout.canvas_to_axis(canvas_pos)
        self._pending_frequency_marker_positions = axis_frequency, None
        self.draw()

    def on_hide_markers(self):
        self._settings.show_time_markers = False
        self._settings.show_frequency_markers = False
        self._settings.on_app_modified_settings()
        self.draw()

    def mark_region(self, region: Tuple[int, int, int, int], drag_mode: DragMode):
        # Convert the drag region pixels to axis values:
        top_left = region[0], region[1]
        bottom_right = region[2], region[3]
        t1, f1 = self._layout.canvas_to_axis(top_left)
        t2, f2 = self._layout.canvas_to_axis(bottom_right)

        if drag_mode == DragMode.DRAG_HORIZONTAL or drag_mode == DragMode.DRAG_RECTANGLE:
            self._settings.show_time_markers = True
            self._pending_time_marker_positions = t1, t2

        if drag_mode == DragMode.DRAG_VERTICAL or drag_mode == DragMode.DRAG_RECTANGLE:
            self._settings.show_frequency_markers = True
            self._pending_frequency_marker_positions = f2, f1  # Axis value ordering is oppostie to pixel value ordering.

        self._settings.on_app_modified_settings()
        self.draw()

    def on_show_update_playback_cursor(self, offset: int):
        # Note any existing line id, and delete it after drawing the new one, for smoothness.
        existing_line_id = self._playback_line_id
        self._playback_line_id = None

        if self._data_area is not None:
            # Draw a vertical line in the data area at the x canvas position corresponding to the
            # raw data sample offset provided.
            # This code may not be the most efficient ever, but it runs in the UI thread which is not
            # doing much else during playback.
            colour = "#00ff00"
            left, top, right, bottom = self._data_area
            if self._dc.afs is not None:
                rendering_data = self._dc.afs.get_rendering_data()
                t: float = offset / self._settings.settings_sample_rate
                x = self._layout.time_to_canvas(t)
                # Only draw it if it is within the data area:
                if left <= x <= right:
                    self._playback_line_id = self._canvas.create_line(x, top, x, bottom, fill=colour, width=1,
                                                                      dash=(1, 1))

        if existing_line_id is not None:
            self._canvas.delete(existing_line_id)

    def on_hide_playback_cursor(self):
        if self._playback_line_id is not None:
            self._canvas.delete(self._playback_line_id)
            self._playback_line_id = None
