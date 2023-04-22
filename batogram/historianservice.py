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

import os.path


class HistorianService:
    """The historian service maintains a list of recently opened data files."""

    _MAX_ENTRIES = 5

    def __init__(self):
        self._history = []

    def add_file(self, path):
        self._history.append(path)

        # Dedupe while preserving order, O(n^2). Reverse so the most recent is kept when there are dupes.
        new_list = []
        for item in reversed(self._history):
            if item not in new_list:
                new_list.append(item)
        self._history = [f for f in reversed(new_list)]

        # Limit the history we store using LRU:
        ln = len(self._history)
        if ln > self._MAX_ENTRIES:
            self._history = self._history[ln - self._MAX_ENTRIES:ln]

    def get_history(self):
        """Get a list of the history with MRU first, in tuples of full path, filename"""
        return [(os.path.basename(p), p) for p in reversed(self._history)]

    def is_empty(self):
        return len(self._history) > 0
