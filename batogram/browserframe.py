import os
import shutil
import time
import tkinter as tk
from tkinter import ttk
import send2trash
from pathlib import Path
from typing import Optional, List, Tuple, Callable

from batogram import get_asset_path
from batogram.moverenamemodal import MoveRenameModal, MoveRenameSettings, MoveType


class FolderWalker:
    """This class knows how to iterate through wav files in a folder."""

    def __init__(self, folder_path: Path):
        self._folder_path: Path = folder_path

    def close(self):
        pass

    def get_path(self) -> Path:
        return self._folder_path

    @staticmethod
    def _formatted_size(raw_size) -> str:
        if raw_size >= 1000000:
            return "{:.1f} MB".format(raw_size / 1000000)
        else:
            return "{:.1f} KB".format(raw_size / 1024)

    def get_list(self) -> List[Tuple[str, str]]:
        contents = os.listdir(self._folder_path)
        paths: List[(str, str)] = []
        for item in contents:
            path = os.path.join(self._folder_path, item)
            if os.path.isdir(path):
                pass  # Don't want folders, only files.
            else:
                _, ext = os.path.splitext(path)
                if ext.lower() == '.wav':
                    raw_mtime = os.path.getmtime(path)
                    raw_size = os.path.getsize(path)
                    paths.append((item, path,
                                  self._formatted_size(raw_size), raw_size,
                                  time.ctime(raw_mtime), raw_mtime)
                                 )

        return paths


MAX_STRING = 50


class BrowserFrame(tk.Frame):
    def __init__(self, parent: "RootWindow", pad: int):
        super().__init__(parent)

        self._flagged_str: str = "FLAGGED"
        self._unflagged_str: str = "UNFLAGGED"

        # The life cycle of the settings is the same as the browser frame, ie the
        # lifetime of the application:
        self._move_rename_settings: MoveRenameSettings = MoveRenameSettings()
        self._parent = parent
        self._file_list_entries: List[Tuple[str, str]] = []

        self._image_unflagged = tk.PhotoImage(file=get_asset_path("transparent.png"))
        self._image_flagged = tk.PhotoImage(file=get_asset_path("flag-fill.png"))

        self._path_var = tk.StringVar(value="")
        self._path_label = tk.Label(self, textvariable=self._path_var, anchor=tk.W)
        self._path_label.grid(row=0, column=0, sticky="ew", padx=pad, pady=pad)

        # State of column sorting: current sorted column, reversed flag:
        self._column_sort_state: Tuple[Optional[int], bool]
        self._reset_sort_start()

        treeview_frame = tk.Frame(self)
        self._file_list_var = tk.StringVar()
        tv = ttk.Treeview(treeview_frame,
                          selectmode=tk.EXTENDED,
                          show='tree headings',  # Don't show the columns headings.
                          columns=("size", "raw size", "modified", "raw modified"),
                          displaycolumns=(0, 2)
                          )
        self._file_treeview = tv
        # tv.column(0, width=10, anchor=tk.E)      # Seems to do nothing.
        # Minwidth set quite large so that horizontal scrolling is possible:
        self._treeview_set_headings(tv)
        # "stretch" controls what happens if the widget is resized, not the column. The columns
        # can always be resized:
        tv.column('#0', width=200, minwidth=150, stretch=True)
        tv.column('#1', width=60, minwidth=70, stretch=False)
        tv.column('#2', width=150, minwidth=100, stretch=False)

        tv.tag_configure(self._flagged_str, image=self._image_flagged, background="#ffcc99")
        tv.tag_configure(self._unflagged_str, image=self._image_unflagged)

        self._file_treeview.bind("<<TreeviewSelect>>", self._on_treeview_select)

        vscrollbar = tk.Scrollbar(treeview_frame, orient=tk.VERTICAL)
        self._file_treeview.config(yscrollcommand=vscrollbar.set)
        vscrollbar.config(command=self._file_treeview.yview)
        vscrollbar.grid(row=0, column=1, sticky="nsew")

        hscrollbar = tk.Scrollbar(treeview_frame, orient=tk.HORIZONTAL)
        self._file_treeview.config(xscrollcommand=hscrollbar.set)
        hscrollbar.config(command=self._file_treeview.xview)
        hscrollbar.grid(row=1, column=0, sticky="nsew")

        self._file_treeview.grid(row=0, column=0, sticky="nsew")

        treeview_frame.rowconfigure(0, weight=1)
        treeview_frame.columnconfigure(0, weight=1)
        treeview_frame.grid(row=1, column=0, sticky="nsew", padx=pad, pady=pad)

        self._flagged_count_var = tk.StringVar(self, "")
        flagged_count_label = tk.Label(self, textvariable=self._flagged_count_var)
        flagged_count_label.grid(row=2, column=0, sticky="ew", padx=pad)

        button_frame1 = tk.Frame(self)
        self._toggle_tagging_button = tk.Button(button_frame1, text="Flag selected", command=self._on_toggle_flags)
        self._toggle_tagging_button.grid(row=0, column=0, sticky="ew", padx=pad)
        self._toggle_tagging_button.config(state=tk.DISABLED)
        self._clear_flags_button = tk.Button(button_frame1, text="Clear flags", command=self._on_clear_flags)
        self._clear_flags_button.grid(row=0, column=1, sticky="ew", padx=pad)
        self._clear_flags_button.config(state=tk.DISABLED)
        self._actions_button = tk.Button(button_frame1, text="Actions...", command=self._on_do_action)
        self._actions_button.grid(row=0, column=2, sticky="ew", padx=pad)
        self._actions_button.config(state=tk.DISABLED)
        button_frame1.grid(row=3, column=0, sticky="nsew")

        button_frame2 = tk.Frame(self)
        reset_button = tk.Button(button_frame2, text="Reload", command=self._on_reset)
        reset_button.grid(row=0, column=0, sticky="nsew", padx=pad, pady=pad)
        close_button = tk.Button(button_frame2, text="Close", command=self._on_close)
        close_button.grid(row=0, column=1, sticky="nsew", padx=pad, pady=pad)
        button_frame2.grid(row=4, column=0, sticky="nsew")

        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=0)
        self.rowconfigure(4, weight=0)

        self._file_treeview.focus_set()

    def _treeview_sort_column(self, tv1: ttk.Treeview, value_index: Optional[int], reset: bool = False):
        # Work what what is required based on current sort state:
        reverse: bool = False
        if reset:
            reverse = False
        else:
            if value_index == self._column_sort_state[0]:
                reverse = not self._column_sort_state[1]

        # Make a list of tuples: entry and column value:
        def get_sort_value(entry):
            if value_index is None:
                return entry['text'].lower()
            else:
                return entry['values'][value_index]

        li = [(get_sort_value(tv1.item(iid)), iid) for iid in tv1.get_children('')]
        # Sort by the value:
        li.sort(key=lambda t: t[0], reverse=reverse)

        # Rearrange items in sorted positions
        for index, (_, iid) in enumerate(li):
            tv1.move(iid, '', index)

        # Update the state to what we have just done:
        self._column_sort_state = (value_index, reverse)

        # Modify the column headers to match the sorting:
        self._treeview_set_headings(tv1)

    def _treeview_set_headings(self, tv: ttk.Treeview):
        def set_heading(cid, text, sort_value_index: Optional[int]):
            sort_column, reverse = self._column_sort_state
            if sort_value_index == sort_column:
                suffix = " ↓" if reverse else " ↑"
            else:
                suffix = ""

            tv.heading(cid, text=text + suffix, anchor=tk.W,
                       command=lambda: self._treeview_sort_column(tv, sort_value_index))

        set_heading('#0', "File",  None)
        set_heading('#1', "Size",  1)
        set_heading('#2', "Modified",  3)

    def _clear_treeview(self):
        for item in self._file_treeview.get_children():
            self._file_treeview.delete(item)

    def _populate(self, folder_walker: Optional[FolderWalker]) -> bool:
        if folder_walker is not None:
            self._folder_walker = folder_walker
        del folder_walker

        self._set_path(self._folder_walker.get_path())

        # Walk the folder, finding files with the right extensions:
        self._clear_treeview()
        empty: bool = True
        for (item, path, size, raw_size, mtime, raw_mtime) in self._folder_walker.get_list():
            empty = False
            self._file_treeview.insert("", tk.END,
                                       text=item,
                                       values=(size, raw_size, mtime, raw_mtime),
                                       tags=[self._unflagged_str],
                                       iid=path  # Use the full path to the file as the iid.
                                       )

        # Reset some things:
        self._treeview_sort_column(self._file_treeview, None, reset=True)
        self._toggle_tagging_button.config(state=tk.DISABLED)
        self._flagged_count_var.set("")

        # Select and load the first file in the list, first clearing any existing selection:
        if not empty:
            iid = self._file_treeview.get_children()[0]
            # A side effect of the following is to load the file, as the selection event is generated:
            self._file_treeview.selection_set(iid)

        return not empty

    def reset(self, folder_walker: Optional[FolderWalker]):
        # Reset the state of this frame and its contents based on the folder walker
        # supplied.
        non_empty = self._populate(folder_walker)
        if folder_walker and not non_empty:
            tk.messagebox.showwarning("Warning", message="The selected folder contains no audio files.")

    def _on_close(self):
        # Notify the parent that they are closing the browser:
        self._parent.close_folder()

    def _on_reset(self):
        self.reset(None)

    def _set_path(self, path):
        p = str(path)
        self._path_var.set(self._truncate_string(p, False) + ":")

    def _on_treeview_select(self, event):
        # Update the UI:
        selection_tuple = self._file_treeview.selection()
        button_state = tk.NORMAL if len(selection_tuple) > 0 else tk.DISABLED
        self._toggle_tagging_button.config(state=button_state)

        # Only load data when exactly one row is selected - to avoid flicker when
        # extending the selection.
        if len(selection_tuple) == 1:
            def update_cb():
                selected = selection_tuple[0]
                self._load_activated_file(lambda x: self._parent.do_open_main_file(x, setfocus=False), selected)

            # We can't do the update here and now because index(tk.ACTIVE) still refers the old value.
            # That seems like a bug in tkinter or tk. So, this little hack is to allow tk to catch up with itself,
            # which it generally will, but might not if the CPU has other things on its mind.
            self.after(200, update_cb)

    @staticmethod
    def _load_activated_file(action: Callable, selection: str):
        selected_path = selection
        action(selected_path)

    def _on_do_action(self):
        ok_clicked: bool = False

        def on_ok():
            nonlocal ok_clicked
            ok_clicked = True

        # Note the selection before displaying the modal, as it can be cleared if
        # they open the directory selection dialog. But not always. Me neither.
        flagged_items = [self._file_treeview.item(iid) for iid in self._get_flagged_items()]

        # Prompt the user with move/rename parameters:
        default_folder = os.path.relpath(self._folder_walker.get_path(), Path.home())
        modal = MoveRenameModal(self, self._move_rename_settings, on_ok, initialdir=default_folder)
        modal.grab_set()
        modal.wait_window()

        # Take the action if they didn't cancel:
        if ok_clicked:
            for item in flagged_items:
                filename = item['text']
                try:
                    self._do_action(filename, self._move_rename_settings)
                except BaseException as e:
                    cont = tk.messagebox.askyesno(title="Error",
                                                  message="Unable to perform requested action:\n\n {}\n\nDo you want to continue?".format(
                                                      str(e)))
                    if not cont:
                        break

            self.reset(None)

    def _on_toggle_flags(self):
        # One or more items in the treeview may be tagged:
        selection_tuple = self._file_treeview.selection()
        if len(selection_tuple) > 0:
            # Get the tagged state of the first selected item:
            tv = self._file_treeview
            first_tags = tv.item(selection_tuple[0])['tags']
            # We will tag if the first item wasn't tagged, otherwise untag:
            new_tags = [self._unflagged_str] if first_tags.count(self._flagged_str) > 0 else [self._flagged_str]

            # Apply to all selected:
            for iid in selection_tuple:
                item = tv.item(iid)
                tv.item(iid, tags=new_tags)

        flagged_count = len(self._get_flagged_items())
        state = tk.NORMAL if flagged_count > 0 else tk.DISABLED
        self._actions_button.config(state=state)
        self._clear_flags_button.config(state=state)
        self._flagged_count_var.set("{} file(s) flagged for action".format(flagged_count))

    def _get_flagged_items(self):
        tv = self._file_treeview
        iids = []
        for iid in tv.get_children(''):
            item = tv.item(iid)
            if item['tags'].count(self._flagged_str) > 0:
                iids.append(iid)

        return iids

    def _on_clear_flags(self):
        # Reset all items to unflagged.
        tv = self._file_treeview
        children = tv.get_children('')
        for iid in children:
            tv.item(iid, tags=[self._unflagged_str])

        self._actions_button.config(state=tk.DISABLED)
        self._clear_flags_button.config(state=tk.DISABLED)
        self._flagged_count_var.set("")

    @staticmethod
    def _truncate_string(s: str, at_end: bool = True) -> str:
        my_ellipsis = "..."
        ellipsis_len = len(my_ellipsis)

        if len(s) > MAX_STRING - ellipsis_len:
            if at_end:
                s = s[:(MAX_STRING - ellipsis_len)] + my_ellipsis
            else:
                s = my_ellipsis + s[-(MAX_STRING - ellipsis_len):]

        return s

    def _do_action(self, source_filename: str, settings: MoveRenameSettings):

        # Note: paths provided by the user are relative to their home directory.

        source_folder: str = str(self._folder_walker.get_path())
        source_path = os.path.normpath(os.path.join(source_folder, source_filename))

        if settings.do_move and settings.move_type == MoveType.MOVE_TO_WASTEBASKET:
            # Move to the waste basket:
            send2trash.send2trash(source_path)
            return

        target_filename = source_filename
        if settings.do_rename:
            target_filename = settings.rename_prefix + source_filename

        target_folder: str = source_folder
        if settings.do_move and settings.move_type == MoveType.MOVE_TO_FOLDER:
            target_folder = os.path.join(Path.home(), settings.relative_folder_name)

        target_path = os.path.normpath(os.path.join(target_folder, target_filename))

        # Creating the target path first if required.
        # Note: it might exist but be a file, not a folder. That will fail
        # downstream.
        if settings.create_folder and not os.path.exists(target_folder):
            os.makedirs(target_folder)  # Doesn't seem to mind if the dirs already exist.

        # Do the move - which might just be a file rename:
        print("Moving {} to {}".format(source_path, target_path))

        shutil.move(source_path, target_path)

    def _reset_sort_start(self):
        self._column_sort_state = (None, False)

