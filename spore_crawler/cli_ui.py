"""
cli_ui.py - CLI visual elements: screen clearing, banner, Win32 palette theming, logging.

Depends on: ui/progress (_move_cursor_to, _get_console_height),
            cli/utilities (get_resource_dir, lazy in print_banner)
Used by: cli/__init__, cli/commands/login, cli/commands/search, cli/commands/bean
"""
import os
import sys
import time
import logging
import threading
from pathlib import Path

_last_size = (0, 0)
_resize_lock = threading.Lock()

# ANSI escape code for 16-color SGR: \033[<code>m
# Reset colors: \033[0m
ANSI_RESET = "\033[0m"
BG_THEME = "\033[43m"           # Background: slot 6 (theme dark purple in default CMD palette)

# Foreground colors (16-color SGR)
FG_YELLOW = "\033[93m"          # Slot 14: Yellow (default text)
FG_GREEN = "\033[92m"           # Slot 10: Bright Green
FG_RED = "\033[91m"             # Slot 12: Bright Red
FG_CYAN = "\033[96m"            # Slot 11: Bright Cyan
FG_WHITE = "\033[97m"           # Slot 15: Bright White
FG_GRAY = "\033[90m"            # Slot 8: Dark Gray


def clear_screen():
    """Clear console screen using direct Win32 API (avoids spawning cmd.exe)."""
    if os.name == 'nt':
        try:
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

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            csbi = CONSOLE_SCREEN_BUFFER_INFO()
            kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi))

            # Wipe the entire scroll buffer, not just the visible window, so no
            # prior history is visible when the user scrolls after launch.
            bufsize = csbi.dwSize.X * csbi.dwSize.Y

            kernel32.FillConsoleOutputCharacterW(handle, ord(' '), bufsize, COORD(0, 0), ctypes.byref(ctypes.c_ulong()))
            kernel32.FillConsoleOutputAttribute(handle, 0x07, bufsize, COORD(0, 0), ctypes.byref(ctypes.c_ulong()))
            kernel32.SetConsoleCursorPosition(handle, COORD(0, 0))
        except Exception:
            import sys
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.flush()
    else:
        import sys
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def enable_ansi():
    """Enable ANSI escape codes on Windows 10+."""
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def init_palette():
    """Remap palette slot 6 to dark purple RGB(19,22,52) so \\033[43m renders correctly."""
    if os.name != 'nt':
        return
    try:
        import ctypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                        ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

        class CONSOLE_SCREEN_BUFFER_INFO_EX(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("dwSize", COORD),
                ("dwCursorPosition", COORD),
                ("wAttributes", ctypes.c_ushort),
                ("srWindow", SMALL_RECT),
                ("dwMaximumSize", COORD),
                ("wPopupAttributes", ctypes.c_ushort),
                ("bFullscreenSupported", ctypes.c_bool),
                ("ColorTable", ctypes.c_ulong * 16),
            ]

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)

        csbiex = CONSOLE_SCREEN_BUFFER_INFO_EX()
        csbiex.cbSize = ctypes.sizeof(csbiex)
        kernel32.GetConsoleScreenBufferInfoEx(handle, ctypes.byref(csbiex))

        # Remap palette slot 6 to RGB(19,22,52)
        # COLORREF is BGR: 0x00BBGGRR
        csbiex.ColorTable[6] = 19 | (22 << 8) | (52 << 16)

        # Windows bug workaround: SetConsoleScreenBufferInfoEx treats srWindow.Bottom
        # as exclusive, but GetConsoleScreenBufferInfoEx returns it as inclusive.
        # Writing the value back unchanged shrinks the window by 1 row — so we
        # compensate by incrementing Bottom by 1 before the set call.
        csbiex.srWindow.Bottom += 1

        kernel32.SetConsoleScreenBufferInfoEx(handle, ctypes.byref(csbiex))
    except Exception:
        pass


def _get_console_size():
    """Get current console window size (width, height)."""
    if os.name != 'nt':
        return 80, 25
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
    return (csbi.srWindow.Right - csbi.srWindow.Left + 1,
            csbi.srWindow.Bottom - csbi.srWindow.Top + 1)


def _resize_monitor():
    """Daemon thread: fill new rows when console grows, refill on shrink."""
    global _last_size
    while True:
        try:
            w, h = _get_console_size()
            with _resize_lock:
                if (w, h) != _last_size and w > 0 and h > 0:
                    old_h = _last_size[1] if _last_size[1] > 0 else h
                    _last_size = (w, h)
                    if h > old_h:
                        # Window grew: fill only new rows with background
                        _fill_rows(old_h, h - 1, w)
                    elif h < old_h:
                        # Window shrank: refill entire screen
                        fill_background()
        except Exception:
            pass
        time.sleep(0.3)


def _fill_rows(start_row: int, end_row: int, width: int):
    """Fill specific rows with background color using Win32 API (no cursor move)."""
    if os.name != 'nt':
        return
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

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)
    csbi = CONSOLE_SCREEN_BUFFER_INFO()
    kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi))
    win_top = csbi.srWindow.Top

    # bg=slot6(dark purple)=0x60, fg=bright yellow=0x0E → 0x6E
    THEME_ATTR = 0x6E
    written = ctypes.c_ulong()
    for row in range(start_row, end_row + 1):
        coord = COORD(0, win_top + row)
        kernel32.FillConsoleOutputCharacterW(handle, ord(' '), width, coord, ctypes.byref(written))
        kernel32.FillConsoleOutputAttribute(handle, THEME_ATTR, width, coord, ctypes.byref(written))


def fill_background():
    """Fill entire console background with theme color using Win32 API."""
    global _content_row
    if os.name != 'nt':
        return

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

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)
    csbi = CONSOLE_SCREEN_BUFFER_INFO()
    kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi))

    width = csbi.srWindow.Right - csbi.srWindow.Left + 1
    height = csbi.srWindow.Bottom - csbi.srWindow.Top + 1

    # Paint the ENTIRE scroll buffer so areas above and below the visible window
    # also have the theme background when the user scrolls.
    cell_count = csbi.dwSize.X * csbi.dwSize.Y
    top = COORD(0, 0)

    # bg=slot6(dark purple)=0x60, fg=bright yellow=0x0E → 0x6E
    # Using Win32 API directly avoids ANSI buffering races and VT-mode dependency.
    THEME_ATTR = 0x6E
    written = ctypes.c_ulong()
    kernel32.FillConsoleOutputCharacterW(handle, ord(' '), cell_count, top, ctypes.byref(written))
    kernel32.FillConsoleOutputAttribute(handle, THEME_ATTR, cell_count, top, ctypes.byref(written))

    # Lock in theme as the console default attribute. This makes the VT "default"
    # background resolve to dark purple so printed text inherits it on every launch,
    # not only after a previous run's _exit_cleanup has already set 0x6E.
    kernel32.SetConsoleTextAttribute(handle, THEME_ATTR)

    # Re-enable VT so subsequent ANSI text colour codes work
    enable_ansi()
    kernel32.SetConsoleCursorPosition(handle, COORD(0, 0))
    _content_row = 0


def reset_background():
    """Reset background color to default."""
    sys.stdout.write(ANSI_RESET)
    sys.stdout.flush()


def set_colors(fg: str = None):
    """Set console foreground color using ANSI escape codes.
    Always pairs with BG_THEME so the VT background is set explicitly — without
    this, the VT background defaults to black on first launch (before _exit_cleanup
    has ever set the console default attribute to the theme value).
    """
    enable_ansi()
    if fg:
        sys.stdout.write(BG_THEME + fg)
    sys.stdout.flush()


def reset_colors():
    """Reset colors to default."""
    sys.stdout.write(ANSI_RESET)
    sys.stdout.flush()


def set_title(title: str):
    """Set console window title."""
    if os.name == 'nt':
        os.system(f'title {title}')


def get_scroll_area_top():
    """Get the row index for the top of the scroll area (above progress line)."""
    h = _get_console_height()
    return h - 5


def _get_console_height():
    """Get console window height."""
    _, h = _get_console_size()
    return h


def scroll_print(text: str, fg: str = None):
    """Print a line in the scroll area above the progress line, with theme color."""
    from spore_crawler.ui.progress import _move_cursor_to
    row = get_scroll_area_top()
    _move_cursor_to(row)
    if fg:
        sys.stdout.write(fg)
    sys.stdout.write(text)
    sys.stdout.flush()
    _refresh_bottom()


def _refresh_bottom():
    """Redraw progress and hotkeys hint after scroll_print."""
    from spore_crawler.ui.progress import _move_cursor_to, _get_console_height as ph
    # This is called after scroll_print, the progress will be redrawn on next render
    pass


def print_banner():
    """Print title.txt ASCII banner with theme colors."""
    global _content_row
    from spore_crawler.cli.utilities import get_resource_dir
    title_path = get_resource_dir() / 'title.txt'
    set_colors(fg=FG_YELLOW)
    if title_path.exists():
        banner = title_path.read_text(encoding='utf-8')
        print(banner)
    else:
        print("SPORE Web Crawler")
    print()

    # Track where content output ends (after banner)
    if os.name == 'nt':
        try:
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
            _content_row = csbi.dwCursorPosition.Y
        except Exception:
            _content_row = 14


def print_header(text: str):
    """Print header text in yellow."""
    set_colors(fg=FG_YELLOW)
    print(f"=== {text} ===")
    print()


def print_success(text: str):
    """Print success message in green."""
    set_colors(fg=FG_GREEN)
    print(f"[OK] {text}")
    set_colors(fg=FG_YELLOW)


def print_error(text: str):
    """Print error message in red."""
    set_colors(fg=FG_RED)
    print(f"[ERROR] {text}")
    set_colors(fg=FG_YELLOW)


def print_info(text: str):
    """Print info message in cyan."""
    set_colors(fg=FG_CYAN)
    print(text)
    set_colors(fg=FG_YELLOW)


def write_status_bar(text: str, fg: str = None):
    """Write status text at row 0 (above banner) without disturbing cursor.

    Saves cursor position, writes at row 0, restores cursor.
    Pads text to console width to clear old content.
    """
    if os.name != 'nt':
        return
    try:
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

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)

        # Save current cursor position
        csbi = CONSOLE_SCREEN_BUFFER_INFO()
        kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi))
        saved_row = csbi.dwCursorPosition.Y
        saved_col = csbi.dwCursorPosition.X

        width = csbi.srWindow.Right - csbi.srWindow.Left + 1

        # Move to row 0 and write status
        kernel32.SetConsoleCursorPosition(handle, COORD(0, 0))
        enable_ansi()
        color_code = fg if fg else FG_YELLOW
        padded = text[:width].ljust(width)
        sys.stdout.write(f"{BG_THEME}{color_code}{padded}{ANSI_RESET}")
        sys.stdout.flush()

        # Restore cursor
        kernel32.SetConsoleCursorPosition(handle, COORD(saved_col, saved_row))
    except Exception:
        pass


def setup_logging(config: dict):
    """Setup logging to file only, not console."""
    log_cfg = config.get("logging", {})
    if not log_cfg.get("enabled", True):
        logging.disable(logging.CRITICAL)
        return

    # Re-enable logging if it was previously disabled
    logging.disable(logging.NOTSET)

    level_name = log_cfg.get("level", "INFO").upper()
    if level_name == "ALL":
        level = logging.NOTSET
    else:
        level = getattr(logging, level_name, logging.INFO)
    log_file = log_cfg.get("file")

    # Only use file handler, no console output
    handlers = []
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )


_content_row = 0  # Tracks where normal content output ends (after banner)


def get_content_row() -> int:
    """Get the row index where content output should start (after banner)."""
    return _content_row


def _restore_palette_slot6():
    """Restore CMD palette slot 6 to its original dark yellow default RGB(128,128,0)."""
    if os.name != 'nt':
        return
    try:
        import ctypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class SMALL_RECT(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                        ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]

        class CONSOLE_SCREEN_BUFFER_INFO_EX(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("dwSize", COORD),
                ("dwCursorPosition", COORD),
                ("wAttributes", ctypes.c_ushort),
                ("srWindow", SMALL_RECT),
                ("dwMaximumSize", COORD),
                ("wPopupAttributes", ctypes.c_ushort),
                ("bFullscreenSupported", ctypes.c_bool),
                ("ColorTable", ctypes.c_ulong * 16),
            ]

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)

        csbiex = CONSOLE_SCREEN_BUFFER_INFO_EX()
        csbiex.cbSize = ctypes.sizeof(csbiex)
        kernel32.GetConsoleScreenBufferInfoEx(handle, ctypes.byref(csbiex))

        # Restore slot 6 to CMD default dark yellow: RGB(128,128,0)
        # COLORREF is BGR: 0x00BBGGRR → R=0x80, G=0x80, B=0x00 → 0x00008080
        csbiex.ColorTable[6] = 0x00008080

        # Windows bug workaround: increment Bottom before writing back (see init_palette)
        csbiex.srWindow.Bottom += 1
        kernel32.SetConsoleScreenBufferInfoEx(handle, ctypes.byref(csbiex))
    except Exception:
        pass


def _exit_cleanup():
    """Restore default CMD console attribute on exit so the CMD prompt is left clean."""
    import atexit
    import ctypes

    # CMD default: black background (0x00), bright white foreground (0x0F)
    _DEFAULT_ATTR = 0x0F

    def _cleanup():
        if os.name != 'nt':
            return
        try:
            # Restore palette slot 6 so no purple tint lingers in CMD after exit
            _restore_palette_slot6()
            # Re-enable ANSI after palette restore (SetConsoleScreenBufferInfoEx resets mode)
            enable_ansi()
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            # Explicitly write white-on-black while VT is active so any text rendered
            # after exit (e.g. the CMD prompt) is visible rather than black-on-black.
            sys.stdout.write(FG_WHITE + "\033[40m")
            sys.stdout.flush()
            # Set default CMD text attribute for the CMD prompt that resumes after us
            kernel32.SetConsoleTextAttribute(handle, _DEFAULT_ATTR)
        except Exception:
            pass

    atexit.register(_cleanup)


def exit_program():
    """Restore default CMD theme and clear screen on exit."""
    if os.name == 'nt':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        # Restore palette slot 6 to original dark yellow
        _restore_palette_slot6()
        # Re-enable ANSI after palette restore (SetConsoleScreenBufferInfoEx resets mode),
        # so the color codes below are interpreted correctly rather than printed literally.
        enable_ansi()
        # Explicitly reset to white text on black background while VT is active.
        sys.stdout.write(ANSI_RESET + FG_WHITE + "\033[40m")
        sys.stdout.flush()
        # Disable VT processing so console reverts to legacy mode
        kernel32.SetConsoleMode(handle, 0x01)
        # Set default CMD text attribute: bright white fg on black bg (0x0F)
        kernel32.SetConsoleTextAttribute(handle, 0x0F)
    else:
        sys.stdout.write(ANSI_RESET + FG_WHITE)
        sys.stdout.flush()
    clear_screen()


def pause_for_exit(hint="                                                                                       [ENTER] Continue    [X] Exit", after_progress=False):
    """Show hint at bottom and wait for ENTER (continue) or X (exit).

    Args:
        after_progress: If True, place hint at Bottom-4 (above progress bar area).
                        If False, place at Bottom-1 (default bottom row).

    Returns:
        True to continue, False to exit.
    """
    if os.name != 'nt':
        choice = input(f"\n{hint}... ").strip().lower()
        return choice != 'x'
    try:
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

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        csbi = CONSOLE_SCREEN_BUFFER_INFO()
        kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi))

        width = csbi.srWindow.Right - csbi.srWindow.Left + 1
        height = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
        hint_row = (height - 4) if after_progress else csbi.srWindow.Bottom - 1

        kernel32.SetConsoleCursorPosition(handle, COORD(0, hint_row))

        padded = hint[:width].ljust(width)
        FG_WHITE = "\033[97m"
        sys.stdout.write(f"{BG_THEME}{FG_WHITE}{padded}")
        sys.stdout.flush()

        import msvcrt
        while True:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key in (b'\r', b'\n'):
                    result = True
                    break
                if key in (b'x', b'X'):
                    result = False
                    break
            import time
            time.sleep(0.05)

        # Clear hint row — keep bg theme, no ANSI_RESET
        kernel32.SetConsoleCursorPosition(handle, COORD(0, hint_row))
        sys.stdout.write(f"{BG_THEME}{' ' * width}")
        sys.stdout.flush()
        return result
    except Exception:
        choice = input(f"\n{hint}... ").strip().lower()
        return choice != 'x'


def ensure_window_rows(min_rows: int):
    """Expand the CMD window to at least min_rows if it is currently smaller."""
    if os.name != 'nt':
        return
    try:
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

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        csbi = CONSOLE_SCREEN_BUFFER_INFO()
        kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(csbi))

        current_height = csbi.srWindow.Bottom - csbi.srWindow.Top + 1
        if current_height >= min_rows:
            return

        # Grow the scroll buffer first if it's not tall enough for the new window
        needed_buf = csbi.srWindow.Top + min_rows
        if needed_buf > csbi.dwSize.Y:
            kernel32.SetConsoleScreenBufferSize(handle, COORD(csbi.dwSize.X, needed_buf))

        # Expand the visible window rectangle
        new_rect = SMALL_RECT(
            csbi.srWindow.Left,
            csbi.srWindow.Top,
            csbi.srWindow.Right,
            csbi.srWindow.Top + min_rows - 1,
        )
        kernel32.SetConsoleWindowInfo(handle, True, ctypes.byref(new_rect))
    except Exception:
        pass


def init_cli(config: dict):
    """Initialize CLI: clear screen, print banner, setup colors."""
    global _last_size
    clear_screen()
    set_title("Sporepedia Bean's Web Crawler")

    # Remap palette slot 6 to dark purple (before VT is enabled)
    init_palette()

    # Re-enable VT processing — SetConsoleScreenBufferInfoEx resets console mode
    enable_ansi()

    # Expand window to at least 39 rows before painting background
    ensure_window_rows(39)

    # Fill background using Win32 API (reliable, no VT dependency)
    fill_background()

    # Record initial size and start resize monitor
    _last_size = _get_console_size()
    t = threading.Thread(target=_resize_monitor, daemon=True)
    t.start()

    # Set foreground color
    set_colors(fg=FG_YELLOW)

    # Register exit cleanup
    _exit_cleanup()

    print_banner()