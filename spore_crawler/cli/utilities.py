"""
utilities.py - Shared CLI utilities: path resolution, temp files, DB export.

Depends on: cli_ui (BG_THEME, lazy import)
Used by: cli/commands/_common, cli/commands/config_cmd
"""
import os
import sys
import sqlite3
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)

FG_END = '\x1b[38;2;176;190;197m'


def _print_result(text: str) -> None:
    """Print a result line at the current cursor position with themed background."""
    from spore_crawler.cli_ui import BG_THEME
    width = _get_console_width()
    padded = text[:width].ljust(width)
    sys.stdout.write(f"{BG_THEME}{FG_END}{padded}{BG_THEME}\n")
    sys.stdout.flush()


def _get_console_width():
    """Get console window width."""
    if os.name != 'nt':
        return 80
    import ctypes

    class COORD(ctypes.Structure):
        _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

    class SMALL_RECT(ctypes.Structure):
        _fields_ = [
            ("Left", ctypes.c_short),
            ("Top", ctypes.c_short),
            ("Right", ctypes.c_short),
            ("Bottom", ctypes.c_short),
        ]

    class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
        _fields_ = [
            ("dwSize", COORD),
            ("dwCursorPosition", COORD),
            ("wAttributes", ctypes.c_ushort),
            ("srWindow", SMALL_RECT),
            ("dwMaximumSize", COORD),
        ]

    csbi = CONSOLE_SCREEN_BUFFER_INFO()
    ctypes.windll.kernel32.GetConsoleScreenBufferInfo(
        ctypes.windll.kernel32.GetStdHandle(-11),
        ctypes.byref(csbi),
    )
    return csbi.srWindow.Right - csbi.srWindow.Left + 1


def get_app_dir() -> Path:
    """Get the application directory for config files.
In PyInstaller: directory containing the .exe.
In development: current working directory (where user runs the command)."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path.cwd()


def get_resource_dir() -> Path:
    """Get the directory for bundled resources (ASCII art, etc.).
In PyInstaller, resources are extracted to _MEIPASS temp dir."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


def get_search_db_path(config: dict) -> str:
    """Get path for search database (search_sporepedia.db) - DWR search results."""
    main_db = str(Path(config['database']['path']).parent)
    return main_db + '/search_sporepedia.db'


def get_sporecast_db_path(config: dict) -> str:
    """Get path for sporecast downloads database (separate from main crawler DB)."""
    main_db = str(Path(config['database']['path']).parent)
    return main_db + '/sporecasts.db'


def get_browse_db_path(config: dict) -> str:
    """Get path for browse database (search_sporecast.db) - REST browse results."""
    main_db = str(Path(config['database']['path']).parent)
    return main_db + '/search_sporecast.db'


def get_temp_file_path(config: dict) -> Path:
    """Get path for sporecasts_temp.txt."""
    output_dir = Path(config['output']['download_folder'])
    return output_dir / 'sporecasts_temp.txt'


def _read_temp_file(temp_file: Path) -> list[tuple]:
    """Read sporecast IDs from sporecasts_temp.txt.

    Returns list of tuples: (id, title, author, description, rating, tags, last_updated, subscribers)

    File format (tab-separated):
      New (9 fields): id  assets  subs  author  title  description  rating  tags  last_updated
      Old (5 fields): id  assets  subs  author  title
      Older (4 fields): id  assets  subs  title
      Legacy (2 fields): id  title
      Minimal (1 field): id
    """
    log.info('Reading temp file: %s', temp_file)
    sporecast_ids = []
    with open(temp_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 9:
                try:
                    sc_id = int(parts[0])
                    sc_author = parts[3]
                    sc_title = parts[4]
                    sc_description = parts[5]
                    sc_rating = parts[6]
                    sc_tags = parts[7]
                    sc_last_updated = parts[8]
                    sc_subs = int(parts[2]) if parts[2].isdigit() else 0
                    sporecast_ids.append((sc_id, sc_title, sc_author, sc_description, sc_rating, sc_tags, sc_last_updated, sc_subs))
                except (ValueError, IndexError):
                    log.debug('Skipping invalid line: %s', line)
            elif len(parts) >= 5:
                try:
                    sc_id = int(parts[0])
                    sc_author = parts[3]
                    sc_title = parts[4]
                    sporecast_ids.append((sc_id, sc_title, sc_author, '', '', '', '', 0))
                except (ValueError, IndexError):
                    log.debug('Skipping invalid line: %s', line)
            elif len(parts) == 4:
                try:
                    sc_id = int(parts[0])
                    sc_title = parts[3]
                    sporecast_ids.append((sc_id, sc_title, '', '', '', '', '', 0))
                except ValueError:
                    log.debug('Skipping invalid line: %s', line)
            elif len(parts) >= 2:
                try:
                    sc_id = int(parts[0])
                    sc_title = parts[1]
                    sporecast_ids.append((sc_id, sc_title, '', '', '', '', '', 0))
                except ValueError:
                    log.debug('Skipping invalid line: %s', line)
            elif len(parts) == 1:
                try:
                    sc_id = int(parts[0])
                    sporecast_ids.append((sc_id, f'sporecast_{sc_id}', '', '', '', '', '', 0))
                except ValueError:
                    log.debug('Skipping invalid line: %s', line)
    log.info('Temp file read: %d sporecast IDs loaded', len(sporecast_ids))
    return sporecast_ids


def _format_datetime(val):
    """Format ISO datetime to '2026-06-19    07:10:22'."""
    if val is None or val == 'NULL':
        return 'NULL'
    try:
        dt = datetime.fromisoformat(val)
        return dt.date().strftime('%Y-%m-%d    %H:%M:%S')
    except (ValueError, TypeError):
        return str(val)


_EXPORT_COLUMN_ORDER = {
    'downloaded_assets': ['asset_id', 'downloaded_at', 'file_size', 'file_path'],
    'scanned_sporecasts': ['sporecast_id', 'asset_count', 'subscribers', 'discovered_at', 'title', 'author'],
}


def _export_database(db_path: Path, txt_path: Path, label: str):
    from spore_crawler.cli_ui import set_colors, FG_GREEN, FG_YELLOW
    log.info('Exporting database: %s -> %s', db_path, txt_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    if not tables:
        print(f"No tables found in {db_path}")
        conn.close()
        return

    set_colors(fg=FG_GREEN)
    print(f"  {label} : Found {len(tables)} tables:")
    set_colors(fg=FG_YELLOW)
    print(f"  {[t['name'] for t in tables]}")

    now = datetime.utcnow()
    lines = [f'{label} exported at {now.strftime("%Y-%m-%d %H:%M:%S")}']
    total_rows = 0

    for t in tables:
        table_name = t['name']
        desired_cols = _EXPORT_COLUMN_ORDER.get(table_name)

        if desired_cols:
            col_list = ', '.join(f'[{c}]' for c in desired_cols)
            rows = conn.execute(f'SELECT {col_list} FROM [{table_name}]').fetchall()
            columns = desired_cols
        else:
            rows = conn.execute(f'SELECT * FROM [{table_name}]').fetchall()
            columns = [col for col in rows[0].keys()] if rows else []

        total_rows += len(rows)

        lines.append('')
        lines.append(f"  TABLE: {table_name} ({len(rows)} rows)")

        if not rows:
            lines.append('  (empty)')
            continue

        lines.append('  ' + ' '.join(col.ljust(max(len(str(row[col] or '')) for row in rows)) for col in columns))
        for row in rows:
            vals = []
            for col in columns:
                val = row[col]
                if val is None:
                    vals.append('NULL')
                else:
                    vals.append(str(val))
            lines.append('  ' + '  '.join(vals))

    lines.append('')
    lines.append(f"  Total: {len(tables)} tables, {total_rows} rows")
    lines.append('')

    txt_path.write_text('\n'.join(lines), encoding='utf-8')
    log.info('Export complete: %s -> %s (%d tables, %d rows)', db_path, txt_path, len(tables), total_rows)
    print(f"  Exported: {label} -> {txt_path} ({len(tables)} tables, {total_rows} rows)")
    print("")
