import argparse

from . import rootwindow, constants as c
from .constants import PROGRAM_NAME


def run():
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME,
        description='This program displays spectograms from raw audio data.')
    parser.add_argument('datafile', metavar='datafile', nargs='?', help='a .wav file contain raw audio data')
    args = parser.parse_args()

    app = rootwindow.RootWindow(className=c.PROGRAM_NAME, initialfile=args.datafile)
    app.mainloop()


if __name__ == '__main__':
    run()
