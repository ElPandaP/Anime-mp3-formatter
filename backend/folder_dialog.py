import tkinter as tk
from pathlib import Path
from tkinter import filedialog


def pick_folder_dialog(initial_dir=None):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(initialdir=initial_dir or str(Path.home()))
    root.destroy()
    return selected or None
