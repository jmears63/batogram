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

import math
import sys
import tkinter as tk
from dataclasses import dataclass

import numpy as np

from typing import Optional, Tuple, List
from PIL import ImageTk, Image, ImageOps

from . import colourmap
from .common import AxisRange

AXIS_BG_COLOUR = "#404040"
AXIS_FG_COLOUR = "white"
GRID_COLOUR = "#404040"


class Layout:
    """A Layout is a helper class that knows how to lay out and draw a graph or a part of a graph."""

    def __init__(self, font_height, canvas_width, canvas_height):
        self._font_height = font_height
        self._canvas_width = canvas_width
        self._canvas_height = canvas_height

    @staticmethod
    def _create_rectangle(canvas, x0, y0, x1, y1, colour):
        """A method for drawing rectangles in a sane way: the coordinates provided
        are inclusive of the rectangle on all sides.

        From the tk docs:
        The outline lies inside the rectangle on its top and left sides, but outside
        the rectangle on its bottom and right side. The default appearance is a one-pixel-wide
        black border.
        """
        canvas.create_rectangle(x0, y0, x1, y1, fill=colour, outline=colour)

    @staticmethod
    def calculate_ticks(axis_range: AxisRange, multiplier, pixel_range, target_spacing_pixels=100):
        # Come up with sane values and positions for ticks, based loosely on have a tick
        # per set number of pixels.

        min_value, max_value = axis_range.min / multiplier, axis_range.max / multiplier

        # Sanity checks:
        if min_value >= max_value:
            return [], 0
        if pixel_range <= 0:
            return [], 0

        pixels_per_tick = target_spacing_pixels
        raw_span = max_value - min_value
        raw_interval = raw_span * pixels_per_tick / pixel_range
        scaler = 10 ** (math.floor(math.log10(raw_interval)))
        normalized_interval = raw_interval / scaler
        if normalized_interval >= 5:
            rounded_normalized_interval = 5
        elif normalized_interval >= 2:
            rounded_normalized_interval = 2
        else:
            rounded_normalized_interval = 1
        rounded_interval = rounded_normalized_interval * scaler
        rounded_min = math.floor(min_value / rounded_interval) * rounded_interval

        tick_values = []
        t = rounded_min
        while t < max_value + rounded_interval:
            if min_value <= t <= max_value:
                tick_values.append(t)
            t += rounded_interval

        # We *could* do something smarter with logs. But will we?
        decimal_places = 0
        if rounded_interval < 0.0001:
            decimal_places = 5
        elif rounded_interval < 0.001:
            decimal_places = 4
        elif rounded_interval < 0.01:
            decimal_places = 3
        elif rounded_interval < 0.1:
            decimal_places = 2
        elif rounded_interval < 1:
            decimal_places = 1

        # print("scaler = {} dps = {}".format(scaler, decimal_places))

        ticks = [(t, int((t - min_value) / (max_value - min_value) * pixel_range + 0.5)) for t in tick_values]

        return ticks, decimal_places


class GraphLayout(Layout):
    """This class knows how to lay out and draw the components of a graph."""

    def __init__(self, font_height, canvas_width, canvas_height):
        super().__init__(font_height, canvas_width, canvas_height)
        self._margin = int(self._font_height * 2)
        self._data_ranges: Optional[Tuple[AxisRange, AxisRange]] = None
        self._data_area = None
        self._x_axis: Optional[AxisLayout] = None
        self._y_axis: Optional[AxisLayout] = None

    def get_data_ranges(self) -> Tuple[AxisRange, AxisRange]:
        return self._data_ranges

    def calc_preferred_time_range(self, sign: int) -> AxisRange:
        return self._x_axis.calc_preferred_range(sign)

    def _get_right_margin(self):
        return self._canvas_width - self._margin, 0, self._canvas_width - 1, self._canvas_height - 1

    def _get_top_margin(self):
        return 0, 0, self._canvas_width - 1, self._margin - 1

    def _get_left_margin(self, axis_size):
        return 0, 0, axis_size - 1, self._canvas_height - 1

    def _get_bottom_margin(self, axis_size):
        return 0, self._canvas_height - 1, self._canvas_width - 1, self._canvas_height - axis_size - 1

    def draw(self, canvas, x_range: AxisRange, y_range: AxisRange, show_grid: bool, zero_based_x_axis: bool):
        """Draw a graph including axes, image and grid. We do this in two phases:
        (1) The axes etc., which are fast to draw, are drawn immediately by this method
        (2) The image and things overlaying it (such as the grid) are drawn later when the image
            has been calculated. A capture is returned that the caller can use later to do this.
        """

        self._data_ranges = x_range, y_range

    def rect_to_values(self, pixel_rect) \
            -> Optional[Tuple[float, float, float, float]]:
        """Scale the pixel rectangle supplied to real axis values."""

        l, t, r, b = pixel_rect
        if self._x_axis and self._y_axis:
            # if clamp:
            vl = self._x_axis.canvas_to_axis(l)
            vr = self._x_axis.canvas_to_axis(r)
            vt = self._y_axis.canvas_to_axis(t)
            vb = self._y_axis.canvas_to_axis(b)
            return vl, vt, vr, vb
        else:
            return None

    def canvas_to_axis(self, p_canvas):
        """Scale the pixel position relative to the canvas origin to real axis values."""

        t_canvas, f_canvas = p_canvas
        if self._x_axis and self._y_axis:
            # We can get the axis values of t and f from the axis scale:
            t_axis = self._x_axis.canvas_to_axis(t_canvas)
            f_axis = self._y_axis.canvas_to_axis(f_canvas)
            return t_axis, f_axis
        else:
            return None

    @staticmethod
    def _draw_graph_image(canvas, data_area, image):
        (il, it, ir, ib) = data_area

        # There may be a right margin to fill, if we are zoomed right out. And
        # rounding errors may result in the image being one pixel short. So, we apply
        # polyfilla around the right and bottom edge.
        image_height, image_width, _ = image.shape
        data_area_width, data_area_height = ir - il + 1, ib - it + 1
        fill_colour: str = colourmap.instance.get_polyfilla_colour()
        if image_width < data_area_width:
            delta = data_area_width - image_width
            canvas.create_rectangle(ir - delta, it, ir, ib, fill=fill_colour, outline=fill_colour)
        if image_height < data_area_height:
            delta = data_area_height - image_height
            canvas.create_rectangle(il, ib - delta, ir, ib, fill=fill_colour, outline=fill_colour)

        inverted_image = Image.fromarray(np.uint8(image)).convert('RGB')
        pil_image = ImageOps.flip(inverted_image)
        image = ImageTk.PhotoImage(pil_image)
        canvas.my_image = image  # Hack to protect the image against garbage collection
        # (see https://web.archive.org/web/20201111190625id_/http://effbot.org/pyfaq/why-do-my-tkinter-images-not-appear.htm)
        canvas.create_image(il, it, image=image, anchor='nw')

    @staticmethod
    def _draw_graph_line_segments(canvas, data_area, line_segments, colour):
        l, t, r, b = data_area
        segments, _ = line_segments.shape
        for i in range(0, segments):
            x1, y1, x2, y2 = line_segments[i]
            x1a, y1a, x2a, y2a = x1 + l, b - y1, x2 + l, b - y2
            canvas.create_line(x1a, y1a, x2a, y2a, fill=colour, width=1, smooth=False)

    @staticmethod
    def _draw_graph_points(canvas, data_area, points, colour):
        l, t, r, b = data_area
        rows, columns = points.shape
        inverted_points = np.zeros_like(points, dtype=np.int16)
        # Perhaps there is a way to do this without unpacking the and reassembling the array?:
        for i in range(0, rows):
            x, y = points[i]
            inverted_points[i] = x + l, b - y
        canvas.create_line(*inverted_points.flatten(), fill=colour, width=1, smooth=True)

        # Layout._create_rectangle(canvas, l, t, r, b, "#800000")

    @staticmethod
    def _draw_x_grid(canvas, x_ticks, data_area):
        l, t, r, b = data_area
        for _, p in x_ticks:
            if p > 0:  # Don't overwrite the axis.
                x_pixels = l + p - 1  # The first x-axis tick is actually over the y-axis
                canvas.create_line(x_pixels, b, x_pixels, t, fill=GRID_COLOUR, width=1, dash=(1, 1))

    @staticmethod
    def _draw_y_grid(canvas, y_ticks, data_area):
        l, t, r, b = data_area
        for v, p in y_ticks:
            if p > 0:  # Don't overwrite the axes.
                y_pixels = b - p + 1  # The first y-axis tick is actually over the xaxis
                canvas.create_line(l, y_pixels, r, y_pixels, fill=GRID_COLOUR, width=1, dash=(1, 1))


@dataclass
class AxisUnit:
    limit: float = sys.float_info.max  # Upper limit for this unit, or sys.float_info.max if it is the default.
    units: str = ""  # The unit.
    scaler: float = 1.0  # Multiples the tick vakues.


class AxisLayout(Layout):
    """This class knows how to lay out and draw a graph axis."""

    ORIENT_VERTICAL = 1
    ORIENT_HORIZONTAL = 2

    def __init__(self, orientation: int, font_height: int, title: str, canvas_width: int,
                 canvas_height: int, units: List[AxisUnit], hide_text: bool = False):
        super().__init__(font_height, canvas_width, canvas_height)
        self._orientation = orientation
        self._title = title
        self._hide_text = hide_text
        self._font_name = "helvetica"
        self._layout()
        self._min_pixel = None
        self._max_pixel = None
        self._axis_range: Optional[AxisRange] = None
        self._units: List[AxisUnit] = sorted(units, key=lambda u: u.limit)  # Ascending.
        self._units_to_use: Optional[AxisUnit] = None

    def _layout(self):
        # These coordinates increase from 0 on the outside to maximum
        # next to the data area.

        unit = self._font_height  # Everything is relative to font size.
        half_unit = int(unit / 2 + 0.5)  # Avoid floating point.

        if self._hide_text:
            self._title_start = half_unit
            self._title_end = half_unit
            self._scale_start = half_unit
            self._scale_end = half_unit
        else:
            self._title_start = half_unit
            self._title_end = self._title_start + unit
            self._scale_start = self._title_end + half_unit
            self._scale_end = self._scale_start + unit
        self._tick_end = self._scale_end + half_unit
        self._tick_start = self._tick_end + half_unit
        self._axis_offset = self._tick_start + 1
        self._size = self._axis_offset

    def get_size(self):
        return self._size

    def draw(self, canvas, x, y, extent, axis_range: AxisRange, zero_based_axis: bool, target_spacing_pixels=100):
        # Note: create_rectangle doesn't include the bottom/right edges, so we have to +1.

        self._axis_range = axis_range

        if zero_based_axis:
            # Offset the time ticks so that they always start at zero:
            offset_axis_range = AxisRange(0, self._axis_range.max - self._axis_range.min)
        else:
            offset_axis_range = self._axis_range

        # Decide what units to use based on the axis range:
        u = self._get_units(offset_axis_range)

        (ticks, decimal_places) = self.calculate_ticks(offset_axis_range, u.scaler, extent,
                                                       target_spacing_pixels=target_spacing_pixels)

        # Negative font height is in pixels:
        axis_font = (self._font_name, -self._font_height)

        text: str = "{} ({})".format(self._title, u.units)

        if self._orientation == self.ORIENT_VERTICAL:
            Layout._create_rectangle(canvas, x, y, self._size - 1, y + extent, AXIS_BG_COLOUR)
            # Line seems to need a +1 to reach the final pixel:
            canvas.create_line([(x + self._axis_offset - 1, y), (x + self._axis_offset - 1, y + extent + 1)],
                               fill=AXIS_FG_COLOUR, width=1)
            if not self._hide_text:
                canvas.create_text(x + self._title_start, x + extent / 2, text=text, fill=AXIS_FG_COLOUR,
                                   angle=90, font=axis_font, anchor=tk.N)
            for v, p in ticks:
                canvas.create_line(x + self._tick_end, y + extent - p, x + self._tick_start, y + extent - p,
                                   fill=AXIS_FG_COLOUR, width=1)
                if not self._hide_text:
                    canvas.create_text(x + self._scale_start, y + extent - p,
                                       text="{0:.{dps}f}".format(float(v), dps=decimal_places), angle=90,
                                       fill=AXIS_FG_COLOUR, font=axis_font, anchor=tk.N)
            self._min_pixel = y + extent  # Pixel that corresponds to the minimum axis value
            self._max_pixel = y

        if self._orientation == self.ORIENT_HORIZONTAL:
            Layout._create_rectangle(canvas, x, y, x + extent, y + self._size - 1, AXIS_BG_COLOUR)
            # Line seems to need a +1 to reach the final pixel:
            canvas.create_line([(x, y), (x + extent + 1, y)], fill=AXIS_FG_COLOUR, width=1)
            if not self._hide_text:
                canvas.create_text(x + extent / 2, y + self._size - self._title_end, text=text,
                                   fill=AXIS_FG_COLOUR,
                                   font=axis_font, anchor=tk.N)
            for t, p in ticks:
                canvas.create_line(x + p, y + self._size - self._tick_end, x + p, y + self._size - self._tick_start,
                                   fill=AXIS_FG_COLOUR, width=1)
                if not self._hide_text:
                    canvas.create_text(x + p, y + self._size - self._scale_end,
                                       text="{0:.{dps}f}".format(float(t), dps=decimal_places), fill=AXIS_FG_COLOUR,
                                       font=axis_font, anchor=tk.N)
            self._min_pixel = x  # Pixel that corresponds to the minimum axis value
            self._max_pixel = x + extent

        return ticks

    def canvas_to_axis(self, p):
        v = (p - self._min_pixel) / (self._max_pixel - self._min_pixel) * (
                self._axis_range.max - self._axis_range.min) + self._axis_range.min
        return v

    def get_axis_range(self) -> AxisRange:
        return self._axis_range

    def _get_units(self, axis_range) -> AxisUnit:
        """Decide what units to use based on the axis range."""

        if len(self._units) == 1:
            return self._units[0]
        else:
            abs_max: float = max(abs(axis_range.min), abs(axis_range.max))
            # The possible units are already sorted in ascending order.
            u = self._units[0]      # Avoid a warning.
            for u in self._units:
                if abs_max < u.limit:
                    return u
            return u

    _preferred_ms_per_100pixels = [1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1000.0, 2000.0, 5000.0]

    def calc_preferred_range(self, sign: int) -> AxisRange:
        """Calculate a preset axis range that is next large (or smaller) than the current range."""

        #
        # We want the total time span to result in one of these peferred ranges.
        #   1, 2, 5, 10, 20, 50 etc ms per 100 pixels.
        # so (time range) / (data_width_pixels) = preset value
        #
        # The supplied sign tells us whether we are aiming to zoom in or out relative to the current.
        # Positive sign increases the axis range.
        #

        current_range = self._axis_range
        centre = (current_range.min + current_range.max) / 2
        span = current_range.max - current_range.min
        pixel_span = self._max_pixel - self._min_pixel

        # Calculate the current scaling, that we went to round up or down to preferred:
        ms_per_100pixels = span * 100.0 * 1000.0 / pixel_span
        new_ms_per_100pixels = ms_per_100pixels     # Default - no change.

        nudge_factor = 1.05     # Slight fudge in case the current range is a preferred range.
        if sign > 0:
            # We want to increase and round the range:
            nudged_ms_per_100pixels = ms_per_100pixels * nudge_factor
            for preferred in self._preferred_ms_per_100pixels:
                if nudged_ms_per_100pixels < preferred:
                    new_ms_per_100pixels = preferred
                    break
            # Otherwise, the range is already larger than the largest, no change.
            pass
        elif sign < 0:
            # We want to decrease and round the range:
            nudged_ms_per_100pixels = ms_per_100pixels / nudge_factor
            for preferred in reversed(self._preferred_ms_per_100pixels):
                if nudged_ms_per_100pixels > preferred:
                    new_ms_per_100pixels = preferred
                    break
            # Otherwise, the range is already smaller than the smallest, no change.
            pass

        new_span = new_ms_per_100pixels * pixel_span / (100.0 * 1000.0)
        # print("Prefered {} -> {}".format(span, new_span))

        # The new span might go beyond the range of the actual data, but it will
        # be clipped by the caller.

        return AxisRange(centre - new_span / 2, centre + new_span / 2)


class SpectrogramLayout(GraphLayout):
    """This Layout knows how to lay out and raw a spectrogram."""

    _x_axis_unit = [AxisUnit(scaler=1.0, units="s"),  # Default
                    AxisUnit(limit=0.5, scaler=1E-3, units="ms")
                    ]
    _y_axis_unit = [AxisUnit(scaler=1000.0, units="kHz")]

    def __init__(self, font_height, canvas_width, canvas_height):
        super().__init__(font_height, canvas_width, canvas_height)
        self._x_axis = AxisLayout(AxisLayout.ORIENT_HORIZONTAL, font_height, "time", canvas_width,
                                  canvas_height, self._x_axis_unit)
        self._y_axis = AxisLayout(AxisLayout.ORIENT_VERTICAL, font_height, "frequency", canvas_width,
                                  canvas_height, self._y_axis_unit, hide_text=False)
        self._layout()

    def _layout(self):
        self._x_axis_height = self._x_axis.get_size()
        self._y_axis_width = self._y_axis.get_size()

        # Calculate some *inclusive* zero based rectangle coords:
        self._data_area = (
            self._y_axis_width, self._margin, self._canvas_width - self._margin - 1,
            self._canvas_height - self._x_axis_height - 1)
        self._dead_space = (
            0, self._canvas_height - self._x_axis_height, self._y_axis_width - 1, self._canvas_height - 1)

    def draw(self, canvas, x_range: AxisRange, y_range: AxisRange, show_grid, zero_based_x_axis: bool):
        super().draw(canvas, x_range, y_range, show_grid, zero_based_x_axis)

        """Draw a graph including axes, image and grid. We do this in two phases:
        (1) The axes etc, which are fast to draw, are drawn immediately by this method
        (2) The image and things overlaying it (such as the grid) are drawn later when the image
            has been calculated. A capture is returned that the caller can use later to do this.
        """

        # We draw things in a specific order so that some things appear on top of others.

        # First blank out the entire canvas to avoid leftovers being visible when resizing:
        Layout._create_rectangle(canvas, 0, 0, self._canvas_width, self._canvas_height, 'black')

        # Fill the margins and the bit of dead space in the bottom left:
        (t, l, r, b) = self._dead_space
        Layout._create_rectangle(canvas, t, l, r, b, AXIS_BG_COLOUR)

        Layout._create_rectangle(canvas, *self._get_right_margin(), AXIS_BG_COLOUR)
        Layout._create_rectangle(canvas, *self._get_top_margin(), AXIS_BG_COLOUR)

        # Draw the axes:
        (yaxis_x, yaxis_y, yaxis_extent) = (0, self._margin, self._canvas_height - self._x_axis_height - self._margin)
        y_ticks = self._y_axis.draw(canvas, yaxis_x, yaxis_y, yaxis_extent, y_range, zero_based_axis=False)

        (xaxis_x, xaxis_y, xaxis_extent) = (
            self._y_axis_width - 1, self._canvas_height - self._x_axis.get_size(),
            self._canvas_width - self._y_axis_width - self._margin)
        x_ticks = self._x_axis.draw(canvas, xaxis_x, xaxis_y, xaxis_extent, x_range, zero_based_axis=zero_based_x_axis)

        # Create a capture that can be used to finish drawing the graph later on, when the image
        # is available:
        def draw_completer(is_memory_limit_hit: bool = False, image=None):
            # width, height = canvas.winfo_width(), canvas.winfo_height()

            if is_memory_limit_hit:
                l1, t1, r1, b1 = self._data_area
                canvas.create_text((l1 + r1) / 2, (t1 + b1) / 2,
                                   text="Insufficient memory to render this spectrogram.\n"
                                        + "Try reducing the time range and FFT overlap.",
                                   fill="grey")
            # Draw the actual data:
            elif image is not None:
                self._draw_graph_image(canvas, self._data_area, image)

            if show_grid:
                self._draw_x_grid(canvas, x_ticks, self._data_area)
                self._draw_y_grid(canvas, y_ticks, self._data_area)

        return draw_completer, self._data_area

    def canvas_to_data_area(self, p_canvas):
        """Finded the zoomed data value corresponding to the canvas point provided."""

        t_canvas, f_canvas = p_canvas
        if self._x_axis and self._y_axis:
            # Calculate the data area coordinates:
            t_data_area = t_canvas - self._y_axis.get_size()
            f_data_area = self._canvas_height - f_canvas - self._x_axis.get_size()

            return t_data_area, f_data_area
        else:
            return None


class AmplitudeLayout(GraphLayout):
    """This Layout knows how to lay out and raw an amplitude graph."""

    _x_axis_unit = [AxisUnit()]
    _y_axis_unit = [AxisUnit()]

    def __init__(self, font_height, canvas_width, canvas_height, is_reference=False):
        super().__init__(font_height, canvas_width, canvas_height)
        self._is_reference = is_reference
        self._x_axis = AxisLayout(AxisLayout.ORIENT_HORIZONTAL, font_height, "time", canvas_width,
                                  canvas_height, units=self._x_axis_unit)
        self._y_axis = AxisLayout(AxisLayout.ORIENT_VERTICAL, font_height, "amplitude", canvas_width,
                                  canvas_height, units=self._y_axis_unit, hide_text=False)
        self._layout()

    def _layout(self):
        self._x_axis_height = self._x_axis.get_size()
        self._y_axis_width = self._y_axis.get_size()

        # Calculate some *inclusive* zero based rectangle coords:
        self._data_area = (
            self._y_axis_width, 0, self._canvas_width - self._margin - 1, self._canvas_height)

    def draw(self, canvas, x_range: AxisRange, y_range: AxisRange, show_grid: bool, zero_based_x_axis: bool = False):
        super().draw(canvas, x_range, y_range, show_grid, zero_based_x_axis)

        """Draw a graph including axes, image and grid. We do this in two phases:
        (1) The axes etc, which are fast to draw, are drawn immediately by this method
        (2) The image and things overlaying it (such as the grid) are drawn later when the image
            has been calculated. A capture is returned that the caller can use later to do this.
        """

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        # We draw things in a specific order so that some things appear on top of others.

        # First blank out the entire canvas to avoid leftovers being visible when resizing:
        Layout._create_rectangle(canvas, 0, 0, width, height, 'black')

        # Fill the margins:
        Layout._create_rectangle(canvas, *self._get_right_margin(), AXIS_BG_COLOUR)
        Layout._create_rectangle(canvas, *self._get_left_margin(self._y_axis_width), AXIS_BG_COLOUR)

        xaxis_x, xaxis_extent = self._y_axis_width - 1, width - self._y_axis_width - self._margin
        x_ticks, _ = self._x_axis.calculate_ticks(x_range, 1, xaxis_extent)

        # Create a capture that can be used to finish drawing the graph later on, when the image
        # is available:
        def draw_followup(is_memory_limit_hit: bool = False, line_segments=None):
            # Reblank the data area in case the two phases of drawing got out of order, to
            # avoid multiple data appearing on the same axis:
            l, t, r, b = self._data_area
            Layout._create_rectangle(canvas, l, t, r, b, 'black')

            if not is_memory_limit_hit:

                # Draw the actual data:
                line_colour = "#00FFFF"
                if line_segments is not None:
                    self._draw_graph_line_segments(canvas, self._data_area, line_segments, line_colour)

                if show_grid:
                    self._draw_x_grid(canvas, x_ticks, self._data_area)

        return draw_followup, self._data_area


class ProfileLayout(GraphLayout):
    """This Layout knows how to lay out and raw a profile graph."""

    _x_axis_unit = [AxisUnit()]
    _y_axis_unit = [AxisUnit()]

    def __init__(self, font_height, canvas_width, canvas_height):
        super().__init__(font_height, canvas_width, canvas_height)
        self._x_axis = AxisLayout(AxisLayout.ORIENT_HORIZONTAL, font_height, "dB", canvas_width,
                                  canvas_height, units=self._x_axis_unit)
        self._y_axis = AxisLayout(AxisLayout.ORIENT_VERTICAL, font_height, "frequency (kHz)", canvas_width,
                                  canvas_height, units=self._y_axis_unit, hide_text=True)
        self._layout()

    def _layout(self):
        self._x_axis_height = self._x_axis.get_size()
        self._y_axis_width = self._y_axis.get_size()

        # Calculate some *inclusive* zero based rectangle coords:
        self._data_area = (
            self._y_axis_width, self._margin, self._canvas_width - self._margin - 1,
            self._canvas_height - self._x_axis_height - 1)
        self._dead_space = (
            0, self._canvas_height - self._x_axis_height, self._y_axis_width - 1, self._canvas_height - 1)

    def draw(self, canvas, x_range: AxisRange, y_range: AxisRange, show_grid: bool, zero_based_x_axis: bool):
        super().draw(canvas, x_range, y_range, show_grid, zero_based_x_axis)

        """Draw a graph including axes, image and grid. We do this in two phases:
        (1) The axes etc, which are fast to draw, are drawn immediately by this method
        (2) The image and things overlaying it (such as the grid) are drawn later when the image
            has been calculated. A capture is returned that the caller can use later to do this.
        """

        width = canvas.winfo_width()
        height = canvas.winfo_height()

        # We draw things in a specific order so that some things appear on top of others.

        # First blank out the entire canvas to avoid leftovers being visible when resizing:
        Layout._create_rectangle(canvas, 0, 0, width, height, 'black')

        # Fill the margins:
        Layout._create_rectangle(canvas, *self._get_top_margin(), AXIS_BG_COLOUR)
        Layout._create_rectangle(canvas, *self._get_right_margin(), AXIS_BG_COLOUR)
        Layout._create_rectangle(canvas, *self._dead_space, AXIS_BG_COLOUR)

        # Draw the axes:
        (yaxis_x, yaxis_y, yaxis_extent) = (0, self._margin, self._canvas_height - self._x_axis_height - self._margin)
        y_ticks = self._y_axis.draw(canvas, yaxis_x, yaxis_y, yaxis_extent, y_range, zero_based_axis=False)

        (xaxis_x, xaxis_y, xaxis_extent) = (
            self._y_axis_width - 1, self._canvas_height - self._x_axis.get_size(),
            self._canvas_width - self._y_axis_width - self._margin)
        x_ticks = self._x_axis.draw(canvas, xaxis_x, xaxis_y, xaxis_extent, x_range, zero_based_axis=zero_based_x_axis)

        # Create a capture that can be used to finish drawing the graph later on, when the image
        # is available:
        def draw_followup(is_memory_limit_hit: bool = False, points=None,
                          axis_range: AxisRange = AxisRange(rmin=0, rmax=1)):
            # Reblank the data area in case the two phases of drawing got out of order, to
            # avoid multiple data appearing on the same axis:
            l, t, r, b = self._data_area
            Layout._create_rectangle(canvas, l, t, r, b, 'black')

            # Redraw the x xaxis and adjacent margins, now that we know its range:
            Layout._create_rectangle(canvas, *self._get_right_margin(), AXIS_BG_COLOUR)
            Layout._create_rectangle(canvas, *self._dead_space, AXIS_BG_COLOUR)
            if not is_memory_limit_hit:
                new_x_ticks = self._x_axis.draw(canvas, xaxis_x, xaxis_y, xaxis_extent, axis_range,
                                                target_spacing_pixels=40, zero_based_axis=zero_based_x_axis)

                # Draw the actual data:
                if points is not None:
                    self._draw_graph_points(canvas, self._data_area, points, '#00FFFF')

                if show_grid:
                    self._draw_y_grid(canvas, y_ticks, self._data_area)
                    self._draw_x_grid(canvas, new_x_ticks, self._data_area)

        return draw_followup, self._data_area
