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

PROGRAM_NAME = "Batogram"
DATA_CHANGE_MAIN_EVENT = "<<OnDataChangeMain>>"  # Underlying data has change: for example, a file opened or closed.
DATA_CHANGE_REF_EVENT = "<<OnDataChangeRef>>"  # Underlying data has change: for example, a file opened or closed.
MAIN_SPECTROGAM_COMPLETER_EVENT = "<<MainSpectrogramCompleter>>"
MAIN_AMPLITUDE_COMPLETER_EVENT = "<<MainAmplitudeCompleter>>"
MAIN_PROFILE_COMPLETER_EVENT = "<<MainProfileCompleter>>"
FONT_SIZE = 12
ZOOM_ORDER = 2  # This will move into settings. 0-2 is a useful range.
COLOUR_MAPS_PATH = "colour_maps"
ASSETS_PATH = "assets"

# Limit how far they can zoom in:
MIN_F_RANGE: float = 500
MIN_T_RANGE: float = 0.001
