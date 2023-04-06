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

from typing import NamedTuple
from .common import AxisRange


class Breadcrumb(NamedTuple):
    """A single entry for the breadcrumb service, encapsulating axis ranges."""
    time_range: AxisRange
    frequency_range: AxisRange
    timestamp: float


class BreadcrumbService:
    """This class provides behaviour to support breadcrumb logic, intended to be used for
    the history pans and zooms. It allows the user to move back and forth through a history
    of pans and zooms."""

    def __init__(self):
        self._history = None
        self._current = None
        self.reset()

    def reset(self):
        # print("reset")
        self._history = []
        self._current = None            # Initially we have no history, hence no current position in it.

    def is_previous_available(self) -> bool:
        return len(self._history) > 0 and self._current > 0

    def push_entry(self, entry) -> None:
        # If we are not currently at the end of the history, delete all history
        # beyond this point:
        if self._current is not None:
            delta = len(self._history) - self._current - 1
            if delta > 0:
                self._history = self._history[0:-delta]
            # Add the new entry to the end of the list, and make it current:
            self._current += 1
        else:
            self._current = 0
        self._history.append(entry)
        # print("push {}".format(self._current))

    def previous_entry(self) -> object:
        # print("previous_entry {}".format(self._current))
        if self._current > 0:
            self._current -= 1
            return self._history[self._current]
        else:
            return None

    def is_next_available(self) -> bool:
        ln = len(self._history)
        return ln > 0 and self._current < ln - 1

    def next_entry(self) -> object:
        print("next_entry {}".format(self._current))
        if self._current < len(self._history) - 1:
            self._current += 1
            return self._history[self._current]
        else:
            return None
