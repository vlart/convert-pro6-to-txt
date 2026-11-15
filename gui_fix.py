# Convert ProPresenter 6 presentations to FreeShow text files.

import base64
import binascii
from pathlib import Path
import re
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import xml.etree.ElementTree as ET


SKIPPED_GROUPS = {
    "fonttbl", "colortbl", "expandedcolortbl", "stylesheet", "info",
    "pict", "object", "header", "footer", "headerl", "headerr",
    "footerl", "footerr", "generator", "listtable", "listoverridetable",
}
CONTROL_WORD = re.compile(r"([a-zA-Z]+)(-?\d+)? ?")


def rtf_to_text(data: bytes) -> str:
    # Extract visible text from the RTF used in .pro6 RTFData fields.
    source = data.decode("latin-1")
    codepage_match = re.search(r"\\ansicpg(\d+)", source[:200])
    codepage = f"cp{codepage_match.group(1)}" if codepage_match else "cp1252"
    try:
        "".encode(codepage)
    except LookupError:
        codepage = "cp1252"

    output = []
    stack = [{"hidden": False, "uc": 1}]
    fallback = 0
    i = 0
    while i < len(source):
        char = source[i]
        if char == "{":
            stack.append(stack[-1].copy())
            i += 1
            continue
        if char == "}":
            if len(stack) > 1:
                stack.pop()
            i += 1
            continue
        if char == "\\" and i + 1 < len(source):
            next_char = source[i + 1]
            if next_char in "\\{}":
                if fallback:
                    fallback -= 1
                elif not stack[-1]["hidden"]:
                    output.append(next_char)
                i += 2
                continue
            if next_char == "'" and i + 3 < len(source):
                try:
                    value = bytes.fromhex(source[i + 2:i + 4]).decode(codepage)
                except (ValueError, LookupError, UnicodeError):
                    value = "\ufffd"
                if fallback:
                    fallback -= 1
                elif not stack[-1]["hidden"]:
                    output.append(value)
                i += 4
                continue
            if next_char in "\r\n":
                if not stack[-1]["hidden"]:
                    output.append("\n")
                i += 2
                if next_char == "\r" and i < len(source) and source[i] == "\n":
                    i += 1
                continue
            if next_char == "*":
                stack[-1]["hidden"] = True
                i += 2
                continue
            match = CONTROL_WORD.match(source, i + 1)
            if match:
                word, number = match.group(1), match.group(2)
                i = match.end()
                if word in SKIPPED_GROUPS:
                    stack[-1]["hidden"] = True
                elif word == "uc" and number is not None:
                    stack[-1]["uc"] = max(0, int(number))
                elif word == "u" and number is not None:
                    if not stack[-1]["hidden"]:
                        output.append(chr(int(number) & 0xFFFF))
                    fallback = stack[-1]["uc"]
                elif not stack[-1]["hidden"]:
                    if word in ("par", "line"):
                        output.append("\n")
                    elif word == "tab":
                        output.append("\t")
                continue
            i += 2
            continue
        if fallback:
            fallback -= 1
        elif not stack[-1]["hidden"] and char not in "\r\n":
            output.append(char if ord(char) < 128 else bytes([ord(char)]).decode(codepage, errors="replace"))
        i += 1

    # RTF Unicode escapes are UTF-16 code units; combine surrogate pairs.
    text = "".join(output).encode("utf-16-le", errors="surrogatepass").decode("utf-16-le", errors="replace")
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<=[А-Яа-яЁё])\s*\n\s*(?=[A-Za-z])", "\n-\n", text)
    text = re.sub(r"(?<=[A-Za-z])\s*\n\s*(?=[А-Яа-яЁё])", "\n-\n", text)
    return text


def convert_file(source: Path, destination: Path) -> int:
    # Convert one presentation; return the number of nonempty slides.
    root = ET.parse(source).getroot()
    slides = []
    for slide in root.iter("RVDisplaySlide"):
        parts = []
        for element in slide.iter("NSString"):
            if element.get("rvXMLIvarName") != "RTFData" or not element.text:
                continue
            try:
                raw = base64.b64decode(element.text, validate=True)
            except binascii.Error as exc:
                raise ValueError("Invalid Base64 data in RTFData") from exc
            text = rtf_to_text(raw)
            if text:
                parts.append(text)
        if parts:
            slides.append("\n·\n".join(parts))
    if not slides:
        raise ValueError("No slides with text were found")
    destination.write_text("\n\n\n".join(slides), encoding="utf-8")
    return len(slides)


class ConverterApp:
    TOP_COLOR = (28, 44, 57)
    BOTTOM_COLOR = (23, 61, 73)
    CARD_COLOR = "#263b4a"
    TEXT_COLOR = "#f2f7f8"
    MUTED_COLOR = "#b4c8cf"
    FIELD_COLOR = "#172c38"

    def __init__(self, root):
        self.root = root
        root.title("ProPresenter 6 to TXT")
        root.geometry("760x570")
        root.resizable(False, False)

        self.background = tk.Canvas(root, bg="#1c2c39", highlightthickness=0)
        self.background.pack(fill="both", expand=True)
        self.background.bind("<Configure>", self.draw_gradient)

        header = tk.Frame(root, bg="#1c2c39")
        header.place(x=40, y=30, width=680, height=88)
        tk.Label(
            header, text="ProPresenter 6  →  TXT", bg="#1c2c39",
            fg=self.TEXT_COLOR, font=("Helvetica Neue", 25, "bold"), anchor="w",
        ).place(x=0, y=0, width=680, height=44)
        tk.Label(
            header, text="Convert presentations into text files for FreeShow",
            bg="#1c2c39", fg=self.MUTED_COLOR,
            font=("Helvetica Neue", 12), anchor="w",
        ).place(x=1, y=46, width=679, height=26)

        card = tk.Frame(
            root, bg=self.CARD_COLOR, highlightthickness=1,
            highlightbackground="#45606c",
        )
        card.place(x=40, y=139, width=680, height=290)
        self.src_entry = self.add_folder_field(
            card, 20, "1  SOURCE FOLDER", "Folder containing your original .pro6 files"
        )
        tk.Frame(card, bg="#45606c").place(x=28, y=143, width=624, height=1)
        self.dst_entry = self.add_folder_field(
            card, 158, "2  OUTPUT FOLDER", "Folder where new .txt files will be saved"
        )

        self.make_button(
            root, "Convert files", 40, 458, 205, 48,
            "#24877b", "#30a193", self.start_conversion,
        )
        self.make_button(
            root, "Reset", 258, 458, 115, 48,
            "#3c5866", "#4d6b79", self.reset,
        )
        self.status_label = tk.Label(
            root, text="Ready to convert .pro6 files", bg="#173d49",
            fg=self.MUTED_COLOR, font=("Helvetica Neue", 11), anchor="w",
        )
        self.status_label.place(x=40, y=525, width=680, height=25)
        root.after_idle(self.draw_gradient)

    def draw_gradient(self, _event=None):
        canvas = self.background
        canvas.delete("gradient")
        height = max(canvas.winfo_height(), 1)
        width = max(canvas.winfo_width(), 1)
        for y in range(height):
            fraction = y / max(height - 1, 1)
            color = tuple(
                round(top + (bottom - top) * fraction)
                for top, bottom in zip(self.TOP_COLOR, self.BOTTOM_COLOR)
            )
            canvas.create_line(
                0, y, width, y, fill="#{:02x}{:02x}{:02x}".format(*color),
                tags="gradient",
            )

    def add_folder_field(self, parent, top, title, description):
        tk.Label(
            parent, text=title, bg=self.CARD_COLOR, fg=self.TEXT_COLOR,
            font=("Helvetica Neue", 12, "bold"), anchor="w",
        ).place(x=28, y=top, width=624, height=26)
        tk.Label(
            parent, text=description, bg=self.CARD_COLOR, fg=self.MUTED_COLOR,
            font=("Helvetica Neue", 11), anchor="w",
        ).place(x=28, y=top + 27, width=624, height=22)
        entry = tk.Entry(
            parent, bg=self.FIELD_COLOR, fg=self.TEXT_COLOR,
            insertbackground=self.TEXT_COLOR, font=("Helvetica Neue", 12),
            relief="flat", borderwidth=0, highlightthickness=0,
        )
        entry.place(x=32, y=top + 63, width=474, height=40)
        self.make_button(
            parent, "Browse…", 522, top + 62, 128, 42,
            "#3c6570", "#4e7a84", lambda: self.browse(entry),
        )
        return entry

    def make_button(self, parent, text, x, y, width, height, color, hover, command):
        button = tk.Label(
            parent, text=text, bg=color, fg=self.TEXT_COLOR,
            font=("Helvetica Neue", 12, "bold"), cursor="hand2",
        )
        button.place(x=x, y=y, width=width, height=height)
        button.bind("<Button-1>", lambda _event: command())
        button.bind("<Enter>", lambda _event: button.configure(bg=hover))
        button.bind("<Leave>", lambda _event: button.configure(bg=color))
        return button

    def set_status(self, text):
        self.status_label.configure(text=text)

    def browse(self, entry):
        path = filedialog.askdirectory(parent=self.root)
        if path:
            entry.delete(0, tk.END)
            entry.insert(0, path)
            self.set_status("Folders selected. Ready to convert.")

    def reset(self):
        self.src_entry.delete(0, tk.END)
        self.dst_entry.delete(0, tk.END)
        self.set_status("Ready to convert .pro6 files")

    def start_conversion(self):
        source_text = self.src_entry.get().strip()
        destination_text = self.dst_entry.get().strip()
        if not source_text or not destination_text:
            messagebox.showwarning(
                "Folders required", "Select both the source and output folders.", parent=self.root
            )
            return
        source = Path(source_text).expanduser()
        destination = Path(destination_text).expanduser()
        if not source.is_dir() or not destination.is_dir():
            messagebox.showerror(
                "Invalid folder", "Check that both folders exist and can be opened.", parent=self.root
            )
            return
        try:
            files = sorted(
                path for path in source.iterdir()
                if path.is_file() and path.suffix.lower() == ".pro6"
            )
        except OSError as exc:
            messagebox.showerror("Cannot open folder", str(exc), parent=self.root)
            return
        if not files:
            messagebox.showwarning(
                "No files found", "The source folder contains no .pro6 files.", parent=self.root
            )
            return
        existing = [path for path in files if (destination / path.with_suffix(".txt").name).exists()]
        if existing and not messagebox.askyesno(
            "Replace existing files",
            f"{len(existing)} .txt file(s) already exist in the output folder. Replace them?",
            parent=self.root,
        ):
            return

        self.set_status(f"Converting {len(files)} file(s)…")
        self.root.update_idletasks()
        converted = 0
        errors = []
        for path in files:
            try:
                convert_file(path, destination / path.with_suffix(".txt").name)
                converted += 1
            except (OSError, ET.ParseError, ValueError) as exc:
                errors.append(f"{path.name}: {exc}")
        summary = f"Converted {converted} of {len(files)} file(s)."
        self.set_status(summary)
        if errors:
            summary += "\n\nErrors:\n" + "\n".join(errors[:8])
            if len(errors) > 8:
                summary += f"\n…and {len(errors) - 8} more."
            messagebox.showwarning("Conversion finished", summary, parent=self.root)
        else:
            messagebox.showinfo("Conversion finished", summary, parent=self.root)


if __name__ == "__main__":
    if sys.platform == "darwin" and tk.TkVersion < 8.6:
        raise SystemExit(
            "The system Tcl/Tk 8.5 cannot display this interface on macOS. "
            "Run it with a Python build using Tcl/Tk 8.6 or newer "
            "(for example: python3.13 gui_fix.py)."
        )
    root = tk.Tk()
    ConverterApp(root)
    root.mainloop()
