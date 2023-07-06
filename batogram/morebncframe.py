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
import tkinter as tk
import numpy as np

from . import colourmap
from abc import abstractmethod, ABC
from typing import Any, List, Tuple, Optional
from .common import clip_to_range
from .frames import DrawableFrame
from .validatingwidgets import ValidatingFrameHelper, ValidatingRadiobutton, \
    DoubleValidatingEntry
from .graphsettings import GraphSettings, borderwidth, BNC_ADAPTIVE_MODE, BNC_MANUAL_MODE, \
    BNC_INTERACTIVE_MODE


class ValidatingFrame(tk.Frame, ValidatingFrameHelper):
    def __init__(self, parent, settings: GraphSettings):
        super().__init__(parent)
        ValidatingFrameHelper.__init__(self, parent, settings)


class HistogramInterface(ABC):
    """An abstraction that provides limited access to control what is displayed
    in the histogram."""

    @abstractmethod
    def show_histogram(self, data: np.ndarray):
        raise NotImplementedError()

    @abstractmethod
    def on_bnc_settings_changed(self):
        """Notification that the BnC settings have changed."""
        raise NotImplementedError()

    @abstractmethod
    def hide_bnc_line(self):
        raise NotImplementedError()

    @abstractmethod
    def hide_histogram(self):
        raise NotImplementedError()


class BrightnessContrastFrame(tk.Frame, ValidatingFrameHelper):
    """A frame containing settings relating to the brightness and contrast."""

    def __init__(self, parent, button_frame, settings: GraphSettings, pad):
        super().__init__(parent, borderwidth=borderwidth)
        ValidatingFrameHelper.__init__(self, parent, settings)

        self._settings = settings

        def threshold_validator(v): return self.generic_value_validator(v, minimum_value=0.0, maximum_value=100.0,
                                                                        message="The background threshold must bein the range 0 to 100.")

        self._mode_var = tk.IntVar(value=BNC_ADAPTIVE_MODE)  # Note: can't be a local variable.
        self._auto_radiobutton = ValidatingRadiobutton(self, button_frame, self, "Auto",
                                                       self._mode_var, BNC_ADAPTIVE_MODE)
        self._auto_radiobutton.grid(row=0, column=0, sticky="W")

        auto_details_frame = ValidatingFrame(self, settings)

        self._auto_label1 = tk.Label(auto_details_frame, text="Background removal:", anchor=tk.W)
        self._auto_label1.grid(row=0, column=0, sticky="W")
        self._background_entry = DoubleValidatingEntry(auto_details_frame, button_frame, self, width=7,
                                                       decimal_places=1,
                                                       value_validator=threshold_validator)
        self._background_entry.grid(row=0, column=1, sticky="W")
        self._auto_label2 = tk.Label(auto_details_frame, text="%", anchor="e")
        self._auto_label2.grid(row=0, column=2, sticky="W")

        self._auto_radiobutton.register_dependent_widgets(
            lambda v: v == BNC_ADAPTIVE_MODE,
            [self._background_entry, self._auto_label1, self._auto_label2])
        auto_details_frame.grid(row=1, column=0, padx=(40, pad))

        self._manual_radiobutton = ValidatingRadiobutton(self, button_frame, self, "Manual",
                                                         self._mode_var, BNC_MANUAL_MODE)
        self._manual_radiobutton.grid(row=2, column=0, sticky="W")

        manual_details_frame = ValidatingFrame(self, settings)

        self._manual_label1 = tk.Label(manual_details_frame, text="Range:", anchor=tk.W)
        self._manual_label1.grid(row=0, column=0, sticky="W")
        self._manual_min = DoubleValidatingEntry(manual_details_frame, button_frame, self, width=7, decimal_places=1)
        self._manual_min.grid(row=0, column=1, sticky="W")
        self._manual_label2 = tk.Label(manual_details_frame, text="to", anchor=tk.W)
        self._manual_label2.grid(row=0, column=2, sticky="W")
        def db_max_validator(v): return self.generic_value_validator(v, minimum_entry=self._manual_min,
                                                                     message="The maximum must be greater than the minimum.")

        self._manual_max = DoubleValidatingEntry(manual_details_frame, button_frame, self, width=7, decimal_places=1,
                                                 value_validator=db_max_validator)
        self._manual_max.grid(row=0, column=3, sticky="W")
        self._manual_label3 = tk.Label(manual_details_frame, text="dB", anchor="e")
        self._manual_label3.grid(row=0, column=4, sticky="W")

        self._auto_radiobutton.register_dependent_widgets(
            lambda v: v == BNC_MANUAL_MODE,
            [self._manual_label1, self._manual_label2, self._manual_label3, self._manual_min, self._manual_max])
        manual_details_frame.grid(row=3, column=0, padx=(40, pad))

        self._interactive_radiobutton = ValidatingRadiobutton(self, button_frame, self, "Interactive",
                                                              self._mode_var, BNC_INTERACTIVE_MODE)
        self._interactive_radiobutton.grid(row=4, column=0, sticky="W")

        self._histogram_frame = HistogramFrame(self, self._settings, pad)
        self._histogram_frame.grid(row=0, column=3, rowspan=5, sticky="NSEW")

        self.copy_settings_to_widgets()

    def get_histogram_interface(self) -> HistogramInterface:
        return self._histogram_frame

    def copy_settings_to_widgets(self):
        # Set all radiobuttons so they aren't dirty:
        self._auto_radiobutton.set_value(self._settings.bnc_adjust_type)
        self._manual_radiobutton.set_value(self._settings.bnc_adjust_type)
        self._interactive_radiobutton.set_value(self._settings.bnc_adjust_type)
        self._background_entry.set_value(self._settings.bnc_background_threshold_percent)
        self._manual_min.set_value(self._settings.bnc_manual_min)
        self._manual_max.set_value(self._settings.bnc_manual_max)

    def copy_widgets_to_settings(self):
        self._settings.bnc_adjust_type = self._auto_radiobutton.get_value()
        self._settings.bnc_background_threshold_percent = self._background_entry.get_value()
        self._settings.bnc_manual_min = self._manual_min.get_value()
        self._settings.bnc_manual_max = self._manual_max.get_value()


CANVAS_WIDTH = 300


class ScaleCanvas(tk.Canvas):
    """A canvas the displays the colour scale for a spectrogram."""

    def __init__(self, parent):
        super().__init__(parent, bg="black", height=15, width=CANVAS_WIDTH)

    def set_scale_pixels(self, prange: Optional[Tuple[int, int]]):
        """Draw a colour mapped scale."""
        width, height = self.winfo_width(), self.winfo_height()

        self.clear()
        if prange is not None:
            xmin, xmax = prange
            if xmin < xmax:
                # Get values in the range 0-1. Values outside that range will be clippped
                # to the limits at 0 and 1:
                values = np.array([float(x - xmin) / float(xmax - xmin) for x in range(width)])
                colours = colourmap.instance.map(values)
                for x in range(width):
                    colour = "#{:02x}{:02x}{:02x}".format(*colours[x])
                    self.create_line(x, 0, x, height - 1, fill=colour)

    def clear(self):
        self.delete("all")


class Dragger:
    """A dragging point on the bright and contrast line."""

    HALF_SIZE: int = 5
    _COLOUR = "#A0A0A0"
    _ACTIVE_COLOUR = "#80FFFF"
    _DRAG_CURSOR = "sb_h_double_arrow"

    def __init__(self, canvas: "HistogramCanvas", line: "BnCLine", which: int, tag_name: str):
        self._line = line
        self._canvas = canvas
        self._tag_name = tag_name
        self._which = which  # Which dragger are we? Maybe a subclass would be cleaner, but hey ho.
        self._rectangle: Optional[int] = None  # The rectangle drawn on the canvas, if any.
        # _pos is the position we were originally drawn at:
        self._pos: Optional[Tuple[int, int]] = None
        # _moved is the position have been moved to, updated during a drag:
        self._moved: Optional[Tuple[int, int]] = None

        self._start_event: Optional[Any] = None  # If this is non None, we know we are currently dragging.
        self._width: Optional[int] = None
        self._height: Optional[int] = None
        self._allowed_x_range: Optional[Tuple[int, int]] = None

        canvas.tag_bind(self._tag_name, "<Enter>", lambda event: self.mouse_enters_dragger(event))
        canvas.tag_bind(self._tag_name, "<Leave>", lambda event: self.mouse_leaves_dragger(event))
        canvas.tag_bind(self._tag_name, "<Button-1>", lambda event: self._on_click(event))
        canvas.tag_bind(self._tag_name, "<B1-Motion>", lambda event: self._on_move(event))
        canvas.tag_bind(self._tag_name, "<ButtonRelease-1>", lambda event: self._on_release(event))

    def get_pos(self) -> Tuple[int, int]:
        return self._pos

    def show(self, pos: Tuple[int, int]):
        self._width, self._height = self._canvas.winfo_width(), self._canvas.winfo_height()
        # Get rid of any dragger we have previously drawn:
        self._canvas.delete(self._tag_name)
        self._pos = pos
        self._rectangle = self._canvas.create_rectangle(*self._to_rect(*pos, self.HALF_SIZE),
                                                        fill=self._COLOUR, activefill=self._ACTIVE_COLOUR,
                                                        tags=[self._tag_name])

    def hide(self):
        # Fails gracefully if none:
        self._canvas.delete(self._tag_name)

    @staticmethod
    def _to_rect(x: int, y: int, delta: int) -> (int, int, int, int):
        """Create a rectangle centred on the point provided."""
        return x - delta, y - delta, x + delta, y + delta

    def mouse_enters_dragger(self, _):
        # Only if we aren't currently dragging - avoids cursor flicker during the drag.
        if self._start_event is None:
            self._canvas.config(cursor=self._DRAG_CURSOR)

    def mouse_leaves_dragger(self, _):
        # Only if we aren't currently dragging - avoids cursor flicker during the drag.
        if self._start_event is None:
            self._canvas.config(cursor="")

    def _on_click(self, event):
        # print("_on_click: {}".format(event))
        self._start_event = event
        self._moved = self._pos
        # Ask the line (which knows about the other dragger) what our allowed positions are:
        self._allowed_x_range = self._line.get_allowed_range(self._which)
        # Set the cursor at the canvas level so it doesn't flicker during dragging:
        self._canvas.config(cursor=self._DRAG_CURSOR)

    def _on_move(self, event):
        # print("_on_move: {}".format(event))

        # This is a little more complex that you might hope as we have
        # to convert between deltas and totals.

        x_resulting = self._calc_dragged(event)

        # Move the dragger object in the canvas, using the intrinsic move method
        # which presumably is the move efficient way:
        x_last, y_last = self._moved
        dx, dy = x_resulting - x_last, 0
        self._canvas.move(self._rectangle, dx, dy)
        self._moved = x_resulting, y_last

        # Tell the line that they moved the dragger. The line
        # can them redraw itself accordingly:
        self._line.on_dragger_moved(self._which, x_resulting)

    def _on_release(self, event):
        # print("_on_release: {}".format(event))

        # Move to the release point just in case we somehow didn't get a move event:
        self._calc_dragged(event)

        # Reset ready for another drag:
        self._pos = self._moved
        self._allowed_x_range = None
        self._start_event = None

        # Tell the line:
        self._line.on_dragger_released()
        self._canvas.config(cursor="")

    def _calc_dragged(self, event) -> int:
        """Figure out how far they have dragged, clipping that to the allowed range."""

        # Note that the event x is not dragger position, it is where
        # the user clicked in the dragger, so most likely off centre:
        x, x0 = event.x, self._start_event.x

        # How far have we dragged from the start?
        x_orig, _ = self._pos
        x_dragged = x - x0
        x_resulting = x_orig + x_dragged
        x_min_allowed, x_max_allowed = self._allowed_x_range
        x_resulting = clip_to_range(x_resulting, x_min_allowed, x_max_allowed)

        return x_resulting


class BnCLine:
    """A line on the histogram that shows how data values map to the range of the colour scale."""

    MIN_DRAGGER = 1
    MAX_DRAGGER = 2

    _BNC_LINE_COLOUR = "grey"
    _LINE_TAG = "bnclinetag"

    def __init__(self, canvas: "HistogramCanvas", scale_canvas: ScaleCanvas):
        self._histogram_canvas = canvas
        self._scale_canvas = scale_canvas  # We'll upate the scale whenever it changes.

        # The line always has a dragger at each end. We will show and hide them as required by the mode:
        self._min_dragger: Dragger = Dragger(self._histogram_canvas, self, self.MIN_DRAGGER, "min")
        self._max_dragger: Dragger = Dragger(self._histogram_canvas, self, self.MAX_DRAGGER, "max")
        self._draggers: List[Dragger] = [self._min_dragger, self._max_dragger]

        self._line: Optional[int] = None       # The line object in the canvas.
        self._prange: Optional[Tuple[int, int]] = None     # The x pixel range spanned by the line.

        self._width: Optional[int] = None      # Cache the canvas size for convenience.
        self._height: Optional[int] = None

    def show(self, prange: Tuple[int, int], with_draggers: bool):
        """
        Draw or remove the BnC line, with or without draggers according to mode.
        """

        # Cache the canvas size for convenience:
        self._width, self._height = self._histogram_canvas.winfo_width(), self._histogram_canvas.winfo_height()
        self._draw_all(*prange, with_draggers)

    def _draw_all(self, pmin, pmax, with_draggers):
        """Draw the line and show the draggers accordinging to mode, all based on pixel values."""
        self._draw_line((pmin, pmax))

        # Draw draggers if required:
        if with_draggers:
            # This has the effect of redraing them if there are already drawn:
            self._show_draggers()
        else:
            self._hide_draggers()

    def _draw_line(self, prange: Tuple[int, int]):
        pmin, pmax = prange
        # Delete any existing line:
        if self._line is not None:
            self._histogram_canvas.delete(self._line)
        coords = [pmin, 0, pmin, self._height - 1, pmax - 1, 0, pmax - 1, self._height - 1]
        self._line = self._histogram_canvas.create_line(*coords, fill=self._BNC_LINE_COLOUR, dash=(3, 5),
                                                        tags=self._LINE_TAG)
        # Cache the line range we drew for convenience:
        self._prange = pmin, pmax

        # Tell the scale to draw itself to match the line range:
        self._scale_canvas.set_scale_pixels(self._prange)

    def hide(self):
        """Get rid of the line, draggers and scale."""
        self._hide_draggers()
        if self._line is not None:
            self._histogram_canvas.delete(self._line)
        self._scale_canvas.set_scale_pixels(None)   # Hide the scale:
        self._prange = None
        self._line = None
        self._width = None
        self._height = None

    def _show_draggers(self):
        width, height = self._histogram_canvas.winfo_width(), self._histogram_canvas.winfo_height()
        if self._prange is not None:
            x1, x2 = self._prange
            offset = Dragger.HALF_SIZE * 3 / 2  # Offset so the draggers never overlap.
            self._min_dragger.show((x1, int(height / 2 - offset)))
            self._max_dragger.show((x2, int(height / 2 + offset)))

    def _hide_draggers(self):
        for d in self._draggers:
            d.hide()

    def on_dragger_moved(self, which: int, x_resulting: int):
        """The draggers call this as notification that they have moved."""

        # Update our record of the dragger positions:
        pmin, pmax = self._prange
        if which == self.MIN_DRAGGER:
            pmin = x_resulting
        elif which == self.MAX_DRAGGER:
            pmax = x_resulting
        else:
            # Shouldn't get here.
            pass
        self._prange = pmin, pmax

        # Redraw the line. The moving dragger has already been redrawn, the other is fine as it is.
        self._draw_line(self._prange)

    def on_dragger_released(self):
        min_x, _ = self._min_dragger.get_pos()
        max_x, _ = self._max_dragger.get_pos()

        # Redraw everything so that we end up with the correct depth order, so that the mouse
        # cursor changes correctly:
        self._draw_all(*self._prange, True)

        # Tell the canvas about the change:
        self._histogram_canvas.on_bnc_interactive_change((min_x, max_x))

    def get_allowed_range(self, which_asking: int) -> Tuple[int, int]:
        """A dragger calls this method to get the range of x values which we will
        allow it to have."""
        min_spacing = 5
        prange = 1, self._width - 1
        if which_asking == BnCLine.MIN_DRAGGER:
            # This dragger must be to the left of the max dragger:
            x_pos, _ = self._max_dragger.get_pos()
            prange = (1, x_pos - min_spacing)
        elif which_asking == BnCLine.MAX_DRAGGER:
            # This dragger must be to the right of the min dragger:
            x_pos, _ = self._min_dragger.get_pos()
            prange = (x_pos + min_spacing, self._width - 1)

        return prange

    def on_wheel_move(self, delta: int):
        # Adjust the lower line value as though dragged left:
        min_x, _ = self._min_dragger.get_pos()
        max_x, _ = self._max_dragger.get_pos()

        # print("dragger positions: {} {}".format(min_x, max_x))

        min_x += delta
        min_x = clip_to_range(min_x, 0, self._width - 1)

        # Redraw everything so that we end up with the correct depth order, so that the mouse
        # cursor changes correctly:
        # self._draw_all(*self._prange, True)

        # Tell the canvas about the change:
        self._histogram_canvas.on_bnc_interactive_change((min_x, max_x))


class HistogramCanvas(tk.Canvas):
    """A canvas that displays a histogram of the data points displayed in the spectrogram."""

    def __init__(self, parent: "HistogramFrame", top_frame, scale_canvas: ScaleCanvas,
                 settings: GraphSettings):
        super().__init__(parent, bg="black", height=10, width=CANVAS_WIDTH)

        # Visual elements:
        self._scale_canvas = scale_canvas
        self._bnc_line = BnCLine(self, scale_canvas)
        self._profile_line = None

        # This class owns the histogram data and the mapping from values to pixels.
        self._data: np.ndarray | None = None
        self._histogram = None
        self._bin_edges = None

        self._parent = parent
        self._top_frame = top_frame
        self._settings = settings
        self._is_interactive_mode: bool = False     # Cached from settings for convenience.

        # Cache some values for convenience:
        self._width: int = 0

        # Bind so we can react to becoming visible and draw ourselves:
        self.bind("<Configure>", self._on_resize)

        # For Linux:
        self.bind('<Button-4>', self._on_wheel_up)
        self.bind('<Button-5>', self._on_wheel_down)
        # For Windows:
        self.bind("<MouseWheel>", self._on_wheel)

        self._reset_histogram()

    def on_bnc_interactive_change(self, prange: Tuple[int, int]):
        # Scale the pixels to values:
        vrange: Optional[Tuple[float, float]] = self._pixels_to_values(prange)
        if vrange is not None:
            self._parent.on_bnc_interactive_change(vrange)

    def show_histogram(self, data: np.ndarray):
        """Called from the rendering pipeline to display the histogram,
        and optionally an auto BnC range."""
        width, height = self.winfo_width(), self.winfo_height()

        # Clean up any previous histogram:
        self._reset_histogram()

        # Cache some things in case of redraw:
        self._data = data
        self._width = width
        # Draw the histogram:
        self._draw(width, height)

    def _draw(self, width: int, height: int):
        # Slight hack: we ignore the lowest few percent of data to avoid artificial wide ranging values
        # in reassignment spectrum:
        vmin = np.percentile(self._data, 5)
        # density=False to avoid log10(0) error
        self._histogram, self._bin_edges = np.histogram(self._data[self._data > vmin], width)
        hmin, hmax = 0, self._histogram.max()  # Range to draw.

        # Don't try to draw the histogram if the canvas is very small - which happens when the canvas
        # is out of sight because it has been grid_removed.
        if hmax > 0 and width > 10 and height > 10:
            # Construct the points in the profile line:
            points = [(x, height * (1 - (self._histogram[x] - hmin) / hmax)) for x in range(len(self._histogram))]
            self._profile_line = self.create_line(*points, fill="#00FFFF")
            # Trigger a draw of the BnC line:
            self.on_bnc_settings_changed()

    def _on_resize(self, event):
        # If the canvas is resized, we should redraw it.

        width, height = self.winfo_width(), self.winfo_height()
        if self._data is not None:
            self._draw(width, height)

    def hide_histogram(self):
        """
        Hide the histogram and related UI elements. Called by higher leve
        UI components when there is no data, such as when the data file is closed.
        """

        self.hide_bnc_line()
        self._scale_canvas.clear()
        self._reset_histogram()

    def _reset_histogram(self):
        """Get rid of the histogram and relates UI elements."""
        if self._profile_line is not None:
            self.delete(self._profile_line)
            self._profile_line = None
        self._cached_data = None
        self._histogram = None
        self._bin_edges = None
        self._auto_vrange = None

    def on_bnc_settings_changed(self):
        # Convert the value range provided to a pixel range. Pixels
        # correspond to bin edges:
        vrange = self._settings.bnc_manual_min, self._settings.bnc_manual_max
        prange: Optional[Tuple[int, int]] = self._values_to_pixels(vrange)
        interactive_mode: bool = self._settings.bnc_adjust_type == BNC_INTERACTIVE_MODE
        self._is_interactive_mode = interactive_mode
        if prange is not None:
            self._bnc_line.show(prange, interactive_mode)

    def hide_bnc_line(self):
        self._is_interactive_mode = False
        self._bnc_line.hide()

    _WHEEL_DELTA = 2

    def _on_wheel_up(self, event):
        # print("_on_wheel_up")
        if self._is_interactive_mode:
            self._bnc_line.on_wheel_move(self._WHEEL_DELTA)

    def _on_wheel_down(self, event):
        # print("_on_wheel_down")
        if self._is_interactive_mode:
            self._bnc_line.on_wheel_move(-self._WHEEL_DELTA)

    def _on_wheel(self, event):
        if self._is_interactive_mode:
            if event.delta > 0:
                self._bnc_line.on_wheel_move(self._WHEEL_DELTA)
            else:
                self._bnc_line.on_wheel_move(-self._WHEEL_DELTA)

    def _values_to_pixels(self, vrange: Tuple[float, float]) -> Optional[Tuple[int, int]]:
        prange: Optional[Tuple[int, int]] = None
        if self._bin_edges is not None:
            vmin, vmax = vrange
            # Scale vmin and vmax to bin numbers (which correspond to the x coordinate).
            # We choose the bin whose centre is closest to the value - that means,
            # add half a bin width and then floor.
            bin_count = len(self._bin_edges) - 1  # n bins have n+1 boundaries.
            if bin_count > 0:
                bin_lowest, bin_highest = self._bin_edges[0], self._bin_edges[-1]
                bin_range = bin_highest - bin_lowest
                if bin_range > 0:
                    bin_min = math.floor((vmin - bin_lowest) * bin_count / bin_range + 0.5)
                    bin_max = math.floor((vmax - bin_lowest) * bin_count / bin_range + 0.5)
                    bin_min = clip_to_range(bin_min, 0, bin_count - 1)
                    bin_max = clip_to_range(bin_max, 1, bin_count)
                    prange = bin_min, bin_max

        return prange

    def _pixels_to_values(self, prange: Tuple[int, int]) -> Optional[Tuple[float, float]]:
        vrange: Optional[Tuple[float, float]] = None
        if self._bin_edges is not None:
            pmin, pmax = prange

            bin_count = len(self._bin_edges - 1)
            if bin_count > 0:
                # Scale bin numbers (which correspond to the x coordinate) to vmin and vmax:
                bin_lowest, bin_highest = self._bin_edges[0], self._bin_edges[-1]
                bin_range = bin_highest - bin_lowest
                bin_width_half = bin_range / (2.0 * bin_count)

                bin_range = bin_highest - bin_lowest
                if bin_range > 0:
                    # Round
                    vmin = (bin_highest - bin_lowest + bin_width_half) * pmin / bin_count + bin_lowest
                    vmax = (bin_highest - bin_lowest + bin_width_half) * pmax / bin_count + bin_lowest
                    vrange = vmin, vmax

        return vrange


class HistogramFrame(tk.Frame, HistogramInterface):
    """A Frame containing a histogram of spectrogram data."""

    def __init__(self, parent, settings: GraphSettings, pad: int):
        super().__init__(parent)

        self._settings = settings

        self._scale_canvas = ScaleCanvas(self)
        self._histogram_canvas = HistogramCanvas(self, parent, self._scale_canvas, settings)
        self._histogram_canvas.grid(row=0, column=0, sticky="NSEW", padx=pad, pady=(pad, 0))
        self._scale_canvas.grid(row=1, column=0, sticky="NSEW", padx=pad, pady=(0, pad))
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

    def on_bnc_interactive_change(self, vrange: Tuple[float, float]):
        """Respond to a manual change to BnC from the histogram: dragging or mouse wheel."""
        self._settings.bnc_manual_min, self._settings.bnc_manual_max = vrange
        # Tell whomever it may concern that new settings values are available,
        # limiting it to a spectrogram redraw only to limit general flicker:
        self._settings.on_user_applied_settings(draw_scope=DrawableFrame.DRAW_SPECTROGRAM)

    def show_histogram(self, data: np.ndarray):
        self._histogram_canvas.show_histogram(data)

    def on_bnc_settings_changed(self):
        self._histogram_canvas.on_bnc_settings_changed()

    def hide_bnc_line(self):
        self._histogram_canvas.hide_bnc_line()

    def hide_histogram(self):
        self._histogram_canvas.hide_histogram()
