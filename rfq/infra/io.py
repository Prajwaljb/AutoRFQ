"""File helpers that behave the same on Windows and Linux."""
import os
import re
import tempfile
import time
from pathlib import Path

from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from rfq.config import MAX_CELL_CHARS

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_folder_name(name, limit=80):
    """A folder name Windows accepts: forbidden characters replaced, no trailing dots/spaces, capped."""
    cleaned = _FORBIDDEN.sub("_", name).rstrip(" .")[:limit].rstrip(" .")
    return cleaned or "email"


def clean_text(value):
    """Text that can go into an Excel cell: illegal control characters removed, length capped.

    Returns (text, was_cut).
    """
    text = ILLEGAL_CHARACTERS_RE.sub("", str(value))
    if len(text) > MAX_CELL_CHARS:
        return text[:MAX_CELL_CHARS], True
    return text, False


def write_bytes_atomic(path, data):
    """Writes through a temp file + os.replace, so a reader never sees a half-written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_text_atomic(path, text):
    write_bytes_atomic(path, text.encode("utf-8"))


def save_workbook(wb, path, retries=3, wait=0.7):
    """Saves an openpyxl workbook atomically.

    If the target is locked (open in Excel on Windows), retries, then saves "<name> (2).xlsx" instead.
    Returns the path actually written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    wb.save(tmp)
    for attempt in range(retries):
        try:
            os.replace(tmp, path)
            return path
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(wait)
    alt = path.with_name(f"{path.stem} (2){path.suffix}")
    try:
        os.replace(tmp, alt)
    except PermissionError:
        Path(tmp).unlink(missing_ok=True)
        raise
    return alt
