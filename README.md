batogram
========

Batogram is an open source application for viewing bat calls spectrograms.

Some capabilities and features: 
* Rendering of spectrograms from .wav files.
* Auto selection of many parameters for simple operation.
* Efficient rendering with graceful handling of larger data files.
* Pan and scale using the mouse or by manual selection.
* Handling of multichannel data files, including stereo.
* Basic side by side comparison of two spectrograms.
* Display of GUANO metadata, including the ability to click to open the location in Google Maps.
* Runs on Windows, macOS and Linux operating systems.

Installation
------------
Batogram is currently installed from the command line using pip, as follows. 

    # Create a virtual environment at a convenient location in your home directory:
    mkdir ~/batogram
    cd batogram
    python3 -m venv venv
    source venv/bin/activate

    # Install batogram and its dependencies. This may take a few moments:
    pip install batogram-x.y.z.tar.gz
    
    # Run batogram:
    batogram

Usage
-----

Refer to files in the docs directory for more information. In particular, see
[batogram.md](docs/batogram.md) for usage notes.

Licence
-------

This project is licensed under the MIT License - see the LICENSE file for details.

Contributing
------------

I welcome bug reports, and requests for minor improvements and major new features.
Please submit these via github. I will prioritize them and get to them when I can.

I also welcome sample .wav files containing representative bat calls of different species.
My hope this that this will grow into a useful collection of reference calls for comparison.

For the moment, while the structure of the code is fairly rapid flux, so I am not accepting
pull requests other than for small fixes. This may change in the future.

About the Author
----------------

I am John Mears. I obtained a degree in physics in the University of Oxford
in the distant past. I have spent much of the last 40 years writing software
relating to scientific and email seccurity applications. In my spare time I cycle,
play double bass in local amateur orchestras, 
and [wander around at dusk](https://fitzharrys.wordpress.com/) with a bat detector of
my own design.

