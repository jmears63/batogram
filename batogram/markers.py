import tkinter as tk
from abc import ABC, abstractmethod, abstractstaticmethod
from typing import Tuple, Optional, Callable, Type

from .constants import AXIS_FONT_NAME, AXIS_FONT_HEIGHT
from .common import AxisRange, clip_to_range, AreaTuple, RangeTuple

MARKER_COLOUR = "#808000"
MARKER_DRAGGER_COLOUR = "#FFFF00"
BAND_COLOUR = "#606000"
MARKER_TEXT_COLOUR = "#FFFF00"

TAN60: float = 1.73  # tan(60), used for drawing triangles.
AXIS_FONT = AXIS_FONT_NAME, -AXIS_FONT_HEIGHT


class Helper(ABC):
    """Instances of this classes contain all knowledge about whether a marker is being
    drawn for a vertical or horizontal axis."""

    def __init__(self):
        self._band_id: Optional[int] = None
        self._band_text_id: Optional[int] = None
        self._lower_overflow_id: Optional[int] = None
        self._upper_overflow_id: Optional[int] = None

    @abstractmethod
    def get_pixel_range(self, rect: AreaTuple) -> int:
        raise NotImplementedError()

    @abstractmethod
    def redraw_band(self, canvas: "SpectrogramCanvas", band_rect: AreaTuple, text: str):
        raise NotImplementedError()

    @abstractmethod
    def make_band_rect(self, band_pixel_width: RangeTuple, lower: int, upper: int) -> AreaTuple:
        raise NotImplementedError()

    @abstractmethod
    def draw_text_impl(self, canvas: "SpectrogramCanvas", band_rect: AreaTuple, text: Optional[str]) -> RangeTuple:
        raise NotImplementedError()

    @abstractmethod
    def draw_lower_overflow(self, canvas: "SpectrogramCanvas", p: int, band_pixel_width: RangeTuple) -> int:
        raise NotImplementedError()

    @abstractmethod
    def draw_upper_overflow(self, canvas: "SpectrogramCanvas", p: int, band_pixel_width: RangeTuple) -> int:
        raise NotImplementedError()

    def draw_band(self, canvas: "SpectrogramCanvas", band_pixel_length: [RangeTuple],
                  band_pixel_width: [RangeTuple],
                  axis_pixel_range: RangeTuple, text: Optional[str]) -> AreaTuple:
        """Draw a band connecting the markers. Deal with all situations including the band being partly
        or wholly outside the range of the axis."""

        # Clip the band to the pixel range available:
        lower = max(band_pixel_length[0], axis_pixel_range[0])
        upper = min(band_pixel_length[1], axis_pixel_range[1])

        # Make sure the band length is at least 1, so there is always something to draw. This makes
        # other code simpler.
        if upper <= lower:
            upper = lower + 1

        band_rect: AreaTuple = self.make_band_rect(band_pixel_width, lower, upper)

        # Actually draw it:
        self._band_id = self._draw_band_impl(canvas, band_rect)
        self._band_text_id = self.draw_text_impl(canvas, band_rect, text)

        # Draw overflow symbols if either end of the band is outside the range of the axis:
        w0, w1 = band_pixel_width
        if band_pixel_length[0] < axis_pixel_range[0]:
            self._lower_overflow_id = self.draw_lower_overflow(canvas, axis_pixel_range[0], band_pixel_width)
        if band_pixel_length[1] > axis_pixel_range[1]:
            self._upper_overflow_id = self.draw_lower_overflow(canvas, axis_pixel_range[1], band_pixel_width)

        return band_rect

    def _draw_band_impl(self, canvas: "SpectrogramCanvas", band_rect: AreaTuple) -> RangeTuple:

        band_id = canvas.create_rectangle(*band_rect, fill=BAND_COLOUR, outline=BAND_COLOUR,
                                          stipple='gray25', tags=[self._BAND_TAG_NAME])
        return band_id


class TimeHelper(Helper):
    _BAND_TAG_NAME: str = "time_band"

    def __init__(self):
        super().__init__()

    def get_pixel_range(self, rect: AreaTuple) -> RangeTuple:
        """Get the range of pixel values corresponding to axis range."""
        return rect[0], rect[2]

    def make_band_rect(self, band_pixel_width: RangeTuple, lower: int, upper: int) -> AreaTuple:
        return lower, band_pixel_width[1], upper, band_pixel_width[0]

    def draw_text_impl(self, canvas: "SpectrogramCanvas", band_rect: AreaTuple, text: Optional[str]) -> RangeTuple:
        l, t, r, b = band_rect
        text_id = None
        if text is not None:
            text_id = None
            min_space_for_text = 60
            if r - l > min_space_for_text:
                # Annotation. +2 to get the text inside the band. Me neither.
                text_id = canvas.create_text(int((l + r) / 2), int((b + t) / 2 + 2), text=text,
                                             fill=MARKER_TEXT_COLOUR, font=AXIS_FONT, anchor=tk.CENTER)

        return text_id

    def draw_lower_overflow(self, canvas: "SpectrogramCanvas", p: int, band_pixel_width: RangeTuple) -> int:
        w0, w1 = band_pixel_width
        return canvas.create_polygon(
            p, w0, p - abs(w0 - w1) / 1.3, int((w0 + w1) / 2), p, w1,
            fill=MARKER_DRAGGER_COLOUR, outline=MARKER_DRAGGER_COLOUR)

    def draw_upper_overflow(self, canvas: "SpectrogramCanvas", p: int, band_pixel_width: RangeTuple) -> int:
        w0, w1 = band_pixel_width
        return canvas.create_polygon(
            p, w0, p + abs(w0 - w1) / 1.3, int((w0 + w1) / 2), p, w1,
            fill=MARKER_DRAGGER_COLOUR, outline=MARKER_DRAGGER_COLOUR)

    def redraw_band(self, canvas: "SpectrogramCanvas", band_rect: AreaTuple, text: str):
        """Redraw an existing band, as a result of an end marker being moved."""

        new_band_id = self._draw_band_impl(canvas, band_rect)
        new_text_id = self.draw_text_impl(canvas, band_rect, text)

        to_delete = [self._band_id, self._band_text_id, self._lower_overflow_id, self._upper_overflow_id]

        # Move it beneath any existing band, before we delete the existing one, to preserve layering order:
        if self._band_id is not None and new_band_id is not None:
            canvas.tag_lower(new_band_id, self._band_id)

        # Delete all the old things:
        [canvas.delete(item) for item in to_delete if item is not None]

        self._band_id = new_band_id
        self._band_text_id = new_text_id


class Marker(ABC):
    def __init__(self, initial_axis_value: Optional[float]):
        # TODO factor out stuff from subclasses to here.
        self._axis_value: Optional[float] = initial_axis_value
        self._pixel_value: Optional[int] = None

    def get_pixel_value(self) -> Optional[int]:
        return self._pixel_value

    def get_axis_value(self) -> Optional[float]:
        return self._axis_value

    @abstractmethod
    def draw(self, marker_rect: AreaTuple, data_rect: AreaTuple,
             margin: int, axis_range: AxisRange) -> Tuple[Callable, RangeTuple]:
        raise NotImplementedError()


class TimeMarker(Marker, ABC):
    _DRAG_CURSOR = "sb_h_double_arrow"
    _CLEARANCE_PIXELS = 15

    def __init__(self, canvas: "SpectrogramCanvas", pair: "Type[MarkerPair]", sgf: "SpectrogramGraphFrame",
                 initial_axis_value: Optional[float], tag_name: str, get_other: Callable):
        super().__init__(initial_axis_value)

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
        self._line_span: Optional[RangeTuple] = None
        self._axis_range: Optional[AxisRange] = None

        canvas.tag_bind(self._tag_name, "<Enter>", lambda event: self.mouse_enters_dragger(event))
        canvas.tag_bind(self._tag_name, "<Leave>", lambda event: self.mouse_leaves_dragger(event))
        canvas.tag_bind(self._tag_name, "<Button-1>", lambda event: self._on_click(event))
        canvas.tag_bind(self._tag_name, "<B1-Motion>", lambda event: self._on_move(event))
        canvas.tag_bind(self._tag_name, "<ButtonRelease-1>", lambda event: self._on_release(event))

    def draw(self, marker_rect: AreaTuple, data_rect: AreaTuple,
             margin: int, axis_range: AxisRange) -> Tuple[Callable, int, int]:
        """Draw the marker, and return the coordinates of the end of the connecting band."""

        # Note some things for use during dragging:
        l, t, r, b = data_rect

        self._pixel_range = l, r
        self._line_span = t, b
        self._axis_range = axis_range

        x_pixels = self._value_to_pixel(self._axis_value)
        self._pixel_value = x_pixels

        line_lower, line_upper = self._line_span
        marker_l, marker_t, marker_r, marker_b = marker_rect
        dragger_height = int(abs(marker_t - marker_b) / 2)

        # Create a closure to actually draw the marker:
        def drawer() -> int:
            lower, upper = self._pixel_range
            if lower < x_pixels < upper:
                self._line = self._canvas.create_line(x_pixels, line_lower, x_pixels, line_upper,
                                                      fill=MARKER_COLOUR, width=1, dash=(2, 2))

                # Draw the dragger:
                self._polygon_id = None
                w = int(dragger_height / TAN60)
                if lower < x_pixels < upper:
                    self._polygon_id = self._canvas.create_polygon(
                        x_pixels, marker_b, x_pixels + w, marker_b - dragger_height,
                                            x_pixels - w, marker_b - dragger_height,
                        fill=MARKER_DRAGGER_COLOUR,
                        outline=MARKER_DRAGGER_COLOUR,
                        tags=[self._tag_name])

                return self._polygon_id

        # Return tuple: closure for drawing, bottom and top of marker for joining the band to.
        return drawer, (marker_b, marker_b - dragger_height)

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
        self._start_pixel_value = self._pixel_value

        # Set the cursor at the canvas level so it doesn't flicker during dragging:
        self._canvas.config(cursor=self._DRAG_CURSOR)

        # Ask the other marker how much space we have to drag in:
        self._allowed_range = self._get_other().get_allowed_for_other()

        # Take control of the mouse away from the canvas:
        self._canvas.preempt_mouse(True)

    def _on_move(self, event):
        # print("TimeMarker._on_move: {}".format(event))

        # Event contains the coordinate of the current mouse position, not a delta.

        x_resulting = self._calc_dragged(event)
        # print("x_resulting = {}".format(x_resulting))

        self.do_move(x_resulting)

    def do_move(self, x_current: int):
        # Move the dragger object in the canvas, using the intrinsic move method
        # which presumably is the most efficient way:
        x_previous = self._pixel_value
        dx = x_current - x_previous
        self._canvas.move(self._polygon_id, dx, 0)
        self._canvas.move(self._line, dx, 0)
        self._pixel_value = x_current
        self._axis_value = self._pixel_to_value(x_current)

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
        x_dragged = event.x - self._start_event.x

        # Note that the event x is not the exact dragger position, it is where
        # the user clicked in the dragger, so most likely off centre. So, we apply the
        # delta to our start position:
        x_resulting = self._start_pixel_value + x_dragged

        # Avoid colliding with the other marker:
        r_min, r_max = self._allowed_range
        if r_min is not None and x_resulting < r_min:
            x_resulting = r_min
        if r_max is not None and x_resulting > r_max:
            x_resulting = r_max

        # Confine to the pixel range of the axis:
        x_resulting = self._pair.clip_to_pixel_range(x_resulting)

        return x_resulting

    @abstractmethod
    def get_allowed_for_other(self) -> Tuple[Optional[int], Optional[int]]:
        raise NotImplementedError

    def _value_to_pixel(self, v: float) -> int:
        lower, upper = self._pixel_range
        p = int((v - self._axis_range.min) / (self._axis_range.max - self._axis_range.min) * (upper - lower) + lower)
        return p

    def _pixel_to_value(self, p: int) -> float:
        lower, upper = self._pixel_range
        v = (p - lower) / (upper - lower) * (self._axis_range.max - self._axis_range.min) + self._axis_range.min
        return v


class LowerTimeMarker(TimeMarker):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "Type[MarkerPair]", sgf: "SpectrogramGraphFrame",
                 axis_value: Optional[float], get_other: Callable):
        super().__init__(canvas, pair, sgf, axis_value, "lower_marker", get_other)

    def do_move(self, x: int):
        super().do_move(x)
        # Notify the pair to redraw the band before we move the marker:
        self._pair.do_move_lower(x)

    def get_allowed_for_other(self) -> Tuple[Optional[int], Optional[int]]:
        # The other marker needs to be higher than this one.
        return self.get_pixel_value() + self._CLEARANCE_PIXELS, None


class UpperTimeMarker(TimeMarker):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "TimeMarkerPair", sgf: "SpectrogramGraphFrame",
                 axis_value: Optional[float], get_other: Callable):
        super().__init__(canvas, pair, sgf, axis_value, "upper_marker", get_other)

    def do_move(self, x: int):
        super().do_move(x)
        # Notify the pair to redraw the band before we move the marker:
        self._pair.do_move_upper(x)

    def get_allowed_for_other(self) -> Tuple[Optional[int], Optional[int]]:
        # The other marker needs to be lower than us.
        return None, self.get_pixel_value() - self._CLEARANCE_PIXELS


class MarkerPair(ABC):
    """Generic MarkerPair that doesn't know if it is vertical or horizontal."""
    def __init__(self, canvas: "SpectrogramCanvas", sgf: "SpectrogramGraphFrame",
                 lower_marker: Marker, upper_marker: Marker, helper: Type[Helper]):
        self._lower_marker: Marker = lower_marker
        self._upper_marker: Marker = upper_marker
        self._sgf = sgf
        self._canvas = canvas
        self._lower_id = self._upper_id = None
        self._lower_overflow_id = self._upper_overflow_id = None
        self._axis_range: Optional[AxisRange] = None
        self._axis_pixel_range: Optional[RangeTuple] = None
        self._helper: Type[Helper] = helper
        self._band_rect: Optional[AreaTuple] = None

    def get_lower_marker(self) -> Marker:
        return self._lower_marker

    def get_upper_marker(self) -> Marker:
        return self._upper_marker

    def clip_to_pixel_range(self, v: int):
        return clip_to_range(v, *self._axis_pixel_range)

    def get_band_text(self) -> Optional[str]:
        return None  # No text by default.

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
        maybe_text = self.get_band_text()

        band_pixel_length = self._lower_marker.get_pixel_value(), self._upper_marker.get_pixel_value()

        self._band_rect = self._helper.draw_band(self._canvas, band_pixel_length, band_pixel_width,
                                                 self._axis_pixel_range, maybe_text)

        # Draw the markers step 1: do the actual drawing here so that they are above the:
        self._lower_id = lower_drawer()
        self._upper_id = upper_drawer()


class TimeMarkerPair(MarkerPair):
    _tag_name = "band"

    def __init__(self, canvas: "SpectrogramCanvas", sgf: "SpectrogramGraphFrame",
                 lower_value: Optional[float], upper_value: Optional[float]):
        super().__init__(canvas, sgf,
                         LowerTimeMarker(canvas, self, sgf, lower_value, self.get_upper_marker),
                         UpperTimeMarker(canvas, self, sgf, upper_value, self.get_lower_marker),
                         TimeHelper())

    def do_move_lower(self, x: int):
        if self._band_rect is not None:
            l, t, r, b = self._band_rect
            self._band_rect = x, t, r, b
            self._helper.redraw_band(self._canvas, self._band_rect, self.get_band_text())

    def do_move_upper(self, x: int):
        if self._band_rect is not None:
            l, t, r, b = self._band_rect
            self._band_rect = l, t, x, b
            self._helper.redraw_band(self._canvas, self._band_rect, self.get_band_text())

    def get_band_text(self) -> Optional[str]:
        """Text to display on a time band: the time range."""
        v_left = self._lower_marker.get_axis_value()
        v_right = self._upper_marker.get_axis_value()
        v_span = v_right - v_left
        text: str = ""
        if v_span < 0.1:
            text = "{0:.1f} ms".format(v_span * 1000)
        else:
            text = "{0:.3f} s".format(v_span)

        return text
