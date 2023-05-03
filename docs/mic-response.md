Microphone Response Correction
==============================

Microphone calibration is important if you want to identify which part of a bat call is the
loudest. Unfortunately microphones commonly used in bat detectors do not have a flat response,
and this may or may not be corrected in the associated electronics and software.

Batogram provides a way for you to apply a frequency response correction if you have suitable
data to use. The data file format needed is outlined below. A file in this format can be specified
in the Settings dialog.

File Format
-----------

Microphone response data should be provided in a comma separate values (CSV) file. This format can be
exported from spreadsheets (Excel, LibreOffice etc), and isn't too hard to create by hand with a
text editor.

Two columns are required: the first should the frequency in Hz, the second should be the microphone
sensitivity in dB at that frequency. So, if you were somehow able to record ideal "white" sound with
a perfectly flat spectrum, and create a spectrum from it in dB, that would be suitable
as a microphone response file. More realistically, you may be able to use the microphone
manufacturer's published data, or even just recorded "noise" (the sound of silence) from your
microphone, to remove banding from background noise.

Batogram will use cubic spline interpolation to convert data points to a smooth curve, and
will use constant extrapolation outside the freqency range provided. The resulting value is
then simply subtracted from the spectrum power depending on frequency.

Here is an example of CSV file contents, with the middle section omitted for brevity: 

```
15000.0, 12.465341458683483 
18000.0, 18.256377064633288
21000.0, 22.821218248161465
24000.0, 24.474815440932932
...
183000.0, -15.120290547916493
186000.0, -14.887572807660924
189000.0, -14.367756998175015
192000.0, -17.102448685052735
```