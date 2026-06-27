"""
clean.py - `clean` command: delete downloaded databases, download folders, and other files.

Depends on: cli/commands/_common (get_search_db_path, get_sporecast_db_path,
            get_browse_db_path)
Used by: cli/commands/__init__, cli/__init__

Side effects:
  - Deletes .db files (sporepedia.db, search_sporepedia.db, sporecasts.db, search_sporecast.db)
  - Deletes downloads/ folder, db_chunks/ folder, test_downloads/ folder
  - Optionally deletes config.yaml, crawler.log, credentials.json, .txt exports
"""
import shutil
import logging
from pathlib import Path

from spore_crawler.cli.commands._common import (
    get_search_db_path, get_sporecast_db_path, get_browse_db_path,
)

log = logging.getLogger(__name__)


async def cmd_clean(config: dict):
    """Delete files and folders based on clean config settings.

    Prompts for confirmation before deleting anything.
    Items are controlled by config['clean'] booleans.
    """
    clean_cfg = config.get('clean', {})
    main_db = Path(config['database']['path'])
    search_db = Path(get_search_db_path(config))
    sporecast_db = Path(get_sporecast_db_path(config))
    browse_db = Path(get_browse_db_path(config))
    download_dir = Path(config['output']['download_folder'])
    chunks_dir = Path(config['database'].get('chunks_dir', './db_chunks'))
    app_dir = main_db.parent

    targets = []

    if clean_cfg.get('databases', True):
        for db_path in [main_db, search_db, sporecast_db, browse_db]:
            if db_path.exists():
                targets.append(('Database', db_path))

    if clean_cfg.get('downloads', True):
        if download_dir.exists() and download_dir.is_dir():
            targets.append(('Downloads folder', download_dir))

    if clean_cfg.get('chunks', True):
        if chunks_dir.exists() and chunks_dir.is_dir():
            targets.append(('Chunks folder', chunks_dir))

    if clean_cfg.get('config_yaml', False):
        cfg_path = app_dir / 'config.yaml'
        if cfg_path.exists():
            targets.append(('Config file', cfg_path))

    if clean_cfg.get('crawler_log', False):
        log_path = app_dir / 'crawler.log'
        if log_path.exists():
            targets.append(('Log file', log_path))
            # Close log handlers before deletion to avoid WinError 32 (file in use)
            root_logger = logging.getLogger()
            for handler in list(root_logger.handlers):
                if isinstance(handler, logging.FileHandler):
                    if handler.baseFilename and Path(handler.baseFilename).resolve() == log_path.resolve():
                        handler.close()
                        root_logger.removeHandler(handler)

    if clean_cfg.get('credentials', False):
        creds_path = app_dir / 'credentials.json'
        if creds_path.exists():
            targets.append(('Credentials file', creds_path))

    if clean_cfg.get('database_txt', False):
        for db_path in [main_db, search_db, sporecast_db, browse_db]:
            txt_path = db_path.with_suffix('.txt')
            if txt_path.exists():
                targets.append(('Export file', txt_path))

    if clean_cfg.get('test_downloads', False):
        test_dl_dir = app_dir / 'test_downloads'
        if test_dl_dir.exists() and test_dl_dir.is_dir():
            targets.append(('Test downloads folder', test_dl_dir))

    if not targets:
        print("Nothing to clean - all clean already!")
        return

    print("The following will be deleted:")
    print()
    for label, path in targets:
        if path.is_file():
            size_mb = path.stat().st_size / 1048576
            print(f"  {label}: {path} ({size_mb:.2f} MB)")
        else:
            print(f"  {label}: {path}")
    print()

    try:
        confirm = input("Type 'yes' to confirm deletion: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return

    if confirm not in ('yes', 'y'):
        print("Cancelled.")
        return

    deleted = 0
    for label, path in targets:
        try:
            if path.is_file():
                path.unlink()
                log.info('Deleted file: %s', path)
                print(f"  Deleted: {path}")
            elif path.is_dir():
                shutil.rmtree(path)
                log.info('Deleted folder: %s', path)
                print(f"  Deleted: {path}")
            deleted += 1
        except Exception as e:
            log.error('Failed to delete %s: %s', path, e)
            print(f"  Failed to delete {path}: {e}")

    print(f"\nCleaned {deleted}/{len(targets)} items.")
