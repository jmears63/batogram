import os
import shutil
import time
import tkinter as tk
from tkinter import ttk
import send2trash
from pathlib import Path
from typing import Optional, List, Tuple, Callable

from batogram import get_asset_path
from batogram.browseractionsmodal import BrowserActionsModal, BrowserActionsSettings, BrowserAction


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
        if raw_size >= 30 * 1E6:
            return "{:.0f} MB".format(raw_size / 1E6)
        elif raw_size >= 1 * 1E6:
            return "{:.1f} MB".format(raw_size / 1E6)
        elif raw_size >= 30 * 1E3:
            return "{:.0f} KB".format(raw_size / 1E3)
        else:
            return "{:.1f} KB".format(raw_size / 1E3)

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
                                  # time.ctime(raw_mtime),
                                  time.strftime("%H:%M:%S %d %b %Y", time.localtime(raw_mtime)),
                                  raw_mtime)
                                 )

        return paths


MAX_STRING = 50


class BrowserFrame(tk.Frame):
    def __init__(self, parent, root_parent: "RootWindow", pad: int):
        super().__init__(parent)

        self._root_parent = root_parent

        self._flagged_str: str = "FLAGGED"
        self._unflagged_str: str = "UNFLAGGED"

        # The life cycle of the settings is the same as the browser frame, ie the
        # lifetime of the application:
        self._action_settings: BrowserActionsSettings = BrowserActionsSettings()

        self._file_list_entries: List[Tuple[str, str]] = []

        self._image_unflagged = tk.PhotoImage(file=get_asset_path("transparent.png"))
        self._image_flagged = tk.PhotoImage(file=get_asset_path("flag-fill.png"))

        self._path_var = tk.StringVar(value="")
        self._path_label = tk.Label(self, textvariable=self._path_var, anchor=tk.W)
        self._path_label.grid(row=0, column=0, sticky="ew", padx=pad, pady=pad)
        self._display_as_ref_var = tk.BooleanVar()

        # State of column sorting: current sorted column, reversed flag:
        self._column_sort_state: Tuple[Optional[int], bool]
        self._reset_sort_state()

        treeview_frame = tk.Frame(self)
        self._file_list_var = tk.StringVar()
        tv = ttk.Treeview(treeview_frame,
                          selectmode=tk.EXTENDED,
                          show='tree headings',  # Don't show the columns headings.
                          columns=("size", "raw size", "modified", "raw modified"),
                          displaycolumns=(0, 2),
                          takefocus=1
                          )
        self._file_treeview = tv
        # tv.column(0, width=10, anchor=tk.E)      # Seems to do nothing.
        # Minwidth set quite large so that horizontal scrolling is possible:
        self._treeview_set_headings(tv)
        # "stretch" controls what happens if the widget is resized, not the column. The columns
        # can always be resized:
        tv.column('#0', width=200, minwidth=150, stretch=True)
        tv.column('#1', width=60, minwidth=60, stretch=True)
        tv.column('#2', width=150, minwidth=100, stretch=True)

        tv.tag_configure(self._flagged_str, image=self._image_flagged, background="#ffffcc")
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

        self._default_flagging_text = "Select and flag items above to perform an action."
        self._flagged_count_var = tk.StringVar(self)
        flagged_count_label = tk.Label(self, textvariable=self._flagged_count_var)
        flagged_count_label.grid(row=2, column=0, sticky="W", padx=pad, pady=pad)

        button_frame1 = tk.Frame(self)
        self._toggle_tagging_button = tk.Button(button_frame1, text="Flag selected items", command=self._on_toggle_flags)
        self._toggle_tagging_button.grid(row=0, column=0, sticky="ew", padx=pad)
        self._toggle_tagging_button.config(state=tk.DISABLED)
        self._clear_flags_button = tk.Button(button_frame1, text="Clear all flags", command=self._on_clear_flags)
        self._clear_flags_button.grid(row=0, column=1, sticky="ew", padx=pad)
        self._clear_flags_button.config(state=tk.DISABLED)
        self._actions_button = tk.Button(button_frame1, text="Action...", command=self._on_do_action)
        self._actions_button.grid(row=0, column=2, sticky="ew", padx=pad)
        self._actions_button.config(state=tk.DISABLED)
        button_frame1.grid(row=3, column=0, sticky="nsew")

        button_frame2 = tk.Frame(self)
        reset_button = tk.Button(button_frame2, text="Reload", command=self._on_reset)
        reset_button.grid(row=0, column=0, sticky="nsew", padx=pad, pady=pad)
        close_button = tk.Button(button_frame2, text="Close", command=self._on_close)
        close_button.grid(row=0, column=1, sticky="nsew", padx=pad, pady=pad)
        ref_checkbutton = tk.Checkbutton(button_frame2, text="Display as reference", variable=self._display_as_ref_var)
        ref_checkbutton.grid(row=0, column=2, sticky="W", padx=pad, pady=pad)
        button_frame2.grid(row=4, column=0, sticky="nsew")

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self._update_ui_state()

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

        # Select the first row, if there is one, leaving
        # any flagging unchanged:
        if len(li) > 0:
            first_iid = li[0][1]
            tv1.selection_set([first_iid])

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

    def _populate(self, folder_walker: Optional[FolderWalker], do_initial_selection: bool = True) -> bool:
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

        # Select and load the first file in the list, first clearing any existing selection:
        if do_initial_selection and not empty:
            iid = self._file_treeview.get_children()[0]
            # Set the focus so that the selection event results in the item being loaded:
            self._file_treeview.focus(iid)
            self._file_treeview.selection_set(iid)

        self._update_ui_state()
        self._file_treeview.focus_set()

        return not empty

    def reset(self, folder_walker: Optional[FolderWalker], do_initial_selection: bool = True):
        # Reset the state of this frame and its contents based on the folder walker
        # supplied.
        non_empty = self._populate(folder_walker, do_initial_selection)
        if folder_walker and not non_empty:
            tk.messagebox.showwarning("Warning", message="The selected folder contains no audio files.")

    def _on_close(self):
        self.do_close()

    def do_close(self):
        if self._folder_walker is not None:
            self._folder_walker.close()
        self._clear_treeview()
        self._update_ui_state()
        # Notify the parent that the broswer is closing:
        self._root_parent.on_close_folder()

    def _on_reset(self):
        self.reset(None)

    def _set_path(self, path):
        p = str(path)
        self._path_var.set(self._truncate_string(p, False) + ":")

    def _on_treeview_select(self, event):
        # Update the UI:
        self._update_ui_state()

        # Load the focussed item:
        def update_cb():
            selected_iid = self._file_treeview.focus()
            if selected_iid != '':
                def open_file(f):
                    if self._display_as_ref_var.get():
                        self._root_parent.do_open_ref_file(f, setfocus=False)
                    else:
                        self._root_parent.do_open_main_file(f, setfocus=False)

                self._load_activated_file(open_file, selected_iid)

        # We can't do the update here and now because index(tk.ACTIVE) still refers the old value.
        # That seems like a bug in tkinter or tk. So, this little hack is to allow tk to catch up with itself,
        # which it generally will, but might not if the CPU has other things on its mind.
        self.after(200, update_cb)

        return

    @staticmethod
    def _load_activated_file(action: Callable, selection: str):
        selected_path = selection
        action(selected_path)

    def _on_do_action(self):
        ok_clicked: bool = False

        def on_ok():
            nonlocal ok_clicked
            ok_clicked = True

        tv = self._file_treeview
        # Note the selection before displaying the modal, as it can be cleared if
        # they open the directory selection dialog. But not always. Me neither.
        flagged_item_iids = self._get_flagged_items()
        flagged_items = [tv.item(iid) for iid in flagged_item_iids]

        # Prompt the user for an action and supporting parameters:
        default_folder = os.path.relpath(self._folder_walker.get_path(), Path.home())
        single_flagged_filename = None if len(flagged_items) != 1 else flagged_items[0]['text']
        modal = BrowserActionsModal(self, self._action_settings, on_ok,
                                    initialdir=default_folder, single_flagged_filename=single_flagged_filename)
        modal.grab_set()
        modal.wait_window()

        # Take the action if they didn't cancel:
        if ok_clicked:            # Note the first flagged item before any action is taken:
            first_flagged_index: Optional[int] = None
            if len(flagged_item_iids) > 0:
                first_flagged_index = tv.index(flagged_item_iids[0])

            for item in flagged_items:
                filename = item['text']
                try:
                    self._do_item_action(filename, self._action_settings)
                except BaseException as e:
                    cont = tk.messagebox.askyesno(title="Error",
                                                  message="Unable to perform requested action:\n\n {}\n\nDo you want to continue?".format(
                                                      str(e)))
                    if not cont:
                        break

            # Refresh the list:
            self.reset(None, do_initial_selection=False)
            # Restore the selection if we can, including flagging:
            selected_count: int = 0
            flagged_count: int = 0
            for iid in flagged_item_iids:
                try:
                    if tv.item(iid) is not None:
                        tv.selection_add(iid)
                        tv.item(iid, tags=[self._flagged_str])
                        selected_count += 1
                        flagged_count += 1
                except tk.TclError:
                    pass        # If an item is deleted or moved, it no longer exists. That is expected.

            # If none were selected, see if we can select the same first row number was as previously
            # selected. That's helpful when we are working through a list deleting things.
            new_children = tv.get_children("")
            if selected_count == 0 and first_flagged_index is not None:
                if first_flagged_index < len(new_children):
                    iid = new_children[first_flagged_index]
                    tv.selection_set(iid)
                    tv.focus(iid)
                    selected_count = 1

            # If all else fails, select the first item, if present:
            if selected_count == 0 and len(new_children) > 0:
                tv.selection_set(new_children[0])
                tv.focus(new_children[0])
                selected_count = 1

            self._update_ui_state()

    def _do_item_action(self, source_filename: str, settings: BrowserActionsSettings):

        # Note: paths provided by the user are relative to their home directory.

        source_folder: str = str(self._folder_walker.get_path())
        source_path = os.path.normpath(os.path.join(source_folder, source_filename))

        if settings.action == BrowserAction.TRASH.value:
            self._root_parent.prepare_to_modify_file(source_path)
            send2trash.send2trash(source_path)
        elif settings.action in [BrowserAction.MOVE.value, BrowserAction.COPY.value]:
            target_filename = source_filename
            if settings.prefix_str is not None:
                target_filename = settings.prefix_str + target_filename
            elif settings.rename_str is not None:
                target_filename = settings.rename_str

            target_folder = os.path.join(Path.home(), settings.relative_folder_name)
            target_path = os.path.normpath(os.path.join(target_folder, target_filename))

            if settings.create_folder and not os.path.exists(target_folder):
                os.makedirs(target_folder)  # Doesn't seem to mind if the dirs already exist.

            # Do the move - which might just be a file rename:
            if settings.action == BrowserAction.MOVE.value:
                self._root_parent.prepare_to_modify_file(source_path)
                print("Moving {} to {}".format(source_path, target_path))
                self._check_target(target_path)
                shutil.move(source_path, target_path)
            elif settings.action == BrowserAction.COPY.value:
                print("Copying {} to {}".format(source_path, target_path))
                self._check_target(target_path)
                shutil.copy(source_path, target_path)
        elif settings.action == BrowserAction.RENAME.value:
            self._root_parent.prepare_to_modify_file(source_path)
            target_path = os.path.normpath(os.path.join(source_folder, settings.rename_str))
            print("Rename {} to {}".format(source_path, target_path))
            self._check_target(target_path)
            shutil.move(source_path, target_path)

    @staticmethod
    def _check_target(target_path):
        # Check if the target already exists and throw an exception if it does.
        if os.path.exists(target_path):
            raise FileExistsError("Target {} already exists".format(target_path))

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

        self._update_ui_state()

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

        self._update_ui_state()

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

    def _reset_sort_state(self):
        self._column_sort_state = (None, False)

    def _update_ui_state(self):
        selected = len(self._file_treeview.selection())
        flagged = len(self._get_flagged_items())

        state = tk.NORMAL if selected > 0 else tk.DISABLED
        self._toggle_tagging_button.config(state=state)

        state = tk.NORMAL if flagged > 0 else tk.DISABLED
        self._clear_flags_button.config(state=state)
        self._actions_button.config(state=state)

        if flagged > 0:
            self._flagged_count_var.set("{} item(s) flagged for action.".format(flagged))
        else:
            self._flagged_count_var.set(self._default_flagging_text)
