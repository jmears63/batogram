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
import webbrowser
from typing import Optional

import numpy as np

from .graphsettings import GraphSettings

from tkinter import scrolledtext
from tkinter import messagebox, ttk, font
from .morebncframe import HistogramInterface, BrightnessContrastFrame
from .moreotherframe import OtherFrame
from .morerenderingframe import RenderingFrame
from .morescaleframe import ScaleFrame
from .external.tooltip import ToolTip
from .validatingwidgets import ControllingFrameMixin
from .external.guano import GuanoFile


class SettingsButtonFrame(tk.Frame, ControllingFrameMixin):
    """A Frame containing buttons used to apply updated settings values."""

    def __init__(self, parent):
        super().__init__(parent)
        ControllingFrameMixin.__init__(self)
        self._apply_button = tk.Button(self, text="Apply", command=self._do_apply)
        self._apply_button.grid(row=0, column=0, sticky="ew")
        self._cancel_button = tk.Button(self, text="Reset", command=self._do_cancel)
        self._cancel_button.grid(row=1, column=0, sticky="ew")
        self._parent = parent

    def _do_apply(self):
        if self.do_validate():
            # Set the UI state to the applied values.
            self.do_apply()
            # Copy the widget values into the settings data class:
            self._parent.on_apply()

    def _do_cancel(self):
        self.do_cancel()

    def enable_controlling_buttons(self, enabled):
        self._apply_button["state"] = enabled
        self._cancel_button["state"] = enabled

    def show_error(self, containing_frame, message):
        self._parent.show_error(containing_frame, message)


class UrlLabel(tk.Label):
    """A clickable Label containing a URL."""

    # One day, avoid this assumption:
    _CLICKABLE_COLOUR = "blue"
    _NORMAL_COLOUR = "black"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self._url: Optional[str] = None
        self._underlined_font = font.Font(self, self.cget("font"))
        self._underlined_font.configure(underline=True)
        self._normal_font = font.Font(self, self.cget("font"))
        self.bind('<Button-1>', self._on_click)

    def set_url(self, url: Optional[str]):
        self._url = url
        if url is not None:
            self.config(fg=self._CLICKABLE_COLOUR)
            self.config(font=self._underlined_font)
            self.config(cursor="hand2")
        else:
            self.config(fg=self._NORMAL_COLOUR)
            self.config(font=self._normal_font)
            self.config(cursor="")

    def _on_click(self, event):
        if self._url is not None:
            webbrowser.open(self._url, new=0, autoraise=True)


class GuanoValue(tk.Label):
    """A file metadata value from GUANO data."""

    def __init__(self, parent: "GuanoFrame", label: UrlLabel, guano_name: str, units: Optional[str]):
        self._my_var = tk.StringVar()
        super().__init__(parent, textvariable=self._my_var, width=25, anchor="w")
        self._my_parent: "GuanoFrame" = parent
        self._guano_name = guano_name
        self._units = "" if units is None else " {}".format(units)
        self._my_parent.register_value_widget(self)
        self._label = label
        ToolTip(self, msgFunc=self.get_tt_text)

    def get_tt_text(self):
        return "{}: {}{}".format(self._guano_name, self._my_var.get(), self._units)

    def notify_update(self, data: GuanoFile):
        # A new value may be available, or not.
        if data is not None and self._guano_name in data:
            value = "{}{}".format(data[self._guano_name], self._units)
            self._my_var.set(value)
        else:
            self._my_var.set("")


class LatLongGuanoValue(GuanoValue):
    def __init__(self, parent: "GuanoFrame", label: UrlLabel, guano_name: str, units: Optional[str]):
        super().__init__(parent, label, guano_name, units)

    def notify_update(self, data: GuanoFile):
        super().notify_update(data)

        url: Optional[str] = None
        if data is not None and self._guano_name in data:
            lat_long = data[self._guano_name]
            try:
                latitude, longitude = lat_long
                zoom = 10
                url = "http://maps.google.com/maps?z={}&t=m&q=loc:{}+{}".format(zoom, latitude, longitude)
                # print("url = {}", url)
            except ValueError:
                pass

        # Setting a None value will clear the clickability:
        self._label.set_url(url)


class MoreWindow(tk.Toplevel):
    def __init__(self, parent, data: GuanoFile, pad: int):
        super().__init__(parent)
        self.title("GUANO Metadata")
        self.transient()  # Doesn't seem to do anything.
        self.attributes('-topmost', 'true')  # Keep in front of its parent.

        # We should really place this relative to the top level window:
        ref = parent
        self.geometry("400x300+{}+{}".format(ref.winfo_rootx() + 50, ref.winfo_rooty() - 100))

        st = scrolledtext.ScrolledText(self, width=300, height=300)
        st.grid(row=0, column=0, sticky="nsew", padx=pad, pady=pad)

        for key, value in data.items():
            st.insert(tk.INSERT, "{}:\t{}\n".format(key, value))

        st.configure(state=tk.DISABLED)

        btn = tk.Button(self, text="Close", command=self.destroy)
        btn.grid(row=1, column=0, padx=pad, pady=pad)

        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.columnconfigure(0, weight=1)


class GuanoFrame(tk.Frame):
    def __init__(self, parent, pad: int):
        super().__init__(parent)
        self._guano_data: Optional[GuanoFile] = None
        self._value_widgets = []
        self._pad = pad

        def add_guano_value(class_to_use, row: int, column: int, guano_field: str, ui_name: str = None,
                            units: str = None):
            if ui_name is None:
                ui_name = guano_field
            label = UrlLabel(self, text="{}:".format(ui_name))
            label.grid(row=row, column=column * 2, sticky="ENS", padx=pad)
            class_to_use(self, label, guano_field, units).grid(row=row, column=column * 2 + 1, sticky="WNS", padx=pad)

        add_guano_value(GuanoValue, 0, 0, "Timestamp", "Timestamp")
        add_guano_value(GuanoValue, 1, 0, "Samplerate", ui_name="Sample rate", units="Hz")
        add_guano_value(LatLongGuanoValue, 2, 0, "Loc Position", ui_name="Location")
        add_guano_value(GuanoValue, 3, 0, "Loc Elevation", ui_name="Elevation", units="m")
        add_guano_value(GuanoValue, 4, 0, "Length", units="s")
        # add_guano_value(GuanoValue, 5, 0, "Original Filename")

        add_guano_value(GuanoValue, 0, 1, "Make")
        add_guano_value(GuanoValue, 1, 1, "Model")
        add_guano_value(GuanoValue, 2, 1, "Species Auto ID")
        add_guano_value(GuanoValue, 3, 1, "Species Manual ID")

        self._more_button = tk.Button(self, text="More...", command=self._show_more)
        self._more_button.grid(row=4, column=3)
        self._more_button["state"] = tk.DISABLED

    def register_value_widget(self, v: GuanoValue):
        self._value_widgets.append(v)

    def set_guano_data(self, data: GuanoFile):
        self._guano_data = data
        # Notify all the fields that new data may be available:
        for v in self._value_widgets:
            v.notify_update(self._guano_data)

        self._more_button["state"] = tk.DISABLED if data is None else tk.NORMAL

    def _show_more(self):
        window = MoreWindow(self, self._guano_data, self._pad)
        window.grab_set()
        window.wait_window()


class SettingsNotebook(ttk.Notebook, HistogramInterface):
    def __init__(self, parent, settings: GraphSettings, button_frame: SettingsButtonFrame, pad):
        super().__init__(parent)
        self._settings = settings

        self._guano_frame = GuanoFrame(self, pad)
        self.add(self._guano_frame, text="GUANO Metadata")

        self._axis_frame = ScaleFrame(self, button_frame, settings, pad)
        self.add(self._axis_frame, text="Scale")

        self._bnc_frame = BrightnessContrastFrame(self, button_frame, settings, pad)
        self.add(self._bnc_frame, text="Brightness/Contrast")
        self._histogram_interface = self._bnc_frame.get_histogram_interface()

        self._processing_frame = RenderingFrame(self, button_frame, settings, pad)
        self.add(self._processing_frame, text="Rendering")

        self._other_frame = OtherFrame(self, button_frame, settings, pad)
        self.add(self._other_frame, text="Other")

        # Tab key moves between tabs:
        self.enable_traversal()

    def copy_settings_to_widgets(self):
        """Called by the application when it has changed a setting. This method updates the UI accordingly."""
        self._axis_frame.copy_settings_to_widgets()
        self._processing_frame.copy_settings_to_widgets()
        self._bnc_frame.copy_settings_to_widgets()
        self._other_frame.copy_settings_to_widgets()

    def copy_widgets_to_settings(self):
        """Called by the controlling frame when the user has applied a new set of settings from
        the UI."""
        self._axis_frame.copy_widgets_to_settings()
        self._processing_frame.copy_widgets_to_settings()
        self._bnc_frame.copy_widgets_to_settings()
        self._other_frame.copy_widgets_to_settings()

    def set_guano_data(self, data: GuanoFile):
        self._guano_frame.set_guano_data(data)

    def show_histogram(self, data: np.ndarray):
        self._histogram_interface.show_histogram(data)

    def on_bnc_settings_changed(self):
        self._histogram_interface.on_bnc_settings_changed()

    def hide_bnc_line(self):
        self._histogram_interface.hide_bnc_line()

    def hide_histogram(self):
        self._histogram_interface.hide_histogram()


class MoreTopFrame(tk.Frame):
    def __init__(self, parent, settings: GraphSettings, pad):
        super().__init__(parent)
        self._settings = settings
        self._error_text = tk.StringVar()

        self._button_frame = SettingsButtonFrame(self)
        self._button_frame.grid(row=0, column=1)

        self._settings_notebook = SettingsNotebook(self, settings, self._button_frame, pad)
        self._settings_notebook.grid(row=0, column=0)

    def on_apply(self):
        # Copy all the new values into the settings data class:
        self.copy_widgets_to_settings()
        # Tell whomever it may concern that new settings values are available:
        self._settings.on_user_applied_settings()

        # Also, show the BnC line, with draggers if the setting is interactive adjust:
        self._settings_notebook.on_bnc_settings_changed()

        # print("Settings = {}".format(self._settings))

    def copy_settings_to_widgets(self):
        """Called by the application when it has changed a setting. This method updates the UI accordingly."""
        self._settings_notebook.copy_settings_to_widgets()

    def copy_widgets_to_settings(self):
        """Called by the controlling frame when the user has applied a new set of settings from
        the UI."""
        self._settings_notebook.copy_widgets_to_settings()

    def show_error(self, container, message):
        # Make sure the error is visible to the user:
        self._settings_notebook.select(container)
        messagebox.showerror('Value Error', message)

    def get_histogram_interface(self) -> HistogramInterface:
        return self._settings_notebook

    def set_guano_data(self, data: Optional[GuanoFile]):
        self._settings_notebook.set_guano_data(data)
