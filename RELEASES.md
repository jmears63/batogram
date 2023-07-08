### Release 1.0.10
* Added multichannel options.
* Added support for reassignment spectrograms for increased resolution.
* Added support for window padding for increase frequency resolution.
* Made guano parsing more tolerant of unexpected data and types.
* Fixed a regression so that the sampling rate in the guano metadata overrides the one in the .wav file header.

### Release 1.0.9
* Added support for manually placed time and frequency markers to read spans off the graph.
* Resizing of main window is now more responsive, especially on Windows.

### Release 1.0.7
Various minor improvements and fixes:
* Microphone frequency response can corrected by providing a CSV calibration file.   
* Batogram is now compatible with Python 3.9 (previously 3.10 was required).
* Up/down keys now select one of a predefined set of time scales (1,2,5,10,20,50 etc ms).
* Other small improvements and fixes.

### Release 1.0.6
Various minor improvements and fixes:
* Panning and scrolling using arrow keys and page up/down keys, with shift.
* A setting for zero based time axis.
* Axis units are now responsive to the range (s versus ms).
* Minor fixes to calculations so the spectrogram fits the available area better.
* More intuitive mouse dragging operations.
* Application level settings modal, with persistent settings.
* Selection of colour maps.
* Added developer notes and this file.
* Moved to a flatter directory layout that simplifies development and packaging, added a top level runner script.
* Other minor tweaks and fixes.