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

### Linux

On Linux, Batogram is currently installed from the command line using pip, as below.
You need to have Python 3.10 as a minimum.  

    # Create a virtual environment at a convenient location in your home directory:
    mkdir ~/batogram
    cd batogram
    python3 -m venv venv
    source venv/bin/activate

    # It's good practice to have pip up to date:
    pip install pip --upgrade

    # Install batogram and its dependencies. This may take a few moments.
    # Obviously, substitute the lastest and greatest version number:
    pip install batogram-x.y.z.tar.gz
    
    # Batogram is now in PATH. You can run it with this simple command:
    batogram

### Windows
For now, Batogram is installed onto windows using the following slightly convoluted
steps. At some point in the future, I will provide a simpler install.

This sequence assumes Windows 11.

* Launch the Microsoft Store. You can do this from the Start menu - search for Microsoft Store,
and launch it.
* In the store, search for Python using the upper right menu. Select a version which is
at least 3.10 - probably, the most recent version. I used version 3.11.
* Go ahead and install it.
* Open a windows command prompt - for example, by searching for cmd from the start menu. 

In the command prompt, enter this command to install Batogram and its dependencies, which
may take a few moments:

    pip install batogram

The install command will finish by displaying a path to batogram.exe. You may wish to copy
that file to your desktop for convenient launching. Otherwise, you can launch
Batogram from the command prompt:

    python -m batogram

Subsequently you can launch Batogram using that command in the command prompt, or by double
clicking on batogram.exe on your desktop, if you copied it there in the previous step.

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

Credits
-------

In no particular order:
* [Pictogrammers Team](https://www.iconarchive.com/show/material-icons-by-pictogrammers/bat-icon.html)
* [Tucker Beck](https://code.activestate.com/recipes/576688-tooltip-for-tkinter/)
* [Remix Icon](https://remixicon.com/)
* [Kenneth Moreland](https://www.kennethmoreland.com/color-advice/)
* [David A. Riggs](https://github.com/riggsd/guano-py/blob/master/guano.py)

About the Author
----------------

I am John Mears. I obtained a degree in physics in the University of Oxford
in the distant past. I have spent much of the last 40 years writing software
relating to scientific and email seccurity applications. In my spare time I cycle,
play double bass in local amateur orchestras, 
and [wander around at dusk](https://fitzharrys.wordpress.com/) with a bat detector of
my own design.

