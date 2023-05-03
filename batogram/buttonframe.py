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
from . import get_asset_path

from .frames import DrawableFrame
from .spectrogrammouseservice import CursorMode
from .external.tooltip import ToolTip


class MyButton(tk.Button):
    _width = 24
    _padding = 5

    def __init__(self, parent, image, command=None):
        super().__init__(parent, image=image, width=self._width, padx=self._padding, pady=self._padding,
                         relief=tk.RAISED, command=command)


class ButtonFrame(DrawableFrame):
    """A Frame containing the control buttons for a pane."""

    def __init__(self, parent, breadcrumb_service, action_target, data_context, program_directory, is_reference):
        super().__init__(parent)
        self._sync_source = None
        self._cursor_mode = CursorMode.CURSOR_ZOOM
        self._breadcrumb_service = breadcrumb_service
        self._program_directory = program_directory
        self._action_target = action_target
        self._dc = data_context

        def home_command():
            self._breadcrumb_service.reset()  # Clicking "home" clears the breadcrumb history
            self._action_target.on_home_button()

        col = 0

        if not is_reference:
            self._sync_image = self._load_image("arrow-right-circle-line.png")
            self._sync_button = MyButton(self, self._sync_image, command=self.sync_command)
            self._sync_button.grid(row=0, column=col, padx=0, ipadx=0, sticky="NSEW")
            ToolTip(self._sync_button, msg="Synchronize main graph axes from reference graph axes")
            col += 1

        left_space = tk.Label(self)
        left_space.grid(row=0, column=col)
        spacer1_index = col
        col += 1

        self._home_image = self._load_image("fullscreen-line.png")
        self._home_button = MyButton(self, self._home_image, command=home_command)
        self._home_button.grid(row=0, column=col, padx=0, ipadx=0, sticky="NSEW")
        ToolTip(self._home_button, msg="Reset axis ranges to match input data")
        col += 1

        self._previous_image = self._load_image("arrow-left-line.png")
        self._previous_button = MyButton(self, self._previous_image,
                                         command=lambda: self._action_target.on_navigation_button(
                                             self._breadcrumb_service.previous_entry()))
        self._previous_button.grid(row=0, column=col, padx=0, ipadx=0, sticky="NSEW")
        ToolTip(self._previous_button, msg="Revert to the previous zoom")
        col += 1

        self._next_image = self._load_image("arrow-right-line.png")
        self._next_button = MyButton(self, self._next_image,
                                     command=lambda: self._action_target.on_navigation_button(
                                         self._breadcrumb_service.next_entry()))
        self._next_button.grid(row=0, column=col, padx=0, ipadx=0, sticky="NSEW")
        ToolTip(self._next_button, msg="Reinstate the subsequent zoom")
        col += 1

        self._zoom_image = self._load_image("zoom-in-line.png")
        self._zoom_button = MyButton(self, self._zoom_image,
                                     command=lambda: self._handle_cursor_mode(CursorMode.CURSOR_ZOOM))
        self._zoom_button.grid(row=0, column=col, padx=(10, 0), ipadx=0, sticky="NSEW")
        ToolTip(self._zoom_button, msg="Select zoom cursor: left mouse drag to zoom.\nHold shift to lock mode.")
        col += 1

        self._pan_image = self._load_image("drag-move-2-line.png")
        self._pan_button = MyButton(self, self._pan_image,
                                    command=lambda: self._handle_cursor_mode(CursorMode.CURSOR_PAN))
        self._pan_button.grid(row=0, column=col, padx=0, ipadx=0, sticky="NSEW")
        ToolTip(self._pan_button, msg="Select pan cursor: left mouse drag to pan/scroll.\nHold shift to lock mode.")
        col += 1

        spacer = tk.Label(self)
        spacer.grid(row=0, column=col)
        spacer2_index = col
        col += 1

        if is_reference:
            self._sync_image = self._load_image("arrow-left-circle-line.png")
            self._sync_button = MyButton(self, self._sync_image, command=self.sync_command)
            self._sync_button.grid(row=0, column=col, padx=0, ipadx=0, sticky="NSEW")
            ToolTip(self._sync_button, msg="Synchronize reference axes from main graph axes")
            col += 1

        self.columnconfigure(index=spacer1_index, weight=1)
        self.columnconfigure(index=spacer2_index, weight=1)

    def get_cursor_mode(self):
        return self._cursor_mode

    @staticmethod
    def _load_image(file_name):
        return tk.PhotoImage(file=get_asset_path(file_name))

    def draw(self, draw_scope: int = DrawableFrame.DRAW_ALL):
        super().draw(draw_scope)

        # Enable the buttons according to the breadcrumb service state:
        self._home_button['state'] = tk.NORMAL  # We can always "home".
        self._previous_button['state'] = tk.NORMAL if self._breadcrumb_service.is_previous_available() else tk.DISABLED
        self._next_button['state'] = tk.NORMAL if self._breadcrumb_service.is_next_available() else tk.DISABLED

        # Enable the sync button if there is a source, and if this panel has data:
        self._sync_button['state'] = tk.NORMAL if self._sync_source and self._dc.afs else tk.DISABLED

        relief = tk.SUNKEN if self._cursor_mode == CursorMode.CURSOR_ZOOM else tk.RAISED
        self._zoom_button['state'] = tk.NORMAL
        self._zoom_button.configure(relief=relief)

        relief = tk.SUNKEN if self._cursor_mode == CursorMode.CURSOR_PAN else tk.RAISED
        self._pan_button['state'] = tk.NORMAL
        self._pan_button.configure(relief=relief)

    def _handle_cursor_mode(self, mode: CursorMode):
        self._cursor_mode = mode
        self.draw()
        self._action_target.on_cursor_mode(mode)

    def set_sync_source(self, sync_source):
        self._sync_source = sync_source
        # Update button enablement:
        self.draw()

    def sync_command(self):
        if self._sync_source:
            self._action_target.apply_sync_data(self._sync_source.get_sync_data())
