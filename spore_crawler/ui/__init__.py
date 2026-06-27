"""
ui/__init__.py - Lightweight ANSI RGB color constants and basic print helpers.

Depends on: None (leaf module)
Used by: cli/commands/_common, cli/commands/search, cli/commands/sporecast,
         cli/commands/crawl, crawlers/hotkeys
"""
import os
import sys
from pathlib import Path

# ANSI escape code for RGB foreground: \033[38;2;r;g;bm
# Reset colors: \033[0m
ANSI_RESET = "\033[0m"

# Foreground colors (using ANSI RGB)
FG_YELLOW = "\033[38;2;255;255;0m"      # Yellow
FG_GREEN = "\033[38;2;0;255;0m"         # Green
FG_RED = "\033[38;2;255;0;0m"           # Red
FG_CYAN = "\033[38;2;0;255;255m"        # Cyan
FG_WHITE = "\033[38;2;255;255;255m"     # White
FG_GRAY = "\033[38;2;128;128;128m"      # Gray

TITLE_PATH = Path(__file__).parent.parent / 'title.txt'


def clear_screen():
    """Clear console screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def enable_ansi():
    """Enable ANSI escape codes on Windows 10+."""
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Enable ANSI escape code processing
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def set_colors(fg: str = None):
    """Set console foreground color using ANSI escape codes."""
    enable_ansi()
    if fg:
        sys.stdout.write(fg)
    sys.stdout.flush()


def reset_colors():
    """Reset colors to default."""
    sys.stdout.write(ANSI_RESET)
    sys.stdout.flush()


def set_title(title: str):
    """Set console window title."""
    if os.name == 'nt':
        os.system(f'title {title}')


def print_banner():
    """Print title.txt ASCII banner with theme colors."""
    set_colors(fg=FG_YELLOW)
    if TITLE_PATH.exists():
        banner = TITLE_PATH.read_text(encoding='utf-8')
        print(banner)
    else:
        print("SPORE Web Crawler")
    print()


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


def print_status(text: str):
    """Print status line (inline, no newline)."""
    set_colors(fg=FG_YELLOW)
    print(text, end='', flush=True)
