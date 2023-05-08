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

import math
from time import process_time

import numpy as np
import scipy
from scipy.interpolate import CubicSpline

from . import colourmap, appsettings
from copy import deepcopy
from dataclasses import dataclass
from threading import Lock, Thread, Condition
from typing import Type, Tuple, Optional, Any, Callable
from scipy import ndimage
from .audiofileservice import AudioFileService, RawDataReader
from .chunky_spectrogram import chunky_spectrogram
from .common import AxisRange, AreaTuple, clip_to_range
from .graphsettings import GraphSettings, ADAPTIVE_FFT_SAMPLES, ADAPTIVE_FFT_OVERLAP_PERCENT, \
    FFT_OVERLAP_PERCENT_OPTIONS, BNC_ADAPTIVE_MODE, BNC_MANUAL_MODE, BNC_INTERACTIVE_MODE


class RenderingRequest:
    """The base class for rendering pipeline requests of any kind."""

    def __init__(self, data_area: AreaTuple, file_data: AudioFileService.RenderingData):
        self.data_area: AreaTuple = data_area
        self.file_data: AudioFileService.RenderingData = file_data


PendingRequestTuple = Tuple[Type[RenderingRequest], Any, Any]


class RenderingPipeline(Thread):
    """This class does spectrogram generation in a background thread in response
    to a request which fully specifies what is required.

    The result is made available as data accessed via this class, in response to an event signalling
    that it is ready.

    Pointless repeat calculations are avoided like this:
    * Each pipeline has only one kind of request.
    * The request queue is one deep, and new requests replace any existing queued request.
    * Response data is versioned, so the client can know if it has already processed a specific response.

    Note that Python threading is dire because of the GIL. However, much of our heavy lifting
    is done by nparray and scipy, which are largely C wrappers which release the GIL whenever
    they can. So threading is likely to help us, though not as much as without the GIL problem.

    The pipeline is separate from the raw file data class, so that multiple pipelines can
    be used to give multiple views of the same file data.

    Note
    : a pipeline could be split so that calculations common to two views of the same
    data can share common code.
    """

    def __init__(self, settings: GraphSettings):
        # daemon means that this thread is killed if the main thread exits.
        super().__init__(daemon=True, name="Pipeline")

        self._settings = settings
        self._shutting_down = False
        self._pending_request_tuple: Optional[PendingRequestTuple] = None  # Use with _lock.
        self._is_processing = False  # Use with _lock.
        self._condition = Condition()  # Used to signal that a new request is ready for our attention.

        # Kick off the thread:
        self.start()

    def submit(self, request: Optional[Type[RenderingRequest]], on_completion: Callable = None,
               on_error: Callable = None):
        # print("Submit {}".format(request))
        # If there is request overrun, discard the older request. The most recent request is the only one of interest:
        with self._condition:
            # Atomically note the request:
            # print("Existing pending request: {}".format(self._pending_request))
            self._pending_request_tuple = request, on_completion, on_error

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
                pending_request_tuple: Optional[PendingRequestTuple] = self._pending_request_tuple
                self._pending_request_tuple = None

            if self._shutting_down:
                print("Exiting from pipeline thread.")
                return

            if pending_request_tuple is None:  # I suppose this might happen if there is a race I haven't thought of.
                continue

            request, on_completion, on_error = pending_request_tuple

            try:
                # Derived classes must define this to contain work they want doing:
                self.do_processing(request)
                pass
            except FailGracefullyException as _:
                pass
            except BaseException as e:
                if on_error:
                    on_error(e)
                else:
                    print("Pipeline exception caught: {}", e)
            else:
                if on_completion is not None:
                    try:
                        on_completion()
                    except BaseException as e:
                        print("Pipeline completion exception caught: {}", e)

    def shutdown(self):
        """Tidily shut down the worker thread when it has finished any work in progress."""
        self._shutting_down = True
        self.submit(None)

    def do_processing(self, request: Type[RenderingRequest]) -> None:
        """Subclasses must override this to do their work."""
        raise NotImplementedError()


class FailGracefullyException(BaseException):
    def __init__(self, msg: str, *args):
        super().__init__(*args)
        self._msg = msg

    def get_msg(self):
        return self._msg


class PipelineStep:
    """All pipeline steps inherit from this class, which provides some common capabilities."""

    def __init__(self, settings: GraphSettings):
        self._cached_settings = None
        self._settings = settings
        self._serial: int = 0
        self._cacheddata = None
        self._cachedparams = None
        self._lock = Lock()

    def process_data(self, inputdata, params: Tuple) -> (Any, int, bool):

        # Hold a lock for this step as we do its calculation. This allows us to share
        # a step between different pipelines so that can do the calculation only once,
        # the first thread that gets there does the work; the other benefits from the
        # cached response. The step needs to be atomic for this to work.

        with self._lock:
            caching_enabled: bool = True
            was_cached_used: bool = False
            outputdata = None
            # Get a hash of the settings that relate to this step, or None if nun:
            settings = deepcopy(self.get_relevant_settings())
            # See if we can use cached results:
            if self._cacheddata is not None:
                if params == self._cachedparams and caching_enabled:
                    if settings is None or settings == self._cached_settings:
                        # We can use the cached value:
                        # print("Using cached data for {}".format(type(self)))
                        outputdata = self._cacheddata
                        was_cached_used = True
            if outputdata is None:
                # print("Calculating data for {}".format(type(self)))
                # The cache didn't work out, so we have to do the calculation.
                t1 = process_time()
                outputdata = self._implementation(inputdata, params)
                t2 = process_time()
                # print("{:.0f} ms for {}".format((t2 - t1) * 1000, type(self).__name__))

                # Cache the result in case we need it again (quite likely):
                self._cacheddata = outputdata
                self._cachedparams = params
                self._cached_settings = settings
                self._serial += 1

        return outputdata, self._serial, not was_cached_used

    def _implementation(self, inputdata, params):
        # Subclasses need to implement this.
        raise NotImplementedError()

    def get_cached_data(self):
        return self._cacheddata

    def get_relevant_settings(self):
        """Return the settings relevant to this calculation, or None if no settings are used."""
        # Subclasses whose calculation depends on any settings MUST implement this
        # so that caching properly.
        return None


class SpectrogramPipelineRequest(RenderingRequest):
    def __init__(self, is_reference: bool, data_area, file_data: AudioFileService.RenderingData, time_range: AxisRange,
                 frequency_range: AxisRange, screen_factors: tuple[float, float],
                 raw_data_reader: RawDataReader):
        super().__init__(data_area, file_data)
        self.axis_time_range: AxisRange = time_range
        self.axis_frequency_range: AxisRange = frequency_range
        self.raw_data_reader = raw_data_reader
        self.screen_factors = screen_factors
        self.is_reference = is_reference

    def __str__(self):
        return "SpectrogramPipelineRequest: {} etc".format(self.data_area)


@dataclass
class GraphParams:
    """Parameters for the graph that will be displayed in the UI."""

    window_type: str
    fft_samples: int
    fft_overlap: float


class BnCHelper:
    """Helper functions used for Brightness and Contrast handling."""

    @staticmethod
    def get_scalar_vmax(data):
        # Use max, not a percentile, to avoid it ever being less than vmin:
        try:
            vmax = data.max()
        except ValueError as e:
            vmax = 0.0
        return vmax

    @staticmethod
    def get_scalar_vmin(data, percent: float):
        try:
            vmin = np.percentile(data, percent)
        except IndexError as e:
            vmin = 0.0
        return vmin


@dataclass
class SpectrogramCalcData:
    """This class encapsulates basic calculations needed to scale and display
    a spectrogram."""

    # Segment index range to include the time axis range:
    first_segment_index: int
    last_segment_index: int  # Half open
    # Time index range needed for the segments index range:
    first_time_index_for_segs: int
    last_time_index_for_segs: int  # Half open
    # The actual time axis range the segment range results in:
    actual_time_axis_min: float
    actual_time_axis_max: float
    # Time index range corresponding directly to actual axis range:
    first_time_index_for_amp: int
    last_time_index_for_amp: int  # Half open

    first_freq_index: int
    last_freq_index: int  # Half open
    actual_freq_axis_min: float
    actual_freq_axis_max: float
    actual_fft_samples: int
    actual_fft_overlap_percent: float
    actual_fft_overlap_samples: int
    step_count: int

    def __init__(self, settings: GraphSettings, axis_time_range: AxisRange, axis_frequency_range: AxisRange,
                 file_data: AudioFileService.RenderingData, screen_factors: tuple[float, float],
                 canvas_width: int, canvas_height: int):
        """
            Do all the scale and offset calculations we will need to render a spectrogram.

            Note: we choose t=0 axis time to be the middle of the first sfft segment. This
            avoids the complication of the first segment offset being more than subsequent ones
            if we chose t=0 to be the left of the first segment. This results in possible negative
            time indexes, which client code clips to 0 and ignores.

            At the ends of the time range we clip the time to what is actually available, which
            can result offsets near the ends. Never mind.

            Note: there is a "blank" of fft_samples / 2 at the start AND end of the data plotted
            which appears in the UI as a blank at the end, relative to the length of data calculated based
            on the sample rate and number of points in the file.
        """

        # General preparation:
        sample_rate: int = file_data.sample_rate

        if settings.fft_samples == ADAPTIVE_FFT_SAMPLES:
            self.actual_fft_samples = self._calculate_auto_fft_samples(sample_rate, screen_factors)
        else:
            self.actual_fft_samples = settings.fft_samples

        if settings.fft_overlap == ADAPTIVE_FFT_OVERLAP_PERCENT:
            self.actual_fft_overlap_percent = self._calculate_auto_fft_overlap(
                sample_rate, self.actual_fft_samples, screen_factors)
        else:
            self.actual_fft_overlap_percent = settings.fft_overlap

        # print("fft_samples = {}, fft_overlap = {}".format(self.actual_fft_samples, self.actual_fft_overlap_percent))
        self.actual_fft_overlap_samples = int(self.actual_fft_overlap_percent / 100.0 * self.actual_fft_samples)
        self.step_count: int = int(self.actual_fft_samples - self.actual_fft_overlap_samples)
        half_segment_offset: int = int(self.actual_fft_samples / 2)  # Ignore the rounding error, small.
        step_time: float = (self.actual_fft_samples - self.actual_fft_overlap_samples) / sample_rate
        time_points = file_data.sample_count
        # max_segment_count: int = int((time_points - half_segment_offset) / self.step_count) + 1  # Ignore any leftover time points.
        max_segment_count: int = int(
            (time_points - self.actual_fft_overlap_samples) / self.step_count)  # Ignore any leftover time points.
        time_axis_min, time_axis_max = axis_time_range.get_tuple()
        freq_axis_min, freq_axis_max = axis_frequency_range.get_tuple()

        # ************** Calculations relating to the time axis **************

        def time_to_segment_index(t: float) -> int:
            """Get the segment number corresponding to the axis time. t=0 at the centre of
            the first segment, and offsets are constant between there and subsequent
            centres. We round down intentionally."""
            segment_index = int(t / step_time)  # This rounds *down* to the nearest step
            return segment_index

        def segment_index_to_time(i: int) -> float:
            """Get the axis time corresponding to a segment index - which is the time at the centre of the segment."""
            t = i * step_time  # - step_time / 2
            return t

        def segment_index_to_time_index(segment_index: int):
            """Get the index of the FIRST time value that is part of the segment."""
            # Offset for the spacing of centres - a negative time range index may result.
            time_index = int(segment_index * self.step_count - half_segment_offset)
            return time_index

        def time_to_time_index(t: float):
            """Get the index of the time sample at the centre of the segment whose centre
            is this axis time."""
            time_index = int(t * sample_rate) + half_segment_offset
            return time_index

        # Convert the axis ranges supplied to data index ranges, rounding outwards.
        # t=0 is the centre of the first sfft segment, so it depends in the window size.
        # This convention avoids varying time offsets as different window sizes are selected.

        self.first_segment_index = time_to_segment_index(time_axis_min)
        self.last_segment_index: int = self.first_segment_index + math.ceil(  # Round outwards.
            (time_axis_max - time_axis_min) / step_time) + 1  # Half open.

        # Allow a left and right margin to hide any edge artifacts from zooming. The
        # result is data indexes that may be outside the range of available data:
        margin: int = 10
        self.first_segment_index -= margin
        self.last_segment_index += margin

        # Limit the segment indexes to the possible range, last segment index is half open:
        self.first_segment_index = max(0, self.first_segment_index)  # Shouldn't be needed.
        self.last_segment_index = min(max_segment_count, self.last_segment_index)

        # Convert the segment index range to a time index range. We know the time indexes are sane,
        # because we clipped the segment indexes above. These time index ranges are the range needed
        # to calculate the segments - not the time range of the segments.
        self.first_time_index_for_segs = segment_index_to_time_index(self.first_segment_index)
        # Note: (1) the last_segment_index is half open so - 1. (2) include the full index range for the previous
        # segment so that it can be calculated.
        self.last_time_index_for_segs = segment_index_to_time_index(
            self.last_segment_index - 1) + self.actual_fft_samples

        # Reverse calculate to the time range we actually cover, which is the segment centres.
        self.actual_time_axis_min = segment_index_to_time(self.first_segment_index)
        self.actual_time_axis_max = segment_index_to_time(self.last_segment_index - 1)  # -1 because half open range

        # Calculate the time index range corresponding to the actual axis values:
        self.first_time_index_for_amp = time_to_time_index(self.actual_time_axis_min)
        self.last_time_index_for_amp = time_to_time_index(self.actual_time_axis_max)

        # ************** Calculations relating to the frequency axis **************

        file_fmin, file_fmax = file_data.frequency_range.get_tuple()
        freq_points: int = int(self.actual_fft_samples / 2 + 1)  # Includes f=0 and f=nyquist, so +1.

        def frequency_to_index(f: float) -> int:
            # Round to nearest index:
            return int((f - file_fmin) / (file_fmax - file_fmin) * freq_points + 0.5)

        def index_to_frequency(i: int) -> float:
            # + 0.5 because the index is a frequencey range and we take the
            # centre of that range:
            return (i - 0.5) * (file_fmax - file_fmin) / freq_points + file_fmin

        # Convert the axis ranges supplied to data index ranges, rounding outwards.

        self.first_freq_index = frequency_to_index(freq_axis_min)
        self.last_freq_index = frequency_to_index(freq_axis_max) + 1  # Half open

        # Allow a top and bottom margin to hide any edge artifacts from zooming. The
        # result is data indexes that may be outside the range of available data:
        margin: int = 3
        self.first_freq_index -= margin
        self.last_freq_index += margin

        # Limit the segment indexes to the possible range:
        self.first_freq_index = max(0, self.first_freq_index)
        self.last_freq_index = min(freq_points + 1, self.last_freq_index)  # Half open

        # Reverse calculate to the frequency range we actually cover:
        self.actual_freq_axis_min = index_to_frequency(self.first_freq_index)
        self.actual_freq_axis_max = index_to_frequency(self.last_freq_index)

        # ************** Calculations for scaling to the canvas pixel area **************

        # We need to scale and offset so that the canvas area maps to the axis data range
        # requested. We have intentionally made the intermediate index ranges larger
        # so there an be a hidden margin and so that fractional data indexes can be
        # represented.

        pixels_per_second: float = canvas_width / (time_axis_max - time_axis_min)
        self.time_dilated_pixels: int = int(
            pixels_per_second * (self.actual_time_axis_max - self.actual_time_axis_min) + 0.5)
        self.time_offset_pixels: int = int((time_axis_min - self.actual_time_axis_min) * pixels_per_second + 0.5)

        pixels_per_hz: float = canvas_height / (freq_axis_max - freq_axis_min)
        self.freq_dilated_pixels: int = int(
            pixels_per_hz * (self.actual_freq_axis_max - self.actual_freq_axis_min) + 0.5)
        self.freq_offset_pixels: int = int((freq_axis_min - self.actual_freq_axis_min) * pixels_per_hz + 0.5)

    @staticmethod
    def _calculate_auto_fft_samples(sample_rate: int, screen_factors: tuple[float, float]) -> int:
        """Select a number of FFT samples that roughly results in square image elements on the screen."""

        # Overlapping of windows increases the resultant sample rate:
        # overlap_ratio = 100.0 / (100.0 - fft_overlap_percent)

        # It seems to work best if we ignore overlapping - which doesn't actually increase
        # time resolution, just smooths over time:
        overlap_ratio = 1

        aspect_factor, _ = screen_factors

        fft_samples_squared = sample_rate * sample_rate * overlap_ratio * aspect_factor

        fft_samples = int(scipy.sqrt(fft_samples_squared) + 0.5)

        # Round to the nearest factor of 2:
        rounded_fft_samples = 2 ** int(scipy.log2(fft_samples) + 0.5)
        rounded_fft_samples *= 2  # Subjectively, this looks better.

        # These limits need to make the range of samples that can be selected manually:
        rounded_fft_samples = max(64, rounded_fft_samples)
        rounded_fft_samples = min(4096, rounded_fft_samples)

        # print("calculated fft samples = {}".format(rounded_fft_samples))

        return rounded_fft_samples

    @staticmethod
    def _calculate_auto_fft_overlap(sample_rate, fft_samples, screen_factors) -> int:

        _, pixels_per_second = screen_factors  # Screen scaling.
        fft_window_time: float = fft_samples / sample_rate
        fft_window_pixels: float = pixels_per_second * fft_window_time

        # Choose an overlap that results in no more than half a data point per screen pixel:
        multiplier: float = 2.0 / fft_window_pixels
        overlap_percentage: float = 100.0 / multiplier
        overlap_percentage = clip_to_range(overlap_percentage, 0.0, 95.0)

        # Round the required overlap to the nearest available option:
        items = [(k, v) for k, v in FFT_OVERLAP_PERCENT_OPTIONS.items() if k != ADAPTIVE_FFT_OVERLAP_PERCENT]
        rounded, _ = items[0]
        delta = abs(rounded - overlap_percentage)
        for k, v in items[1:]:
            this_delta = abs(k - overlap_percentage)
            if this_delta < delta:
                rounded = k
                delta = this_delta

        return rounded


class PipelineHelper:
    """Handy common capabilities useful to all pipelines."""

    _MAX_FILE_MEMORY_USAGE = 250000000  # Maximum size of data we allow to be read from a file.
    _MAX_SPECTROGRAM_MEMORY_USAGE = 500000000  # Maximum working memory we allow a spectrogram pipeline to require.

    def __init__(self):
        pass

    @staticmethod
    def _estimate_memory_needed(file_data: AudioFileService.RenderingData,
                                calc_data: SpectrogramCalcData) -> Tuple[int, int]:
        """Estimate the memory needed to render a spectrogram from file with the settings provided."""

        # First, the memory needed to load the raw data from file:
        file_data_samples_needed: int = (calc_data.last_time_index_for_segs - calc_data.first_time_index_for_segs) \
                                        * file_data.channels
        file_data_bytes_needed: int = file_data_samples_needed * file_data.bytes_per_value

        # Space needed to store the spectrum data. Divide by two because we discard the phase info.
        overlap_factor: float = calc_data.actual_fft_samples / (
                calc_data.actual_fft_samples - calc_data.actual_fft_overlap_samples)
        spectrum_data_bytes_needed: int = int(file_data_samples_needed * overlap_factor * np.float32(0).nbytes / 2)

        total_bytes_needed: int = spectrum_data_bytes_needed + file_data_bytes_needed

        return total_bytes_needed, file_data_bytes_needed


class SpectrogramPipeline(RenderingPipeline, PipelineHelper):
    """All steps needed to render a spectrogram."""

    def __init__(self, settings: GraphSettings, spectrogram_step: "SpectrogramFftStep",
                 data_reader_step: "SpectrogramDataReaderStep"):
        super().__init__(settings)
        PipelineHelper.__init__(self)

        self._completion_data = None
        self._graph_params = None
        self._histogram_interface = None
        self._spectrogram_step = spectrogram_step
        self._data_reader_step = data_reader_step
        self._zoom_step = SpectrogramZoomStep(settings)
        self._bnc_step = SpectrogramBNCStep(settings)
        self._apply_colour_map_step = SpectrogramApplyColourMapStep(settings)

        # Remember info about the last histogram data, so we know if there is any change to it:
        self._last_histogram_data_details: tuple[int, int] | None = None

    def get_completion_data(self):
        return self._completion_data

    def get_graph_parameters(self) -> Optional[GraphParams]:
        return self._graph_params

    def do_processing(self, request: SpectrogramPipelineRequest):
        # print("do_processing {}".format(request))

        self._completion_data = None

        # Unpack some parameters:
        l, t, r, b = request.data_area
        height, width = b - t + 1, r - l + 1
        filedata, filedata_serial = request.file_data, request.file_data.data_serial
        sample_rate, sample_count = filedata.sample_rate, filedata.sample_count
        file_time_range, file_frequency_range = request.file_data.time_range, request.file_data.frequency_range

        if height < 10 or width < 10:
            # They've asked for a tiny or negative image size. Fail gracefully.
            # print(height)
            raise FailGracefullyException("Area to draw is too small")

        calc_data = SpectrogramCalcData(
            self._settings, request.axis_time_range, request.axis_frequency_range, request.file_data,
            request.screen_factors, width, height)

        bytes_needed, _ = self._estimate_memory_needed(request.file_data, calc_data)
        # print("Bytes needed: {:,}".format(bytes_needed))

        if bytes_needed > self._MAX_SPECTROGRAM_MEMORY_USAGE:
            # No, we aren't going ahead with a request that needs this much memory.
            self._completion_data = True, request, None, None, None
            return

        # The pattern for each step is:
        #       get request data for the step
        #       see if there is a cached result for the same request data
        #       if so use it (and the result might be an error: no such file, bad file format etc.)
        #       if not, calculate the result and cache it, and invalidate all downstream cached values.

        if filedata is None:
            raise ValueError("There is no spectrum data")

        # Note that this step is shared with the profile pipeline, to avoid needless double calculation,
        # so we need to make sure we use the same settings in each pipeline.

        # Include the settings serial number artificially so that any settings change
        # results in a complete rerender:
        params = filedata_serial, request.raw_data_reader, calc_data.first_time_index_for_segs, \
            calc_data.last_time_index_for_segs, appsettings.instance.serial_number
        (rawdata, raw_data_offset), raw_data_serial, _ = self._data_reader_step.process_data(
            None, params)

        if rawdata.min() == rawdata.max():
            raise FailGracefullyException("Range of raw data values is zero")

        # Include the actual fft samples and overlap to force a cache miss when they change:
        params = raw_data_serial, sample_rate, sample_count, request.axis_time_range, \
            calc_data.actual_fft_samples, calc_data.actual_fft_overlap_samples, calc_data.actual_fft_overlap_percent, \
            request.is_reference
        (specdata, self._graph_params), specdata_serial, _ = \
            self._spectrogram_step.process_data((rawdata, raw_data_offset), params)

        del rawdata  # Allow the gc to reclaim this memory.

        params = raw_data_serial, height, width, request.axis_time_range, request.axis_frequency_range, \
            file_time_range, file_frequency_range, calc_data
        zoomed_specdata, zoomed_serial, _ = self._zoom_step.process_data(specdata, params)

        params = (zoomed_serial,)
        (bnc_specdata, auto_vrange), bnc_serial, _ = self._bnc_step.process_data(zoomed_specdata, params)
        # auto_vrange is the auto range chosen, or None if not in autorange mode.

        mapped_specdata, mapped_specdata_serial, _ = self._apply_colour_map_step.process_data(
            bnc_specdata, (bnc_serial,))

        # Decide if the histogram needs updating (only if it has changed, taking into
        # account the basis setting):
        histogram_data, histogram_serial = zoomed_specdata, zoomed_serial
        this_histogram_data_details = histogram_data, histogram_serial
        if this_histogram_data_details == self._last_histogram_data_details:
            histogram_data = None

        # Return data, rather than updating the histogram directly from here, because this is running
        # in a different thread from the one we use to update the UI.

        self._completion_data = False, request, mapped_specdata, histogram_data, auto_vrange

    def data_area_to_value(self, p_data_area):
        """Get the zoomed data value for the data area coords provided."""
        zoom_data = self._zoom_step.get_cached_data()
        if zoom_data is not None:
            n_f, n_t = zoom_data.shape
            t, f = p_data_area
            if 0 <= t < n_t and 0 <= f < n_f:
                return zoom_data[f, t]

        return None


class SpectrogramDataReaderStep(PipelineStep):
    """Get the raw data we need to render the spectrogram."""

    @dataclass
    class RelevantSettings:
        time_range: Optional[AxisRange]

        def __init__(self, settings: GraphSettings):
            self.time_range = settings.time_range

    def get_relevant_settings(self) -> RelevantSettings:
        """Get the settings subset that is relevant to this step. We will use this as a basis
        for cache invalidation."""
        return SpectrogramDataReaderStep.RelevantSettings(self._settings)

    def __init__(self, settings: GraphSettings):
        super().__init__(settings)

    def _implementation(self, inputdata, params):
        _, raw_data_reader, time_min_index, time_max_index, _ = params

        raw_data, samples_read = raw_data_reader.read_raw_data((time_min_index, time_max_index))
        return raw_data, time_min_index


class SpectrogramFftStep(PipelineStep):
    """Calculate a spectrogram from the raw data"""

    def __init__(self, settings: GraphSettings):
        super().__init__(settings)

    @dataclass
    class RelevantSettings:
        fft_samples: int
        fft_overlap: int
        window_type: str

        def __init__(self, settings: GraphSettings):
            self.fft_samples = settings.fft_samples
            self.fft_overlap = settings.fft_overlap
            self.window_type = settings.window_type

    def get_relevant_settings(self) -> RelevantSettings:
        """Get the settings subset that is relevant to this step. We will use this as a basis
        for cache invalidation."""
        return SpectrogramFftStep.RelevantSettings(self._settings)

    def _implementation(self, inputdata, params):
        previous_serial, sample_rate, file_data_samples, axis_time_range, actual_fft_samples, \
            actual_fft_overlap_samples, actual_fft_overlap_percent, is_reference = params
        rs = self.get_relevant_settings()

        # Input data is a subset of raw data from the input file, chosen to include
        # the axis range required. It consists of the data itself, and the offset from the
        # start of the data file in samples:
        data_read, data_read_offset = inputdata
        _, data_sample_count = data_read.shape
        del inputdata

        # We will calculate the spectogram corresponding of the somewhat enlarged actual axis range
        # in the SpectrogramCalcData. Later on, when we zoom the data to fit the display, we will discard
        # the excess data. That means we fft the range of data indexes in the SpectrogramCalcData.

        # print("calculating spectrogram: {}: {}", params, inputdata.shape)

        frequencies, combined_spectrogram = self._do_spectrogram(data_read, sample_rate, rs.window_type,
                                                                 actual_fft_samples, actual_fft_overlap_samples)

        # print("delta_t = {}".format(delta_t))

        # We now have spectrogram data corresponding to *actual* axis range, ie spanning from the middle of the
        # first segment to the middle of the last segment.

        # Make sure there aren't any zero values that would make log10 below fail:
        if combined_spectrogram.min() == 0.0:
            # s = np.sort(combined_spectrogram)
            arbitrary_small_number = 1E-20  # TODO review this arbitrary small number.
            combined_spectrogram = np.where(combined_spectrogram <= 0, arbitrary_small_number, combined_spectrogram)

        # Convert the resulting spectrogram to dB.
        # Multiplier is 10, not 20, because _do_spectrogram has already squared it.
        db_spectrogram = 10 * np.log10(combined_spectrogram)

        # Apply frequency response correction if required.
        response_data = appsettings.instance.ref_mic_response_data if is_reference else appsettings.instance.main_mic_response_data
        if response_data is not None:
            frequency_response = self._calculate_frequency_response(frequencies, response_data)
            # We need to change the shape of the frequency response so that it will "broadcast" over the spectrogram:
            frequency_response = frequency_response.reshape(-1, 1)
            db_spectrogram -= frequency_response

        return db_spectrogram, \
            GraphParams(fft_samples=actual_fft_samples, fft_overlap=actual_fft_overlap_percent,
                        window_type=rs.window_type)

    @staticmethod
    def _calculate_frequency_response(frequencies: np.ndarray, mic_response_data: Tuple[CubicSpline, float, float, float, float])\
            -> np.ndarray:
        """Interpolate/extrapolate the microphones response to match the frequency buckets suppled."""

        cs, f_min, f_max, r_min, r_max = mic_response_data
        interpolated = cs(frequencies)
        # Override the spline's extrapolation with constant extrapolation (much safer):
        for i in range(len(frequencies)):
            f = frequencies[i]
            if f < f_min:
                interpolated[i] = r_min
            if f > f_max:
                interpolated[i] = r_max

        return interpolated

    @staticmethod
    def _do_spectrogram(data: np.ndarray, sample_rate: int, window_type, actual_fft_samples: int, overlap: int) \
            -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate the spectrogram that is the scalar sum of powers from all channels - ie,
        ignoring phase.
        """

        # Create a spectrogram for each channel:
        spectrograms = []
        frequencies = None
        for d in data:
            # print("spectrogram of {} points".format(len(d)))
            # t1 = process_time()
            fbuckets, _, spectrum_data = chunky_spectrogram(
                d, fs=sample_rate,
                window=window_type,
                nperseg=actual_fft_samples,
                noverlap=overlap,
                nfft=None,
                # detrend=False, # Defaults to constant.
                return_onesided=True,
                scaling='density',
                # So that power dB is independent of window size.
                # Power per Hz.
                axis=-1,
                mode='psd')  # psd to square the data to get power.

            if frequencies is None:
                frequencies = fbuckets

            # t2 = process_time()
            # print("chunked_spectrogram time: {}".format(t2 - t1))
            # t1 = process_time()

            spectrograms.append(spectrum_data)

            # t2 = process_time()
        #            print("data faffing time: {}".format(t2 - t1))

        # Create a combined spectrogram by summing the power amplitudes. ndarray earns its keep here:
        # the alternative of doing this by looping dumbly is quite slow.
        # This results in the same data type as in the input array:

        _, n_segments = spectrograms[0].shape

        # Do the sum in chunks, as ndarray.sum inexplicably assigns lots of memory.
        chunk_size: int = 10000  # TODO
        samples_done = 0
        while samples_done < n_segments:
            # Create a sub-range of all the ndarrays in the python array:
            to_sum = min(chunk_size, n_segments - samples_done)
            segment_sub_range = samples_done, samples_done + to_sum
            sub_spectrograms = [s[:, slice(*segment_sub_range)] for s in spectrograms]
            # Write the sum into the first spectrum array to conserve memory:
            chunk_data_target = spectrograms[0][:, samples_done:samples_done + to_sum]
            np.sum(sub_spectrograms, axis=0, out=chunk_data_target)
            samples_done += to_sum

        # np.sum(spectrograms, axis=0, out=combined_spectrogram)  # Sum across all axes. Hungry on memory.

        # return combined_spectrogram
        return frequencies, spectrograms[0]


class SpectrogramZoomStep(PipelineStep):
    """Zoom the data in or out to match the number of pixels we went to fill in the display."""

    def __init__(self, settings: GraphSettings):
        super().__init__(settings)

    @dataclass
    class RelevantSettings:
        zoom_interpolation: int

        def __init__(self, settings: GraphSettings):
            self.zoom_interpolation = settings.zoom_interpolation

    def get_relevant_settings(self) -> RelevantSettings:
        """Get the settings subset that is relevant to this step. We will use this as a basis
        for cache invalidation."""
        return SpectrogramZoomStep.RelevantSettings(self._settings)

    def _implementation(self, specdata, params):
        previous_serial, canvas_height, canvas_width, canvas_time_range, canvas_frequency_range, \
            file_time_range, file_frequency_range, calc_data = params

        rs = self.get_relevant_settings()

        # print("zoom input {},{}".format(inputdata.min(), inputdata.max()))

        # The segment and frequency range provided matches that in the calc data:
        clipped_inputdata = specdata[calc_data.first_freq_index:calc_data.last_freq_index, :]

        # Zoom the spectrogram index ranges into dilated canvas pixels size:
        y_scaler: float = calc_data.freq_dilated_pixels / (calc_data.last_freq_index - calc_data.first_freq_index)
        x_scaler: float = calc_data.time_dilated_pixels / (calc_data.last_segment_index - calc_data.first_segment_index)

        dilated_canvas_data = ndimage.zoom(clipped_inputdata,
                                           (y_scaler, x_scaler),
                                           # Scale to apply per axis.
                                           # order=rs.zoom_interpolation,  # Interpolation spline order
                                           order=rs.zoom_interpolation,  # Interpolation spline order
                                           mode='nearest',
                                           # grid-constant results in bright artifacts at the bottom edge.
                                           prefilter=False,  # Subjectively looks better as False: fewer artifacts.
                                           grid_mode=True)  # n pixels <=> width is n.

        # Clip the canvas dilated size back to the size we need to display:
        freq_offset_pixels = max(calc_data.freq_offset_pixels, 0)  # Paranoia.
        time_offset_pixels = max(calc_data.time_offset_pixels, 0)
        # Note: slicing fails gracefully if the upper value > array size.
        outputdata = dilated_canvas_data[
                     freq_offset_pixels:canvas_height + freq_offset_pixels,
                     time_offset_pixels:canvas_width + time_offset_pixels]

        # print("zoom ouput {},{}".format(outputdata.min(), outputdata.max()))

        return outputdata


class SpectrogramBNCStep(PipelineStep, BnCHelper):
    """Apply brightness and contrast settings to the image."""

    def __init__(self, settings: GraphSettings):
        super().__init__(settings)
        BnCHelper.__init__(self)

    @dataclass
    class RelevantSettings:
        bnc_adjust_type: int
        bnc_background_threshold_percent: float
        bnc_manual_min: float
        bnc_manual_max: float

        def __init__(self, settings: GraphSettings):
            self.bnc_adjust_type = settings.bnc_adjust_type
            self.bnc_background_threshold_percent = settings.bnc_background_threshold_percent
            self.bnc_manual_min = settings.bnc_manual_min
            self.bnc_manual_max = settings.bnc_manual_max

    def get_relevant_settings(self) -> RelevantSettings:
        """Get the settings subset that is relevant to this step. We will use this as a basis
        for cache invalidation."""
        return SpectrogramBNCStep.RelevantSettings(self._settings)

    def _implementation(self, inputdata, params):
        """Rescale the input data to the range 0-1 that will be directly mapped to the colour map.
        Data outside the range is clipped to the limits of the range.
        """
        previous_serial, = params

        rs = self.get_relevant_settings()

        # Defensive:
        auto_background_percent = max(rs.bnc_background_threshold_percent, 0.0)
        auto_background_percent = min(auto_background_percent, 100.0)

        vmin: float = self.get_scalar_vmin(inputdata, auto_background_percent)
        vmax: float = self.get_scalar_vmax(inputdata)
        auto_vrange = None  # Set this only if we autorange.

        if rs.bnc_adjust_type == BNC_ADAPTIVE_MODE:
            auto_vrange = vmin, vmax
        elif rs.bnc_adjust_type == BNC_MANUAL_MODE:
            vmin, vmax = rs.bnc_manual_min, rs.bnc_manual_max
        elif rs.bnc_adjust_type == BNC_INTERACTIVE_MODE:
            vmin, vmax = rs.bnc_manual_min, rs.bnc_manual_max

        # print("inputdata (vmin, vmax) is ({} to {})".format(inputdata.min(), inputdata.max()))

        # Apply the resultant brightness/contrast scaling:
        if vmax > vmin:
            bnc_data = (inputdata - vmin) / (vmax - vmin)
        else:
            bnc_data = inputdata

        # Clip the range to 0-1:
        bnc_data = np.where(bnc_data < 0.0, 0.0, bnc_data)
        bnc_data = np.where(bnc_data > 1.0, 1.0, bnc_data)

        # print("bnc_data (vmin, vmax) is ({} to {})".format(bnc_data.min(), bnc_data.max()))

        # Only return vrange if we have auto selected it here in this function, null otherwise,
        # for example if none was selected, or if it is manually selected.
        return bnc_data, auto_vrange


class SpectrogramApplyColourMapStep(PipelineStep):
    """Replace each value in the supplied data with an RGB colour"""

    def __init__(self, settings: GraphSettings):
        super().__init__(settings)

    @dataclass
    class RelevantSettings:
        colour_map_name: str  # Included slightly artificially to invalidate cached results.

        def __init__(self, settings: GraphSettings):
            self.colour_map_name = appsettings.instance.colour_map

    def get_relevant_settings(self) -> RelevantSettings:
        """Get the settings subset that is relevant to this step. We will use this as a basis
        for cache invalidation."""
        return SpectrogramApplyColourMapStep.RelevantSettings(self._settings)

    def _implementation(self, inputdata, params):
        # previous_serial, = params
        # s = self.get_relevant_settings()
        outputdata = colourmap.instance.map(inputdata)
        return outputdata


class AmplitudePipelineRequest(RenderingRequest):
    def __init__(self, data_area, file_data: AudioFileService.RenderingData, time_range: AxisRange,
                 frequency_range: AxisRange,
                 amplitude_range: AxisRange, screen_factors: tuple[float, float], rdr: RawDataReader):
        super().__init__(data_area, file_data)
        self.time_range: AxisRange = time_range
        self.amplitude_range: AxisRange = amplitude_range
        self.frequency_range = frequency_range
        self.raw_data_reader = rdr
        self.screen_factors = screen_factors

    def __str__(self):
        return "AmplitudePipelineRequest {} etc".format(self.data_area)


class AmplitudePipeline(RenderingPipeline, PipelineHelper):
    """All steps needed to render an amplitude graph."""

    def __init__(self, settings: GraphSettings, data_reader_step: SpectrogramDataReaderStep):
        super().__init__(settings)
        PipelineHelper.__init__(self)

        self._completion_data = None
        self._reduce_step = AmplitudeReduceData(settings)
        self._amplitude_image_step = AmplitudeLineSegmentStep(settings)
        self._data_reader_step = data_reader_step

    def do_processing(self, request: AmplitudePipelineRequest) -> None:
        # Unpack some parameters:
        l, t, r, b = request.data_area
        height, width = b - t + 1, r - l + 1
        sample_rate, filedata, filedata_serial = request.file_data.sample_rate, request.file_data, request.file_data.data_serial
        axis_trange, axis_arange = request.time_range, request.amplitude_range
        filedata_trange = filedata.time_range
        filedata_arange = filedata.amplitude_range
        filedata_sample_count = filedata.sample_count

        if height < 1 or width < 1:
            # They've asked for a tiny or negative image size. Fail gracefully.
            # print(height)
            raise FailGracefullyException("Image size is invalid")

        if filedata is None:
            raise ValueError("There is no spectrum data")

        calc_data = SpectrogramCalcData(
            self._settings, request.time_range, request.frequency_range, request.file_data,
            request.screen_factors, width, height)

        _, bytes_needed = self._estimate_memory_needed(request.file_data, calc_data)
        # print("Bytes needed: {:,}".format(bytes_needed))

        if bytes_needed > self._MAX_SPECTROGRAM_MEMORY_USAGE:
            # No, we aren't going ahead with a request that needs this much memory.
            self._completion_data = True, request, None
            return

        params = filedata_serial, request.raw_data_reader, calc_data.first_time_index_for_segs, \
            calc_data.last_time_index_for_segs, appsettings.instance.serial_number
        (rawdata, raw_data_offset), raw_data_serial, _ = self._data_reader_step.process_data(
            None, params)

        # For performance, reduce the data volume to be close to the target canvas width. The
        # resulting reduced data matches the time range wanted for the axis:
        params = filedata_serial, width, axis_trange, axis_arange, filedata_trange, filedata_arange, \
            filedata_sample_count, calc_data.first_time_index_for_amp, calc_data.last_time_index_for_amp
        (reduced_data, reduction_ratio), reduce_serial, _ = self._reduce_step.process_data(
            (rawdata, raw_data_offset), params)

        # Draw the amplitude spans into a bitmap array:
        params = reduce_serial, sample_rate, height, width, axis_trange, axis_arange, filedata_trange, filedata_arange
        line_segments, ampdata_serial, _ = self._amplitude_image_step.process_data(
            reduced_data, params)

        # print("Amplitude calcs complete")
        self._completion_data = False, request, line_segments

    def get_completion_data(self):
        return self._completion_data


class AmplitudeReduceData(PipelineStep):
    """Calculate a reduced version of the input data by combining time axis buckets. This reduces
    expensive downstream calculations."""

    def __init__(self, settings: GraphSettings):
        super().__init__(settings)

    def _implementation(self, input_data, params):
        calc_data: SpectrogramCalcData
        previous_serial, canvas_width, axis_trange, axis_arange, filedata_trange, filedata_arange, \
            filedata_samples, first_time_index_for_amp, last_time_index_for_amp = params
        (rawdata, input_data_offset) = input_data
        del input_data
        channels, _ = rawdata.shape
        _, raw_samples = rawdata.shape

        # Map the required axis range back to raw data samples supplied:
        # The time axis range corresponds to the segment range:
        min_input_index = first_time_index_for_amp - input_data_offset
        max_input_index = last_time_index_for_amp - input_data_offset

        # Sanity:
        min_input_index = max(0, min_input_index)
        max_input_index = min(raw_samples, max_input_index)

        target_bucket_count = canvas_width * 2
        slicing_factor = int((max_input_index - min_input_index) / target_bucket_count)
        slicing_factor = max(1, slicing_factor)  # Sanity - if they zoom in a long way.

        # We have to make the input number of samples a multiple of the slicing factor for reshape
        # to work:
        rounded_input_count = int((max_input_index - min_input_index) / slicing_factor) * slicing_factor
        slice_count = int(rounded_input_count / slicing_factor)

        # Slice the data:
        min_input_index = max(min_input_index, 0)  # Paranoia
        truncated = rawdata[:, min_input_index:min_input_index + rounded_input_count]
        sliced = np.reshape(truncated, (channels, slice_count, slicing_factor))

        # Aggregate the slices across all channels then combine across channels:
        aggregated_max = sliced.max(2)
        aggregated_min = sliced.min(2)
        flattened_max = aggregated_max.max(0)
        flattened_min = aggregated_min.min(0)

        # Combine the max and min data into a single result array:
        aggregated_ranges = np.stack((flattened_min, flattened_max), -1)

        # Finally we have a reduced data array that corresponds to the time range
        # wanted. We will ignore rounding errors as they as sub pixel, and downstream
        # steps can assume the reduced data exactly matches the time range we want.
        return aggregated_ranges, slicing_factor


class AmplitudeLineSegmentStep(PipelineStep):
    """Calculate an amplitude image from the input range data"""

    def __init__(self, settings: GraphSettings):
        super().__init__(settings)

    def _implementation(self, inputdata, params):
        previous_serial, sample_rate, height, width, trange, arange, filedata_trange, filedata_arange = params

        # Input data is in aggregated buckets, each point is the amplitude range, and the bucket range
        # already matches the time axis range we need:
        inputdata_buckets_t, _ = inputdata.shape
        # tmin_file, tmax_file = filedata_trange

        # Get the axis ranges we need:
        # tmin, tmax = trange
        amin, amax = arange.get_tuple()  # Aggregated values from the reduce step.

        y_margin = 5  # Unused pixels above and below the graph.
        columns, _ = inputdata.shape
        arange = float(amax) - float(amin)

        def y_scaler(a):
            return (height - 1 - y_margin * 2) * (a - amin) / arange + y_margin

        # We will generate a line segment for every input bucket
        line_segments = np.zeros((inputdata_buckets_t, 4), dtype=np.int16)
        segment_index = 0

        last_y = None
        for x in range(0, columns):
            alow, ahigh = inputdata[x]
            # Avoid overflows when alow and ahigh are close to the range of their data type:
            alow, ahigh = float(alow), float(ahigh)
            scaled_ylow = y_scaler(alow)
            scaled_yhigh = y_scaler(ahigh)
            scaled_x = np.rint(x * (width - 1) / columns).astype(int)
            ymin, ymax = np.rint(scaled_ylow).astype(int), np.rint(scaled_yhigh).astype(int) + 1

            # Line from min to max for the first point:
            if last_y is None:
                line_segments[segment_index] = (scaled_x, ymin, scaled_x, ymax)
                segment_index += 1
            else:
                last_ymin, last_ymax = last_y
                pair_ymax = max(ymin, ymax, last_ymin, last_ymax)
                pair_ymin = min(ymin, ymax, last_ymin, last_ymax)
                line_segments[segment_index] = (scaled_x, pair_ymin, scaled_x, pair_ymax)
                segment_index += 1
            last_y = ymin, ymax

        return line_segments


class ProfilePipelineRequest(RenderingRequest):
    def __init__(self, is_reference: bool, data_area, file_data: AudioFileService.RenderingData, time_range: AxisRange,
                 frequency_range: AxisRange, screen_factors, raw_data_reader: RawDataReader):
        super().__init__(data_area, file_data)
        self.axis_time_range = time_range
        self.axis_frequency_range = frequency_range
        self.raw_data_reader = raw_data_reader
        self.screen_factors = screen_factors
        self.is_reference = is_reference

    def __str__(self):
        return "ProfilePipelineRequest {} etc".format(self.data_area)


class ProfilePipeline(RenderingPipeline, PipelineHelper):
    """All steps needed to render a profile graph."""

    def __init__(self, settings: GraphSettings, spectrogram_step: SpectrogramFftStep,
                 data_reader_step: SpectrogramDataReaderStep):
        super().__init__(settings)
        PipelineHelper.__init__(self)

        self._spectrogram_step = spectrogram_step
        self._data_reader_step = data_reader_step
        self._zoom_step = SpectrogramZoomStep(settings)
        self._profile_line_segment_step = ProfileLineSegmentStep(settings)
        self._data_reader_step = data_reader_step
        self._completion_data = None

    def do_processing(self, request: ProfilePipelineRequest) -> None:
        # Unpack some parameters:
        l, t, r, b = request.data_area
        height, width = b - t + 1, r - l + 1
        file_time_range, file_frequency_range = request.file_data.time_range, request.file_data.frequency_range
        filedata, filedata_serial = request.file_data, request.file_data.data_serial
        sample_rate, sample_count = filedata.sample_rate, filedata.sample_count

        self._completion_data = None

        if height < 1 or width < 1:
            # They've asked for a tiny or negative image size. Fail gracefully.
            # print(height)
            raise FailGracefullyException("Image size is invalid")

        if filedata is None:
            raise ValueError("There is no spectrum data")

        calc_data = SpectrogramCalcData(
            self._settings, request.axis_time_range, request.axis_frequency_range, request.file_data,
            request.screen_factors, width, height)

        bytes_needed, _ = self._estimate_memory_needed(request.file_data, calc_data)
        # print("Bytes needed: {:,}".format(bytes_needed))

        if bytes_needed > self._MAX_SPECTROGRAM_MEMORY_USAGE:
            # No, we aren't going ahead with a request that needs this much memory.
            self._completion_data = True, request, None, None
            return

        # This step is shared with the main spectrogram pipeline step, to avoid needlessly
        # calculating it twice:

        params = filedata_serial, request.raw_data_reader, calc_data.first_time_index_for_segs, \
            calc_data.last_time_index_for_segs, appsettings.instance.serial_number
        (rawdata, raw_data_offset), raw_data_serial, _ = self._data_reader_step.process_data(
            None, params)

        params = raw_data_serial, sample_rate, sample_count, request.axis_time_range, \
            calc_data.actual_fft_samples, calc_data.actual_fft_overlap_samples, calc_data.actual_fft_overlap_percent, \
            request.is_reference
        (specdata, self._graph_params), specdata_serial, spectrogram_serial = \
            self._spectrogram_step.process_data((rawdata, raw_data_offset), params)

        del rawdata  # Allow the gc to reclaim this memory.

        params = raw_data_serial, height, width, request.axis_time_range, request.axis_frequency_range, \
            file_time_range, file_frequency_range, calc_data
        zoomed_specdata, zoomed_serial, _ = self._zoom_step.process_data(specdata, params)

        # Create a series of points for drawing the profile:
        params = zoomed_serial, height, width
        (profile_points, vmin, vmax), specdata_serial, _ = self._profile_line_segment_step.process_data(
            zoomed_specdata, params)

        self._completion_data = False, request, profile_points, AxisRange(vmin, vmax)

    def get_completion_data(self):
        return self._completion_data


class ProfileLineSegmentStep(PipelineStep):
    """This step generates all the line segments needed to draw a profile."""

    def __init__(self, settings: GraphSettings):
        super().__init__(settings)

    def _implementation(self, input_data, params):
        previous_serial, height, width = params

        # The input is the spectrogram data. Aggregate each row to get the profile.
        # Use a percentile to focus on the signal, while trimming some noise:
        try:
            profile_data = np.percentile(input_data, 98, axis=1)
        except IndexError as e:
            profile_data = np.mean(input_data, axis=1)  # If there is no data in the percentile.

        rows, = profile_data.shape

        # Create a series of x,y points for the profile:
        profile_points = np.zeros((rows, 2), dtype=np.int16)

        vmax, vmin = profile_data.max(), profile_data.min()
        vrange = vmax - vmin
        if vrange > 0:
            for y in range(0, rows):
                v = profile_data[y]
                # Avoid overflows when vlow and vhigh are close to the range of their data type:
                scaled_x = (v - vmin) / vrange * (width - 1)
                scaled_y = np.rint(y * height / rows + 0.5).astype(int)
                profile_points[y] = np.rint(scaled_x).astype(int), scaled_y

        return profile_points, vmin, vmax
