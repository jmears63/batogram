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

import os
import time
from typing import Optional, Tuple

import numpy as np

from abc import ABC, abstractmethod
from dataclasses import dataclass
from numpy import ndarray
from .common import AxisRange
from .graphsettings import MAX_FFT_SAMPLES
from .wavfileparser import WavFileParser


class RawDataReader(ABC):
    """An abstraction for reading raw data."""

    def __init__(self):
        pass

    @abstractmethod
    def read_raw_data(self, index_range: Tuple[int, int]) -> ndarray:
        """Read raw file data for the half open range provided."""
        raise NotImplementedError()


class AudioFileService(RawDataReader):
    """A service that allows the application to read raw data from a data file."""

    @dataclass
    class Metadata:
        """Metadata is used for displaying in the UI."""
        file_name: str
        file_path: str
        file_sample_rate: int
        channels: int
        length_seconds: float
        frame_data_present: bool

    @dataclass
    class RenderingData:
        """Data used for calculations and rendering."""
        file_sample_rate: int
        sample_count: int
        amplitude_range: AxisRange
        time_range: AxisRange
        frequency_range: AxisRange
        data_serial: int
        channels: int
        bytes_per_value: int
        frame_data_present: bool
        frame_data_offset: bool
        frame_length: int
        frame_data_values: int

    def __init__(self, filepath):
        super().__init__()

        self._amplitude_range = None
        self._time_range = None
        self._frequency_range = None
        self._filepath = filepath
        self._file_sample_rate = None
        self._sample_count = None
        self._data_serial: int = 0  # Used for the pipeline to detect when the file data has changed.
        self._metadata = None
        self._guano_data = None
        self._file_parser: Optional[WavFileParser] = None
        self._channels: Optional[int] = None
        self._bytes_per_value: Optional[int] = None
        self.frame_data_present = None
        self.frame_offset = None
        self.frame_length = None
        self.frame_data_values = None
        # IMPORTANT: also add any new properties to make_slave_copy.

    @staticmethod
    def make_slave_copy(other: "AudioFileService") -> "AudioFileService":
        """Create a copy of an instance of this class, duplicating the file parser so the copy
        can be closed independently of the original."""

        new_instance = AudioFileService(other._filepath)

        # Much of this is copied by reference as the slave is always used to refer
        # to the same file.
        new_instance._amplitude_range = other._amplitude_range
        new_instance._time_range = other._time_range
        new_instance._frequency_range = other._frequency_range
        # new_instance._filepath = other._filepath      # No need, pass via the argument.
        new_instance._file_sample_rate = other._file_sample_rate
        new_instance._sample_count = other._sample_count
        new_instance._data_serial = other._data_serial
        new_instance._metadata = other._metadata
        new_instance._guano_data = other._guano_data
        new_instance._file_parser = WavFileParser.make_slave_copy(other._file_parser)
        new_instance._channels = other._channels
        new_instance._bytes_per_value = other._bytes_per_value
        new_instance.frame_data_present = other.frame_data_present
        new_instance.frame_offset = other.frame_offset
        new_instance.frame_length = other.frame_length
        new_instance.frame_data_values = other.frame_data_values

        return new_instance

    def __enter__(self):
        # Support for with.
        pass

    def __exit__(self, *args):
        # Support for with.
        self.close()

    def open(self):
        self._file_parser = WavFileParser(self._filepath)
        chunks: WavFileParser.Chunks = self._file_parser.open()
        sample_rate, data, guanodata = chunks.header.sample_rate_hz, chunks.data, chunks.guanodata

        channels = chunks.header.num_channels  # Avoid warnings.
        sample_count = chunks.data.actual_sample_count
        # print("Opened file {}: rate = {} channels = {} samples = {}".format(self._filepath, sample_rate, channels, sample_count))

        # Do some sanity checks:
        if chunks.header.bits_per_sample != 16:
            raise ValueError(
                "Support is currently limited to 16 bit PCM - found {} bit data.".format(int(chunks.header.bits_per_sample)))
        if channels < 1:
            raise ValueError(
                "The data file must contain at least one channel - it actually contains {}".format(channels))
        if sample_rate < 0:
            raise ValueError(
                "The sample rate must be a positive number - it is actually {}".format(sample_rate))
        min_samples = MAX_FFT_SAMPLES * 2
        if sample_count < min_samples:
            raise ValueError(
                "The data file contains too few samples ({}, must be at least {})."
                .format(sample_count, min_samples))

        # The data seems sane, so go ahead and try to use it:

        # See if there is a sample rate in the GUANO. If there is, use it, because the
        # header sometimes reflects data stored in TE form:
        guano_key = 'Samplerate'
        if guanodata is not None and guano_key in guanodata:
            self._file_sample_rate = int(guanodata[guano_key])
        else:
            self._file_sample_rate = sample_rate
        self._sample_count = sample_count
        self._channels = channels
        self._bytes_per_value = int(chunks.header.bits_per_sample / 8)

        self.frame_data_present = chunks.data.frame_data_present
        self.frame_offset = chunks.data.frame_offset
        self.frame_length = chunks.data.frame_length
        self.frame_data_values = chunks.data.frame_data_num_values

        # Force the amplitude range to be symmetrical. The inner max is avoid the impossible negation of -32678.
        # There is no such positive number.
        abs_a_max = max(-(max(data.data_range[0], -32767)), data.data_range[1])
        self._amplitude_range = AxisRange(-abs_a_max, abs_a_max)

        if self._file_sample_rate > 0:
            self._time_range = AxisRange(0, self._sample_count / self._file_sample_rate)
        else:
            self._time_range = AxisRange(0, 1)

        self._frequency_range = AxisRange(0, self._file_sample_rate / 2)

        # Construct a string that can be used to know if a new (or the same) file has been loaded:
        self._data_serial = "{}:{}".format(self._filepath, time.time())

        # Prepare some metadata that will be used for the UI:
        _, file_name = os.path.split(self._filepath)
        length_seconds = sample_count / self._file_sample_rate
        self._metadata = AudioFileService.Metadata(file_name=file_name, file_path=self._filepath,
                                                   file_sample_rate=self._file_sample_rate,
                                                   channels=channels, length_seconds=length_seconds,
                                                   frame_data_present=chunks.data.frame_data_present)

        self._guano_data = guanodata

    def close(self):
        if self._file_parser is not None:
            self._file_parser.close()
        self._file_parser = None

    def get_metadata(self) -> Metadata:
        return self._metadata

    @staticmethod
    def _create_channels_array(wavdata, samples, channels):
        # Take care of the facts that multichannel audio is an array of arrays of samples at a given instants,
        # while single channel is just a 1d array.
        #
        # Return an array of channel arrays in all cases.
        #

        if channels == 1:
            data = np.reshape(wavdata, (1, samples))
        else:
            data = wavdata.transpose()  # nparray

        return data

    def get_rendering_data(self) -> "RenderingData":
        return AudioFileService.RenderingData(
            file_sample_rate=self._file_sample_rate,
            sample_count=self._sample_count,
            amplitude_range=self._amplitude_range,
            time_range=self._time_range,
            frequency_range=self._frequency_range,
            data_serial=self._data_serial,
            channels=self._channels,
            bytes_per_value=self._bytes_per_value,
            frame_data_present=self.frame_data_present,
            frame_data_offset=self.frame_offset,
            frame_length=self.frame_length,
            frame_data_values=self.frame_data_values
        )

    def get_guano_data(self):
        return self._guano_data

    def read_raw_data(self, index_range: Tuple[int, int]) -> Tuple[ndarray, int]:
        """
        Read raw file data for the half open range provided.
        Truncate the data to the actual range available from the file.
        """

        # Sanitize the range requested:
        start, end = index_range
        start = max(0, start)
        end = min(self._sample_count, end)      # Half open.
        actual_range = start, end

        # Read the data from file and organize it into channels:
        raw_data, samples_read = self._file_parser.read_data(actual_range)
        channels = self._create_channels_array(raw_data, samples_read, self._channels)

        return channels, samples_read
