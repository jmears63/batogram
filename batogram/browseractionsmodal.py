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

import os
import tkinter as tk
from enum import Enum
from pathlib import Path
from tkinter import filedialog
from typing import Callable, Literal, Optional

from batogram.modalwindow import ModalWindow


class BrowserAction(Enum):
    TRASH = 1
    MOVE = 2
    COPY = 3
    RENAME = 4


class BrowserActionsSettings:
    action: int = BrowserAction.TRASH.value
    relative_folder_name: Optional[str] = None  # Path relative to the current user's home directory.
    create_folder: bool = False
    prefix_str: Optional[str] = None
    rename_str: Optional[str] = None


class BrowserActionsModal(ModalWindow):
    def __init__(self, parent, move_rename_settings: BrowserActionsSettings, on_ok: Callable,
                 initialdir: str, single_flagged_filename: Optional[str]):
        super().__init__(parent)
        self._settings: BrowserActionsSettings = move_rename_settings
        self._on_ok = on_ok
        self._initial_dir: str = initialdir
        self._single_flagged_filename: str = single_flagged_filename

        if self._settings.relative_folder_name is None:
            self._settings.relative_folder_name = initialdir
        self._settings.rename_str = None    # Reset this every time.

        self.title("Flagged Item Action")

        self._action_var = tk.IntVar()
        self._folder_name_var: tk.StringVar = tk.StringVar()
        self._create_folder_var = tk.BooleanVar()
        self._prefix_var = tk.StringVar()
        self._rename_var = tk.StringVar()

        pad = 5
        margin = 30
        button_width = 7

        action_frame = tk.Frame(self)

        self._action_radiobutton = tk.Radiobutton(action_frame, text="Send item(s) to trash", variable=self._action_var,
                                                  value=BrowserAction.TRASH.value)
        self._action_radiobutton.grid(row=0, column=0, sticky="W")

        self._action_radiobutton = tk.Radiobutton(action_frame, text="Copy item(s) to folder", variable=self._action_var,
                                                  value=BrowserAction.COPY.value)
        self._action_radiobutton.grid(row=1, column=0, sticky="W")

        self._action_radiobutton = tk.Radiobutton(action_frame, text="Move item(s) to folder", variable=self._action_var,
                                                  value=BrowserAction.MOVE.value)
        self._action_radiobutton.grid(row=2, column=0, sticky="W")

        self._action_radiobutton = tk.Radiobutton(action_frame, text="Rename single item", variable=self._action_var,
                                                  value=BrowserAction.RENAME.value)
        # Allow rename only if a single item is selected:
        self._action_radiobutton.configure(state=self._state_literal(single_flagged_filename is not None))
        self._action_radiobutton.grid(row=3, column=0, sticky="W")

        action_frame.rowconfigure(0, weight=0, pad=pad)
        action_frame.rowconfigure(1, weight=0, pad=pad)
        action_frame.rowconfigure(2, weight=0, pad=pad)
        action_frame.rowconfigure(3, weight=0, pad=pad)
        action_frame.columnconfigure(0, pad=pad)
        action_frame.grid(row=0, column=0, sticky="EW", padx=margin, pady=pad*3)

        values_frame = tk.Frame(self)
        self._folder_name_label = tk.Label(values_frame, text="Target folder (relative to home):")
        self._folder_name_label.grid(row=0, column=0, sticky="W")

        self._folder_name_entry = tk.Entry(values_frame, width=30, textvariable=self._folder_name_var)
        self._folder_name_entry.grid(row=0, column=1, sticky="EW")

        self._folder_name_select_btn = tk.Button(values_frame, text="Select", underline=0, width=button_width, command=self._select_folder)
        self._folder_name_select_btn.grid(row=0, column=2, padx=pad, pady=pad)

        self._create_folder_checkbutton = tk.Checkbutton(values_frame, text="Create folder as required",
                                                         variable=self._create_folder_var)
        self._create_folder_checkbutton.grid(row=1, column=1, sticky="W")

        self._prefix_name_label = tk.Label(values_frame, text="Prefix item name with:")
        self._prefix_name_label.grid(row=2, column=0, sticky="W")
        self._prefix_name_entry = tk.Entry(values_frame, textvariable=self._prefix_var)
        self._prefix_name_entry.grid(row=2, column=1, sticky="EW")

        self._rename_name_label = tk.Label(values_frame, text="Rename single item to:")
        self._rename_name_label.grid(row=3, column=0, sticky="W")
        self._rename_name_entry = tk.Entry(values_frame, textvariable=self._rename_var)
        self._rename_name_entry.grid(row=3, column=1, sticky="EW")

        values_frame.columnconfigure(0, weight=0, pad=pad)
        values_frame.columnconfigure(1, weight=1, pad=pad)
        values_frame.columnconfigure(2, weight=0, pad=pad)
        values_frame.columnconfigure(3, weight=0, pad=pad)
        values_frame.rowconfigure(0, weight=0, pad=pad)
        values_frame.rowconfigure(1, weight=0, pad=pad)
        values_frame.rowconfigure(2, weight=0, pad=pad)
        values_frame.grid(row=1, column=0, sticky="EW", padx=(margin * 2, 0), pady=(0, pad*3))

        okcancel_frame = tk.Frame(self)
        self._ok_btn = tk.Button(okcancel_frame, text="OK", underline=0, width=button_width, command=self.on_ok)
        self._ok_btn.grid(row=0, column=1, padx=pad, pady=pad)

        self._cancel_btn = tk.Button(okcancel_frame, text="Cancel", underline=0, width=button_width,
                                     command=self.on_cancel)
        self._cancel_btn.grid(row=0, column=2, padx=pad, pady=pad)

        okcancel_frame.columnconfigure(0, weight=1)
        okcancel_frame.grid(row=2, column=0, sticky=tk.EW, padx=margin)

        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.columnconfigure(0, weight=1)

        # Respond to changes in values so we can enable widgets accordingly:
        self._action_var.trace("w", self._enable_widgets)
        self._folder_name_var.trace("w", self._enable_widgets)
        self._create_folder_var.trace("w", self._enable_widgets)
        self._prefix_var.trace("w", self._enable_widgets)
        self._rename_var.trace("w", self._enable_widgets)

        self._settings_to_vars()

    def _enable_widgets(self, *args):
        ok_permitted: bool = False
        ok_vetoed: bool = False
        v = self._action_var.get()
        if self._action_var.get() == BrowserAction.TRASH.value:
            ok_permitted = True
            self._folder_name_label.configure(state=self._state_literal(False))
            self._folder_name_entry.configure(state=self._state_literal(False))
            self._folder_name_select_btn.configure(state=self._state_literal(False))
            self._create_folder_checkbutton.configure(state=self._state_literal(False))
            self._prefix_name_label.configure(state=self._state_literal(False))
            self._prefix_name_entry.configure(state=self._state_literal(False))
            self._rename_name_label.configure(state=self._state_literal(False))
            self._rename_name_entry.configure(state=self._state_literal(False))
        elif self._action_var.get() in [BrowserAction.COPY.value, BrowserAction.MOVE.value]:
            ok_permitted = True
            self._folder_name_label.configure(state=self._state_literal(True))
            self._folder_name_entry.configure(state=self._state_literal(True))
            self._folder_name_select_btn.configure(state=self._state_literal(True))
            self._create_folder_checkbutton.configure(state=self._state_literal(True))
            self._prefix_name_label.configure(state=self._state_literal(True))
            self._prefix_name_entry.configure(state=self._state_literal(True))
            can_rename = self._single_flagged_filename is not None and (len(self._prefix_name_entry.get()) == 0)
            self._rename_name_label.configure(state=self._state_literal(can_rename))
            self._rename_name_entry.configure(state=self._state_literal(can_rename))
            ok_vetoed |= len(self._folder_name_var.get()) == 0
        elif self._action_var.get() == BrowserAction.RENAME.value:
            ok_permitted = True
            self._folder_name_label.configure(state=self._state_literal(False))
            self._folder_name_entry.configure(state=self._state_literal(False))
            self._folder_name_select_btn.configure(state=self._state_literal(False))
            self._create_folder_checkbutton.configure(state=self._state_literal(False))
            self._prefix_name_label.configure(state=self._state_literal(False))
            self._prefix_name_entry.configure(state=self._state_literal(False))
            self._rename_name_label.configure(state=self._state_literal(self._single_flagged_filename is not None))
            self._rename_name_entry.configure(state=self._state_literal(self._single_flagged_filename is not None))
            ok_vetoed |= len(self._rename_name_entry.get()) == 0
        else:
            ok_permitted = False
            self._folder_name_label.configure(state=self._state_literal(False))
            self._folder_name_entry.configure(state=self._state_literal(False))
            self._folder_name_select_btn.configure(state=self._state_literal(False))
            self._create_folder_checkbutton.configure(state=self._state_literal(False))
            self._prefix_name_label.configure(state=self._state_literal(False))
            self._prefix_name_entry.configure(state=self._state_literal(False))
            self._rename_name_label.configure(state=self._state_literal(False))
            self._rename_name_entry.configure(state=self._state_literal(False))

        # Only allow OK if all is sane:
        self._ok_btn.configure(state=self._state_literal(ok_permitted and not ok_vetoed))

    @staticmethod
    def _state_literal(enabled: bool) -> Literal["normal", "active", "disabled"]:
        return "normal" if enabled else "disabled"  # Don't know why type hints warns.

    def on_ok(self):
        # Ideally we would do a bit more validation here but it is simpler
        # to aske forgiveness than permission - ie, we will go ahead and try it.

        self._vars_to_settings()
        self._on_ok()
        super().on_ok()

    def _select_folder(self):
        initial = self._initial_dir
        directory_selected = filedialog.askdirectory(parent=self, mustexist=False,
                                                     initialdir=os.path.join(Path.home(), initial))
        if directory_selected != '':  # Urgh. You would hope it would None if the user cancels. Oh well.
            self._settings.data_directory = directory_selected
            self._folder_name_var.set(self._shortened_path(directory_selected))

    @staticmethod
    def _shortened_path(path: str) -> str:
        """Create a shortened version of a path intended to fit in a UI label widget."""

        try:
            shortened_path = os.path.relpath(path, start=Path.home())
        except ValueError as e:
            shortened_path = path

        return shortened_path

    def _settings_to_vars(self):
        self._action_var.set(self._settings.action)
        self._folder_name_var.set(self._settings.relative_folder_name)
        self._create_folder_var.set(True if self._settings.create_folder else False)
        self._prefix_var.set(self._settings.prefix_str if self._settings.prefix_str is not None else "")
        self._rename_var.set(self._settings.rename_str if self._settings.rename_str is not None else "")

    def _vars_to_settings(self):
        self._settings.action = self._action_var.get()
        self._settings.relative_folder_name = self._folder_name_var.get()
        self._settings.create_folder = self._create_folder_var.get()
        self._settings.prefix_str = self._prefix_var.get() if self._prefix_var.get() else None
        self._settings.rename_str = self._rename_var.get() if self._rename_var.get() else None
