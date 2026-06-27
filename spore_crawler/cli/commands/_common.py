"""
_common.py - Central shared imports and mutable state for all command modules.

Depends on: api/client, api/auth, storage/database, crawlers/full_crawler,
            organizers/folders, ui, ui/progress, cli/utilities
Used by: cli/commands/search, cli/commands/sporecast, cli/commands/crawl,
         cli/commands/config_cmd, cli/commands/convert_sql, cli/commands/bean,
         cli/commands/clean, cli/__init__
"""
import re
import os
import sys
import json
import yaml
import sqlite3
import logging
from pathlib import Path

from spore_crawler.api.client import SporeAPI, USER_AGENT_TEST
from spore_crawler.api.auth import (
    SporeAuth, get_credentials, get_credentials_interactive,
    save_credentials, load_credentials,
)
from spore_crawler.storage.database import Database
from spore_crawler.crawlers.full_crawler import crawl_assets, crawl_sporecast
from spore_crawler.organizers.folders import ensure_directories
from spore_crawler.ui import FG_YELLOW
from spore_crawler.ui.progress import print_hotkeys_hint, scroll_print, _move_cursor_to
from spore_crawler.cli.utilities import (
    get_app_dir, get_resource_dir, get_search_db_path,
    get_sporecast_db_path, get_browse_db_path, get_temp_file_path,
    _read_temp_file, _format_datetime, _export_database,
)

log = logging.getLogger(__name__)

# Mutable container for shared state across command modules.
# Commands set state['used_progress_bar'] = True when they use a progress bar.
# Commands set state['skip_pause'] = True to skip the post-command pause.
# The cli __init__.py reads/resets it.
state = {'used_progress_bar': False, 'skip_pause': False}
