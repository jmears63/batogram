import tkinter as tk

from batogram import get_asset_path


class ImageButton(tk.Button):
    _width = 24
    _padding = 5

    def __init__(self, parent, image_file_name: str, command=None):
        # Give the image instance scope to prevent it being garbage collected:
        self._image = self._load_image(image_file_name)
        super().__init__(parent, image=self._image, width=self._width, padx=self._padding, pady=self._padding,
                         relief=tk.RAISED, command=command)

    @staticmethod
    def _load_image(file_name):
        return tk.PhotoImage(file=get_asset_path(file_name))
