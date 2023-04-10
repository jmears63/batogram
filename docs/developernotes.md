Notes for the Developer
=======================

How to Run and Debug
--------------------

Batogram is a Python package, and intended to be run as a package. That means you need the package to be present
somewhere in your PYTHONPATH, and you need to run it like this:

    python3 -m batogram

There are several ways to achieve this. The most obvious is to install the Batogram package using pip, possibly
into a virtual environment. The PYTHONPATH then automatically includes the location where it is installed.
This is not convenient for development though, when you want a copy of the source in your working directory,
and need to make changes and try them out immediately.

Developing from the Commannd Line
---------------------------------

The PYTHONPATH automatically includes the current directory, so you can execute the package *without* installing
it with pip, by checking the complete source out of github, and changing into the src directory:

    git pull git@github.com:jmears63/batogram.git
    cd batogramO
    cd src
    python3 -m batogram
    # Now you can use your favourite editor to edit the source, and re-run:
    kate src/batogram/about.py

Developing using PyCharm
------------------------

I generally do development using [PyCharm](https://www.jetbrains.com/pycharm/). Some things
need to be configured for PyCharm to be able to run and debug from the environment:

* Open a new PyCharm project based on the top level directory - that's the directory that contains README.md.
* We need the src directory to be a source root, so navigate to File | Settings, and expand the node
for the batogram project. Select "src" in the source tree, and make it a source root by clicking on
"Sources", above the source tree. The src folder will turn blue:

![pycharm1.png](pycharm1.png)
* Go to Run | Edit configurations.
  * We need to run the code as a module, not a script, so click on the dropdown near
  the top of the configuration options and change it from "script path" to "Module name", and enter "batogram":
  * We need the src directory to be in the PYTHONPATH, make sure "Add source roots to PYTHONPATH" is ticked
  (checked):

![pycharm.png](pycharm.png)

You can now run and debug the code interactively from PyCharm in the usual way.


