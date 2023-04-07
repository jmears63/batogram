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

from enum import Enum
from timeit import default_timer as timer
from typing import Tuple

DRAG_RECTANGLE_COLOUR = "white"
DRAG_LINE_COLOUR = "white"
ARROW_SHAPE = (16, 20, 6)


class CursorMode(Enum):
    CURSOR_ZOOM = 0
    CURSOR_PAN = 1


class MouseState(Enum):
    START = 1
    LEFT_DRAGGING = 2
    MIDDLE_DRAGGING = 3


class SpectrogramMouseService:
    """This class provides mouse behaviour for the spectrogram."""

    # Zoom factor per mouse wheel click:
    _ZOOM_FACTOR = 0.60

    # Wheel clicks within this number of seconds will be considered
    # to be part of the same zoom operation, and only recentre initially.
    _WHEEL_TIMEOUT = 1.0

    def __init__(self, canvas: tk.Canvas, initial_cursor_mode, graph_frame):
        self._cursor_mode = initial_cursor_mode
        self._graph_frame = graph_frame
        self._canvas = canvas

        self._state: MouseState = MouseState.START
        self._start_position = None
        self._rect = None
        self._line = None
        self._line1 = None
        self._line2 = None
        self._last_wheel_time = timer()
        self._is_frequency_clamped: bool = False
        self._canvas_height: int | None = None

        # Left mouse button:
        canvas.bind('<ButtonPress-1>', self._on_button1_press)
        canvas.bind('<Shift-ButtonPress-1>', self._on_shift_button1_press)
        canvas.bind('<ButtonRelease-1>', self._on_button1_release)
        canvas.bind('<Shift-ButtonRelease-1>', self._on_button1_release)
        canvas.bind('<B1-Motion>', self._on_button1_move)

        # Middle mouse button:
        canvas.bind('<ButtonPress-2>', self._on_button2_press)
        canvas.bind('<Shift-ButtonPress-2>', self._on_shift_button2_press)
        canvas.bind('<ButtonRelease-2>', self._on_button2_release)
        canvas.bind('<Shift-ButtonRelease-2>', self._on_button2_release)
        canvas.bind('<B2-Motion>', self._on_button2_move)

        # Right mouse button:
        canvas.bind('<ButtonPress-3>', self._on_button3_press)
        canvas.bind('<ButtonRelease-3>', self._on_button3_release)
        canvas.bind('<B3-Motion>', self._on_button3_move)

        # Any mouse motion:
        canvas.bind('<Motion>', self._on_move)
        canvas.bind('<Leave>', self._on_leave)

        # Mouse wheel:
        self._bind_wheel()

    def _on_button1_press(self, event):
        # print("1+")
        if self._cursor_mode == CursorMode.CURSOR_ZOOM:
            self._on_zoom_press(event, clamp=False)
        elif self._cursor_mode == CursorMode.CURSOR_PAN:
            self._on_pan_press(event, clamp=False)

    def _on_shift_button1_press(self, event):
        if self._cursor_mode == CursorMode.CURSOR_ZOOM:
            self._on_zoom_press(event, clamp=True)
        elif self._cursor_mode == CursorMode.CURSOR_PAN:
            self._on_pan_press(event, clamp=True)

    def _on_button1_move(self, event):
        if self._cursor_mode == CursorMode.CURSOR_ZOOM:
            self._on_zoom_move(event)
        elif self._cursor_mode == CursorMode.CURSOR_PAN:
            self._on_pan_move(event)

    def _on_button1_release(self, event):
        # print("1-")
        if self._cursor_mode == CursorMode.CURSOR_ZOOM:
            self._on_zoom_release(event)
        elif self._cursor_mode == CursorMode.CURSOR_PAN:
            self._on_pan_release(event)

    def _on_button2_press(self, event):
        # print("2+")
        self._on_pan_press(event, clamp=False)

    def _on_shift_button2_press(self, event):
        # print("2+")
        self._on_pan_press(event, clamp=True)

    def _on_button2_release(self, event):
        # print("2-")
        self._on_pan_release(event)

    def _on_button2_move(self, event):
        # print("B2 move")
        self._on_pan_move(event)

    def _on_button3_press(self, _):
        # print("3+")
        if self._state == MouseState.LEFT_DRAGGING:
            self._reset()

    def _on_button3_release(self, event):
        # print("3-")
        pass

    def _on_button3_move(self, event):
        pass

    def _on_wheel(self, event):
        print("wheel {}".format(event))
        if event.delta > 0:
            self._wheel_action(event, self._ZOOM_FACTOR, frequency_clamped=False)
        else:
            self._wheel_action(event, 1.0 / self._ZOOM_FACTOR, frequency_clamped=False)

    def _on_shift_wheel(self, event):
        print("shift wheel {}".format(event))
        if event.delta > 0:
            self._wheel_action(event, self._ZOOM_FACTOR, frequency_clamped=True)
        else:
            self._wheel_action(event, 1.0 / self._ZOOM_FACTOR, frequency_clamped=True)

    def _on_wheel_up(self, event):
        # print("up {}".format(event))
        self._wheel_action(event, self._ZOOM_FACTOR, frequency_clamped=False)

    def _on_shift_wheel_up(self, event):
        # print("shift up")
        self._wheel_action(event, self._ZOOM_FACTOR, frequency_clamped=True)

    def _on_wheel_down(self, event):
        # print("down {}".format(event))
        self._wheel_action(event, 1.0 / self._ZOOM_FACTOR, frequency_clamped=False)

    def _on_shift_wheel_down(self, event):
        # print("shift down")
        self._wheel_action(event, 1.0 / self._ZOOM_FACTOR, frequency_clamped=True)

    def _wheel_action(self, event, factor, frequency_clamped: bool):
        self._unbind_wheel()  # An attempt to reduce event pile-up.

        position = None
        t = timer()
        if t - self._last_wheel_time > self._WHEEL_TIMEOUT:
            position = (event.x, event.y)
        self._graph_frame.on_zoom_about_centre(position, factor, frequency_clamped)
        self._last_wheel_time = timer()

    def _unbind_wheel(self):
        self._canvas.unbind('<Button-4>')
        self._canvas.unbind('<Button-5>')

    def _bind_wheel(self):
        # For linux:
        self._canvas.bind('<Button-4>', self._on_wheel_up)
        self._canvas.bind('<Shift-Button-4>', self._on_shift_wheel_up)
        self._canvas.bind('<Button-5>', self._on_wheel_down)
        self._canvas.bind('<Shift-Button-5>', self._on_shift_wheel_down)
        # For Windows:
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Shift-MouseWheel>", self._on_shift_wheel)

    def _on_zoom_drag_complete(self, start: Tuple[int, int], end: Tuple[int, int], frequency_clamped: bool):
        """
        * Coordinates provided are relative to the top left corner of the canvas.
        * "start" and "end" are not in any particular order.
        * Coordinates may be outside the range of the canvas, if the drag moves off the edge.
        """
        # print("rectangle selected: {}, {}".format(start, end))

        # Order the coordinates ltrb:
        (l, t), (r, b) = start, end
        if t > b:
            t, b = b, t
        if l > r:
            l, r = r, l

        # Sanity check - did they select a tiny area? If so, do nothing.
        delta = 10
        if frequency_clamped:
            if r - l < delta:
                return
        else:
            if r - l < delta or b - t < delta:
                return

        # Notify whoever it concerns that they need to rescale to the area selected:
        self._graph_frame.on_zoom_to_rect((l, t, r, b), frequency_clamped)

    def _reset(self):
        self._state = MouseState.START
        self._start_position = None
        self._delete_canvas_items()

    def _on_zoom_press(self, event, clamp: bool):
        self._reset()
        self._canvas_height = self._canvas.winfo_height()
        self._state = MouseState.LEFT_DRAGGING
        self._start_position = event.x, event.y
        self._is_frequency_clamped = clamp

    def _on_pan_press(self, event, clamp: bool):
        self._reset()
        self._state = MouseState.MIDDLE_DRAGGING
        self._start_position = event.x, event.y
        self._is_frequency_clamped = clamp

    def _on_zoom_move(self, event):
        if self._state == MouseState.LEFT_DRAGGING:
            # If this is not the first move event, we need to delete the previous rectangle we drew:
            self._delete_canvas_items()
            if self._is_frequency_clamped:
                self._line1 = self._canvas.create_line(
                    self._start_position[0], 0, self._start_position[0], self._canvas_height,
                    fill=DRAG_RECTANGLE_COLOUR)
                self._line2 = self._canvas.create_line(
                    event.x, 0, event.x, self._canvas_height,
                    fill=DRAG_RECTANGLE_COLOUR)
            else:
                self._rect = self._canvas.create_rectangle(*self._start_position, event.x, event.y,
                                                           outline=DRAG_RECTANGLE_COLOUR)

    def _on_pan_move(self, event):
        if self._state == MouseState.MIDDLE_DRAGGING:
            self._delete_canvas_items()
            if self._is_frequency_clamped:
                self._line = self._canvas.create_line(*self._start_position, event.x, self._start_position[1],
                                                      fill=DRAG_LINE_COLOUR, arrow=tk.LAST, arrowshape=ARROW_SHAPE)
            else:
                self._line = self._canvas.create_line(*self._start_position, event.x, event.y,
                                                      fill=DRAG_LINE_COLOUR, arrow=tk.LAST, arrowshape=ARROW_SHAPE)

    def _on_zoom_release(self, event):
        self._delete_canvas_items()
        if self._state == MouseState.LEFT_DRAGGING:
            self._state = MouseState.START
            start = self._start_position
            end = event.x, event.y
            self._start_position = None
            if start != end:
                self._on_zoom_drag_complete(start, end, self._is_frequency_clamped)

    def _on_pan_release(self, event):
        self._delete_canvas_items()
        if self._state == MouseState.MIDDLE_DRAGGING:
            self._state = MouseState.START
            start = self._start_position
            if self._is_frequency_clamped:
                end = event.x, start[1]
            else:
                end = event.x, event.y
            self._start_position = None
            if start != end:
                self._graph_frame.on_pan((*start, *end))

    def set_cursor_mode(self, mode):
        self._cursor_mode = mode

    def notify_draw_complete(self):
        # Rebind to wheel events now that outstanding drawing is complete:
        self._bind_wheel()

    def _on_move(self, event):
        # print("Move {}, {}".format(event.x, event.y))
        # Provide the current mouse canvas coordinates:
        self._graph_frame.on_mouse_move((event.x, event.y))

    def _on_leave(self, _: tk.Event):
        self._graph_frame.on_mouse_move(None)

    def _delete_canvas_items(self):
        if self._rect is not None:
            self._canvas.delete(self._rect)
            self._rect = None
        if self._line1 is not None:
            self._canvas.delete(self._line1)
            self._line1 = None
        if self._line2 is not None:
            self._canvas.delete(self._line2)
            self._line2 = None
        if self._line is not None:
            self._canvas.delete(self._line)
            self._line = None
