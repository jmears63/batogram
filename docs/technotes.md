Technical Notes
---------------

Batogram is implemented in Python 3, and makes heavy use of open source packages numpy and scipy for data processing.
It uses tkinter to provide a cross platform GUI.

Image rendering is implemented as a pipeline of steps:

- Read the data subset from file.
- Do a Fourier transform (FFT).
- Interpolate the FFT data to match the screen resolution.
- Map the resultant values as required by the brightness and contrast settings.
- Map the resulting value to a colour from the colour map.

The result of each step is cached to avoid unnecessary recalculation. For example, if
just the brightness and contrast is changed, only the last two steps are required to rerender
the spectrogram.

The pipeline reads the minimum data from data file required to render
the spectrogram, as determined by the time axis range. This helps to limit the 
memory used to update the UI, allowing larger data files to be processed.

Each graph (spectrogam, profile and amplitude) and pane (main or reference) has its own rendering pipeline, which is executed
in a separate thread. This allows multiple CPUs to share the calculation workload, speeding up rendering.
Note that the infamous Python Global Interpeter Lock (GIL) is released during the heaviest calculations, allowing 
for effective multithreading.
