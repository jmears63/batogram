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
from abc import ABC, abstractmethod
from typing import Tuple, Optional, Callable, Type, List

from .constants import AXIS_FONT_NAME, AXIS_FONT_HEIGHT
from .common import AxisRange, clip_to_range, AreaTuple, RangeTuple

MARKER_COLOUR = "#808000"
MARKER_DRAGGER_COLOUR = "#FFFF00"
BAND_COLOUR = "#606000"
MARKER_TEXT_COLOUR = "#FFFF00"

TAN60: float = 1.73  # tan(60), used for drawing triangles.
AXIS_FONT = AXIS_FONT_NAME, -AXIS_FONT_HEIGHT
LR_DRAG_CURSOR = "sb_h_double_arrow"
UD_DRAG_CURSOR = "sb_v_double_arrow"
CLEARANCE_PIXELS = 15


class AbstractHelper(ABC):
    def __init__(self, tag_name: str):
        self._band_id: Optional[int] = None
        self._band_text_ids: List[int] = []
        self._lower_overflow_id: Optional[int] = None
        self._upper_overflow_id: Optional[int] = None
        self._tag_name: str = tag_name

    @abstractmethod
    def get_pixel_range(self, rect: AreaTuple) -> RangeTuple:
        """Get the pixel value range in an order that matches
        the axis low and high values: left is low, down is low.
        """
        raise NotImplementedError()

    @abstractmethod
    def get_line_span(self, rect: AreaTuple) -> RangeTuple:
        raise NotImplementedError()

    @abstractmethod
    def make_band_rect(self, band_pixel_width: RangeTuple, band_pixel_length: RangeTuple,
                       axis_pixel_range: RangeTuple) -> Tuple[AreaTuple, Tuple[bool, bool]]:
        raise NotImplementedError()

    @abstractmethod
    def draw_text_impl(self, canvas: "SpectrogramCanvas", band_rect: AreaTuple,
                       text: List[str], is_clipped: Tuple[bool, bool]) -> List[int]:
        raise NotImplementedError()

    @abstractmethod
    def draw_overflows(self, canvas: "SpectrogramCanvas", band_pixel_width: RangeTuple,
                       band_pixel_length: RangeTuple, axis_pixel_range: RangeTuple):
        raise NotImplementedError()

    def draw_band(self, canvas: "SpectrogramCanvas", band_pixel_length: [RangeTuple],
                  band_pixel_width: [RangeTuple],
                  axis_pixel_range: RangeTuple, text: List[str]) -> Tuple[AreaTuple, Tuple[bool, bool]]:
        """Draw a band connecting the markers. Deal with all situations including the band being partly
        or wholly outside the range of the axis."""

        # Get the rectangle for the band. The first coordinate pair is for the lower axis value;
        # the second for the upper. Width coords are in increasing order.
        band_rect: AreaTuple
        is_clipped: Tuple[bool, bool]
        band_rect, is_clipped = self.make_band_rect(band_pixel_width, band_pixel_length, axis_pixel_range)

        # Actually draw it:
        self._band_id = self._draw_band_impl(canvas, band_rect)
        self._band_text_ids = self.draw_text_impl(canvas, band_rect, text, is_clipped)

        # Draw overflow symbols if either end of the band is outside the range of the axis:
        self.draw_overflows(canvas, band_pixel_width, band_pixel_length, axis_pixel_range)

        return band_rect, is_clipped

    def redraw_band(self, canvas: "SpectrogramCanvas", band_rect: AreaTuple,
                    text: List[str], is_clipped: Tuple[bool, bool]):
        """Redraw an existing band, as a result of an end marker being moved."""

        # Create the new canvas widgets, then delete the existing ones. This allows us to layer
        # the new ones relative to the existing ones.

        new_band_id = self._draw_band_impl(canvas, band_rect)
        new_text_ids = self.draw_text_impl(canvas, band_rect, text, is_clipped)

        to_delete = [self._band_id, self._lower_overflow_id, self._upper_overflow_id]
        to_delete.extend(self._band_text_ids)

        # Move it beneath any existing band, before we delete the existing one, to preserve layering order:
        if self._band_id is not None and new_band_id is not None:
            canvas.tag_lower(new_band_id, self._band_id)

        # Delete all the old things:
        [canvas.delete(item) for item in to_delete if item is not None]

        self._band_id = new_band_id
        self._band_text_ids = new_text_ids

    def _draw_band_impl(self, canvas: "SpectrogramCanvas", band_rect: AreaTuple) -> RangeTuple:
        band_id = canvas.create_rectangle(*band_rect, fill=BAND_COLOUR, outline=BAND_COLOUR,
                                          stipple='gray25', tags=[self._tag_name])
        return band_id


class TimeHelper(AbstractHelper):
    _TIME_BAND_TAG_NAME: str = "time_band"

    def __init__(self):
        super().__init__(self._TIME_BAND_TAG_NAME)

    def get_pixel_range(self, rect: AreaTuple) -> RangeTuple:
        """Get the range of pixel values corresponding to axis range."""

        # In the order that matches the axis low and high value:
        return rect[0], rect[2]

    def get_line_span(self, rect: AreaTuple) -> RangeTuple:
        """Get the range of pixel values corresponding to the line we well draw.."""
        return rect[1], rect[3]

    def make_band_rect(self, band_pixel_width: RangeTuple, band_pixel_length: RangeTuple,
                       axis_pixel_range: RangeTuple) -> Tuple[AreaTuple, Tuple[bool, bool]]:
        # Clip the band to the pixel range available:
        # Make sure the band length is at least 1, so there is always something to draw. This makes
        # other code simpler.
        lower, upper = band_pixel_length
        lower_clipped, upper_clipped = False, False

        if lower < axis_pixel_range[0]:
            lower = axis_pixel_range[0]
            lower_clipped = True
        if upper > axis_pixel_range[1]:
            upper = axis_pixel_range[1]
            upper_clipped = True
        if upper <= lower:
            upper = lower + 1

        return (lower, band_pixel_width[1], upper, band_pixel_width[0]), (lower_clipped, upper_clipped)

    def draw_text_impl(self, canvas: "SpectrogramCanvas", band_rect: AreaTuple,
                       text: List[str], is_clipped: Tuple[bool, bool]) -> List[int]:
        l, t, r, b = band_rect
        text_id = None
        if len(text) > 0 and not is_clipped[0] and not is_clipped[1]:
            text_id = None
            min_space_for_text = 60
            if r - l > min_space_for_text:
                # Annotation. +2 to get the text inside the band. Me neither.
                text_id = canvas.create_text(int((l + r) / 2), int((b + t) / 2 + 2), text=text[0],
                                             fill=MARKER_TEXT_COLOUR, font=AXIS_FONT, anchor=tk.CENTER)

        return [text_id]

    def draw_overflows(self, canvas: "SpectrogramCanvas", band_pixel_width: RangeTuple,
                       band_pixel_length: RangeTuple, axis_pixel_range: RangeTuple):
        if band_pixel_length[0] < axis_pixel_range[0]:
            self._lower_overflow_id = self._draw_lower_overflow(canvas, axis_pixel_range[0], band_pixel_width)
        if band_pixel_length[1] > axis_pixel_range[1]:
            self._upper_overflow_id = self._draw_upper_overflow(canvas, axis_pixel_range[1], band_pixel_width)

    @staticmethod
    def _draw_lower_overflow(canvas: "SpectrogramCanvas", p: int, band_pixel_width: RangeTuple) -> int:
        w0, w1 = band_pixel_width
        return canvas.create_polygon(
            p, w0, p - abs(w0 - w1) / 1.3, int((w0 + w1) / 2), p, w1,
            fill=MARKER_DRAGGER_COLOUR, outline=MARKER_DRAGGER_COLOUR)

    @staticmethod
    def _draw_upper_overflow(canvas: "SpectrogramCanvas", p: int, band_pixel_width: RangeTuple) -> int:
        w0, w1 = band_pixel_width
        return canvas.create_polygon(
            p, w0, p + abs(w0 - w1) / 1.3, int((w0 + w1) / 2), p, w1,
            fill=MARKER_DRAGGER_COLOUR, outline=MARKER_DRAGGER_COLOUR)


class FrequencyHelper(AbstractHelper):
    _FREQUENCY_BAND_TAG_NAME: str = "frequency_band"

    def __init__(self):
        super().__init__(self._FREQUENCY_BAND_TAG_NAME)

    def get_pixel_range(self, rect: AreaTuple) -> RangeTuple:
        """Get the range of pixel values corresponding to axis range."""

        # In the order that matches the axis low and high value:
        lower, upper = rect[1], rect[3]
        if lower < upper:
            temp = lower
            lower = upper
            upper = temp
        return lower, upper

    def get_line_span(self, rect: AreaTuple) -> RangeTuple:
        """Get the range of pixel values corresponding to the line we well draw.."""
        return rect[0], rect[2]

    def make_band_rect(self, band_pixel_width: RangeTuple, band_pixel_length: RangeTuple,
                       axis_pixel_range: RangeTuple) -> Tuple[AreaTuple, Tuple[bool, bool]]:
        # Clip the band to the pixel range available:
        # Make sure the band length is at least 1, so there is always something to draw. This makes
        # other code simpler.
        lower, upper = band_pixel_length
        lower_clipped, upper_clipped = False, False

        if lower > axis_pixel_range[0]:
            lower = axis_pixel_range[0]
            lower_clipped = True
        if upper < axis_pixel_range[1]:
            upper = axis_pixel_range[1]
            upper_clipped = True
        if upper >= lower:
            upper = lower - 1

        return (band_pixel_width[0], lower, band_pixel_width[1], upper), (lower_clipped, upper_clipped)

    def draw_text_impl(self, canvas: "SpectrogramCanvas", band_rect: AreaTuple,
                       text: List[str], is_clipped: Tuple[bool, bool]) -> List[int]:
        text_ids = []
        if len(text) == 2:
            l, t, r, b = band_rect
            delta = 2  # Avoid crowding.
            if not is_clipped[0]:
                text_ids.append(canvas.create_text(l - delta, t, text=text[0],
                                                   fill=MARKER_TEXT_COLOUR, font=AXIS_FONT, anchor=tk.SE))
            if not is_clipped[1]:
                text_ids.append(canvas.create_text(l - delta, b, text=text[1],
                                                   fill=MARKER_TEXT_COLOUR, font=AXIS_FONT, anchor=tk.SE))

        return text_ids

    def draw_overflows(self, canvas: "SpectrogramCanvas", band_pixel_width: RangeTuple,
                       band_pixel_length: RangeTuple, axis_pixel_range: RangeTuple):
        if band_pixel_length[0] > axis_pixel_range[0]:
            self._lower_overflow_id = self._draw_lower_overflow(canvas, axis_pixel_range[0], band_pixel_width)
        if band_pixel_length[1] < axis_pixel_range[1]:
            self._upper_overflow_id = self._draw_upper_overflow(canvas, axis_pixel_range[1], band_pixel_width)

    @staticmethod
    def _draw_lower_overflow(canvas: "SpectrogramCanvas", p: int, band_pixel_width: RangeTuple) -> int:
        w0, w1 = band_pixel_width
        return canvas.create_polygon(
            w0, p,
            int((w0 + w1) / 2), p + abs(w0 - w1) / 1.3,
            w1, p,
            fill=MARKER_DRAGGER_COLOUR, outline=MARKER_DRAGGER_COLOUR)

    @staticmethod
    def _draw_upper_overflow(canvas: "SpectrogramCanvas", p: int, band_pixel_width: RangeTuple) -> int:
        w0, w1 = band_pixel_width
        return canvas.create_polygon(
            w0, p,
            int((w0 + w1) / 2), p - abs(w0 - w1) / 1.3,
            w1, p,
            fill=MARKER_DRAGGER_COLOUR, outline=MARKER_DRAGGER_COLOUR)


class AbstractMarker(ABC):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "Type[AbstractMarkerPair]", sgf: "SpectrogramGraphFrame",
                 initial_axis_value: Optional[float], tag_name: str, get_other: Callable,
                 helper: Type[AbstractHelper], drag_curser: str):
        self._axis_value: Optional[float] = initial_axis_value
        self._pixel_value: Optional[int] = None
        self._pair = pair
        self._sgf = sgf
        self._tag_name: str = tag_name
        self._canvas: "SpectrogramCanvas" = canvas
        self._start_event = None
        self._saved_cursor = None
        self._polygon_id = None
        self._line = None
        self._get_other = get_other
        self._pixel_range: Optional[RangeTuple] = None
        self._axis_range: Optional[AxisRange] = None
        self._helper: Type[AbstractHelper] = helper
        self._drag_curser = drag_curser

        # The mouse is used to drag the markers:
        canvas.tag_bind(self._tag_name, "<Enter>", lambda event: self._mouse_enters_dragger(event))
        canvas.tag_bind(self._tag_name, "<Leave>", lambda event: self._mouse_leaves_dragger(event))
        canvas.tag_bind(self._tag_name, "<Button-1>", lambda event: self._on_click(event))
        canvas.tag_bind(self._tag_name, "<B1-Motion>", lambda event: self._on_move(event))
        canvas.tag_bind(self._tag_name, "<ButtonRelease-1>", lambda event: self._on_release(event))

    @abstractmethod
    def create_drawer(self, marker_rect: AreaTuple, pixel_value: int, line_span: RangeTuple) \
            -> Tuple[Callable, RangeTuple]:
        """Create a callable for drawing the marker, returning also the width of the marker drawn."""
        raise NotImplementedError()

    @abstractmethod
    def get_allowed_for_other(self) -> Tuple[Optional[int], Optional[int]]:
        """Get the axis pixel range that the other marker is allowed to be in. This is used
        to prevent the markers being dragged past each other or off the end."""
        raise NotImplementedError()

    @abstractmethod
    def do_move(self, pixel_current: int):
        """Move the marker by the pixel offset provided."""
        raise NotImplementedError()

    @abstractmethod
    def get_pixels_dragged(self, event, start_event):
        """Get the pixel distance dragged between the two events supplied."""
        raise NotImplementedError()

    def draw(self, marker_rect: AreaTuple, data_rect: AreaTuple,
             margin: int, axis_range: AxisRange) -> Tuple[Callable, RangeTuple]:
        """Draw the marker, and return the coordinates of the end of the connecting band."""

        # Note some things for use during dragging:
        self._pixel_range = self._helper.get_pixel_range(data_rect)
        line_span: RangeTuple = self._helper.get_line_span(data_rect)
        self._axis_range = axis_range

        pixel_value = self._value_to_pixel(self._axis_value)
        self._pixel_value = pixel_value

        return self.create_drawer(marker_rect, pixel_value, line_span)

    def get_pixel_value(self) -> Optional[int]:
        """Return the current pixel position of the marker."""
        return self._pixel_value

    def get_axis_value(self) -> Optional[float]:
        """Return the current axis value of the marker."""
        return self._axis_value

    def _mouse_enters_dragger(self, _):
        # Only if we aren't currently dragging - avoids cursor flicker during the drag.
        if self._start_event is None:
            self._saved_cursor = self._canvas.config('cursor')[-1]
            self._canvas.config(cursor=self._drag_curser)

    def _mouse_leaves_dragger(self, _):
        # Only if we aren't currently dragging - avoids cursor flicker during the drag.
        if self._start_event is None and self._saved_cursor is not None:
            self._canvas.config(cursor=self._saved_cursor)
            self._saved_cursor = None

    def set_position(self, value: float):
        self._axis_value = value

    def _on_click(self, event):
        # print("_on_click: {}".format(event))
        self._start_event = event
        self._start_pixel_value = self._pixel_value

        # Set the cursor at the canvas level so it doesn't flicker during dragging:
        self._canvas.config(cursor=self._drag_curser)

        # Ask the other marker how much space we have to drag in:
        self._allowed_range = self._get_other().get_allowed_for_other()

        # Take control of the mouse away from the canvas:
        self._canvas.preempt_mouse(True)

    def _on_move(self, event):
        # print("TimeMarker._on_move: {}".format(event))

        # Event contains the coordinate of the current mouse position, not a delta.

        pixel_resulting = self._calc_dragged(event)
        # print("pixel_resulting = {}".format(x_resulting))

        self.do_move(pixel_resulting)

    def _on_release(self, event):
        # print("_on_release: {}".format(event))

        # In case we somehow miss the last move:
        self._on_move(event)

        # Reset ready for another drag:
        self._allowed_range = None
        self._start_event = None

        # Return control of the mouse to the canvas:
        self._canvas.preempt_mouse(False)

    def _calc_dragged(self, event) -> int:
        """Figure out by how far they have dragged, clipping that to the allowed range."""

        # How far have we dragged since the start?
        pixels_dragged = self.get_pixels_dragged(event, self._start_event)

        # Note that the event x is not the exact dragger position, it is where
        # the user clicked in the dragger, so most likely off centre. So, we apply the
        # delta to our start position:
        pixels_resulting = self._start_pixel_value + pixels_dragged

        # Avoid colliding with the other marker:
        r_min, r_max = self._allowed_range
        if r_min is not None and pixels_resulting < r_min:
            pixels_resulting = r_min
        if r_max is not None and pixels_resulting > r_max:
            pixels_resulting = r_max

        # Confine to the pixel range of the axis:
        pixels_resulting = self._pair.clip_to_pixel_range(pixels_resulting)

        return pixels_resulting

    def _value_to_pixel(self, v: float) -> int:
        """Convert the supplied axis value to a pixel value."""
        lower, upper = self._pixel_range
        p = int((v - self._axis_range.min) / (self._axis_range.max - self._axis_range.min) * (upper - lower) + lower)
        return p

    def _pixel_to_value(self, p: int) -> float:
        """Convert the supplied pixel value to an axis value."""
        lower, upper = self._pixel_range
        v = (p - lower) / (upper - lower) * (self._axis_range.max - self._axis_range.min) + self._axis_range.min
        return v


class TimeMarker(AbstractMarker, ABC):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "Type[AbstractMarkerPair]", sgf: "SpectrogramGraphFrame",
                 initial_axis_value: Optional[float], tag_name: str, get_other: Callable,
                 helper: Type[AbstractHelper]):
        super().__init__(canvas, pair, sgf, initial_axis_value, tag_name, get_other, helper, LR_DRAG_CURSOR)

    def create_drawer(self, marker_rect: AreaTuple, pixel_value: int, line_span: RangeTuple) \
            -> Tuple[Callable, RangeTuple]:
        marker_l, marker_t, marker_r, marker_b = marker_rect
        dragger_height = int(abs(marker_t - marker_b) / 2)
        line_lower, line_upper = line_span

        # Create a closure to actually draw the marker:
        def drawer() -> int:
            lower, upper = self._pixel_range
            if lower < pixel_value < upper:
                self._line = self._canvas.create_line(pixel_value, line_lower, pixel_value, line_upper,
                                                      fill=MARKER_COLOUR, width=1, dash=(2, 2))

                # Draw the dragger:
                self._polygon_id = None
                w = int(dragger_height / TAN60)
                self._polygon_id = self._canvas.create_polygon(
                    pixel_value, marker_b,
                    pixel_value + w, marker_b - dragger_height,
                    pixel_value - w, marker_b - dragger_height,
                    fill=MARKER_DRAGGER_COLOUR,
                    outline=MARKER_DRAGGER_COLOUR,
                    tags=[self._tag_name])

                return self._polygon_id

        return drawer, (marker_b, marker_b - dragger_height)

    def do_move(self, x_current: int):
        # Move the dragger object in the canvas, using the intrinsic move method
        # which presumably is the most efficient way:
        x_previous = self._pixel_value
        dx = x_current - x_previous
        self._canvas.move(self._polygon_id, dx, 0)
        self._canvas.move(self._line, dx, 0)
        self._pixel_value = x_current
        self._axis_value = self._pixel_to_value(x_current)

    def get_pixels_dragged(self, event, start_event):
        return event.x - start_event.x


class LowerTimeMarker(TimeMarker):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "Type[AbstractMarkerPair]", sgf: "SpectrogramGraphFrame",
                 axis_value: Optional[float], get_other: Callable, helper: Type[AbstractHelper]):
        super().__init__(canvas, pair, sgf, axis_value, "lower_marker", get_other, helper)

    def do_move(self, x: int):
        super().do_move(x)
        # Notify the pair to redraw the band before we move the marker:
        self._pair.do_move_lower(x)

    def get_allowed_for_other(self) -> Tuple[Optional[int], Optional[int]]:
        # The other marker needs to be higher than this one.
        return self.get_pixel_value() + CLEARANCE_PIXELS, None


class UpperTimeMarker(TimeMarker):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "Type[AbstractMarkerPair]", sgf: "SpectrogramGraphFrame",
                 axis_value: Optional[float], get_other: Callable, helper: Type[AbstractHelper]):
        super().__init__(canvas, pair, sgf, axis_value, "upper_marker", get_other, helper)

    def do_move(self, x: int):
        super().do_move(x)
        # Notify the pair to redraw the band before we move the marker:
        self._pair.do_move_upper(x)

    def get_allowed_for_other(self) -> Tuple[Optional[int], Optional[int]]:
        # The other marker needs to be lower than us.
        return None, self.get_pixel_value() - CLEARANCE_PIXELS


class FrequencyMarker(AbstractMarker, ABC):

    def __init__(self, canvas: "SpectrogramCanvas", pair: "Type[AbstractMarkerPair]", sgf: "SpectrogramGraphFrame",
                 initial_axis_value: Optional[float], tag_name: str, get_other: Callable,
                 helper: Type[AbstractHelper]):
        super().__init__(canvas, pair, sgf, initial_axis_value, tag_name, get_other, helper, UD_DRAG_CURSOR)

    def create_drawer(self, marker_rect: AreaTuple, pixel_value: int, line_span: RangeTuple) \
            -> Tuple[Callable, RangeTuple]:
        marker_l, marker_t, marker_r, marker_b = marker_rect
        dragger_width = int(abs(marker_r - marker_l) / 2)
        line_lower, line_upper = line_span

        # Create a closure to actually draw the marker:
        def drawer() -> int:
            lower, upper = self._pixel_range
            if lower > pixel_value > upper:  # TODO dupe
                self._line = self._canvas.create_line(line_lower, pixel_value, line_upper, pixel_value,
                                                      fill=MARKER_COLOUR, width=1, dash=(2, 2))

                # Draw the dragger:
                self._polygon_id = None
                w = int(dragger_width / TAN60)
                self._polygon_id = self._canvas.create_polygon(
                    marker_l, pixel_value,
                    marker_l + dragger_width, pixel_value + w,
                    marker_l + dragger_width, pixel_value - w,
                    fill=MARKER_DRAGGER_COLOUR,
                    outline=MARKER_DRAGGER_COLOUR,
                    tags=[self._tag_name])

                return self._polygon_id

        return drawer, (marker_l, marker_l + dragger_width)

    def do_move(self, pixel_current: int):
        # Move the dragger object in the canvas, using the intrinsic move method
        # which presumably is the most efficient way:
        pixel_previous = self._pixel_value
        delta = pixel_current - pixel_previous
        self._canvas.move(self._polygon_id, 0, delta)
        self._canvas.move(self._line, 0, delta)
        self._pixel_value = pixel_current
        self._axis_value = self._pixel_to_value(pixel_current)

    def get_pixels_dragged(self, event, start_event):
        return event.y - start_event.y


class LowerFrequencyMarker(FrequencyMarker):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "Type[AbstractMarkerPair]", sgf: "SpectrogramGraphFrame",
                 axis_value: Optional[float], get_other: Callable, helper: Type[AbstractHelper]):
        super().__init__(canvas, pair, sgf, axis_value, "lower_frequency_marker", get_other, helper)

    def do_move(self, x: int):
        super().do_move(x)
        # Notify the pair to redraw the band before we move the marker:
        self._pair.do_move_lower(x)

    def get_allowed_for_other(self) -> Tuple[Optional[int], Optional[int]]:
        # The other marker needs to be higher than this one.
        return None, self.get_pixel_value() - CLEARANCE_PIXELS


class UpperFrequencyMarker(FrequencyMarker):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "Type[AbstractMarkerPair]", sgf: "SpectrogramGraphFrame",
                 axis_value: Optional[float], get_other: Callable, helper: Type[AbstractHelper]):
        super().__init__(canvas, pair, sgf, axis_value, "upper_frequency_marker", get_other, helper)

    def do_move(self, x: int):
        super().do_move(x)
        # Notify the pair to redraw the band before we move the marker:
        self._pair.do_move_upper(x)

    def get_allowed_for_other(self) -> Tuple[Optional[int], Optional[int]]:
        # The other marker needs to be lower than us.
        return self.get_pixel_value() + CLEARANCE_PIXELS, None


class AbstractMarkerPair(ABC):
    """Abstract MarkerPair that doesn't know if it is vertical or horizontal."""

    def __init__(self, canvas: "SpectrogramCanvas", sgf: "SpectrogramGraphFrame",
                 lower_marker: AbstractMarker, upper_marker: AbstractMarker, helper: Type[AbstractHelper]):
        self._lower_marker: AbstractMarker = lower_marker
        self._upper_marker: AbstractMarker = upper_marker
        self._sgf = sgf
        self._canvas = canvas
        self._lower_id = self._upper_id = None
        self._lower_overflow_id = self._upper_overflow_id = None
        self._axis_range: Optional[AxisRange] = None
        self._axis_pixel_range: Optional[RangeTuple] = None
        self._helper: Type[AbstractHelper] = helper
        self._band_rect: Optional[AreaTuple] = None
        self._is_clipped: Tuple[bool, bool] = False, False

    def set_positions(self, positions: Tuple[Optional[float], Optional[float]]):
        v_lower, v_upper = positions
        if v_lower is not None:
            self._lower_marker.set_position(v_lower)
        if v_upper is not None:
            self._upper_marker.set_position(v_upper)

    def get_positions(self) -> Tuple[float, float]:
        return self._lower_marker.get_axis_value(), self._upper_marker.get_axis_value()

    def get_lower_marker(self) -> AbstractMarker:
        return self._lower_marker

    def get_upper_marker(self) -> AbstractMarker:
        return self._upper_marker

    def clip_to_pixel_range(self, v: int):
        lower, upper = self._axis_pixel_range
        if lower < upper:
            return clip_to_range(v, lower, upper)
        else:
            return clip_to_range(v, upper, lower)

    def get_band_text(self) -> List[str]:
        return []

    @abstractmethod
    def do_move_lower(self, x: int):
        raise NotImplementedError()

    @abstractmethod
    def do_move_upper(self, x: int):
        raise NotImplementedError()

    def draw(self, marker_rect: AreaTuple, data_rect: AreaTuple,
             margin_size: int, axis_range: AxisRange):
        # Note: the code in this method is orientation independent.

        self._axis_range = axis_range

        # Note the allowed pixel range in the data area:
        self._axis_pixel_range = self._helper.get_pixel_range(data_rect)

        # Draw the markers step 1: returns closures for actually drawing them further down:
        lower_drawer, band_pixel_width = self._lower_marker.draw(marker_rect, data_rect, margin_size, axis_range)
        upper_drawer, _ = self._upper_marker.draw(marker_rect, data_rect, margin_size, axis_range)

        # Get some optional text to display:
        text_list = self.get_band_text()
        band_pixel_length = self._lower_marker.get_pixel_value(), self._upper_marker.get_pixel_value()

        self._band_rect, self._is_clipped = self._helper.draw_band(self._canvas, band_pixel_length, band_pixel_width,
                                                                   self._axis_pixel_range, text_list)

        # Draw the markers step 1: do the actual drawing here so that they are above the band:
        self._lower_id = lower_drawer()
        self._upper_id = upper_drawer()


class TimeMarkerPair(AbstractMarkerPair):
    _tag_name = "band"

    def __init__(self, canvas: "SpectrogramCanvas", sgf: "SpectrogramGraphFrame",
                 lower_value: Optional[float], upper_value: Optional[float]):
        helper: Type[AbstractHelper] = TimeHelper()
        super().__init__(canvas, sgf,
                         LowerTimeMarker(canvas, self, sgf, lower_value, self.get_upper_marker, helper),
                         UpperTimeMarker(canvas, self, sgf, upper_value, self.get_lower_marker, helper),
                         helper)

    def do_move_lower(self, x: int):
        if self._band_rect is not None:
            l, t, r, b = self._band_rect
            self._band_rect = x, t, r, b
            self._helper.redraw_band(self._canvas, self._band_rect, self.get_band_text(), self._is_clipped)

    def do_move_upper(self, x: int):
        if self._band_rect is not None:
            l, t, r, b = self._band_rect
            self._band_rect = l, t, x, b
            self._helper.redraw_band(self._canvas, self._band_rect, self.get_band_text(), self._is_clipped)

    def get_band_text(self) -> List[str]:
        """Text to display on a time band: the time range."""
        v_left = self._lower_marker.get_axis_value()
        v_right = self._upper_marker.get_axis_value()
        v_span = v_right - v_left
        if v_span < 0.1:
            text = "{0:.1f} ms".format(v_span * 1000)
        else:
            text = "{0:.3f} s".format(v_span)

        return [text]


class FrequencyMarkerPair(AbstractMarkerPair):
    _tag_name = "frequency_band"

    def __init__(self, canvas: "SpectrogramCanvas", sgf: "SpectrogramGraphFrame",
                 lower_value: Optional[float], upper_value: Optional[float]):
        helper: Type[AbstractHelper] = FrequencyHelper()
        super().__init__(canvas, sgf,
                         LowerFrequencyMarker(canvas, self, sgf, lower_value, self.get_upper_marker, helper),
                         UpperFrequencyMarker(canvas, self, sgf, upper_value, self.get_lower_marker, helper),
                         helper)

    def do_move_lower(self, y: int):
        if self._band_rect is not None:
            l, t, r, b = self._band_rect
            self._band_rect = l, y, r, b
            self._helper.redraw_band(self._canvas, self._band_rect, self.get_band_text(), self._is_clipped)

    def do_move_upper(self, y: int):
        if self._band_rect is not None:
            l, t, r, b = self._band_rect
            self._band_rect = l, t, r, y
            self._helper.redraw_band(self._canvas, self._band_rect, self.get_band_text(), self._is_clipped)

    def get_band_text(self) -> List[str]:
        """Text to display on a time band: the freqeuencies."""
        f_lower = self._lower_marker.get_axis_value()
        f_upper = self._upper_marker.get_axis_value()
        t_lower = "{0:.1f} kHz".format(f_lower / 1000)
        t_upper = "{0:.1f} kHz".format(f_upper / 1000)
        return [t_lower, t_upper]
