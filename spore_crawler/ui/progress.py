"""
progress.py - Real-time progress display with spinner, fixed bottom-row rendering.

Depends on: None (leaf module)
Used by: cli/commands/_common, cli/commands/search, cli/commands/sporecast,
         cli/commands/crawl, crawlers/hotkeys, cli_ui
"""
import os
import sys
import threading


def _get_console_height():
    """Get console window height via Windows API."""
    if os.name != 'nt':
        return 25
    import ctypes

    class COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    class SMALL_RECT(ctypes.Structure):
        _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                    ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

    class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
        _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD),
                    ("wAttributes", ctypes.c_ushort), ("srWindow", SMALL_RECT),
                    ("dwMaximumSize", COORD)]

    csbi = CONSOLE_SCREEN_BUFFER_INFO()
    ctypes.windll.kernel32.GetConsoleScreenBufferInfo(
        ctypes.windll.kernel32.GetStdHandle(-11), ctypes.byref(csbi)
    )
    return csbi.srWindow.Bottom - csbi.srWindow.Top + 1


def _get_console_width():
    """Get console window width via Windows API."""
    if os.name != 'nt':
        return 80
    import ctypes

    class COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    class SMALL_RECT(ctypes.Structure):
        _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                    ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

    class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
        _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD),
                    ("wAttributes", ctypes.c_ushort), ("srWindow", SMALL_RECT),
                    ("dwMaximumSize", COORD)]

    csbi = CONSOLE_SCREEN_BUFFER_INFO()
    ctypes.windll.kernel32.GetConsoleScreenBufferInfo(
        ctypes.windll.kernel32.GetStdHandle(-11), ctypes.byref(csbi)
    )
    return csbi.srWindow.Right - csbi.srWindow.Left + 1


def _move_cursor_to(row: int):
    """Move console cursor to a specific row (0-indexed)."""
    if os.name != 'nt':
        return
    import ctypes

    class COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    handle = ctypes.windll.kernel32.GetStdHandle(-11)
    ctypes.windll.kernel32.SetConsoleCursorPosition(handle, COORD(0, row))


# ANSI codes for colors
_RESET = "\033[0m"
_FG_YELLOW = "\033[38;2;255;255;0m"
_FG_GREEN = "\033[38;2;0;255;0m"
_FG_RED = "\033[38;2;255;0;0m"
_FG_CYAN = "\033[38;2;0;255;255m"
_FG_GRAY = "\033[38;2;128;128;128m"
_FG_END = "\033[38;2;176;190;197m"  # End message color (RGB 176,190,197)

# Background color (16-color palette slot 6 = dark purple, must match cli_ui.py)
_BG_DARK_BLUE = "\033[43m"


class Spinner:
    """Cycling animation: / - \\ |"""
    FRAMES = ['/', '-', '\\', '|']

    def __init__(self):
        self._index = 0
        self._lock = threading.Lock()

    def next(self) -> str:
        with self._lock:
            frame = self.FRAMES[self._index % len(self.FRAMES)]
            self._index += 1
            return frame

    def reset(self):
        with self._lock:
            self._index = 0


class ProgressDisplay:
    """Real-time progress display fixed at bottom of console.

    Layout (bottom 6 rows):
      row height-6: scroll area
      row height-5: progress line
      row height-4: hotkeys hint
      row height-3..1: (empty/spare)
    """

    STATUS_RUNNING = "running"
    STATUS_PAUSED = "paused"
    STATUS_STOPPED = "stopped"

    def __init__(self):
        self.spinner = Spinner()
        self.status = self.STATUS_RUNNING
        self.current_view = ""
        self.current_type = ""
        self.downloaded = 0
        self.skipped = 0
        self.failed = 0
        self.bytes = 0.0
        self.category_bytes = 0.0
        self.page = 0
        self._lock = threading.Lock()
        self._render_disabled = False  # Prevent rendering after stop

    def disable_rendering(self):
        """Disable further progress rendering (call on stop)."""
        with self._lock:
            self._render_disabled = True

    def _get_progress_row(self):
        """Row index for the progress line."""
        return _get_console_height() - 3

    def _get_hotkeys_row(self):
        """Row index for the hotkeys hint."""
        return _get_console_height() - 2

    def update_progress(self, downloaded: int = 0, skipped: int = 0, failed: int = 0, bytes: float = 0.0, page: int = 0, category_bytes: float = 0.0):
        """Update progress counters."""
        with self._lock:
            self.downloaded = downloaded
            self.skipped = skipped
            self.failed = failed
            self.bytes = bytes
            self.page = page
            self.category_bytes = category_bytes

    def set_status(self, status: str):
        """Set status to running/paused/stopped."""
        with self._lock:
            self.status = status

    def render_progress(self):
        """Render progress line fixed at bottom of console."""
        with self._lock:
            if self._render_disabled:
                return

            row = self._get_progress_row()
            _move_cursor_to(row)

            if self.status == self.STATUS_RUNNING:
                symbol = f"[{self.spinner.next()}]"
                color = _FG_YELLOW
            elif self.status == self.STATUS_PAUSED:
                symbol = "[PAUSED]"
                color = _FG_CYAN
            elif self.status == self.STATUS_STOPPED:
                symbol = "[STOPPING]"
                color = _FG_RED
            else:
                symbol = "[...]"
                color = _FG_YELLOW

            mb = self.bytes / 1024 / 1024
            cat_label = f"[{self.current_view}_{self.current_type}]" if self.current_view and self.current_type else ""

            # Build line - no extra padding after symbol
            line = f"{symbol} Page: {self.page} | Downloaded: {self.downloaded} | Skipped: {self.skipped} | Failed: {self.failed} | {mb:.1f} MB | {cat_label}"

            # Pad to full width to clear old content
            width = _get_console_width()
            line = line[:width].ljust(width)

            # Write with background + foreground
            sys.stdout.write(f"\r{_BG_DARK_BLUE}{color}{line}{_RESET}")
            sys.stdout.flush()

    def clear_line(self):
        """Clear the progress line area."""
        with self._lock:
            row = self._get_progress_row()
            _move_cursor_to(row)
            width = _get_console_width()
            sys.stdout.write(f"\r{_BG_DARK_BLUE}{' ' * width}{_RESET}")
            sys.stdout.flush()

    def clear_hotkeys_row(self):
        """Clear the hotkeys hint row."""
        row = self._get_hotkeys_row()
        _move_cursor_to(row)
        width = _get_console_width()
        sys.stdout.write(f"\r{_BG_DARK_BLUE}{' ' * width}{_RESET}")
        sys.stdout.flush()


def print_hotkeys_hint():
    """Print hotkeys hint at the bottom row of the console."""
    height = _get_console_height()
    hint_row = height - 2
    _move_cursor_to(hint_row)
    width = _get_console_width()
    hint = "                  [P] PAUSE                             [R] RESUME                            [X] STOP"
    hint = hint[:width].ljust(width)
    _FG_WHITE = "\033[97m"
    sys.stdout.write(f"{_BG_DARK_BLUE}{_FG_WHITE}{hint}{_RESET}")
    sys.stdout.flush()


_scroll_cursor = 0  # Tracks current scroll row offset


def scroll_print(text: str, fg: str = None):
    """Print text in the scroll area, stacking with each call.

    First call starts at height-6, subsequent calls go down.
    Includes background color so text renders on purple.
    Default color is FG_END (RGB 176,190,197) for end messages.
    """
    global _scroll_cursor
    height = _get_console_height()

    # Reset cursor on first call (after clear_bottom_area resets it)
    if _scroll_cursor == 0:
        _scroll_cursor = height - 6

    _move_cursor_to(_scroll_cursor)

    width = _get_console_width()
    # Write with background + foreground
    color = fg if fg else _FG_END
    padded = text[:width].ljust(width)
    sys.stdout.write(f"{_BG_DARK_BLUE}{color}{padded}{_RESET}")
    sys.stdout.flush()

    _scroll_cursor += 1


def reset_scroll_cursor():
    """Reset scroll cursor to start position."""
    global _scroll_cursor
    _scroll_cursor = 0


def clear_scroll_row():
    """Clear the scroll row."""
    height = _get_console_height()
    scroll_row = height - 6
    _move_cursor_to(scroll_row)
    width = _get_console_width()
    sys.stdout.write(f"\r{_BG_DARK_BLUE}{' ' * width}{_RESET}")
    sys.stdout.flush()


def clear_bottom_area():
    """Clear progress line, hotkeys hint, and scroll row. Reset scroll cursor."""
    global _scroll_cursor
    _scroll_cursor = 0
    width = _get_console_width()
    empty = f"\r{_BG_DARK_BLUE}{' ' * width}{_RESET}"
    height = _get_console_height()
    for row in range(height - 5, height):
        _move_cursor_to(row)
        sys.stdout.write(empty)
    sys.stdout.flush()


def clear_progress_display():
    """Clear just the progress line and hotkeys hint rows (2 rows at h-3, h-2)."""
    height = _get_console_height()
    width = _get_console_width()
    for row in (height - 3, height - 2):
        _move_cursor_to(row)
        sys.stdout.write(f"{_BG_DARK_BLUE}{' ' * width}{_RESET}")
    sys.stdout.flush()


def print_results(lines, fg=None):
    """Print end results after crawl, using explicit cursor positioning (no \\n).

    Writes each result line at the next available row -- continuing after any
    scroll_print messages, or at h-5 (right above the hint/progress bar area)
    if there were none. Does NOT clear the progress bar -- its last state
    stays visible.
    """
    global _scroll_cursor

    height = _get_console_height()
    width = _get_console_width()
    color = fg if fg else _FG_END

    if _scroll_cursor > 0:
        start_row = _scroll_cursor
    else:
        start_row = height - 5

    for i, line in enumerate(lines):
        row = start_row + i
        if row >= height - 3:
            break
        _move_cursor_to(row)
        padded = line[:width].ljust(width)
        sys.stdout.write(f"{_BG_DARK_BLUE}{color}{padded}{_RESET}")

    next_row = min(start_row + len(lines), height - 1)
    _move_cursor_to(next_row)
    sys.stdout.flush()
