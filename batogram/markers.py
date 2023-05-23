import tkinter as tk
from abc import ABC, abstractmethod
from typing import Tuple, Optional, Callable

from .constants import AXIS_FONT_NAME, AXIS_FONT_HEIGHT
from .common import AxisRange, clip_to_range


class TimeMarker(ABC):
    _DRAG_CURSOR = "sb_h_double_arrow"
    _MARKER_COLOUR = "#808000"
    _MARKER_DRAGGER_COLOUR = "#FFFF00"

    _CLEARANCE_PIXELS = 15

    def __init__(self, canvas: "SpectrogramCanvas", pair: "TimeMarkerPair", sgf: "SpectrogramGraphFrame",
                 initial_axis_value: Optional[float], tag_name: str, get_other: Callable):
        self._pair = pair
        self._sgf = sgf
        self._axis_value: Optional[float] = initial_axis_value
        self._pixel_value: Optional[int] = None
        self._tag_name: str = tag_name
        self._canvas: "SpectrogramCanvas" = canvas
        self._start_event = None
        self._saved_cursor = None
        self._polygon_id = None
        self._line = None
        self._get_other = get_other
        self._data_rect: Optional[Tuple[int, int, int, int]] = None
        self._axis_range: Optional[AxisRange] = None

        canvas.tag_bind(self._tag_name, "<Enter>", lambda event: self.mouse_enters_dragger(event))
        canvas.tag_bind(self._tag_name, "<Leave>", lambda event: self.mouse_leaves_dragger(event))
        canvas.tag_bind(self._tag_name, "<Button-1>", lambda event: self._on_click(event))
        canvas.tag_bind(self._tag_name, "<B1-Motion>", lambda event: self._on_move(event))
        canvas.tag_bind(self._tag_name, "<ButtonRelease-1>", lambda event: self._on_release(event))

    def get_pixel_value(self) -> Optional[int]:
        return self._pixel_value

    def get_axis_value(self) -> Optional[float]:
        return self._axis_value

    def draw(self, marker_rect: Tuple[int, int, int, int], data_rect: Tuple[int, int, int, int],
             margin: int, axis_range: AxisRange) -> Tuple[Callable, int, int]:
        """Draw the marker, and return the coordinates of the end of the connecting band."""

        # Note some things for use during dragging:
        self._data_rect = data_rect
        self._axis_range = axis_range

        # Draw the line:
        _, t, _, b = data_rect
        x_pixels = self._value_to_pixel(self._axis_value)
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
        l, _, r, _ = self._data_rect
        p = int((v - self._axis_range.min) / (self._axis_range.max - self._axis_range.min) * (r - l) + l)
        return p

    def _pixel_to_value(self, p: int) -> float:
        l, _, r, _ = self._data_rect
        v = (p - l) / (r - l) * (self._axis_range.max - self._axis_range.min) + self._axis_range.min
        return v


class LowerMarker(TimeMarker):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "TimeMarkerPair", sgf: "SpectrogramGraphFrame",
                 axis_value: Optional[float], get_other: Callable):
        super().__init__(canvas, pair, sgf, axis_value, "lower_marker", get_other)

    def do_move(self, x: int):
        super().do_move(x)
        # Notify the pair to redraw the band before we move the marker:
        self._pair.do_move_left(x)

    def get_allowed_for_other(self) -> Tuple[Optional[int], Optional[int]]:
        # The other marker needs to be to our right.
        return self.get_pixel_value() + self._CLEARANCE_PIXELS, None


class UpperMarker(TimeMarker):
    def __init__(self, canvas: "SpectrogramCanvas", pair: "TimeMarkerPair", sgf: "SpectrogramGraphFrame",
                 axis_value: Optional[float], get_other: Callable):
        super().__init__(canvas, pair, sgf, axis_value, "upper_marker", get_other)

    def do_move(self, x: int):
        super().do_move(x)
        # Notify the pair to redraw the band before we move the marker:
        self._pair.do_move_right(x)

    def get_allowed_for_other(self) -> Tuple[Optional[int], Optional[int]]:
        # The other marker needs to be to our left.
        return None, self.get_pixel_value() - self._CLEARANCE_PIXELS


class TimeMarkerPair:
    _BAND_COLOUR = "#606000"
    _MARKER_TEXT_COLOUR = "#FFFF00"
    _tag_name = "band"

    def __init__(self, canvas: "SpectrogramCanvas", sgf: "SpectrogramGraphFrame",
                 lower_value: Optional[float], upper_value: Optional[float]):
        self._left_marker = LowerMarker(canvas, self, sgf, lower_value, self.get_right_marker)
        self._right_marker = UpperMarker(canvas, self, sgf, upper_value, self.get_left_marker)
        self._sgf = sgf
        self._canvas = canvas
        self._band_rect: Optional[Tuple[int, int, int, int]] = None
        self._band_id = self._text_id = None
        self._left_id = self._right_id = None
        self._axis_range: Optional[AxisRange] = None
        self._pixel_range: Optional[Tuple[int, int]] = None
        self._axis_font = AXIS_FONT_NAME, -AXIS_FONT_HEIGHT

    def get_left_marker(self) -> TimeMarker:
        return self._left_marker

    def get_right_marker(self) -> TimeMarker:
        return self._right_marker

    def draw(self, marker_rect: Tuple[int, int, int, int], data_rect: Tuple[int, int, int, int],
             margin: int, axis_range: AxisRange):

        self._axis_range = axis_range

        # Note the allowed pixel range for markers for later:
        l, t, r, b = data_rect
        self._pixel_range = l, r

        # Draw the markers:
        left_drawer, bottom, top = self._left_marker.draw(marker_rect, data_rect, margin, axis_range)
        right_drawer, _, _ = self._right_marker.draw(marker_rect, data_rect, margin, axis_range)

        def pixel_to_value(p: int) -> float:
            return (p - l) / (r - l) * (axis_range.max - axis_range.min) + axis_range.min

        # Some text to display:
        text = self._get_text()

        # Draw a connecting band between them:
        self._band_rect = self._left_marker.get_pixel_value(), top, self._right_marker.get_pixel_value(), bottom
        self._band_id, self._text_id = self._draw_band(*self._band_rect, text)

        # Finally, draw the markers, so that they overlap the band on top of it:
        self._left_id = left_drawer()
        self._right_id = right_drawer()

    def do_move_left(self, x: int):
        if self._band_rect is not None:
            l, t, r, b = self._band_rect
            self._band_rect = x, t, r, b
            self._redraw_band(*self._band_rect, self._get_text())

    def do_move_right(self, x: int):
        if self._band_rect is not None:
            l, t, r, b = self._band_rect
            self._band_rect = l, t, x, b
            self._redraw_band(*self._band_rect, self._get_text())

    def _draw_band(self, left: int, top: int, right: int, bottom: int, text: str) -> Tuple[int, int]:
        band_id = self._canvas.create_rectangle(left, top, right, bottom,
                                                fill=self._BAND_COLOUR,
                                                outline=self._BAND_COLOUR,
                                                stipple='gray25',
                                                tags=[self._tag_name])
        # Annotation. +2 to get the text inside the band.
        text_id = self._canvas.create_text((left + right) / 2, bottom + 2, text=text,
                                           fill=self._MARKER_TEXT_COLOUR, font=self._axis_font, anchor=tk.S)

        return band_id, text_id

    def _redraw_band(self, left: int, top: int, right: int, bottom: int, text: str):
        new_band_id, new_text_id = self._draw_band(left, top, right, bottom, text)

        # Move it beneath any existing band, before we delete the existing one, to preserve layering order:
        if self._band_id is not None:
            self._canvas.tag_lower(new_band_id, self._band_id)
            self._canvas.delete(self._band_id)
        if self._text_id is not None:
            self._canvas.delete(self._text_id)
        self._band_id = new_band_id
        self._text_id = new_text_id

    def clip_to_pixel_range(self, v: int):
        return clip_to_range(v, *self._pixel_range)

    def _get_text(self) -> str:
        v_left = self._left_marker.get_axis_value()
        v_right = self._right_marker.get_axis_value()
        v_span = v_right - v_left
        text: str = ""
        if v_span < 0.1:
            text = "{0:.1f} ms".format(v_span * 1000)
        else:
            text = "{0:.3f} s".format(v_span)

        return text


