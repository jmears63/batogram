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

import numpy as np

from scipy.signal import spectrogram
# from timeit import default_timer as timer


def chunky_spectrogram(*args, **kwargs):
    """Scipy's spectrogram calculations uses quite a lot of memory. One reason is because creates *all* the
    segments that will be FFTed, which results in duplication of data depending on the overlap, then
    FFTs as a next step on all of them - rather than pipelining.

    We can manage memory usage by feeding scipy *chunks* of data, which we can concatenate afterwards."""

    # Split the input in chunks which overlap by half the window size.
    # Run fft on them chunk by chunk, appending each chunk to a list of chunks.

    nominal_chunk_len: int = 100000      # Must be at least the window length x several.

    data, = args
    total_len = len(data)

    # If the window is n and the overlap is m:
    #   The first point is at n / 2
    #   Subsequent points have a spacing of n - m
    #
    # Here's what we do:
    #   Round the length of the chunk down, so that ends exactly on a window boundary ( n + k * (n - m)).
    #   Calculate that chunk.
    #   The chunks overlap, with an overlap of window length. The first point is therefore
    #       the same as the last point of the previous chunk, and can be discarded.
    #   etc
    #

    nperseg, noverlap = kwargs['nperseg'], kwargs['noverlap']
    initial_final_step, step = nperseg, nperseg - noverlap
    rounded_chunk_len = int((nominal_chunk_len - initial_final_step) / step) * step + initial_final_step
    del nominal_chunk_len

    # Calculate the total number of resulting data points (windowed segments).
    # The following is the same calculation as scipy uses internally; any incomplete segment
    # at the end is discarded:
    total_segments = int((total_len - noverlap) / (nperseg - noverlap))

    # Preallocate an array for the entire resuts, to avoid endless and expensive
    # concatenation:
    all_spectra = None
    all_times = None
    all_freqs = None

    start, end = 0, 0
    segments_written = 0
    first_segment = True
    previous_time = None
    while end < total_len:
        end = min(start + rounded_chunk_len, total_len)    # Don't overflow the end of the data.
        chunk = data[start:end]
        start += rounded_chunk_len - nperseg

        # Transform this chunk:
        # t1 = timer()
        # The following yields a spectrogam np.single, ie 32 bit floats.
        freqs, times, spectrum = spectrogram(chunk, *args[1:], **kwargs)
        # t2 = timer()
        # print("Spectrogram: {}".format(t2 - t1))
        new_segments = len(times)

        if first_segment:
            all_freqs = freqs    # Note the frequencies from the first response. Subsequent ones are the same.
            all_times = np.zeros(total_segments, dtype=np.single)       # dtype is important for memory conservation.
            all_spectra = np.zeros((len(freqs), total_segments), dtype=np.single)
            segments_to_skip = 0
            previous_time = 0
        else:
            # Other than the first time around, we discard the initial data point
            # as it duplicates the last point of the previous chunk.
            segments_to_skip = 1

        # Adjust the times to follow the correct sequence:
        if not first_segment:
            # Adjust for discarding the first point:
            t0 = times[0]
            times = times[segments_to_skip:] - t0
            # Make the times continue from the previous ones:
            times += previous_time      # Using += avoids a copy of the array.

        # Copy the data into our full results arrays:
        all_times[segments_written:segments_written + new_segments - segments_to_skip] = times[:]
        all_spectra[:, segments_written:segments_written + new_segments - segments_to_skip] = spectrum[:, segments_to_skip:]
        segments_written += new_segments - segments_to_skip

        # We may have reduced times to zero length above.
        if len(times) > 0:
            # Note this for next time around:
            previous_time = times[-1]

        first_segment = False

    return all_freqs, all_times, all_spectra
