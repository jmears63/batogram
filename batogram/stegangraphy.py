import numbers
from typing import List, Optional

import numpy as np


class LSBSteganography:
    """Use this class for extracting data from a raw data stream, where additional int16 data is encoded
    as the LSB of the raw data."""

    def __init__(self):
        pass

    @staticmethod
    def process(raw_data: np.ndarray, length: Optional[int] = None) -> np.ndarray:
        """Extract LSB encoded data from the single column array of raw integer data provided."""

        # The raw data must be some kind of integer:
        if not np.issubdtype(raw_data.dtype, np.integer):
            return np.zeros(0, dtype=np.int16)

        raw_length = len(raw_data)
        if length is None:
            length = raw_length
        length = min(length, raw_length)
        short_zero = np.int16(0)  # Appease the type checker.

        decoded_length: int = int(length / 16)
        decoded_data = np.zeros(decoded_length, dtype=np.int16)
        bit = 0
        value: np.int16 = short_zero
        j = 0
        for i in range(length):
            raw_value: np.int16 = raw_data[i]
            lsb = raw_value & 1
            value |= lsb << bit
            bit += 1
            if bit == 16:
                decoded_data[j] = value
                j += 1
                value = short_zero
                bit = 0

        return decoded_data
