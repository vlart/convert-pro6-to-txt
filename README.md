# ProPresenter 6 to TXT

A small Python GUI that converts text from ProPresenter 6 `.pro6` presentations into UTF-8 `.txt` files for import into FreeShow. Each source file produces one text file; slides are separated by three newlines.

## Run the GUI

Use Python with Tcl/Tk 8.6 or newer. On macOS, the Apple-supplied Python may use Tcl/Tk 8.5 and open a blank window. Install a recent Python with Tkinter, then run:

```bash
cd /path/to/convert-pro6-to-txt
python3.13 gui_fix.py
```

With Homebrew on macOS, the Tkinter package for Python 3.13 is installed with:

```bash
brew install python-tk@3.13
```

Check which Tk your Python uses:

```bash
python3.13 -c "import tkinter; print(tkinter.TkVersion)"
```

In the app, choose the source folder containing `.pro6` files and the output folder for `.txt` files. Existing output files require confirmation before replacement.

The converter uses only Python's standard library. `fix.py` is an older command-line prototype with hard-coded folder paths.
