"""
convert_sql.py - `convert-sql` command: export SQLite databases to plain text.

Depends on: cli/commands/_common (get_search_db_path, get_sporecast_db_path,
            get_browse_db_path, _export_database)
Used by: cli/commands/__init__, cli/__init__

Side effects:
  - Writes .txt export files to disk
"""
import logging
from pathlib import Path

from spore_crawler.cli.commands._common import (
    get_search_db_path, get_sporecast_db_path, get_browse_db_path, _export_database,
)
from spore_crawler.cli_ui import set_colors, FG_GREEN, FG_YELLOW

log = logging.getLogger(__name__)


def _print_db_found(db_name: str, table_count: int):
    set_colors(fg=FG_GREEN)
    print(f"  {db_name} : Found {table_count} tables:")
    set_colors(fg=FG_YELLOW)


def _print_db_not_found(db_path: Path):
    print(f"  DATABASE NOT FOUND: ", end='')
    print(f"{db_path}")


async def cmd_convert_sql(config: dict, db_type: str):
    main_db_path = Path(config['database']['path'])
    search_db_path = Path(get_search_db_path(config))
    sporecast_db_path = Path(get_sporecast_db_path(config))
    browse_db_path = Path(get_browse_db_path(config))

    log.info('Command: convert-sql, type=%s', db_type)
    log.info('  Main DB: %s (exists=%s)', main_db_path, main_db_path.exists())
    log.info('  Search DB: %s (exists=%s)', search_db_path, search_db_path.exists())
    log.info('  Sporecast DB: %s (exists=%s)', sporecast_db_path, sporecast_db_path.exists())
    log.info('  Browse DB: %s (exists=%s)', browse_db_path, browse_db_path.exists())

    if db_type in ('crawler', 'sporepedia'):
        if main_db_path.exists():
            txt_path = main_db_path.with_suffix('.txt')
            _export_database(main_db_path, txt_path, 'sporepedia.db')
        else:
            log.warning('Database not found: %s', main_db_path)
            _print_db_not_found(main_db_path)

    elif db_type == 'search':
        if search_db_path.exists():
            txt_path = search_db_path.with_suffix('.txt')
            _export_database(search_db_path, txt_path, 'search_sporepedia.db')
        else:
            log.warning('Database not found: %s', search_db_path)
            _print_db_not_found(search_db_path)

    elif db_type == 'browse':
        if browse_db_path.exists():
            txt_path = browse_db_path.with_suffix('.txt')
            _export_database(browse_db_path, txt_path, 'search_sporecast.db')
        else:
            log.warning('Database not found: %s', browse_db_path)
            _print_db_not_found(browse_db_path)

    elif db_type == 'sporecast':
        if sporecast_db_path.exists():
            txt_path = sporecast_db_path.with_suffix('.txt')
            _export_database(sporecast_db_path, txt_path, 'sporecasts.db')
        else:
            log.warning('Database not found: %s', sporecast_db_path)
            _print_db_not_found(sporecast_db_path)

    elif db_type == 'all':
        set_colors(fg=FG_GREEN)
        print('EXPORTING ALL DATABASES')
        set_colors(fg=FG_YELLOW)
        print()
        if main_db_path.exists():
            txt = main_db_path.with_suffix('.txt')
            _export_database(main_db_path, txt, 'sporepedia.db')
        else:
            _print_db_not_found(main_db_path)
        if search_db_path.exists():
            txt = search_db_path.with_suffix('.txt')
            _export_database(search_db_path, txt, 'search_sporepedia.db')
        else:
            _print_db_not_found(search_db_path)
        if sporecast_db_path.exists():
            txt = sporecast_db_path.with_suffix('.txt')
            _export_database(sporecast_db_path, txt, 'sporecasts.db')
        else:
            _print_db_not_found(sporecast_db_path)
        if browse_db_path.exists():
            txt = browse_db_path.with_suffix('.txt')
            _export_database(browse_db_path, txt, 'search_sporecast.db')
        else:
            _print_db_not_found(browse_db_path)

    else:
        log.warning('Unknown database type: %s', db_type)
        print(f"UNKNOWN DATABASE TYPE: {db_type}")
        print('Use: crawler, search, browse, sporecast, or all')
