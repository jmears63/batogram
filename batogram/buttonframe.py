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
from typing import Type, Optional

from . import get_asset_path
from .audiofileservice import AudioFileService
from .common import AxisRange
from .constants import PLAYBACK_EVENT

from .frames import DrawableFrame
from .playbackservice import PlaybackProcessor, PlaybackRequest, PlaybackEventHandler, PlaybackRequestTuple, \
    EventClosureType, PlaybackSignal
from .spectrogrammouseservice import CursorMode
from .external.tooltip import ToolTip


class MyButton(tk.Button):
    _width = 24
    _padding = 5

    def __init__(self, parent, image, command=None):
        super().__init__(parent, image=image, width=self._width, padx=self._padding, pady=self._padding,
                         relief=tk.RAISED, command=command)


class PlaybackState(Enum):
    PLAYBACK_STOPPED = 0  # Starting state.
    PLAYBACK_PLAY_PENDING = 1
    PLAYBACK_PLAYING = 2
    PLAYBACK_STOP_PENDING = 3
    PLAYBACK_PAUSED = 4
    PLAYBACK_PAUSE_PENDING = 5
    PLAYBACK_DISABLED = 6


class ButtonFrame(DrawableFrame, PlaybackEventHandler):
    """A Frame containing the control buttons for a pane."""

    def __init__(self, parent, breadcrumb_service, action_target, data_context, program_directory, is_reference,
                 playback_processor: PlaybackProcessor):
        super().__init__(parent)

        self._sync_source = None
        self._cursor_mode = CursorMode.CURSOR_ZOOM
        self._playback_state: PlaybackState = PlaybackState.PLAYBACK_STOPPED
        self._breadcrumb_service = breadcrumb_service
        self._program_directory = program_directory
        self._action_target = action_target
        self._dc = data_context
        self._playback_processor: PlaybackProcessor = playback_processor

        self._playback_processor.add_watcher(self, self._event_processor)  # Don't know why type hinting complains.

        col = 0
        small_gap = 10

        self._event_closure: Optional[EventClosureType] = None
        self.bind(PLAYBACK_EVENT, self._do_playback_event)

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

        def home_command():
            self._breadcrumb_service.reset()        # Clicking "home" clears the breadcrumb history
            self._action_target.on_home_button()

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
        self._zoom_button.grid(row=0, column=col, padx=(small_gap, 0), ipadx=0, sticky="NSEW")
        ToolTip(self._zoom_button, msg="Select zoom cursor: left mouse drag to zoom.\nHold shift to lock mode.")
        col += 1

        self._pan_image = self._load_image("drag-move-2-line.png")
        self._pan_button = MyButton(self, self._pan_image,
                                    command=lambda: self._handle_cursor_mode(CursorMode.CURSOR_PAN))
        self._pan_button.grid(row=0, column=col, padx=0, ipadx=0, sticky="NSEW")
        ToolTip(self._pan_button, msg="Select pan cursor: left mouse drag to pan/scroll.\nHold shift to lock mode.")
        col += 1

        self._play_image = self._load_image("play-line.png")
        self._play_button = MyButton(self, self._play_image,
                                     command=lambda: self._handle_play())
        self._play_button.grid(row=0, column=col, padx=(small_gap * 3, 0), ipadx=0, sticky="NSEW")
        ToolTip(self._play_button, msg="Play the recording.")
        col += 1

        self._pause_image = self._load_image("pause-line.png")
        self._pause_button = MyButton(self, self._pause_image,
                                      command=lambda: self._handle_pause())
        self._pause_button.grid(row=0, column=col, padx=0, ipadx=0, sticky="NSEW")
        ToolTip(self._pause_button, msg="Pause playback.")
        col += 1

        self._stop_image = self._load_image("stop-line.png")
        self._stop_button = MyButton(self, self._stop_image,
                                     command=lambda: self._handle_stop())
        self._stop_button.grid(row=0, column=col, padx=0, ipadx=0, sticky="NSEW")
        ToolTip(self._stop_button, msg="Stop playback")
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

    _ui_states = {
        PlaybackState.PLAYBACK_STOP_PENDING:
            [(tk.DISABLED, tk.RAISED),  # play
             (tk.DISABLED, tk.RAISED),  # pause
             (tk.DISABLED, tk.SUNKEN)  # stop
             ],
        PlaybackState.PLAYBACK_STOPPED:
            [(tk.NORMAL, tk.RAISED),  # play
             (tk.DISABLED, tk.RAISED),  # pause
             (tk.DISABLED, tk.RAISED)  # stop
             ],

        PlaybackState.PLAYBACK_PLAY_PENDING:
            [(tk.NORMAL, tk.SUNKEN),
             (tk.DISABLED, tk.RAISED),
             (tk.DISABLED, tk.RAISED)
             ],
        PlaybackState.PLAYBACK_PLAYING:
            [(tk.NORMAL, tk.SUNKEN),
             (tk.NORMAL, tk.RAISED),
             (tk.NORMAL, tk.RAISED)
             ],

        PlaybackState.PLAYBACK_PAUSE_PENDING:
            [(tk.NORMAL, tk.SUNKEN),
             (tk.DISABLED, tk.SUNKEN),
             (tk.DISABLED, tk.RAISED)
             ],
        PlaybackState.PLAYBACK_PAUSED:
            [(tk.NORMAL, tk.SUNKEN),
             (tk.NORMAL, tk.SUNKEN),
             (tk.NORMAL, tk.RAISED)
             ],

        PlaybackState.PLAYBACK_DISABLED:
            [(tk.DISABLED, tk.RAISED),
             (tk.DISABLED, tk.RAISED),
             (tk.DISABLED, tk.RAISED)
             ]
    }

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

        a = self._dc.afs
        if a is not None:
            # Playback controls:
            ui_state = self._ui_states[self._playback_state]
        else:
            ui_state = self._ui_states[PlaybackState.PLAYBACK_DISABLED]

        self._play_button['state'] = ui_state[0][0]
        self._play_button.configure(relief=ui_state[0][1])
        self._pause_button['state'] = ui_state[1][0]
        self._pause_button.configure(relief=ui_state[1][1])
        self._stop_button['state'] = ui_state[2][0]
        self._stop_button.configure(relief=ui_state[2][1])

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

    def _handle_play(self):
        if self._playback_state == PlaybackState.PLAYBACK_STOPPED:
            # Send a playback request off to the async service:
            slave_afs: AudioFileService = AudioFileService.make_slave_copy(self._dc.afs)#
            rendering_data = slave_afs.get_rendering_data()
            if rendering_data.sample_rate > 0:
                # Determine the range of data to play back:
                tmin, tmax = self._dc.time_range.get_tuple()
                tmin, tmax = tmin / rendering_data.sample_rate, tmax / rendering_data.sample_rate
                tmin, tmax = max(tmin, 0), min(tmax, rendering_data.sample_count)
                pr = PlaybackRequest(slave_afs, (tmin, tmax))
                request: PlaybackRequestTuple = pr, self._event_processor

                self._playback_state = PlaybackState.PLAYBACK_PLAY_PENDING
                self.draw()
                self._playback_processor.submit(request)
            else:
                print("Sample rate is insane: {}".format(rendering_data.sample_rate))

    def _handle_pause(self):
        if self._playback_state == PlaybackState.PLAYBACK_PLAYING:
            self._playback_state = PlaybackState.PLAYBACK_PAUSE_PENDING
            self._playback_processor.signal(PlaybackSignal.SIGNAL_PAUSE)
        elif self._playback_state == PlaybackState.PLAYBACK_PAUSED:
            self._playback_state = PlaybackState.PLAYBACK_PLAYING
            self._playback_processor.signal(PlaybackSignal.SIGNAL_NONE)

        self.draw()

    def _handle_stop(self):
        self._playback_state = PlaybackState.PLAYBACK_STOP_PENDING
        self.draw()

        self._playback_processor.signal(PlaybackSignal.SIGNAL_STOP)

    def on_play_started(self):
        """Notification callback called in the thread of the playback service."""
        self._playback_state = PlaybackState.PLAYBACK_PLAYING
        self.draw()

    def on_play_cancelled(self):
        """Notification callback called in the thread of the playback service."""

        # The finished callback will reset the UI state, so nothing to be done here.

    def on_play_finished(self):
        """Notification callback called in the thread of the playback service."""
        self._playback_state = PlaybackState.PLAYBACK_STOPPED
        self.draw()

    def on_play_paused(self):
        """Notification callback called in the thread of the playback service."""
        self._playback_state = PlaybackState.PLAYBACK_PAUSED
        self.draw()

    def on_play_resumed(self):
        self._playback_state = PlaybackState.PLAYBACK_PLAYING
        self.draw()

    def on_exception(self, e: Type[Exception]):
        """Notificiation callback called in the thread of the playback service."""
        pass

    def on_broadcast_busy(self):
        self._playback_state = PlaybackState.PLAYBACK_DISABLED
        self.draw()

    def on_broadcast_ready(self):
        self._playback_state = PlaybackState.PLAYBACK_STOPPED
        self.draw()

    def _event_processor(self, event_closure: EventClosureType):
        """This method is passed to the playback service for it to send us events back from
        its thread. It passes us a closure of the code it wants to be execute in this UI thread.

        The closure is a method that takes a PlaybackNotificationHandler (ourselves) as a parameter.
        """

        self._event_closure = event_closure
        self.event_generate(PLAYBACK_EVENT)

    def _do_playback_event(self, _):
        event_closure: EventClosureType = self._event_closure

        self._event_closure = None
        if event_closure:
            event_closure(self)  # No idea why typing hinting complains about this.
