"""Convert ProPresenter 6 presentations to FreeShow text files."""

import base64
import binascii
from pathlib import Path
import re
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
    """Extract visible text from the RTF used in .pro6 RTFData fields."""
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
    """Convert one presentation; return the number of nonempty slides."""
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
    WIDTH = 760
    HEIGHT = 570
    TOP_COLOR = (29, 43, 56)
    BOTTOM_COLOR = (17, 49, 60)
    CARD_COLOR = "#253847"
    TEXT_COLOR = "#f0f6f8"
    MUTED_COLOR = "#a9bdc7"
    ACCENT_COLOR = "#54cdbb"

    def __init__(self, root):
        self.root = root
        root.title("ProPresenter 6 to TXT")
        root.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        root.minsize(620, 570)

        self.canvas = tk.Canvas(root, highlightthickness=0, borderwidth=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self.draw_interface)

        entry_style = {
            "bg": "#192b39",
            "fg": self.TEXT_COLOR,
            "insertbackground": self.TEXT_COLOR,
            "relief": "flat",
            "borderwidth": 0,
            "highlightthickness": 0,
            "font": ("Helvetica Neue", 12),
        }
        self.src_entry = tk.Entry(self.canvas, **entry_style)
        self.dst_entry = tk.Entry(self.canvas, **entry_style)
        self.status = "Ready to convert .pro6 files"

    @staticmethod
    def rounded_rectangle(canvas, x1, y1, x2, y2, radius, fill, tag=None):
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1,
            x2, y1 + radius, x2, y2 - radius, x2, y2,
            x2 - radius, y2, x1 + radius, y2, x1, y2,
            x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        return canvas.create_polygon(
            points, smooth=True, splinesteps=24, fill=fill, outline="", tags=tag
        )

    def draw_button(self, x1, y1, x2, y2, label, fill, hover, command, tag):
        shape = self.rounded_rectangle(self.canvas, x1, y1, x2, y2, 12, fill, tag)
        self.canvas.create_text(
            (x1 + x2) / 2, (y1 + y2) / 2, text=label,
            fill=self.TEXT_COLOR, font=("Helvetica Neue", 12, "bold"), tags=tag,
        )
        self.canvas.tag_bind(tag, "<Button-1>", lambda _event: command())
        self.canvas.tag_bind(tag, "<Enter>", lambda _event: self.button_hover(shape, hover))
        self.canvas.tag_bind(tag, "<Leave>", lambda _event: self.button_hover(shape, fill))

    def button_hover(self, shape, color):
        self.canvas.itemconfigure(shape, fill=color)

    def draw_interface(self, _event=None):
        canvas = self.canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 620)
        height = max(canvas.winfo_height(), self.HEIGHT)
        for y in range(height):
            fraction = y / max(height - 1, 1)
            color = tuple(
                round(top + (bottom - top) * fraction)
                for top, bottom in zip(self.TOP_COLOR, self.BOTTOM_COLOR)
            )
            canvas.create_line(0, y, width, y, fill="#{:02x}{:02x}{:02x}".format(*color))

        left = (width - min(680, width - 48)) / 2
        right = width - left
        canvas.create_text(
            width / 2, 58, text="ProPresenter 6  →  TXT",
            fill=self.TEXT_COLOR, font=("Helvetica Neue", 27, "bold"),
        )
        canvas.create_text(
            width / 2, 96, text="Convert presentations into text files for FreeShow",
            fill=self.MUTED_COLOR, font=("Helvetica Neue", 12),
        )
        self.rounded_rectangle(canvas, left, 138, right, 430, 22, self.CARD_COLOR)

        self.draw_folder_row(
            left, right, 175, "1", "SOURCE FOLDER", "Your original .pro6 files",
            self.src_entry, lambda: self.browse(self.src_entry), "browse_source",
        )
        canvas.create_line(left + 34, 279, right - 34, 279, fill="#3b5360")
        self.draw_folder_row(
            left, right, 304, "2", "OUTPUT FOLDER", "Where the new .txt files will be saved",
            self.dst_entry, lambda: self.browse(self.dst_entry), "browse_output",
        )

        self.draw_button(
            left, 458, left + 210, 506, "Convert files", "#237b72", "#2b9689",
            self.start_conversion, "convert_button",
        )
        self.draw_button(
            left + 224, 458, left + 352, 506, "Reset", "#394e5b", "#4b6471",
            self.reset, "reset_button",
        )
        self.status_item = canvas.create_text(
            left, 538, anchor="w", text=self.status,
            fill=self.MUTED_COLOR, font=("Helvetica Neue", 11),
        )

    def draw_folder_row(self, left, right, top, number, title, subtitle, entry, browse, tag):
        canvas = self.canvas
        canvas.create_oval(
            left + 33, top, left + 61, top + 28,
            fill="#2a6f6c", outline="",
        )
        canvas.create_text(
            left + 47, top + 14, text=number,
            fill=self.TEXT_COLOR, font=("Helvetica Neue", 11, "bold"),
        )
        canvas.create_text(
            left + 75, top + 6, anchor="nw", text=title,
            fill=self.TEXT_COLOR, font=("Helvetica Neue", 12, "bold"),
        )
        canvas.create_text(
            left + 75, top + 29, anchor="nw", text=subtitle,
            fill=self.MUTED_COLOR, font=("Helvetica Neue", 11),
        )
        field_left = left + 34
        field_top = top + 67
        button_left = right - 145
        self.rounded_rectangle(
            canvas, field_left, field_top, button_left - 12, field_top + 42,
            10, "#192b39",
        )
        canvas.create_window(
            field_left + 15, field_top + 21, window=entry, anchor="w",
            width=button_left - field_left - 43, height=29,
        )
        self.draw_button(
            button_left, field_top, right - 34, field_top + 42,
            "Browse…", "#3a5a68", "#4c7180", browse, tag,
        )

    def set_status(self, text):
        self.status = text
        if hasattr(self, "status_item"):
            self.canvas.itemconfigure(self.status_item, text=text)

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
    root = tk.Tk()
    ConverterApp(root)
    root.mainloop()
