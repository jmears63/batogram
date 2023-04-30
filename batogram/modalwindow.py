import tkinter as tk


class ModalWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)

        # Find the highest level parent window we can:
        ancestor = parent
        while ancestor.master:
            ancestor = ancestor.master

        # Don't prescribe the size, let the window adjust to its contents:
        # self.geometry("+{}+{}".format(
        #     ref.winfo_rootx() + (ref.winfo_width()) // 2,
        #     ref.winfo_rooty() + (ref.winfo_height()) // 2))
        # TODO: figure out how to centre without a flicker as we move it:
        self.geometry("+{}+{}".format(
            ancestor.winfo_rootx() + 100,
            ancestor.winfo_rooty() + 100))

        # self.geometry("{}x{}+{}+{}".format(
        #     width, height,
        #     ref.winfo_rootx() + (ref.winfo_width() - width) // 2,
        #     ref.winfo_rooty() + (ref.winfo_height() - height) // 2))

        # self.update_idletasks()
        # bbox = self.grid_bbox()
        # pass

    def on_cancel(self):
        self.destroy()

    def on_ok(self):
        self.destroy()

