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

import sys
import tkinter as tk
import tkinter.filedialog
import tkinter.messagebox

from itertools import chain
from timeit import default_timer as timer
from typing import NamedTuple, Optional
from . import audiofileservice as af, appsettings, colourmap
from .amplitudegraphframe import AmplitudeGraphFrame
from .appsettings import COLOUR_MAPS
from .appsettingsmodal import AppSettingsWindow
from .audiofileservice import AudioFileService
from .breadcrumbservice import BreadcrumbService, Breadcrumb
from .buttonframe import ButtonFrame
from .common import AxisRange
from .constants import *
from .fileinfoframe import FileInfoFrame
from .frames import DrawableFrame
from .graphsettings import GraphSettings
from .historianservice import HistorianService
from .rendering import SpectrogramPipeline, SpectrogramFftStep, \
    AmplitudePipeline, ProfilePipeline, GraphParams, SpectrogramDataReaderStep
from .profilegraphframe import ProfileGraphFrame
from .readoutframe import ReadoutFrame, SettingsButton
from .moreframe import MoreTopFrame
from .spectrogramgraphframe import SpectrogramGraphFrame
from .wavfileparser import WavFileError
from .about import AboutWindow
from . import get_asset_path

# One day, we will define the menus using a table including shortcuts and underlined letters:
MENU_TEXT_FILE = "File"
MENU_TEXT_ABOUT = "About"
MENU_TEXT_SETTINGS = "Settings"
MENU_TEXT_OPEN_MAIN = "Open"
MENU_TEXT_OPEN_RECENT_MAIN = "Open recent"
MENU_TEXT_OPEN_REF = "Open reference"
MENU_TEXT_OPEN_RECENT_REF = "Open recent as reference"
MENU_TEXT_CLOSE_MAIN = "Close"
MENU_TEXT_CLOSE_REF = "Close reference"
# MENU_TEXT_SAVE = "Save"
MENU_TEXT_EXIT = "Exit"

program_directory = sys.path[0]


class SettingsButtonsController:
    """
    Encapsulate the bit of logic relating to showing and hiding the settings frames in response
    the more/less buttons being pressed.
    """
    _NONE = 0
    _MAIN = 1
    _REF = 2

    def __init__(self, parent: tk.Frame, main_settings_button: SettingsButton, main_settings_frame: tk.Frame,
                 ref_settings_button: SettingsButton, ref_settings_frame: tk.Frame):
        self._parent = parent
        self._state: int = self._NONE
        self._main_settings_button: SettingsButton = main_settings_button
        self._ref_settings_button: SettingsButton = ref_settings_button
        self._main_settings_frame = main_settings_frame
        self._ref_settings_frame = ref_settings_frame

        self._main_settings_button.configure(command=self.on_main_settings)
        self._ref_settings_button.configure(command=self.on_ref_settings)

        self.on_reset()

    def on_reset(self):
        self._state = self._NONE
        self._do_update()

    def on_main_settings(self):
        if self._state == self._MAIN:
            self._state = self._NONE
        else:
            self._state = self._MAIN
        self._do_update()

    def on_ref_settings(self):
        if self._state == self._REF:
            self._state = self._NONE
        else:
            self._state = self._REF
        self._do_update()

    def _do_update(self):
        if self._state == self._MAIN:
            self._main_settings_button.update_button_appearance(True, False)
            self._ref_settings_button.update_button_appearance(False, True)
            self._main_settings_frame.grid()
            self._ref_settings_frame.grid_remove()
        elif self._state == self._REF:
            self._main_settings_button.update_button_appearance(False, True)
            self._ref_settings_button.update_button_appearance(True, False)
            self._main_settings_frame.grid_remove()
            self._ref_settings_frame.grid()
        else:
            self._main_settings_button.update_button_appearance(False, False)
            self._ref_settings_button.update_button_appearance(False, False)
            self._main_settings_frame.grid_remove()
            self._ref_settings_frame.grid_remove()

            # We have to tell the parent frame to reduce size, it doesn't do this
            # automatically when we remove the settings frames sadly:
            self._parent.configure(height=0, width=100)  # Width has to be non zero for some reason.


class GraphPipelines(NamedTuple):
    """A tuple of rendering pipelines relating to a set of graphs."""
    amplitude: Optional[AmplitudePipeline]
    spectrogram: Optional[SpectrogramPipeline]
    profile: Optional[ProfilePipeline]


class PanelFrame(tk.Frame):
    """This is a Frame which contains the set of graphs relating to the main or the reference data."""

    def __init__(self, parent, root, pipelines, data_context, settings, settings_frame, pad, is_reference):
        super().__init__(parent)

        self._pipelines = pipelines
        self._dc = data_context
        self._settings = settings
        self._settings_frame = settings_frame

        col = 0
        self._fileinfo_frame = FileInfoFrame(self, self._dc)
        self._fileinfo_frame.grid(row=0, column=col, columnspan=3, pady=(pad, 0), sticky='ew', padx=pad)

        self._button_frame = ButtonFrame(self, self._dc.breadcrumb_service, self, self._dc, program_directory,
                                         is_reference)
        self._button_frame.grid(row=1, column=col, columnspan=3, pady=(0, 0), sticky='we', padx=pad)
        initial_cursor_mode = self._button_frame.get_cursor_mode()

        self._amplitude_frame = AmplitudeGraphFrame(self, root, pipelines.amplitude, self._dc, self._settings,
                                                    is_reference=is_reference)
        self._amplitude_frame.grid(row=2, column=col, sticky='nesw', padx=pad)

        self._spectrogram_frame = SpectrogramGraphFrame(self, root, pipelines.spectrogram, self._dc, self._settings,
                                                        initial_cursor_mode, is_reference=is_reference)
        self._spectrogram_frame.grid(row=3, column=col, sticky='nesw', padx=pad)

        # Set up two-way communications between the scroll bar and the graph frame.
        # Set repeatdelay=0 to disable repeating, which behaves oddly.
        self._time_scroller = tk.Scrollbar(self, orient='horizontal', jump=True, repeatdelay=0)
        self._spectrogram_frame.set_scroller_t(self._time_scroller)
        self._time_scroller.grid(row=4, column=col, sticky="ew", padx=pad)

        self._readout_frame = ReadoutFrame(self)
        self._readout_frame.grid(row=6, column=col, pady=pad, sticky='we')

        col = 1
        self._profile_frame = ProfileGraphFrame(self, root, pipelines.profile, self._dc, self._settings, is_reference=is_reference)
        self._profile_frame.grid(row=3, column=col, sticky='ns')

        col = 2
        frequency_scroller = tk.Scrollbar(self, orient='vertical', jump=True, repeatdelay=0)
        frequency_scroller.grid(row=3, column=col, sticky="ns")
        self._spectrogram_frame.set_scroller_f(frequency_scroller)

        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=0)
        self.rowconfigure(3, weight=1)
        self.rowconfigure(4, weight=0)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.columnconfigure(2, weight=0)

        # The profile is initially absent, to avoid an annoying flicker on startup:
        self._profile_frame.grid_remove()

        # Tell the spectrogram framehow it can control its histogram:
        self._spectrogram_frame.set_histogram_interface(self._settings_frame.get_histogram_interface())

        self._frames = [self._amplitude_frame, self._spectrogram_frame, self._profile_frame,
                        self._button_frame, self._fileinfo_frame, self._readout_frame]

    def get_settings_button(self) -> SettingsButton:
        return self._readout_frame.get_settings_button()

    def on_user_applied_settings(self, draw_scope: int):
        """The user change the settings - refresh the display accordingly."""
        self.on_rescale_handler(self._settings.time_range, self._settings.frequency_range, draw_scope=draw_scope)

    def update_readout_coords(self, p_axis, p_data_area):
        # Use the data area coordinates to get a data value (power) from the pipeline's
        # zoomed data, which maps to data area pixels:
        power = None
        if p_data_area:
            power = self._pipelines.spectrogram.data_area_to_value(p_data_area)
        self._readout_frame.update_readout_coords(p_axis, power)

    def update_readout_params(self, params: GraphParams):
        self._readout_frame.update_graph_parameters(params)

    def on_rescale_handler(self, time_range: AxisRange, frequency_range: AxisRange,
                           add_breadcrumb=True, draw_scope: int = DrawableFrame.DRAW_ALL):
        """Do a graph rescale triggered from the UI."""

        # Clip the requested ranges to the limits from the data file:
        af_data = self._dc.get_afs_data()
        if af_data:
            time_range = self._clip_to_file_data_range(time_range, af_data.time_range, self._dc.time_range)
            frequency_range = self._clip_to_file_data_range(frequency_range, af_data.frequency_range,
                                                            self._dc.frequency_range)

        self._dc.time_range, self._dc.frequency_range = time_range, frequency_range
        if add_breadcrumb:
            self._dc.push_breadcrumb()

        self.draw(draw_scope)

    def on_scroll_handler(self, delta_t: float, delta_f: float,
                          range_t: AxisRange, range_f: AxisRange, add_breadcrumb=True):
        """
        Scroll time and/or frequency in response to the UI, maintaining the range, and limiting
        to the range of available data. The deltas must be less than the current axis ranges.
        """

        # Limit the the deltas to the range of the available data, maintaining the span of each axis,
        # and assuming (1) the existing range is valid (2) the deltas are less than the current axis ranges.
        af_data = self._dc.get_afs_data()
        if af_data:
            time_min, time_max = af_data.time_range.get_tuple()
            if delta_t > 0:
                if range_t.max + delta_t > time_max:
                    delta_t = time_max - range_t.max
            else:
                if range_t.min + delta_t < time_min:
                    delta_t = -(range_t.min - time_min)

            freq_min, freq_max = af_data.frequency_range.get_tuple()
            if delta_f > 0:
                if range_f.max + delta_f > freq_max:
                    delta_f = freq_max - range_f.max
            else:
                if range_f.min + delta_f < freq_min:
                    delta_f = -(range_f.min - freq_min)

        limited_range_t = AxisRange(range_t.min + delta_t, range_t.max + delta_t)
        limited_range_f = AxisRange(range_f.min + delta_f, range_f.max + delta_f)

        self.on_rescale_handler(limited_range_t, limited_range_f,
                                add_breadcrumb=add_breadcrumb,
                                draw_scope=DrawableFrame.DRAW_ALL)

    def draw(self, draw_scope: int = DrawableFrame.DRAW_ALL):
        # Update the settings to match the *actual* new axis ranges:
        self._settings.time_range = self._dc.time_range
        self._settings.frequency_range = self._dc.frequency_range
        self._settings.on_app_modified_settings()

        # Show or hide the profile graph as required:
        if self._settings.show_profile:
            self._profile_frame.grid()
        else:
            self._profile_frame.grid_remove()

        # Tell each frame to redraw themselves:
        for f in self._frames:
            if f:
                f.reset_draw(draw_scope)
        for f in self._frames:
            if f:
                f.draw(draw_scope)

    @staticmethod
    def _clip_to_file_data_range(r_in: AxisRange, r_permitted, r_default):
        in_min, in_max = r_in.get_tuple()
        permitted_min, permitted_max = r_permitted.get_tuple()
        out_min = max(in_min, permitted_min)
        out_max = min(in_max, permitted_max)
        # sanity:
        if out_min >= out_max:
            out_min, out_max = r_default
        return AxisRange(out_min, out_max)

    def on_home_button(self):
        # We add an initial breadcrumb for home.
        myaf = self._dc.afs
        if myaf:
            # If there is a file, home takes us to the file limits:
            fdata = myaf.get_rendering_data()
            self.on_rescale_handler(fdata.time_range, fdata.frequency_range, add_breadcrumb=True)
        else:
            # Otherwise, home to the default ranges.
            self.on_rescale_handler(DataContext.DEFAULT_TIME_RANGE, DataContext.DEFAULT_FREQUENCY_RANGE,
                                    add_breadcrumb=True)

    def on_navigation_button(self, breadcrumb: Breadcrumb):
        self._dc.time_range = breadcrumb.time_range
        self._dc.frequency_range = breadcrumb.frequency_range
        # Don't add a breadcrumb when we navigate based on breadcrumbs:
        self.on_rescale_handler(breadcrumb.time_range, breadcrumb.frequency_range, add_breadcrumb=False)

    def on_cursor_mode(self, mode):
        self._spectrogram_frame.set_cursor_mode(mode)

    def set_sync_source(self, sync_source):
        """Notify this panel that there is a sync source it can use, or None if
        there isn't"""
        return self._button_frame.set_sync_source(sync_source)

    def get_sync_data(self):
        """This panel is being requests for sync data"""
        return self._dc.time_range, self._dc.frequency_range, self._spectrogram_frame.get_canvas_size()

    def apply_sync_data(self, sync_data):
        """Sync the ranges of this panel to those supplied."""
        time_range, frequency_range, other_canvas_size = sync_data
        this_canvas_width, _ = self._spectrogram_frame.get_canvas_size()
        other_canvas_width, _ = other_canvas_size

        # Apply the frequency range directly, and centre the time range on the current
        # time range's centre:
        t1, t2 = self._dc.time_range.get_tuple()
        new_t1, new_t2 = time_range.get_tuple()
        existing_centre = (t1 + t2) / 2
        new_half_span = (new_t2 - new_t1) / 2
        # Scale the half span by ratio of canvas widths so the on-screen scaling is the same:
        new_half_span *= this_canvas_width / other_canvas_width
        centred_time_range = AxisRange(existing_centre - new_half_span, existing_centre + new_half_span)
        self.on_rescale_handler(centred_time_range, frequency_range, add_breadcrumb=True)

    def get_screen_factors(self) -> tuple[float, float]:
        # Calculate the screen aspect factor based on the spectrogram graph,
        # that will be used in adaptive window length calculations.
        return self._spectrogram_frame.calculate_screen_factors()

    def on_left_key(self, event):
        self._spectrogram_frame.tview(tk.SCROLL, -1, tk.UNITS)

    def on_shift_left_key(self, event):
        self._spectrogram_frame.tview(tk.SCROLL, -1, tk.PAGES)

    def on_right_key(self, event):
        self._spectrogram_frame.tview(tk.SCROLL, 1, tk.UNITS)

    def on_shift_right_key(self, event):
        self._spectrogram_frame.tview(tk.SCROLL, 1, tk.PAGES)

    def on_up_key(self, event):
        self._spectrogram_frame.set_preset_time_range(-1)

    def on_shift_up_key(self, event):
        pass

    def on_down_key(self, event):
        self._spectrogram_frame.set_preset_time_range(+1)

    def on_shift_down_key(self, event):
        pass

    def on_page_up_key(self, event):
        self._spectrogram_frame.fview(tk.SCROLL, -1, tk.UNITS)

    def on_shift_page_up_key(self, event):
        self._spectrogram_frame.fview(tk.SCROLL, -1, tk.PAGES)

    def on_page_down_key(self, event):
        self._spectrogram_frame.fview(tk.SCROLL, 1, tk.UNITS)

    def on_shift_page_down_key(self, event):
        self._spectrogram_frame.fview(tk.SCROLL, 1, tk.PAGES)

    def on_home_key(self, event):
        self.on_home_button()


class DataContext:
    """This class contains data used by a graph pane, including raw file data and axis ranges."""

    DEFAULT_TIME_RANGE = AxisRange(rmin=0, rmax=30)
    DEFAULT_FREQUENCY_RANGE = AxisRange(rmin=0, rmax=192000)
    DEFAULT_AMPLITUDE_RANGE = AxisRange(rmin=-1, rmax=1)

    def __init__(self):
        self.afs: Optional[AudioFileService] = None
        self.breadcrumb_service = BreadcrumbService()
        self.time_range: Optional[AxisRange] = None
        self.frequency_range: Optional[AxisRange] = None
        self.amplitude_range: Optional[AxisRange] = None
        self.reset()

    def reset(self):
        self._set_afs(None)
        self.time_range = self.DEFAULT_TIME_RANGE
        self.frequency_range = self.DEFAULT_FREQUENCY_RANGE
        self.amplitude_range = self.DEFAULT_AMPLITUDE_RANGE

    def _set_afs(self, afs: Optional[AudioFileService]):
        # If we already have an afs, close it:
        if self.afs is not None:
            self.afs.close()
        self.afs = afs

    def get_ranges(self):
        return self.time_range, self.frequency_range, self.amplitude_range

    def get_afs(self) -> Optional[AudioFileService]:
        return self.afs

    def get_afs_data(self) -> Optional[AudioFileService.RenderingData]:
        return self.afs.get_rendering_data() if self.afs is not None else None

    def update_from_af(self, afs: AudioFileService):
        self._set_afs(afs)
        af_data = afs.get_rendering_data()
        self.amplitude_range = af_data.amplitude_range
        self.time_range = af_data.time_range
        self.frequency_range = af_data.frequency_range

    def push_breadcrumb(self):
        self.breadcrumb_service.push_entry(
            Breadcrumb(time_range=self.time_range, frequency_range=self.frequency_range, timestamp=timer()))

    def on_data_change(self):
        self.breadcrumb_service.reset()
        self.push_breadcrumb()


class RootWindow(tk.Tk):
    """The top level application window."""

    def __init__(self, *args, initialfile=None, **kwargs):
        super().__init__(*args, **kwargs)

        self._paned_window: tk.PanedWindow

        self._main_pipelines = GraphPipelines(None, None, None)
        self._dc_main: DataContext = DataContext()
        self._main_historian = HistorianService()
        self._main_settings = GraphSettings(self._on_app_modified_main_settings, self.on_user_applied_main_settings)
        self._main_settings.show_profile = True

        self._ref_pipelines = GraphPipelines(None, None, None)
        self._dc_ref: DataContext = DataContext()
        self._ref_historian = HistorianService()
        self._ref_settings = GraphSettings(self._on_app_modified_ref_settings, self.on_user_applied_ref_settings)
        self._ref_settings.show_profile = False

        self._menu_recent_main = None
        self._menu_recent_ref = None
        self._menu_analysis = None
        self._menu_image = None
        self._menu_edit = None
        self._menu_file = None
        self._first_file_open = True  # Track whether this is the first time the user has opened a file.

        appsettings.instance.read()
        self._apply_settings()

        # Keep track of what cursors have been set:
        self._cursor_stack = []
        self._push_cursor()

        self.title(PROGRAM_NAME)

        # Define the initial window position and size:
        self.geometry("900x700+100+100")
        self.iconphoto(True, tk.PhotoImage(file=get_asset_path("batogram.png")))

        self.protocol("WM_DELETE_WINDOW", self.exit)

        # Kick off all the rendering pipelines:
        self._start_pipelines()

        self._create_menus()
        self._create_widgets()

        self.bind(DATA_CHANGE_MAIN_EVENT, self._on_data_change_main)
        self.bind(DATA_CHANGE_REF_EVENT, self._on_data_change_ref)

        self.bind('<Left>', self._main_pane.on_left_key)
        self.bind('<Shift-Left>', self._main_pane.on_shift_left_key)
        self.bind('<Right>', self._main_pane.on_right_key)
        self.bind('<Shift-Right>', self._main_pane.on_shift_right_key)
        self.bind('<Up>', self._main_pane.on_up_key)
        self.bind('<Shift-Up>', self._main_pane.on_shift_up_key)
        self.bind('<Down>', self._main_pane.on_down_key)
        self.bind('<Shift-Down>', self._main_pane.on_shift_down_key)
        self.bind('<Prior>', self._main_pane.on_page_up_key)
        self.bind('<Shift-Prior>', self._main_pane.on_shift_page_up_key)
        self.bind('<Next>', self._main_pane.on_page_down_key)
        self.bind('<Shift-Next>', self._main_pane.on_shift_page_down_key)
        self.bind('<Home>', self._main_pane.on_home_key)

        # Allow tk to work out the size of things before we try to draw any graphs:
        self.update_idletasks()

        self._main_pane.draw()
        self._ref_pane.draw()

        if initialfile is not None:
            self.after_idle(lambda: self._do_open_main_file(initialfile))

    def _start_pipelines(self):
        # Kick off the spectrogram rendering pipelines. This has to done at this level because
        # the pipelines share some steps for effiency, to avoid repeated expensive calculations.
        main_spectrogram_step = SpectrogramFftStep(self._main_settings)
        main_data_reader_step = SpectrogramDataReaderStep(self._main_settings)
        self._main_pipelines = GraphPipelines(
            AmplitudePipeline(self._main_settings, main_data_reader_step),
            SpectrogramPipeline(self._main_settings, main_spectrogram_step, main_data_reader_step),
            ProfilePipeline(self._main_settings, main_spectrogram_step, main_data_reader_step))

        ref_spectrogram_step = SpectrogramFftStep(self._ref_settings)
        ref_data_reader_step = SpectrogramDataReaderStep(self._ref_settings)
        self._ref_pipelines = GraphPipelines(
            AmplitudePipeline(self._ref_settings, ref_data_reader_step),
            SpectrogramPipeline(self._ref_settings, ref_spectrogram_step, ref_data_reader_step),
            ProfilePipeline(self._ref_settings, ref_spectrogram_step, ref_data_reader_step))

    def _create_widgets(self):
        pad = 5
        self._paned_window = tk.PanedWindow(self, orient=tk.HORIZONTAL, showhandle=True, sashcursor="sb_h_double_arrow",
                                            sashrelief=tk.GROOVE)

        bottom = self._create_bottom_panel(self, pad)
        bottom.grid(row=1, column=0)

        # Create the settings frames first so they can be passed as parameters
        # to other frames below:

        self._ref_pane = PanelFrame(
            self._paned_window, self, self._ref_pipelines, self._dc_ref, self._ref_settings,
            self._ref_settings_frame, pad, is_reference=True)
        self._ref_pane.pack(side=tk.LEFT)

        self._main_pane = PanelFrame(
            self._paned_window, self, self._main_pipelines, self._dc_main, self._main_settings,
            self._main_settings_frame, pad, is_reference=False)
        self._main_pane.pack(side=tk.RIGHT)

        SettingsButtonsController(bottom,
                                  self._main_pane.get_settings_button(), self._main_settings_frame,
                                  self._ref_pane.get_settings_button(), self._ref_settings_frame)

        # Assemble the panel window:
        self._paned_window.add(self._ref_pane)
        self._paned_window.add(self._main_pane)
        self._paned_window.grid(row=0, column=0, sticky="nsew")

        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.columnconfigure(0, weight=1)

        # This code annoyingly jumps on startup. I can't find simple way to avoid that right now.
        # Maybe we should make the frame invisible? I don't know if that would work.
        self.update()  # Need to do this before we can place the sash.
        sash_pixels = 0
        self._paned_window.sash_place(0, sash_pixels, 0)

    def _create_bottom_panel(self, parent, pad):

        frame = tk.Frame(parent)
        self._ref_settings_frame = MoreTopFrame(frame, self._ref_settings, pad)
        self._ref_settings_frame.grid(row=0, column=0)
        self._main_settings_frame = MoreTopFrame(frame, self._main_settings, pad)
        self._main_settings_frame.grid(row=1, column=0)

        return frame

    def _create_menus(self):
        # Set up the menus (see https://tkdocs.com/tutorial/menus.html):
        self.option_add('*tearOff', False)
        menubar = tk.Menu(self)
        self['menu'] = menubar

        self._menu_file = tk.Menu(menubar)
        menubar.add_cascade(menu=self._menu_file, label=MENU_TEXT_FILE, underline=0)
        self._menu_file.add_command(label=MENU_TEXT_OPEN_MAIN, command=self._open_main_file, underline=0)
        self._menu_file.entryconfigure(MENU_TEXT_OPEN_MAIN, accelerator='Ctrl+O')
        self.bind("<Control-o>", self._open_main_file_event)
        self._menu_recent_main = tk.Menu(self._menu_file)
        self._menu_file.add_cascade(menu=self._menu_recent_main, label=MENU_TEXT_OPEN_RECENT_MAIN)
        self._populate_file_history(self._menu_recent_main, self._main_historian, self._do_open_main_file)
        self._menu_file.add_command(label=MENU_TEXT_CLOSE_MAIN, command=self._close_main_file_event, underline=0)
        self._menu_file.add_separator()

        self._menu_file.add_command(label=MENU_TEXT_OPEN_REF, command=self._open_ref_file, underline=5)
        self._menu_file.entryconfigure(MENU_TEXT_OPEN_REF, accelerator='Ctrl+R')
        self.bind("<Control-r>", self._open_ref_file_event)
        self._menu_recent_ref = tk.Menu(self._menu_file)
        self._menu_file.add_cascade(menu=self._menu_recent_ref, label=MENU_TEXT_OPEN_RECENT_REF)
        self._populate_file_history(self._menu_recent_ref, self._ref_historian, self._do_open_ref_file)
        self._menu_file.add_command(label=MENU_TEXT_CLOSE_REF, command=self.close_ref_file_event)
        self._menu_file.add_separator()

        # self._menu_file.add_command(label=MENU_TEXT_SAVE, command=self.save_files_as)
        # self._menu_file.add_separator()
        self._menu_file.add_command(label=MENU_TEXT_EXIT, command=self.exit, underline=1)
        self._menu_file.entryconfigure(MENU_TEXT_EXIT, accelerator='Ctrl+X')
        self.bind("<Control-x>", self.exit_event)

        menubar.add_command(label=MENU_TEXT_SETTINGS, command=self._show_settings, underline=0)

        menubar.add_command(label=MENU_TEXT_ABOUT, command=self._show_about)

        self.enable_menu_items()

    @staticmethod
    def _populate_file_history(parent_menu_item, historian, method):
        parent_menu_item.delete(0, "end")
        for basename, file_path in historian.get_history():
            parent_menu_item.add_command(label=basename,
                                         command=lambda f=file_path: method(f))

    def enable_menu_items(self):
        # self._menu_file.entryconfigure(MENU_TEXT_SAVE, state=tk.DISABLED)
        self._menu_file.entryconfigure(MENU_TEXT_OPEN_RECENT_MAIN,
                                       state=tk.DISABLED if self._main_historian.is_empty() else tk.NORMAL)
        self._menu_file.entryconfigure(MENU_TEXT_OPEN_RECENT_REF,
                                       state=tk.DISABLED if self._ref_historian.is_empty() else tk.NORMAL)

    def _pop_cursor(self):
        try:
            self._cursor_stack.pop()
            cursor_name = self._cursor_stack[-1]
        except IndexError as e:
            print("Warning - couldn't pop the cursor: {}".format(e))
            self.config(cursor="")
        else:
            self.config(cursor=cursor_name)

    def _push_cursor(self, cursor_name=""):
        self._cursor_stack.append(cursor_name)
        self.config(cursor=cursor_name)
        self.update()

    filetypes = (
        ('audio files', '*.wav *.WAV'),
        ('All files', '*.*')
    )

    def _open_main_file_event(self, _):
        self._open_main_file()

    def _open_file_dialog(self, title: str) -> str:
        initialdir = None
        if self._first_file_open:
            self._first_file_open = False
            # Only do this the first time a file is opened; thereafter, the dialog
            # remembers where the user last navigated it to:
            initialdir = appsettings.instance.data_directory

        filepath: str = tk.filedialog.askopenfilename(title=title, filetypes=self.filetypes,
                                                      initialdir=initialdir)
        return filepath

    def _open_main_file(self):
        filepath = self._open_file_dialog("Open an audio file")
        if filepath:
            self._do_open_main_file(filepath)

    def _open_ref_file_event(self, _):
        self._open_ref_file()

    def _open_ref_file(self):
        filepath = self._open_file_dialog("Open a reference audio file")
        if filepath:
            self._do_open_ref_file(filepath)

    def _do_open_main_file(self, filepath):
        myaf = self._do_open_file(filepath, self._menu_recent_main, self._do_open_main_file, self._main_historian)
        if myaf is not None:
            self._dc_main.update_from_af(myaf)
            self._main_settings_frame.copy_settings_to_widgets()  # The axis ranges have changed
            self._main_settings_frame.set_guano_data(myaf.get_guano_data())
            self._main_settings.on_open_new_file()
            self.event_generate(DATA_CHANGE_MAIN_EVENT)

    def _do_open_ref_file(self, filepath):
        myaf = self._do_open_file(filepath, self._menu_recent_ref, self._do_open_ref_file, self._ref_historian)
        if myaf is not None:
            self._dc_ref.update_from_af(myaf)
            self._ref_settings_frame.copy_settings_to_widgets()  # The axis ranges have changed
            self._ref_settings_frame.set_guano_data(myaf.get_guano_data())
            self._main_settings.on_open_new_file()
            # Make sure the ref pane is visible:
            x, y = self._paned_window.sash_coord(0)
            if x < 10:
                self._paned_window.sash_place(0, 300, y)
            self.event_generate(DATA_CHANGE_REF_EVENT)

    def _do_open_file(self, filepath, recent_menu_item, method, historian):
        self._push_cursor("watch")  # A large file might take time to load. Though, it seems not.
        try:
            # Attempt to read the wav file provided:
            af_this = af.AudioFileService(filepath)
            af_this.open()
        except (FileNotFoundError, WavFileError) as e:
            tk.messagebox.showerror(PROGRAM_NAME, "Error reading audio file: {}".format(e))
            return None
        else:
            self._main_historian.add_file(filepath)
            self._populate_file_history(recent_menu_item, historian, method)
            return af_this
        finally:
            self._pop_cursor()

    def _close_main_file_event(self):
        self._dc_main.reset()
        self._main_settings_frame.set_guano_data(None)
        self.event_generate(DATA_CHANGE_MAIN_EVENT)

    def close_ref_file_event(self):
        self._dc_ref.reset()
        self._main_settings_frame.set_guano_data(None)
        self.event_generate(DATA_CHANGE_REF_EVENT)

    def exit_event(self, _):
        self.exit()

    def exit(self):
        if (tk.messagebox.askokcancel(
                message='Are you sure you want to exit {}?'.format(PROGRAM_NAME),
                icon='question', title='Exit')):
            for p in chain(self._main_pipelines, self._ref_pipelines):
                if p:
                    p.shutdown()

            appsettings.instance.write()

            self.destroy()

    def _on_data_change_main(self, _):
        self._dc_main.on_data_change()
        self._main_pane.draw()
        # Tell the other pane we can accept sync requests (as we have some data):
        sync_source = self._main_pane if self._dc_main.afs else None
        self._ref_pane.set_sync_source(sync_source)

    def _on_data_change_ref(self, _):
        self._dc_ref.on_data_change()
        self._ref_pane.draw()
        # Tell the other pane we can accept sync requests (as we have some data):
        sync_source = self._ref_pane if self._dc_ref.afs else None
        self._main_pane.set_sync_source(sync_source)

    @staticmethod
    def _pipeline_error_handler(e):
        tk.messagebox.showerror(PROGRAM_NAME, "Error encountered in processing pipeline: {}".format(e))
        raise e

    def _on_app_modified_main_settings(self, draw_scope: int = DrawableFrame.DRAW_ALL):
        # This gets called from the graph pane when the user changes settings
        # such as graph scaling.
        self._main_settings_frame.copy_settings_to_widgets()

    def on_user_applied_main_settings(self, draw_scope: int = DrawableFrame.DRAW_ALL):
        # New settings values are available to be applied to the application.
        self._main_pane.on_user_applied_settings(draw_scope)

    def _on_app_modified_ref_settings(self, draw_scope: int = DrawableFrame.DRAW_ALL):
        # This gets called from the graph pane when the user changes settings
        # such as graph scaling.
        self._ref_settings_frame.copy_settings_to_widgets()

    def on_user_applied_ref_settings(self, draw_scope: int = DrawableFrame.DRAW_ALL):
        # New settings values are available to be applied to the application.
        self._ref_pane.on_user_applied_settings(draw_scope)

    def _show_about(self):
        window = AboutWindow(self)
        window.grab_set()
        window.wait_window()

    def _show_settings(self):
        modal = AppSettingsWindow(self, appsettings.instance, lambda: self._on_settings_ok())
        modal.grab_set()
        modal.wait_window()

    def _on_settings_ok(self):
        # Refresh some things from the updated settings values:
        self._apply_settings()
        self._main_pane.draw()
        self._ref_pane.draw()

    @staticmethod
    def _apply_settings():
        # Refresh some things from the updated settings values:
        cmap_file = COLOUR_MAPS[appsettings.instance.colour_map]
        colourmap.instance.reload_map(cmap_file)
