from . import rootwindow, constants as c


def run():
    app = rootwindow.RootWindow(className=c.PROGRAM_NAME)
    app.mainloop()


if __name__ == '__main__':
    run()
