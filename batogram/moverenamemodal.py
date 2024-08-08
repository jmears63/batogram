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
from enum import Enum, IntEnum
from pathlib import Path
from tkinter import filedialog
from typing import List, Callable, Literal, Optional

from batogram.modalwindow import ModalWindow


class MoveType(IntEnum):
    MOVE_TO_FOLDER = 0
    MOVE_TO_WASTEBASKET = 1


class MoveRenameSettings:
    do_move: bool = False
    move_type: int = MoveType.MOVE_TO_FOLDER.value
    relative_folder_name: Optional[str] = None           # Path relative to the current user's home directory.
    create_folder: bool = False
    do_rename: bool = False
    rename_prefix: str = ""


class MoveRenameModal(ModalWindow):
    def __init__(self, parent, move_rename_settings: MoveRenameSettings, on_ok: Callable, initialdir: str):
        super().__init__(parent)
        self._move_rename_settings: MoveRenameSettings = move_rename_settings
        self._on_ok = on_ok
        self._initial_dir = initialdir

        if self._move_rename_settings.relative_folder_name is None:
            self._move_rename_settings.relative_folder_name = initialdir

        self.title("Move/Rename Selected")

        self._do_move_var = tk.BooleanVar()
        self._move_type_var = tk.IntVar()
        self._folder_name_var: tk.StringVar = tk.StringVar("")
        self._create_folder_var = tk.BooleanVar()
        self._do_rename_var = tk.BooleanVar()
        self._rename_prefix_var = tk.StringVar("")

        pad = 5
        margin = 30
        button_width = 7

        settings_frame = tk.Frame(self)

        row = 0
        self._move_checkbutton = tk.Checkbutton(settings_frame, text="Move to", variable=self._do_move_var)
        self._move_checkbutton.grid(row=row, column=0, sticky="W")

        row += 1
        self._move_folder_radiobutton = tk.Radiobutton(settings_frame, text="Folder (relative to home)", variable=self._move_type_var,
                                                       value=MoveType.MOVE_TO_FOLDER.value)
        self._move_folder_radiobutton.grid(row=row, column=1, sticky="W")

        row += 1
        self._folder_name_entry = tk.Entry(settings_frame, textvariable=self._folder_name_var)
        self._folder_name_entry.grid(row=row, column=1, sticky="EW")

        self._select_btn = tk.Button(settings_frame, text="Select", underline=0, width=button_width, command=self._select_folder)
        self._select_btn.grid(row=row, column=2, padx=pad, pady=pad)

        self._create_folder_checkbutton = tk.Checkbutton(settings_frame, text="Create",
                                                         variable=self._create_folder_var)
        self._create_folder_checkbutton.grid(row=row, column=3, sticky="W")

        row += 1
        self._move_wastebasket_radiobutton = tk.Radiobutton(settings_frame, text="Wastebasket",
                                                            variable=self._move_type_var,
                                                            value=MoveType.MOVE_TO_WASTEBASKET.value)
        self._move_wastebasket_radiobutton.grid(row=row, column=1, sticky="W")

        row += 1
        self._rename_prefix_checkbutton = tk.Checkbutton(settings_frame, text="Prefix name",
                                                         variable=self._do_rename_var)
        self._rename_prefix_checkbutton.grid(row=row, column=0, sticky="W")

        self._rename_prefix_entry = tk.Entry(settings_frame, width=7, textvariable=self._rename_prefix_var)
        self._rename_prefix_entry.grid(row=row, column=1, sticky="W")

        settings_frame.rowconfigure(0, weight=0, pad=pad)
        settings_frame.rowconfigure(1, weight=0, pad=pad)
        settings_frame.rowconfigure(2, weight=0, pad=pad)
        settings_frame.rowconfigure(3, weight=0, pad=pad * 5)
        settings_frame.columnconfigure(0, pad=margin)
        settings_frame.columnconfigure(1, pad=margin, weight=1)
        settings_frame.grid(row=0, column=0, sticky="EW")

        okcancel_frame = tk.Frame(self)
        self._ok_btn = tk.Button(okcancel_frame, text="OK", underline=0, width=button_width, command=self.on_ok)
        self._ok_btn.grid(row=0, column=1, padx=pad, pady=pad)

        self._cancel_btn = tk.Button(okcancel_frame, text="Cancel", underline=0, width=button_width, command=self.on_cancel)
        self._cancel_btn.grid(row=0, column=3, padx=pad, pady=pad)

        okcancel_frame.columnconfigure(0, weight=1)
        okcancel_frame.grid(row=1, column=0, sticky=tk.EW)

        self.rowconfigure(0, weight=1, pad=margin)
        self.rowconfigure(1, weight=0, pad=margin)
        self.columnconfigure(0, weight=1, pad=margin)

        self.data_directory_var = tk.StringVar()

        self._do_move_var.trace("w", self._enable_widgets)
        self._do_rename_var.trace("w", self._enable_widgets)
        self._move_type_var.trace("w", self._enable_widgets)
        self._folder_name_var.trace("w", self._enable_widgets)
        self._rename_prefix_var.trace("w", self._enable_widgets)
        self._settings_to_vars()

    def _enable_widgets(self, *args):
        ok_permitted: bool = False
        ok_vetoed: bool = False
        if self._do_move_var.get():
            ok_permitted = True
            selected: int = self._move_type_var.get()
            self._move_folder_radiobutton.configure(state=self._state_literal(True))
            self._select_btn.configure(state=self._state_literal(selected == MoveType.MOVE_TO_FOLDER.value))
            self._move_wastebasket_radiobutton.configure(state=self._state_literal(True))
            self._folder_name_entry.configure(state=self._state_literal(selected == MoveType.MOVE_TO_FOLDER.value))
            self._create_folder_checkbutton.configure(
                state=self._state_literal(selected == MoveType.MOVE_TO_FOLDER.value))
            if selected == MoveType.MOVE_TO_FOLDER.value:
                ok_vetoed |= len(self._folder_name_var.get()) == 0
        else:
            self._folder_name_entry.configure(state=self._state_literal(False))
            self._select_btn.configure(state=self._state_literal(False))
            self._create_folder_checkbutton.configure(state=self._state_literal(False))
            self._move_folder_radiobutton.configure(state=self._state_literal(False))
            self._move_wastebasket_radiobutton.configure(state=self._state_literal(False))

        if self._do_rename_var.get():
            ok_permitted = True
            self._rename_prefix_entry.configure(state=self._state_literal(True))
            ok_vetoed |= len(self._rename_prefix_var.get()) == 0
        else:
            self._rename_prefix_entry.configure(state=self._state_literal(False))

        # It makes no sense to rename and move to the wastebasket:
        if self._do_rename_var.get() and self._do_move_var.get() and selected == MoveType.MOVE_TO_WASTEBASKET.value:
            ok_vetoed = True

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
        if directory_selected != '':    # Urgh. You would hope it would None if the user cancels. Oh well.
            self._move_rename_settings.data_directory = directory_selected
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
        self._move_type_var.set(self._move_rename_settings.move_type)
        self._do_move_var.set(1 if self._move_rename_settings.do_move else 0)
        self._folder_name_var.set(self._move_rename_settings.relative_folder_name)
        self._create_folder_var.set(1 if self._move_rename_settings.create_folder else 0)
        self._do_rename_var.set(1 if self._move_rename_settings.do_rename else 0)
        self._rename_prefix_var.set(self._move_rename_settings.rename_prefix)

    def _vars_to_settings(self):
        self._move_rename_settings.move_type = self._move_type_var.get()
        self._move_rename_settings.do_move = False if self._do_move_var.get() == 0 else True
        self._move_rename_settings.relative_folder_name = self._folder_name_var.get()
        self._move_rename_settings.create_folder = False if self._create_folder_var.get() == 0 else True
        self._move_rename_settings.do_rename = False if self._do_rename_var.get() == 0 else True
        self._move_rename_settings.rename_prefix = self._rename_prefix_var.get()
