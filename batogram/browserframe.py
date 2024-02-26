import os
import tkinter as tk
from pathlib import Path
from typing import Optional, List, Tuple, Callable

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
                pass        # Don't want folders, only files.
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

        self._parent = parent
        self._file_list_entries: List[Tuple[str, str]] = []

        self._path_var = tk.StringVar(value="")
        self._path_label = tk.Label(self, textvariable=self._path_var, anchor=tk.W)
        self._path_label.grid(row=0, column=0, sticky="ew", padx=pad, pady=pad)

        list_frame = tk.Frame(self)
        self._file_list_var = tk.StringVar()
        self._file_list = tk.Listbox(list_frame, listvariable=self._file_list_var,
                                     width=0,       # Adjust width to data.
                                     height=10)
        self._file_list.bind("<<ListboxSelect>>", self._on_listbox_select_main)
        scrollbar = tk.Scrollbar(list_frame)
        self._file_list.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self._file_list.yview)
        self._file_list.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=pad, pady=pad)

        sort_options = (SORT_NATURAL, SORT_TIME, SORT_ALPHABETICAL)
        self._sorting_var = tk.StringVar(self, SORT_TIME)
        sorting_menu = tk.OptionMenu(self, self._sorting_var, *sort_options, command=self._on_sort_order_changed)
        sorting_menu.grid(row=2, column=0, sticky="ew", padx=pad)

        button_frame = tk.Frame(self)
        reset_button = tk.Button(button_frame, text="Reset", command=self._on_reset)
        reset_button.grid(row=0, column=0, sticky="nsew", padx=pad, pady=pad)
        close_button = tk.Button(button_frame, text="Close", command=self._on_close)
        close_button.grid(row=0, column=1, sticky="nsew", padx=pad, pady=pad)
        button_frame.grid(row=3, column=0, sticky="nsew")

        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=0)

    def _populate(self, folder_walker: Optional[FolderWalker]) -> bool:

        if folder_walker is not None:
            self._folder_walker = folder_walker
        del folder_walker

        self._set_path(self._folder_walker.get_path())

        # Walk the folder, finding files with the right extensions:
        self._file_list_entries = self._folder_walker.get_list(self._sorting_var.get())
        # Limit the length of the string:
        entries_as_array = [self._truncate_string(item) for (item, path) in self._file_list_entries]
        self._file_list_var.set(entries_as_array)

        # Select and load the first file in the list, first clearing any existing selection:
        self._file_list.select_clear(0, tk.END)
        if len(self._file_list_entries) > 0:
            self._file_list.select_set(0)
            self._load_selected_file(self._parent.do_open_main_file)

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

    def _load_selected_file(self, action: Callable):
        sel_tuple = self._file_list.curselection()
        if len(sel_tuple) > 0:
            selection = sel_tuple[0]
            _, selected_path = self._file_list_entries[selection]
            action(selected_path)

    def _on_listbox_select_main(self, _):
        self._load_selected_file(self._parent.do_open_main_file)

    def _on_listbox_select_ref(self, _):
        self._load_selected_file(self._parent.do_open_ref_file)

    def _on_sort_order_changed(self, _):
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

