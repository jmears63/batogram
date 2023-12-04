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
from __future__ import annotations

import time
import pyaudio

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from threading import Thread, Condition
from typing import Type, Tuple, Optional, Callable, List

from batogram.audiofileservice import AudioFileService


@dataclass
class PlaybackRequest:
    """This class encapsulates everything we need to do to play back some audio."""
    afs: AudioFileService
    sample_range: Tuple[int, int]


class PlaybackEventHandler(ABC):
    """Classes that need to handle playback notifications should implement this interface."""

    @abstractmethod
    def on_play_started(self):
        raise NotImplementedError()

    @abstractmethod
    def on_play_cancelled(self):
        raise NotImplementedError()

    @abstractmethod
    def on_play_finished(self):
        raise NotImplementedError()

    @abstractmethod
    def on_play_paused(self):
        raise NotImplementedError()

    @abstractmethod
    def on_play_resumed(self):
        raise NotImplementedError()

    @abstractmethod
    def on_exception(self, e: Type[BaseException]):
        raise NotImplementedError()

    @abstractmethod
    def on_broadcast_busy(self):
        """The service is busy and can't accept any requests to play."""
        raise NotImplementedError()

    @abstractmethod
    def on_broadcast_ready(self):
        """The service is ready to accept requests to play."""
        raise NotImplementedError()


# The event closure is a closure that this class passes back to the invoker:
EventClosureType = Callable[[Type[PlaybackEventHandler]], None]

# The event processor is a method implement on the invoker, used to send events to it:
EventProcessorType = Callable[[EventClosureType], None]

# This is the request that the playback invoker sends us:
PlaybackRequestTuple = Tuple[PlaybackRequest, EventProcessorType]


class PlaybackService(Thread):
    """This class does audio playback in a background thread in response
    to a request which fully specifies what is required.

    Note that Python threading is dire because of the GIL. Therefore we try to do as much of our
    heavy lifting as we can by nparray and scipy, which are largely C wrappers which release the GIL whenever
    they can. So threading is likely to help us, though not as much as without the GIL problem.
    """

    def __init__(self):
        # daemon means that this thread is killed if the main thread exits.
        super().__init__(daemon=True, name="Playback")

        self._shutting_down = False
        self._pending_request_tuple: Optional[PlaybackRequestTuple] = None  # Use with _lock.
        self._is_processing = False  # Use with _lock.
        self._condition = Condition()  # Used to signal that a new request is ready for our attention.
        self._watchers: List[Tuple[Type[PlaybackEventHandler], EventProcessorType]] = []
        self._shutting_down = False
        self._pa: Optional[pyaudio.PyAudio] = None

        # Kick off the thread:
        self.start()

    def get_pa(self) -> pyaudio.PyAudio:
        if self._pa is None:
            self._pa = pyaudio.PyAudio()
        return self._pa

    def add_watcher(self, watcher: Type[PlaybackEventHandler], processor: EventProcessorType):
        """Add a watcher which will receive broadcast events."""
        self._watchers.append((watcher, processor))

    def shutdown(self):
        """Tidily shut down the worker thread when it has finished any work in progress."""
        self._shutting_down = True
        self.submit(None)

    def submit(self, request: Optional[PlaybackRequestTuple]):
        # print("Submit {}".format(request))
        # If there is request overrun, discard the older request. The most recent request is the only one of interest:
        with self._condition:
            # Atomically note the request:
            # print("Existing pending request: {}".format(self._pending_request))
            self._pending_request_tuple = request

            # Tell the worker there is a new request for it, when it is ready.
            # Note that we might notify the worker redundantly because of the way we discard
            # submit overruns, so the worker needs to be able to deal with that.
            self._condition.notify()

    def run(self) -> None:
        """This method waits for work and performs it. One request at a time."""

        while True:
            with self._condition:
                # Wait until our services are required. Note that our master is impatient and may ring for us
                # more than once, so don't be surprised if there is no request waiting.
                self._condition.wait_for(lambda: self._pending_request_tuple is not None)

                # You called, my lord?

                # Atomically consume any request before we release the condition lock:
                pending_request_tuple: Optional[PlaybackRequestTuple] = self._pending_request_tuple
                self._pending_request_tuple = None

            if self._shutting_down:
                # print("Exiting from playback thread.")
                if self._pa:
                    self._pa.terminate()
                return

            if pending_request_tuple is None:  # I suppose this might happen if there is a race I haven't thought of.
                continue

            request, event_processor = pending_request_tuple
            try:
                # Derived classes must define this to contain work they want doing:
                self.do_processing(request, event_processor)
                pass
            except FailGracefullyException as _:
                pass
            except BaseException as e:
                event_processor(lambda handler: handler.on_exception(e))
            else:
                pass  # We completed cleanly.

    def do_processing(self, request: PlaybackRequest, event_processor: EventProcessorType) -> None:
        """Subclasses must override this to do their work."""
        raise NotImplementedError()

    def broadcast(self, active_event_processor: EventProcessorType, closure: EventClosureType):
        """Notify all watchers but the currently active one."""

        for _, p in self._watchers:
            if p != active_event_processor:
                p(closure)


class FailGracefullyException(BaseException):
    def __init__(self, msg: str, *args):
        super().__init__(*args)
        self._msg = msg

    def get_msg(self):
        return self._msg


class PlaybackSignal(Enum):
    SIGNAL_NONE = 0
    SIGNAL_PAUSE = 1
    SIGNAL_STOP = 2


class PlaybackProcessor(PlaybackService):
    def __init__(self):
        super().__init__()

        self._pending_signal = PlaybackSignal.SIGNAL_NONE

    def signal(self, signal):
        self._pending_signal = signal

    def do_processing(self, request: Type[PlaybackRequest], event_processor: EventProcessorType) -> None:
        afs = request.afs
        with afs:       # Automatically close the file handle when we are done.
            print("Starting")
            self._pending_signal = PlaybackSignal.SIGNAL_NONE
            self.broadcast(event_processor, lambda handler: handler.on_broadcast_busy())

            ########################################
            # Kick off the playback.
            sample_width_bytes: int = 2                             # TODO avoid this hard coding.
            rendering_data = afs.get_rendering_data()
            # TODO Check for sane parameter values below.
            pa = self.get_pa()

            stream = pa.open(format=pa.get_format_from_width(sample_width_bytes, unsigned=False),
                            channels=rendering_data.channels,
                            rate=rendering_data.sample_rate,
                            output=True)
            ########################################

            event_processor(lambda handler: handler.on_play_started())

            # This is a worker thread, so we will use the pyaudio blocking model.

            ########################################
            chunk_len: int = 1024   # Arbitrary.
            start, finish = request.sample_range
            ########################################
            for offset in range(start, finish, chunk_len):
                ########################################
                if self._pending_signal == PlaybackSignal.SIGNAL_PAUSE:
                    # Slowly spin here until they have finished pausing:
                    event_processor(lambda handler: handler.on_play_paused())
                    print("Pausing")
                    while self._pending_signal == PlaybackSignal.SIGNAL_PAUSE and not self._shutting_down:
                        time.sleep(0.2)     # TODO could we use a condition variable instead of the poll?
                    event_processor(lambda handler: handler.on_play_resumed())
                    print("Resuming")
                elif self._pending_signal == PlaybackSignal.SIGNAL_STOP:
                    print("Stopping")
                    event_processor(lambda handler: handler.on_play_cancelled)
                    break
                elif self._shutting_down:
                    break

                ########################################
                chunk_data, samples_read = afs.read_raw_data((offset, offset + chunk_len))
                if samples_read == 0:
                    break
                try:
                    stream.write(chunk_data.tobytes(), samples_read)        # Hopefully this releases the GIL.
                except BaseException as e:
                    print(e)
                ########################################

            stream.close()

            ########################################
            event_processor(lambda handler: handler.on_play_finished())
            print("Finishing")
            self.broadcast(event_processor, lambda handler: handler.on_broadcast_ready())

