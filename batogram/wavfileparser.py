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

import io
import os

import numpy as np

from dataclasses import dataclass
from typing import List, Callable, Any, Tuple, Optional
from .external.guano import GuanoFile
from .stegangraphy import LSBSteganography


class WavFileError(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, *kwargs)


class WavFileParser:
    """A parser for wav files. It's simplest to implement our own, as off the shelf
    wav parsers don't handle the quirks for bat detector wav files, and it is not a
    difficult format to parse. Also, we need the ability to read a subset of the spectrum
    to avoid holding the entire data in memory at once."""

    @dataclass
    class Header:
        num_channels: int
        sample_rate_hz: int
        bits_per_sample: int

    @dataclass
    class Data:
        actual_sample_count: int  # The number of samples found may be less than the header said.
        data_byte_count: int
        data_range: Tuple[Any, Any]
        frame_data_present: bool
        frame_offset: int
        frame_length: int
        frame_data_num_values: int

    @dataclass
    class Chunks:
        header: "WavFileParser.Header"
        data: "WavFileParser.Data"
        guanodata: GuanoFile

    def __init__(self, filepath: str):
        self._filepath = filepath
        self._f = None
        self._start_of_data = None  # File offset to where data starts.
        self._fmt_header: Optional[WavFileParser.Header] = None
        # IMPORTANT: also add any new properties to make_slave_copy.

    @staticmethod
    def make_slave_copy(other: "WavFileParser") -> "WavFileParser":
        """Create a copy of this file parser, including duping the file handle so that the
        copied instance can be used and closed independently of the original.

        Simple variables are copied by value; objects that we regard as constant are copied
        by reference; the file descriptor is duped.
        """

        new_instance = WavFileParser(other._filepath)
        new_instance._filepath = other._filepath                # By reference as we regard as unchanging.
        new_instance._start_of_data = other._start_of_data      # Copy.
        new_instance._fmt_header = other._fmt_header            # By reference as we regard as unchanging.

        # Duplicate the file handle and create an associated python file object. This allows us to seek
        # and close independently using the new file descriptor:
        fd2 = os.dup(other._f.fileno())
        new_instance._f = os.fdopen(fd2)

        return new_instance

    def open(self) -> Chunks:
        # Binary mode:
        self._f = open(self._filepath, "rb")
        return self._read_chunks()

    def close(self):
        if self._f is not None:
            self._f.close()
        self._f = None

    def _read_chunks(self, ) -> Chunks:
        """Read all the metadata we can from the wav file. Call read_data() later to get the actual data."""

        # See http://soundfile.sapp.org/doc/WaveFormat/
        # See https://github.com/riggsd/guano-spec/blob/master/guano_specification.md

        self._f.seek(0, io.SEEK_END)
        file_len = self._f.tell()

        self._f.seek(0)

        # Read the main header which must come first:
        self._read_text_bytes(4, "ChunkID", b'RIFF')
        # self._read_int32("ChunkSize", expected=file_len - 8)      # Why is this sometimes off by 8?
        self._read_int32("ChunkSize")
        self._read_text_bytes(4, "Format", b'WAVE')
        self.fmt_header = data = guano = None

        # Keep going as long as there is unconsumed input:
        while self._f.tell() < file_len:
            subchunk_id = self._read_text_bytes(4, "SubchunkID")
            if subchunk_id == b'data':
                if data is not None:
                    print("Ignoring subsequent data chunks")
                else:
                    if self._fmt_header is not None:
                        data = self._skim_data(self._fmt_header)
                    else:
                        raise WavFileError("data chunk found without fmt header")
            elif subchunk_id == b'fmt ':  # Note: trailing space.
                if self._fmt_header is not None:
                    print("Ignoring subsequent fmt chunks")
                else:
                    self._fmt_header = self._read_fmt()
            elif subchunk_id == b'guan':
                if guano is not None:
                    print("Ignoring subsequent guano chunks")
                else:
                    guano = self._read_guan()
            else:
                print("ignoring unknown chunk {}".format(subchunk_id))
                self._skip_chunk()

        return WavFileParser.Chunks(header=self._fmt_header, data=data, guanodata=guano)

    def _read_fmt(self) -> Header:
        chunk_size = self._read_int32("fmt SubchunkSize")
        format_tag = self._read_int16("AudioFormat")

        if format_tag == 1:  # PCM no compression.
            required_chunk_size = 14 + 2  # More data may be supplied, we will ignore it.
            self._check_value("fmt SubchunkSize", chunk_size,
                              lambda v: v >= required_chunk_size, "must be >= {}".format(required_chunk_size))
            num_channels = self._read_int16("NumChannels")
            sample_rate_hz = self._read_int32("SampleRate")
            byte_rate = self._read_int32("ByteRate")
            block_align = self._read_int16("BlockAlign")
            bits_per_sample = self._read_int16("BitsPerSample")
        elif format_tag == 65534:  # WAVE_FORMAT_EXTENSIBLE
            # This limited supprt is reverse engineered from sample files,
            # and from https://www.jensign.com/riffparse/

            required_chunk_size = 36  # More data may be supplied, we will ignore it.
            self._check_value("fmt SubchunkSize", chunk_size,
                              lambda v: v >= required_chunk_size, "must be >= {}".format(required_chunk_size))
            num_channels = self._read_int16("NumChannels")
            sample_rate_hz = self._read_int32("SampleRate")
            byte_rate = self._read_int32("ByteRate")
            block_align = self._read_int16("BlockAlign")
            bits_per_sample = self._read_int16("BitsPerSample")
            cb_size = self._read_int16("ExtraSize")
            valid_bits_per_sample = self._read_int16("validBitsPerSample")
            channel_mask = self._read_int32("ChannelMask")  # Me neither.
            # Read and validate the 12 byte sub format in 3 pieces:
            subformat1 = self._read_int32("Subformat1", expected=0x00000001)
            subformat2 = self._read_int32("Subformat2", expected=0x00100000)
            subformat3 = self._read_int32("Subformat3", expected=0xAA000080)
        else:
            raise WavFileError("Unknown wav file format: {}".format(format_tag))

        # Sanity checks:
        self._check_value("NumChannels", num_channels, lambda v: v > 0, "must be > 0")
        self._check_value("SampleRate", sample_rate_hz, lambda v: v > 0, "must be > 0")
        self._check_value("BitsPerSample", bits_per_sample,
                          lambda v: v == 8 or v == 16 or v == 24 or v == 32,
                          "must be one of 8, 16, 24, 32 bits")

        # Does it really matter if we get unexpected values for the following?
        expected = sample_rate_hz * num_channels * bits_per_sample / 8
        self._check_value("ByteRate", byte_rate, lambda v: v == expected, "must be {}".format(expected))
        expected = num_channels * bits_per_sample / 8
        self._check_value("BlockAlign", block_align, lambda v: v == expected, "must be {}".format(expected))

        # Read and discard any extra data on the end of the chunk. Sometimes this is present, like this
        # example:
        #   00000000  52 49 46 46 48 4f 4c 00  57 41 56 45 66 6d 74 20  |RIFFHOL.WAVEfmt |
        #   00000010  44 00 00 00 01 00 01 00  20 a1 07 00 40 42 0f 00  |D....... ...@B..|
        #   00000020  02 00 10 00 4d 4d 4d 4d  4d 4d 4d 4d 4d 28 23 35  |....MMMMMMMMM(#5|
        #   00000030  30 30 30 30 30 23 29 3c  26 31 26 3e 5b 21 35 30  |00000#)<&1&>[!50|
        #   00000040  30 21 5d 4c 6f 63 61 74  69 6f 6e 5b 53 42 4d 4d  |0!]Location[SBMM|
        #   00000050  4d 4d 4d 4d 4d 4d 4d 00  64 61 74 61 40 47 4c 00  |MMMMMMM.data@GL.|

        excess_data = chunk_size - required_chunk_size
        if excess_data > 0:
            print("Discarding {} excess bytes from the end of fmt".format(excess_data))
            self._f.read(excess_data)

        if self._is_odd(chunk_size):
            self._read_int8("padding")  # Allow for padding 0 byte if the chunk is an odd length. Actually, it isn't.

        return WavFileParser.Header(num_channels=num_channels, sample_rate_hz=sample_rate_hz,
                                    bits_per_sample=bits_per_sample)

    def _skim_data(self, header: Header) -> Optional[Data]:
        """Process the data chunk without storing any of the data."""

        data_byte_count = self._read_int32("ChunkSize")

        frame_data_present = False
        frame_length = 0
        frame_offset = 0

        # Note where the data starts so we can come back for it later.
        self._start_of_data = self._f.tell()

        # Figure out the number of values we expect to find:
        value_count = int(data_byte_count * 8 / header.bits_per_sample)
        expected_sample_count = int(value_count / header.num_channels)

        min_value, max_value = None, None
        frame_data_present, frame_offset, frame_length, frame_data_num_values = False, 0, 0, 0

        # Read portions of data using via ndarray for speed, in portions
        # to avoid excessive memory usage, and track the data range
        # as we go.
        portion_size = 50000  # 50000 x 2 bytes is about 100K
        samples_read = 0
        first_time = True
        while samples_read < expected_sample_count:
            count = min(expected_sample_count - samples_read, portion_size)
            data, _ = self.read_data((samples_read, samples_read + count))
            samples_read += count
            if data is None:
                break  # Some issue in reading the data.
            if min_value is None:
                min_value, max_value = data.min(), data.max()
            else:
                min_value = min(min_value, data.min())
                max_value = max(max_value, data.max())

            if first_time and data is not None:
                frame_data_present, frame_offset, frame_length, frame_data_num_values = self._find_frame_data(data)
            first_time = False

            if data.shape[0] < count:
                break  # Hit the end prematurely.

        # Sometimes headers are wrong, because they are written in advance of the data.
        # Note the actual sample count. This is what we will use.
        actual_sample_count: int = samples_read

        # We have been seeking around in the file to read data, so we need
        # to seek to the end of data chunk now to not confuse the caller:
        self._f.seek(self._start_of_data + data_byte_count)
        if self._is_odd(data_byte_count):
            self._read_int8("padding")  # Allow for padding 0 byte if the chunk is an odd length.

        return WavFileParser.Data(actual_sample_count=actual_sample_count,
                                  data_range=(min_value, max_value),
                                  data_byte_count=data_byte_count,
                                  frame_data_present=frame_data_present,
                                  frame_offset=frame_offset,
                                  frame_length=frame_length,
                                  frame_data_num_values=frame_data_num_values)

    def read_data(self, index_range: Tuple[int, int]) -> Tuple[Optional[np.ndarray], int]:
        """Read the request range of data (half open), and return the data and actual count read."""

        dt = None
        if self._fmt_header.bits_per_sample == 8:
            dt = np.dtype(np.uint8)
        elif self._fmt_header.bits_per_sample == 16:
            dt = np.dtype(np.int16)
        # elif self._fmt_header.bits_per_sample == 24:
        #    dt = np.dtype(np.int24)        # Not supported in numpy.
        elif self._fmt_header.bits_per_sample == 32:
            dt = np.dtype(np.int32)
        else:
            # All bets are off.
            return None, 0

        dt = dt.newbyteorder('<')  # Wave files are little endian.

        bytes_per_value = int(self._fmt_header.bits_per_sample / 8)
        bytes_per_sample = bytes_per_value * self._fmt_header.num_channels
        start, end = index_range
        sample_count = end - start
        value_count = sample_count * self._fmt_header.num_channels

        # Move to the start of the data we are interested in:
        self._f.seek(self._start_of_data + start * bytes_per_sample)

        data = np.fromfile(self._f, dtype=dt, count=value_count)
        actual_values_read, = data.shape  # Use the actual count read, just in case.
        actual_samples_read = actual_values_read

        # Sometimes wav files do end prematurely - I guess the code that writes them just
        # guesses the length to write up front, then the actual length is defined by the
        # amount of data in the file.

        if self._fmt_header.num_channels > 1:
            actual_samples_read = int(actual_values_read / self._fmt_header.num_channels)
            data = data.reshape((actual_samples_read, self._fmt_header.num_channels))

        if self._is_odd(actual_samples_read * bytes_per_sample):
            self._read_int8("padding")  # Allow for padding 0 byte if the chunk is an odd length.

        return data, actual_samples_read

    def _read_guan(self) -> Optional[GuanoFile]:
        # https://www.wildlifeacoustics.com/SCHEMA/GUANO.html
        # https://github.com/riggsd/guano-py/blob/master/guano.py

        chunk_size_bytes = self._read_int32("ChunkSize")
        metadata = self._f.read(chunk_size_bytes)
        gf = None
        try:
            gf = GuanoFile.from_string(metadata, strict=False)
        except Exception as e:
            # Fail open if the guano is bad:
            print("Exception raised parsing guano data: {}".format(e))

        # for key, value in gf.items():
        #    print('{}: {}'.format(key, value))

        if self._is_odd(chunk_size_bytes):
            self._read_int8("padding")  # Allow for padding 0 byte if the chunk is an odd length.

        return gf

    def _skip_chunk(self):
        """Consume and ignore an entire chunk, assuming the chunk id has already been read."""
        bytes_to_skip = self._read_int32("ChunkSize")
        if self._is_odd(bytes_to_skip):
            bytes_to_skip += 1  # Allow for padding 0 byte if the chunk is an odd length.
        t = self._f.tell()
        self._f.seek(t + bytes_to_skip)

    def _check_value(self, fieldname: str, value, check: Callable, text: str):
        if not check(value):
            raise WavFileError("Unexpected value for {} in {}: found {}: {}"
                               .format(fieldname, self._filepath, value, text))

    def _read_int32(self, fieldname: str, expected: Optional[int] = None) -> int:
        b = self._f.read(4)
        n = int.from_bytes(b, byteorder='little')
        if expected is not None and n != expected:
            raise WavFileError("Unexpected value for {} in {}: found {}, expected {}"
                               .format(fieldname, self._filepath, n, expected))
        return n

    def _read_int16(self, fieldname: str, expected: Optional[int] = None) -> int:
        b = self._f.read(2)
        n = int.from_bytes(b, byteorder='little')
        if expected is not None and n != expected:
            raise WavFileError("Unexpected value for {} in {}: found {}, expected {}"
                               .format(fieldname, self._filepath, n, expected))
        return n

    def _read_int8(self, fieldname: str, expected: Optional[int] = None) -> int:
        b = self._f.read(1)
        n = int.from_bytes(b, byteorder='little')
        if expected is not None and n != expected:
            raise WavFileError("Unexpected value for {} in {}: found {}, expected {}"
                               .format(fieldname, self._filepath, n, expected))
        return n

    def _read_text_bytes(self, length, fieldname, expected: Optional[bytes] = None) -> List[bytes]:
        b = self._f.read(length)
        if expected is not None and b != expected:
            raise WavFileError("Unexpected value for {} in {}: found {}, expected {}"
                               .format(fieldname, self._filepath, b, expected))

        return b

    @staticmethod
    def _is_odd(i: int) -> bool:
        return bool(i & 1)

    @staticmethod
    def _find_frame_data(data) -> Tuple[bool, int, int, int]:
        """See if we can find frame data in the audio stream as LSB steganography.
        That means, extract the LSB from each audio sample (first channel) and use
        it to construct 16 bit words of data."""

        # Assume that the supplied data is the start of the audio stream, so the first data
        # value is bit zero of any frame data.
        # TODO: relax that assumption so that we deal with data extracts that don't align 16.

        if len(data.shape) == 1:
            channel_data = data[:]
        else:
            # We take the first channel if there is more than one:
            channel_data = data[:, 0]

        search_range = 1024     # Hope to find a frame start in this range.
        chunk_size = min(search_range, len(channel_data))
        frame_data = LSBSteganography.process(channel_data, chunk_size)

        # Decide if there is frame data. If the data comes direct from the microphone, it
        # will start at the first location. If the data has been messed around with, such as
        # being extracted from the middle of a stream, it may not.
        frame_data_present = False
        frame_len = 0
        frame_data_values = 0
        frame_offset = 0
        for i in range(len(frame_data)):
            if frame_data[i] == LSBSteganography.prefix_value:
                # Take this as the start of frame (though it could be chance).
                frame_data_present = True
                frame_len = frame_data[i + 1]
                frame_data_values = frame_data[i + 2]
                frame_offset = i
                break

        if frame_data_present:
            # There seems to be frame data at offset frame_offset. Double check that by
            # looking one frame ahead to see if we find a prefix value there.
            next_frame_offset = frame_offset + frame_len
            if len(channel_data) > next_frame_offset + chunk_size:
                frame_data = LSBSteganography.process(channel_data[next_frame_offset:], chunk_size)
                if frame_data[0] != LSBSteganography.prefix_value:
                    frame_data_present = False

        return frame_data_present, frame_offset, frame_len, frame_data_values
