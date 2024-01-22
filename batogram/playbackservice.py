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

import copy
import time
import wave

import numpy as np
import pyaudio

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from threading import Thread, Condition, RLock
from typing import Type, Tuple, Optional, Callable, List

from scipy.signal import cheby1, sosfilt, sosfilt_zi, resample_poly

from batogram.audiofileservice import AudioFileService
from batogram.playbackmodal import PlaybackMethod, PlaybackSettings

# Our data type, currently limited to this:
playback_dtype: np.dtype = np.dtype(np.int16)

# Our target sample rate for playback.
native_sample_rate: int = int(48000)

# Frame size for pyaudio playback. Must be a multiple of 2, 3... so
# we can manage all the TD ratios and get an integer number of samples
# per frame.
native_frame_size: int = 6 * (1 * 2 * 3 * 4 * 5 * 6)  # Support interpolation up to 6 times.
max_interpolation_ratio: int = 6


#   Decimation:     raw chunk size must be a multiple of the decimation ratio.
#   Heterodyne:     raw chunk size must be a multiple of the heterodyne samples per cycle.
#   Interpolation:  raw chunk size must be an integer, even after division by the interpolation ratio.
#
#   Direct:             Scaling | Decimation                        Automatically raw chunk is a multiple of the ratio.
#   Heterodyne:         Scaling | Multiplication | Decimation       ditto
#   TD+Decimation:      Scaling | Decimation                        ditto
#   TD+Interpolation:   Scaling | Interpolation                     The raw chunk has to be a multiple of the ratio.


@dataclass
class PlaybackRequest:
    """This class encapsulates everything we need to do to play back some audio."""
    afs: AudioFileService
    sample_range: Tuple[int, int]
    settings: PlaybackSettings
    wave_file: Optional[wave.Wave_write]


class PlaybackCursorEventHandler(ABC):
    @abstractmethod
    def on_show_update_playback_cursor(self, offset: int):
        raise NotImplementedError()

    @abstractmethod
    def on_hide_playback_cursor(self):
        raise NotImplementedError()


class PlaybackEventHandler(PlaybackCursorEventHandler):
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

    @abstractmethod
    def on_show_update_playback_cursor(self, offset: int):
        raise NotImplementedError()

    @abstractmethod
    def on_hide_playback_cursor(self):
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

        # Lock for safe access to data in this instance. That includes other objects
        # used internally in this instance.

        self._rlock = RLock()
        self._condition = Condition(self._rlock)  # Used to signal that a new request is ready for our attention.

        self._shutting_down = False
        self._pending_request_tuple: Optional[PlaybackRequestTuple] = None  # Use with _lock.
        self._is_processing = False  # Use with _lock.
        self._watchers: List[Tuple[Type[PlaybackEventHandler], EventProcessorType]] = []
        self._shutting_down = False
        self._pa: Optional[pyaudio.PyAudio] = None

        # Kick off the thread:
        self.start()

    def get_pa(self) -> pyaudio.PyAudio:
        with self._rlock:
            if self._pa is None:
                self._pa = pyaudio.PyAudio()
            return self._pa

    def add_watcher(self, watcher: Type[PlaybackEventHandler], processor: EventProcessorType):
        """Add a watcher which will receive broadcast events."""
        with self._rlock:
            self._watchers.append((watcher, processor))

    def shutdown(self):
        """Tidily shut down the worker thread when it has finished any work in progress."""
        with self._rlock:
            self._shutting_down = True
            self.submit(None)

    def submit(self, request: Optional[PlaybackRequestTuple]):
        with self._rlock:
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
        """
        Thread: playback thread.

        This method waits for work and performs it. One request at a time.
        """

        with self._rlock:
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
                    try:
                        self._rlock.release()       # The sub class will lock the lock as required.
                        self.do_processing(request, event_processor)
                    finally:
                        self._rlock.acquire()
                except FailGracefullyException as _:
                    pass
                except BaseException as e:
                    event_processor(lambda handler: handler.on_exception(e))
                else:
                    pass  # We completed cleanly.

    def do_processing(self, request: PlaybackRequest, event_processor: EventProcessorType) -> None:
        """Subclasses must override this to do their work."""
        raise NotImplementedError()

    def _broadcast(self, active_event_processor: EventProcessorType, closure: EventClosureType):
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


class AbstractPlaybackEngine(ABC):
    """Any playback method class must subclass this one."""

    @abstractmethod
    def do_calculations(self) -> None:
        """Do all calculations needed in readiness, return the chunk size."""
        raise NotImplementedError()

    @abstractmethod
    def get_data(self, length: int) -> Tuple[np.ndarray, int, bool]:
        """Request a length data. We can't necessarily fulfill the request. The 
        return tuple is: data, length actually returned, is this the end of data?"""
        raise NotImplementedError()

    @abstractmethod
    def start(self):
        """Do any startup needed for this method, and return the chunk size we want to be used."""
        raise NotImplementedError()

    @abstractmethod
    def finish(self):
        """Clean up."""
        raise NotImplementedError()

    @abstractmethod
    def is_active(self) -> bool:
        """Is playback ongoing?"""
        raise NotImplementedError()

    @abstractmethod
    def stop_stream(self):
        """Stop playback."""
        raise NotImplementedError()

    @abstractmethod
    def start_stream(self):
        """Resume playback."""
        raise NotImplementedError()

    @abstractmethod
    def get_current_offset(self) -> int:
        """Get the current position of playback."""
        raise NotImplementedError()


class Modifier(ABC):
    @dataclass
    class Params:
        sample_rate: int
        chunk_size: int  # The length of modifier input data needed.

    @abstractmethod
    def calculate(self, params: Params) -> Params:
        raise NotImplementedError()

    def post_calculate(self, final_params: Params) -> None:
        """Called after all modifier calculate methods are called."""
        pass

    @abstractmethod
    def modify(self, data: np.ndarray, length: int) -> Tuple[np.ndarray, int]:
        raise NotImplementedError()


class PlaybackServiceImpl(PlaybackService):
    def __init__(self):
        super().__init__()
        # We use the parent class's lock for thread safety.

        self._engine: Optional[Type[AbstractPlaybackEngine]] = None
        self._pausing: bool = False
        self._stopping: bool = False

    def signal(self, signal: PlaybackSignal):
        with self._rlock:
            engine = self._engine  # Avoid races.
            if engine is not None:
                if signal == PlaybackSignal.SIGNAL_STOP:
                    if not self._pausing:
                        engine.stop_stream()
                    self._pausing = False
                    self._stopping = True
                elif signal == PlaybackSignal.SIGNAL_PAUSE:
                    self._pausing = True
                    self._stopping = False
                    engine.stop_stream()
                elif signal == PlaybackSignal.SIGNAL_NONE:
                    self._pausing = False
                    self._stopping = False

    def do_processing(self, request: PlaybackRequest, event_processor: EventProcessorType) -> None:
        with self._rlock:
            self._pausing = False
            afs: AudioFileService = request.afs

            # Configure the output file if any:
            if request.wave_file:
                bytes_per_value = playback_dtype.itemsize
                # The length will be filled in later, when we know what it is:
                params = afs.get_rendering_data().channels, bytes_per_value, native_sample_rate, 0, "NONE", ""
                request.wave_file.setparams(params)

            try:    # Define a scope for cleaning up.
                # print("Starting")
                self._broadcast(event_processor, lambda handler: handler.on_broadcast_busy())

                # Select the method based on the user's selection:
                if request.settings.autoscale:
                    scaler: float = self._get_autoscale_factor(afs, request.sample_range)
                    i_scaler = max(int(1), int(scaler + 0.5))

                event_processor(lambda handler: handler.on_play_started())

                # The code below would probably be nicer written as a state machine. Another day.

                self._engine: Type[AbstractPlaybackEngine] = self._get_engine(
                    request, event_processor, i_scaler, request.wave_file)
                self._pausing = self._stopping = False
                terminating: bool = False
                # print("Starting")
                while not terminating:
                    # Start from the beginning:
                    self._engine.start()

                    # Wait while it plays, including pauses:
                    while True:
                        while self._engine.is_active():
                            # We update the playback curser here rather than from data callback in the engine.
                            # Doing that resulted in the program freezing; either a deadlock resulting from pyaudio
                            # locking something that tkinter needs, or just a simple pile up of events.
                            offset = self._engine.get_current_offset()
                            event_processor(lambda handler: handler.on_show_update_playback_cursor(offset))
                            try:
                                self._rlock.release()
                                time.sleep(0.1)
                            finally:
                                self._rlock.acquire()
                        if self._pausing:
                            event_processor(lambda handler: handler.on_play_paused())
                            # print("Pausing")
                            # Wait for resume, stop or shutdown:
                            while self._pausing and not self._shutting_down and not self._stopping:
                                try:
                                    self._rlock.release()
                                    time.sleep(0.1)
                                finally:
                                    self._rlock.acquire()
                            event_processor(lambda handler: handler.on_play_resumed())
                            if not self._shutting_down and not self._stopping:
                                self._engine.start_stream()
                                # print("Resuming.")
                        else:
                            break  # Reached the end or stop pressed.

                    if self._stopping:
                        # They clicked stop.
                        # print("Stopping")
                        event_processor(lambda handler: handler.on_play_cancelled)
                        self._stopping = False
                        terminating = True
                    else:
                        # We got to the end of input.
                        # print("End of input")
                        terminating = not request.settings.repeat

                engine = self._engine  # Avoid races during shutdown.
                self._engine = None
                engine.finish()

                event_processor(lambda handler: handler.on_hide_playback_cursor())
                event_processor(lambda handler: handler.on_play_finished())
                self._broadcast(event_processor, lambda handler: handler.on_broadcast_ready())
            finally:
                afs.close()
                if request.wave_file:
                    request.wave_file.close()

    def _get_engine(self, request: PlaybackRequest, event_processor: EventProcessorType, i_scaler: int,
                    wave_file: Optional[wave.Wave_write]) -> Type[
            AbstractPlaybackEngine]:

        rendering_data = request.afs.get_rendering_data()
        settings = request.settings
        modifiers: List[Modifier] = [ScalingModifier(i_scaler)]
        if settings.method == PlaybackMethod.PLAYBACK_HETERODYNE_METHOD:
            modifiers.append(HeterodyneModifier(settings.reference_khz, settings.settings_sample_rate))
            # Decimate to get to 48 kHz, rounding if the raw sample rate is not a multiple of 48:
            factor: int = int(settings.settings_sample_rate / native_sample_rate + 0.5)
            factor = max(factor, 1)
            modifiers.append(DecimationModifier(factor, rendering_data.channels))
        elif settings.method == PlaybackMethod.PLAYBACK_TD_METHOD:
            # TD can go one of two ways to end up with 48 kHz.
            # A large division would result in a sample rate < 48 kHz: we interpolate/upsample.
            # A smaller division would result in a sample rate > 48 kHz: we need to decimate.
            # The raw data must be a multiple of 48 kHz: if it isn't, we pretend that it is by rounding.

            total_factor: int = int(settings.settings_sample_rate / native_sample_rate + 0.5)
            td_factor: int = settings.td_factor
            modifiers.append(TDModifier(td_factor))
            if td_factor < total_factor:
                decimation_factor: int = int(total_factor / td_factor + 0.5)
                modifiers.append(DecimationModifier(decimation_factor, rendering_data.channels))
            elif td_factor > total_factor:
                interpolation_factor: int = int(td_factor / total_factor + 0.5)
                interpolation_factor = max(min(max_interpolation_ratio, interpolation_factor), 1)
                modifiers.append(InterpolationModifier(interpolation_factor, rendering_data.channels))
            else:
                pass  # Nothing more to do.
        else:
            # Decimate to get to 48 kHz, rounding if the raw sample rate is not a multiple of 48:
            factor: int = int(settings.settings_sample_rate / native_sample_rate + 0.5)
            factor = max(factor, 1)
            modifiers.append(DecimationModifier(factor, rendering_data.channels))

        method: Type[AbstractPlaybackEngine] = PyAudioPlaybackEngine(request, self, modifiers, wave_file)

        return method

    @staticmethod
    def _get_autoscale_factor(afs: AudioFileService, sample_range: Tuple[int, int]) -> float:
        """Examine the amplitude of the range of data provided and figure out
        a multiplier that scales it to 80% of the range available."""

        scaler: float = 1.0  # Default

        abs_max = 0
        chunk = 10000
        data: np.ndarray
        start, end = sample_range
        time_to_consider: float = 20.0
        end = min(end, int(start + (384000 * time_to_consider)))  # Sanity limit on the amount of data to consider.
        for offset in range(start, end, chunk):
            data, length = afs.read_raw_data((offset, offset + chunk))
            if length > 0:
                abs_max = int(max(abs_max, data.max() - 1))
                abs_max = int(max(abs_max, -(data.min() + 1)))

        if abs_max > 0:
            target_range: float = 0.70
            scaler = float(np.iinfo(playback_dtype).max / abs_max) * target_range

        return scaler


class DecimationHelper:
    """This class provides a way to decimate a data stream in chunks. It is inspired
    by the scipy.decimate method. Multiple channels of data in the stream are supported."""

    def __init__(self, ratio: int, channels: int):
        self._sos = None
        self._zi = None  # We'll populate this lazily as it is required
        self._ratio: int = ratio
        self._channels = channels
        if self._ratio > 1:
            # Set up a set of second order IIR filters for use in decimation later on:
            filter_order: int = 8
            sos = cheby1(filter_order, 0.05, 0.8 / self._ratio, output='sos')
            self._sos = np.asarray(sos, dtype=np.float64)
            zi = sosfilt_zi(self._sos)
            # The shape of zi is now (4, 2) but it needs to be (4, nchannels, 2)
            zi = zi[:, np.newaxis, :]
            self._zi = np.repeat(zi, self._channels, axis=1)

    def decimate_chunk(self, data: np.ndarray) -> Tuple[np.ndarray, int]:
        """Important: the caller must make sure the chunk length is a multiple of the
        decimation ratio.
        """

        # Step one: filter.
        if self._ratio > 1:
            # Filter to minimize aliasing from the next step:
            filtered_data, zo = sosfilt(self._sos, data, zi=self._zi)
            self._zi = zo  # Preserve state for the next chunk, to avoid discontinuities.
            filtered_data = filtered_data.astype(dtype=data.dtype)
        else:
            filtered_data = data

        # Step 2: down sample.
        # The caller has made sure the chunk length is a multiple of the decimation
        # ratio:
        filtered_data = filtered_data[:, 0::self._ratio]
        length = filtered_data.shape[1]

        return filtered_data, length


class InterpolationHelper:
    """This class provides a way to interpolate a data stream in chunks."""

    def __init__(self, ratio: int, channels: int):
        self._sos = None
        self._zi = None  # We'll populate this lazily as it is required
        self._ratio: int = ratio
        self._channels = channels
        if self._ratio > 1:
            # Set up a set of second order IIR filters for use in interpolation later on:
            filter_order: int = 8
            sos = cheby1(filter_order, 0.05, 0.8 / self._ratio, output='sos')
            self._sos = np.asarray(sos, dtype=np.float64)
            zi = sosfilt_zi(self._sos)
            # The shape of zi is now (4, 2) but it needs to be (4, nchannels, 2)
            zi = zi[:, np.newaxis, :]
            self._zi = np.repeat(zi, self._channels, axis=1)

    def interpolate_chunk(self, data: np.ndarray) -> Tuple[np.ndarray, int]:

        filtered_data = data

        if self._ratio > 1:
            # Step 1: upsample by repeating elements:
            expanded_data = np.repeat(data, self._ratio, axis=1)

            # Low pass filter based on the ratio, as there will be unwanted stuff above
            # the new nyquist frequency / ratio.
            filtered_data, zo = sosfilt(self._sos, expanded_data, zi=self._zi)
            self._zi = zo  # Preserve state for the next chunk, to avoid discontinuities.
            filtered_data = filtered_data.astype(dtype=data.dtype)

        length = filtered_data.shape[1]

        return filtered_data, length


class ScalingModifier(Modifier, ABC):
    """This modifier resamples the data to a lower sampling rate. Integer factors only."""

    def __init__(self, factor: int):
        self._factor = factor

    def calculate(self, params: Modifier.Params) -> Modifier.Params:
        return params

    def modify(self, data: np.ndarray, length: int) -> Tuple[np.ndarray, int]:
        return data[:, 0:length] * self._factor, length


class DecimationModifier(Modifier):
    """This modifier resamples the data to a lower sampling rate. Integer factors only."""

    def __init__(self, factor: int, channels: int):
        self._factor = factor
        self._helper: DecimationHelper = DecimationHelper(factor, channels)

    def calculate(self, params: Modifier.Params) -> Modifier.Params:
        params.sample_rate //= self._factor
        params.chunk_size *= self._factor  # So, always a multiple of factor, which is required.
        return params

    def modify(self, data: np.ndarray, length: int) -> Tuple[np.ndarray, int]:
        data, _ = self._helper.decimate_chunk(data[:, 0:length])
        return data, data.shape[1]


class InterpolationModifier(Modifier):
    """This modifier resamples the data to a lower sampling rate. Integer factors only."""

    def __init__(self, factor: int, channels: int):
        self._factor = factor
        self._helper: InterpolationHelper = InterpolationHelper(factor, channels)

    def calculate(self, params: Modifier.Params) -> Modifier.Params:
        params.sample_rate *= self._factor
        params.chunk_size //= self._factor
        return params

    def modify(self, data: np.ndarray, length: int) -> Tuple[np.ndarray, int]:
        data, _ = self._helper.interpolate_chunk(data[:, 0:length])
        return data, data.shape[1]


class HeterodyneModifier(Modifier):
    """This modifier resamples the data to a lower sampling rate. Integer factors only."""

    def __init__(self, reference_khz: int, sample_rate: int):
        self._reference_freq: int = int(reference_khz * 1000)
        self._sample_rate: int = sample_rate
        self._reference: Optional[np.ndarray] = None

    def calculate(self, params: Modifier.Params) -> Modifier.Params:
        return params

    def post_calculate(self, params: Modifier.Params) -> None:
        # Create a reference sine wave.
        # We want an exact number of cyles to fit in a chunk, for convenience. The chunks
        # are quite long so no one will notice the difference.
        cycles_per_chunk: int = int(self._reference_freq / self._sample_rate * params.chunk_size + 1)

        # Calculate a chunk's worth of reference sine wave:
        reference = np.sin(np.linspace(0, 2 * np.pi * cycles_per_chunk, num=params.chunk_size, dtype=np.float32))
        reference = (np.sin(reference) * (np.iinfo(playback_dtype).max - 1)).astype(playback_dtype)
        self._reference = reference

    def modify(self, data: np.ndarray, length: int) -> Tuple[np.ndarray, int]:
        heterodyned_data = ((data.astype(dtype=np.int32) * self._reference[0:length]) >> 16).astype(
            dtype=playback_dtype)
        return heterodyned_data, heterodyned_data.shape[1]


class TDModifier(Modifier):
    """This modifier applies time division by adjusting the sampling rate."""

    def __init__(self, td_factor: int):
        self._td_factor: int = td_factor

    def calculate(self, params: Modifier.Params) -> Modifier.Params:
        # Consider the input to be a different sampling rate, without actually
        # modifying it.
        params.sample_rate //= self._td_factor
        return params

    def modify(self, data: np.ndarray, length: int) -> Tuple[np.ndarray, int]:
        return data[:, 0:length], length


class PlaybackEngine(AbstractPlaybackEngine, ABC):
    """Basic stuff that any playbck engine will need."""

    def __init__(self, request: Type[PlaybackRequest], service: Type[PlaybackService], modifiers: List[Modifier],
                 wave_file: Optional[wave.Wave_write]):
        self._rlock = RLock()
        self._request: Type[PlaybackRequest] = request
        self._service: Type[PlaybackService] = service
        self._afs: AudioFileService = request.afs
        self._signal: PlaybackSignal = PlaybackSignal.SIGNAL_NONE
        self._modifiers: List[Modifier] = modifiers
        self._final_params: Optional[Modifier.Params] = None
        self._raw_params: Optional[Modifier.Params] = None
        self._current_offset: int = 0
        self._start_offset, self._end_offset = request.sample_range
        self._wave_file: Optional[wave.Wave_write] = wave_file  # Non custodial.

    def get_current_offset(self) -> int:
        with self._rlock:
            return self._current_offset

    def do_calculations(self) -> None:
        """Iterate through the data modifiers, doing calculations."""

        with self._rlock:
            rendering_data = self._request.afs.get_rendering_data()

            # Parameters as they are before any modifiers are applied:
            self._raw_params = Modifier.Params(sample_rate=self._request.settings.settings_sample_rate,
                                               chunk_size=native_frame_size)

            # Each modifier gets to update the params in turn:
            params = copy.deepcopy(self._raw_params)
            for m in self._modifiers:
                params = m.calculate(params)
            for m in self._modifiers:
                m.post_calculate(params)

            # Parameters as they are afer modifications:
            self._final_params = params

    def start(self):
        with self._rlock:
            self._current_offset = self._start_offset

    def finish(self):
        pass

    def get_data(self, length: int) -> Tuple[bytes, int, bool]:
        """
        Threading: this method is called in the pyaudio worker thread.
        """
        # with self._rlock:

        # The length of data needed to fulfull the request, taking into account the processing we will do:
        raw_length: int = min(self._final_params.chunk_size, self._end_offset - self._current_offset)
        data, actual_raw_length = self._afs.read_raw_data((self._current_offset, self._current_offset + raw_length))
        self._current_offset += actual_raw_length

        # Apply the modifiers:
        modified_length: int = actual_raw_length
        for m in self._modifiers:
            data, modified_length = m.modify(data, modified_length)

        # We should have the requested length at this point unless we are at the end of data.

        # Flag back to pyaudio if we have finished. I have a feeling that pyaudio discards the final
        # incomplete chunk without playing it. Oh well.
        finished = self._current_offset >= self._end_offset

        # We need the 'F' so that the two channels are interleaved LRLR rather than LLRR:
        databytes = data.tobytes('F')

        if self._wave_file:
            if finished:
                # This updates the file length as a side effect.
                self._wave_file.writeframes(databytes)
            else:
                self._wave_file.writeframesraw(databytes)

        return databytes, length, finished


class PyAudioPlaybackEngine(PlaybackEngine, ABC):
    """Provide a PyAudio implementatation."""

    def __init__(self, request: Type[PlaybackRequest], service: Type[PlaybackService], modifiers: List[Modifier],
                 wave_file: Optional[wave.Wave_write]):
        super().__init__(request, service, modifiers, wave_file)
        self._stream: Optional[pyaudio.Stream] = None

    def _pyaudio_data_callback(self, in_data, frame_count, time_info, status):
        """
        Threading: this method is called in the pyaudio worker thread.
        """

        with self._rlock:
            data: np.ndarray
            signal: PlaybackSignal

            databytes, length, finished = self.get_data(frame_count)

            # If len(data) is less than requested frame_count, PyAudio automatically
            # assumes the stream is finished, and the stream stops.
            # We stop playback by externally calling stream.stop()

            rc = pyaudio.paComplete if finished else pyaudio.paContinue

        return databytes, rc

    def start(self):
        with self._rlock:
            self.do_calculations()

            super().start()

            # For debugging in the UI thread:
            # d1 = self._pyaudio_data_callback(None, native_frame_size, None, None)
            # d2 = self._pyaudio_data_callback(None, native_frame_size, None, None)

            sample_width_bytes: int = playback_dtype.itemsize
            pa = self._service.get_pa()
            rendering_data = self._request.afs.get_rendering_data()

        # Release the lock now we have finished with instance data, so that pyaudio
        # callback is not blocked:
        self._stream = pa.open(format=pa.get_format_from_width(sample_width_bytes, unsigned=False),
                               channels=rendering_data.channels,
                               rate=self._final_params.sample_rate,
                               stream_callback=self._pyaudio_data_callback,
                               frames_per_buffer=native_frame_size,
                               output=True,
                               start=True)

    def finish(self):
        super().finish()
        with self._rlock:
            if self._stream:
                self._stream.close()
                self._stream = None

    def is_active(self) -> bool:
        # with self._rlock:   # Rely on _stream being thread safe.
        return self._stream.is_active()

    def stop_stream(self):
        # with self._rlock:
        if self._stream:
            self._stream.stop_stream()

    def start_stream(self):
        # with self._rlock:     # Rely on _stream being thread safe.
        if self._stream:
            self._stream.start_stream()
