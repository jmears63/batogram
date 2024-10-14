import os
import shutil
import tkinter as tk
from tkinter import ttk
import send2trash
from pathlib import Path
from typing import Optional, List, Tuple, Callable

from batogram import get_asset_path
from batogram.moverenamemodal import MoveRenameModal, MoveRenameSettings, MoveType

SORT_NATURAL = "Natural order"
SORT_TIME = "Time order"
SORT_ALPHABETICAL = "Alphabetical order"


class FolderWalker:
    """This class knows how to iterate through wav files in a folder in a given sort order."""

    def __init__(self, folder_path: Path):
        self._folder_path: Path = folder_path

    def close(self):
        pass

    def get_path(self) -> Path:
        return self._folder_path

    def get_list(self, sort_type: str) -> List[Tuple[str, str]]:
        contents = os.listdir(self._folder_path)
        paths: List[(str, str)] = []
        for item in contents:
            path = os.path.join(self._folder_path, item)
            if os.path.isdir(path):
                pass  # Don't want folders, only files.
            else:
                _, ext = os.path.splitext(path)
                if ext.lower() == '.wav':
                    paths.append((item, path))

        # The folder contents are in natural order at this point. If the user has
        # asked for a different sort order, do that now:

        if sort_type == SORT_TIME:
            def time_compare(entry):
                _, p = entry
                return os.path.getmtime(p)

            paths = sorted(paths, key=time_compare)
        elif sort_type == SORT_ALPHABETICAL:
            def alpha_compare(entry):
                name, _ = entry
                return name

            paths = sorted(paths, key=alpha_compare)

        return paths


MAX_STRING = 35


class BrowserFrame(tk.Frame):
    def __init__(self, parent: "RootWindow", pad: int):
        super().__init__(parent)

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

        treeview_frame = tk.Frame(self)
        self._file_list_var = tk.StringVar()
        tv = ttk.Treeview(treeview_frame,
                          selectmode=tk.EXTENDED,
                          show='tree headings',  # Don't show the columns headings.
                          columns=("size", "time"),
                          )
        self._file_treeview = tv
        # tv.column(0, width=10, anchor=tk.E)      # Seems to do nothing.
        # Minwidth set quite large so that horizontal scrolling is possible:
        tv.heading('#0', text="File", anchor=tk.W)
        tv.heading('#1', text="Size", anchor=tk.W)
        tv.heading('#2', text="Time", anchor=tk.W)
        # "stretch" controls what happens if the widget is resized, not the column. The columns
        # can always be resized:
        tv.column('#0', width=200, minwidth=150, stretch=True)
        tv.column('#1', width=60, minwidth=60, stretch=False)
        tv.column('#2', width=150, minwidth=100, stretch=False)

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

        self._selected_count_var = tk.StringVar(self, "")
        selected_count_label = tk.Label(self, textvariable=self._selected_count_var)
        selected_count_label.grid(row=2, column=0, sticky="ew", padx=pad)

        sort_options = (SORT_NATURAL, SORT_TIME, SORT_ALPHABETICAL)
        self._sorting_var = tk.StringVar(self, SORT_TIME)
        sorting_menu = tk.OptionMenu(self, self._sorting_var, *sort_options, command=self._on_sort_order_changed)
        sorting_menu.grid(row=3, column=0, sticky="ew", padx=pad)

        self._moverename_button = tk.Button(self, text="Move/Rename", command=self._on_moverename)
        self._moverename_button.grid(row=4, column=0, sticky="ew", padx=pad)
        self._moverename_button.config(state=tk.DISABLED)

        button_frame = tk.Frame(self)
        reset_button = tk.Button(button_frame, text="Reload", command=self._on_reset)
        reset_button.grid(row=0, column=0, sticky="nsew", padx=pad, pady=pad)
        close_button = tk.Button(button_frame, text="Close", command=self._on_close)
        close_button.grid(row=0, column=1, sticky="nsew", padx=pad, pady=pad)
        button_frame.grid(row=5, column=0, sticky="nsew")

        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=0)

        self._file_treeview.focus_set()

    def _clear_treeview(self):
        for item in self._file_treeview.get_children():
            self._file_treeview.delete(item)

    def _populate(self, folder_walker: Optional[FolderWalker]) -> bool:
        if folder_walker is not None:
            self._folder_walker = folder_walker
        del folder_walker

        self._set_path(self._folder_walker.get_path())

        # Walk the folder, finding files with the right extensions:
        self._file_list_entries = self._folder_walker.get_list(self._sorting_var.get())
        # Limit the length of the string:
        # entries_as_array = [self._truncate_string(item) for (item, path) in self._file_list_entries]
        entries_as_array = [item for (item, path) in self._file_list_entries]

        self._clear_treeview()
        for entry in entries_as_array:
            self._file_treeview.insert("", tk.END,
                                       text=entry,
                                       image=self._image_flagged if False else self._image_unflagged,
                                       values=("1.2M", "2024-12-05 22.43"),
                                       iid=self._folder_walker.get_path() / entry        # Use the file path as the iid.
                                       )

        # Select and load the first file in the list, first clearing any existing selection:
        if len(self._file_list_entries) > 0:
            iid = self._file_treeview.get_children()[0]
            # A side effect of the following is to load the file, as the selection event is generated:
            self._file_treeview.selection_set(iid)

        return len(self._file_list_entries) > 0

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
        # selection_tuple = self._file_treeview.curselection()
        selection_tuple = self._file_treeview.selection()
        self._selected_count_var.set("{} selected".format(len(selection_tuple)))
        button_state = tk.NORMAL if len(selection_tuple) > 0 else tk.DISABLED
        self._moverename_button.config(state=button_state)

        # Only load data when exactly one row is selected - to avoid flicker when
        # extending the selection.
        if len(selection_tuple) == 1:
            def update_cb():
                # selected = self._file_treeview.index(tk.ACTIVE)
                selected = selection_tuple[0]
                self._load_activated_file(lambda x: self._parent.do_open_main_file(x, setfocus=False), selected)

            # We can't do the update here and now because index(tk.ACTIVE) still refers the old value.
            # That seems like a bug in tkinter or tk. So, this little hack is to allow tk to catch up with itself,
            # which it generally will, but might not if the CPU has other things on its mind.
            self.after(200, update_cb)

        if False:
            def print_hierarchy(w, depth=0):
                print('  ' * depth + w.winfo_class() + ' w=' + str(w.winfo_width()) + ' h=' + str(
                    w.winfo_height()) + ' x=' + str(w.winfo_x()) + ' y=' + str(w.winfo_y()))
                for i in w.winfo_children():
                    print_hierarchy(i, depth + 1)

            print_hierarchy(self, 5)

            c = self._file_treeview.configure()
            print(c)

            print("Requested: {} {}".format(self._file_treeview.winfo_reqwidth(), self._file_treeview.winfo_reqheight()))
            print("Actual: {} {}".format(self._file_treeview.winfo_width(), self._file_treeview.winfo_height()))

    def _load_activated_file(self, action: Callable, selection: str):
        # _, selected_path = self._file_list_entries[selection]
        selected_path = selection
        action(selected_path)

    def _on_sort_order_changed(self, _):
        self.reset(None)

    def _on_moverename(self):
        ok_clicked: bool = False

        def on_ok():
            nonlocal ok_clicked
            ok_clicked = True

        # Note the selection before displaying the modal, as it can be cleared if
        # they open the directory selection dialog. But not always. Me neither.
        current_selection = self._file_treeview.curselection()

        # Prompt the user with move/rename parameters:
        default_folder = os.path.relpath(self._folder_walker.get_path(), Path.home())
        modal = MoveRenameModal(self, self._move_rename_settings, on_ok, initialdir=default_folder)
        modal.grab_set()
        modal.wait_window()

        # Take the action if they didn't cancel:
        if ok_clicked:
            for sel_index in current_selection:
                filename = self._file_treeview.get(sel_index)
                try:
                    self._do_move_rename(filename, self._move_rename_settings)
                except BaseException as e:
                    cont = tk.messagebox.askyesno(title="Error",
                                                  message="Unable to perform requested action:\n\n {}\n\nDo you want to continue?".format(
                                                      str(e)))
                    if not cont:
                        break

            self.reset(None)

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

    def _do_move_rename(self, source_filename: str, settings: MoveRenameSettings):

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
