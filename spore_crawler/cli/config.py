"""
config.py - YAML config loading, defaults, env overrides, validation, presets.

Depends on: cli/utilities (get_app_dir)
Used by: cli/__init__, cli/commands/_common, cli/commands/config_cmd
"""
import os
import sys
import yaml
import logging
from pathlib import Path
from spore_crawler.cli.utilities import get_app_dir

log = logging.getLogger(__name__)


DEFAULT_CONFIG = {
    'crawler': {
        'requests_per_second': 1.5,
        'request_timeout': 30,
        'max_retries': 3,
        'page_size': 500,
        'max_concurrent_downloads': 5,
        'sporecast_search_mode': 'batch',  # 'batch' = enumerate all then download, 'sequential' = search one download one
        'sort_method': ['NEWEST', 'TOP_RATED', 'TOP_RATED_NEW', 'FEATURED', 'MAXIS_MADE'],
        'asset_types': ['CREATURE', 'BUILDING', 'VEHICLE', 'ADVENTURE', 'UFO'],
        'subtypes': [
            'Animal', 'Tribal', 'Civ', 'Space', 'Captain',
            'City Hall', 'House', 'Factory', 'Entertainment',
            'Military Land', 'Military Water', 'Military Air',
            'Economic Land', 'Economic Water', 'Economic Air',
            'Religious Land', 'Religious Water', 'Religious Air',
            'Colony Land', 'Colony Water', 'Colony Air', 'Spaceships',
            'Attack', 'Collect', 'Defend', 'Explore', 'Puzzle',
            'Quest', 'Socialize', 'Story', 'Template', 'No Genre',
        ],
        'search_fields': ['title', 'author', 'tags', 'subtitle'],
    },
    'output': {
        'download_folder': './downloads',
        'organize_by_type': True,
        'embed_metadata': True,
    },
    'database': {
        'path': './sporepedia.db',
        'chunks_dir': './db_chunks',
        'auto_save_chunk': False,
        'auto_save_name': 'auto_backup',
    },
    'logging': {
        'enabled': True,
        'level': 'INFO',
        'file': './crawler.log',
    },
    'bean_test': False,
    'clean': {
        'databases': True,
        'downloads': True,
        'chunks': True,
        'config_yaml': False,
        'crawler_log': False,
        'credentials': False,
        'database_txt': False,
        'test_downloads': False,
    },
}

DEFAULT_CONFIG_YAML = """# Sporepedia Bean's Web Crawler - Configuration
# ================================================
# Edit this file to customize crawl behavior.
# After changes, run: crawl
#
# You can also override settings with environment variables:
#   SPORE_CRAWLER_CRAWLER_REQUESTS_PER_SECOND=2.0
#   SPORE_CRAWLER_OUTPUT_DOWNLOAD_FOLDER=/tmp/downloads
#
# Use 'config presets' to see predefined profiles
# Use 'config validate' to check your config

# Credentials are stored in credentials.json (managed via 'login' command).
# Use 'login --new' to save new credentials, 'login --del' to remove them.

# Crawler settings
crawler:
  requests_per_second: 1.5   # Delay between API calls (lower = faster, higher = safer)
                             # Range: 0.1 - 10.0 (default: 1.5)
  request_timeout: 30        # Seconds to wait for API response
                             # Range: 5 - 300 (default: 30)
  max_retries: 3             # Retry failed requests
                             # Range: 0 - 10 (default: 3)
  page_size: 500             # Assets per API request (max 500)
                             # Range: 1 - 500 (default: 500)
  max_concurrent_downloads: 5  # Parallel download threads
                             # Range: 1 - 20 (default: 5)

  # Sort method for sporepedia crawl (Sporepedia sort)
  # Options:
  #   NEWEST           - Recently uploaded
  #   TOP_RATED        - Most Popular (all time)
  #   TOP_RATED_NEW    - Most Popular New (recent high-rated)
  #   FEATURED         - Featured by Maxis
  #   MAXIS_MADE       - Official Maxis creations
  #   RANDOM           - Random selection
  #   CUTE_AND_CREEPY  - Creepy & Cute pack
  sort_method:
    - NEWEST
    - TOP_RATED
    - TOP_RATED_NEW
    - FEATURED
    - MAXIS_MADE

  # Which asset types to crawl
  # Options: CREATURE, BUILDING, VEHICLE, ADVENTURE, UFO
  asset_types:
    - CREATURE
    - BUILDING
    - VEHICLE
    - ADVENTURE
    - UFO

  # Which subtypes to crawl (all enabled by default)
  # Creatures: Animal, Tribal, Civ, Space, Captain
  # Buildings: City Hall, House, Factory, Entertainment
  # Vehicles: Military Land/Water/Air, Economic Land/Water/Air,
  #           Religious Land/Water/Air, Colony Land/Water/Air, Spaceships
  # Adventures: Attack, Collect, Defend, Explore, Puzzle,
  #             Quest, Socialize, Story, Template, No Genre
  subtypes:
    - Animal
    - Tribal
    - Civ
    - Space
    - Captain
    - City Hall
    - House
    - Factory
    - Entertainment
    - Military Land
    - Military Water
    - Military Air
    - Economic Land
    - Economic Water
    - Economic Air
    - Religious Land
    - Religious Water
    - Religious Air
    - Colony Land
    - Colony Water
    - Colony Air
    - Spaceships
    - Attack
    - Collect
    - Defend
    - Explore
    - Puzzle
    - Quest
    - Socialize
    - Story
    - Template
    - No Genre

  # Search fields for sporecast search command
  # Which fields to search when using 'search <keyword>'
  # Options: title, author, tags, subtitle
  #   title    - Sporecast Name
  #   author   - Creator Name
  #   tags     - Tags
  #   subtitle - Description
  # Empty list [] = search ALL fields (default)
  # Override with --fields argument: search pop --fields title,tags
  search_fields:
    - title
    - author
    - tags
    - subtitle

# Output settings
output:
  download_folder: "./downloads"    # Where to save downloaded PNGs
  organize_by_type: true            # Sort files into category folders
  embed_metadata: true              # Embed XML metadata into PNGs (zTXt chunk)
                                    # Set to false for pure PNGs without metadata
                                    # Affected files: <0.7% size increase
                                    # Game-compatible: spOr chunks preserved

# Database for tracking downloads (allows resume)
database:
  path: "./sporepedia.db"        # Main database file
  chunks_dir: "./db_chunks"         # Directory for database chunks
  auto_save_chunk: false            # Auto-save database chunk after each crawl
  auto_save_name: "auto_backup"     # Name for auto-saved chunks

# Logging (set enabled: false to disable file logging)
logging:
  enabled: true
  level: ALL                       # DEBUG, INFO, WARNING, ERROR, ALL
  file: "./crawler.log"

# Quick presets (use 'config presets' to see all):
#   config apply quick    # Fastest, limited scope
#   config apply full     # Comprehensive crawl
#   config apply safe     # Conservative, respectful

# Bean Test Mode (enable to unlock 'bean_test' command)
# When enabled, allows running automated test suite with 'bean_test'
bean_test: false

# Clean command settings (what 'clean' will delete)
# Set to true to include these items in cleanup
clean:
  databases: true           # Delete .db files (sporepedia.db, search_sporepedia.db, sporecasts.db, search_sporecast.db)
  downloads: true           # Delete downloads/ folder
  chunks: true              # Delete db_chunks/ folder
  config_yaml: false        # Delete config.yaml
  crawler_log: false        # Delete crawler.log
  credentials: false        # Delete credentials.json
  database_txt: false       # Delete converted .txt files (DATABASE.txt)
  test_downloads: false     # Delete test_downloads/ folder
"""


def load_config(config_path=None):
    if config_path is None:
        config_path = get_app_dir() / 'config.yaml'
    else:
        config_path = Path(config_path)

    if not config_path.exists():
        print(f"Config not found, creating default: {config_path}")
        config_path.write_text(DEFAULT_CONFIG_YAML, encoding='utf-8')

    with open(config_path, encoding='utf-8') as f:
        config = yaml.safe_load(f)

    config = apply_env_overrides(config)

    config = merge_defaults(config, DEFAULT_CONFIG)

    errors = validate_config(config)
    if errors:
        print('Config validation errors:')
        for error in errors:
            print(f'  - {error}')
        print('\nUsing default values for invalid settings.')
        config = merge_defaults(config, DEFAULT_CONFIG)

    return config


def apply_env_overrides(config: dict) -> dict:
    """Apply environment variable overrides to config.

Environment variables follow the pattern:
SPORE_CRAWLER_SECTION_KEY=value

Examples:
SPORE_CRAWLER_CRAWLER_REQUESTS_PER_SECOND=2.0
SPORE_CRAWLER_OUTPUT_DOWNLOAD_FOLDER=/tmp/downloads
SPORE_CRAWLER_DATABASE_PATH=/tmp/sporepedia.db
SPORE_CRAWLER_LOGGING_LEVEL=DEBUG
"""
    prefix = 'SPORE_CRAWLER_'

    env_mappings = {
        f'{prefix}CRAWLER_REQUESTS_PER_SECOND': ('crawler', 'requests_per_second', float),
        f'{prefix}CRAWLER_REQUEST_TIMEOUT': ('crawler', 'request_timeout', int),
        f'{prefix}CRAWLER_MAX_RETRIES': ('crawler', 'max_retries', int),
        f'{prefix}CRAWLER_PAGE_SIZE': ('crawler', 'page_size', int),
        f'{prefix}CRAWLER_MAX_CONCURRENT_DOWNLOADS': ('crawler', 'max_concurrent_downloads', int),
        f'{prefix}CRAWLER_SEARCH_FIELDS': ('crawler', 'search_fields', list),
        f'{prefix}OUTPUT_DOWNLOAD_FOLDER': ('output', 'download_folder', str),
        f'{prefix}OUTPUT_ORGANIZE_BY_TYPE': ('output', 'organize_by_type', bool),
        f'{prefix}OUTPUT_EMBED_METADATA': ('output', 'embed_metadata', bool),
        f'{prefix}DATABASE_PATH': ('database', 'path', str),
        f'{prefix}DATABASE_CHUNKS_DIR': ('database', 'chunks_dir', str),
        f'{prefix}DATABASE_AUTO_SAVE_CHUNK': ('database', 'auto_save_chunk', bool),
        f'{prefix}DATABASE_AUTO_SAVE_NAME': ('database', 'auto_save_name', str),
        f'{prefix}LOGGING_ENABLED': ('logging', 'enabled', bool),
        f'{prefix}LOGGING_LEVEL': ('logging', 'level', str),
        f'{prefix}LOGGING_FILE': ('logging', 'file', str),
    }

    for env_var, config_path in env_mappings.items():
        value = os.environ.get(env_var)
        if value is None:
            continue
        if len(config_path) == 2:
            key, target_type = config_path
            old_value = config.get(key)
            if target_type == bool:
                config[key] = value.lower() in ('true', '1', 'yes', 'on')
            elif target_type == int:
                config[key] = int(value)
            elif target_type == float:
                config[key] = float(value)
            elif target_type == list:
                config[key] = [v.strip() for v in value.split(',') if v.strip()]
            else:
                config[key] = value
            log.debug('Env override: %s=%s (was=%s, now=%s)', env_var, value, old_value, config[key])
        elif len(config_path) == 3:
            section, key = config_path[0], config_path[1]
            target_type = config_path[2]
            if section not in config:
                config[section] = {}
            target = config[section]
            if key in target:
                old_value = target[key]
                if target_type == bool:
                    target[key] = value.lower() in ('true', '1', 'yes', 'on')
                elif target_type == int:
                    target[key] = int(value)
                elif target_type == float:
                    target[key] = float(value)
                elif target_type == list:
                    target[key] = [v.strip() for v in value.split(',') if v.strip()]
                else:
                    target[key] = value
                log.debug('Env override: %s=%s (was=%s, now=%s)', env_var, value, old_value, target[key])
            else:
                if target_type == bool:
                    target[key] = value.lower() in ('true', '1', 'yes', 'on')
                elif target_type == int:
                    target[key] = int(value)
                elif target_type == float:
                    target[key] = float(value)
                else:
                    target[key] = value
                log.debug('Env override: %s=%s (now=%s)', env_var, value, target[key])

    return config


def merge_defaults(config: dict, defaults: dict) -> dict:
    """Merge config with defaults, preserving existing values."""
    result = defaults.copy()

    for key, value in config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_defaults(value, result[key])
        else:
            result[key] = value

    return result


def validate_config(config: dict) -> list[str]:
    """Validate config values and return list of errors."""
    errors = []

    crawler = config.get('crawler', {})

    if 'requests_per_second' in crawler:
        rps = crawler['requests_per_second']
        if not isinstance(rps, (int, float)) or rps < 0.1 or rps > 10:
            error = f'Invalid requests_per_second: {rps}. Must be between 0.1 and 10'
            log.warning('Config validation: %s', error)
            errors.append(error)

    if 'request_timeout' in crawler:
        timeout = crawler['request_timeout']
        if not isinstance(timeout, int) or timeout < 5 or timeout > 300:
            error = f'Invalid request_timeout: {timeout}. Must be between 5 and 300 seconds'
            log.warning('Config validation: %s', error)
            errors.append(error)

    if 'max_retries' in crawler:
        retries = crawler['max_retries']
        if not isinstance(retries, int) or retries < 0 or retries > 10:
            error = f'Invalid max_retries: {retries}. Must be between 0 and 10'
            log.warning('Config validation: %s', error)
            errors.append(error)

    if 'page_size' in crawler:
        page_size = crawler['page_size']
        if not isinstance(page_size, int) or page_size < 1 or page_size > 500:
            error = f'Invalid page_size: {page_size}. Must be between 1 and 500'
            log.warning('Config validation: %s', error)
            errors.append(error)

    if 'max_concurrent_downloads' in crawler:
        max_concurrent = crawler['max_concurrent_downloads']
        if not isinstance(max_concurrent, int) or max_concurrent < 1 or max_concurrent > 20:
            error = f'Invalid max_concurrent_downloads: {max_concurrent}. Must be between 1 and 20'
            log.warning('Config validation: %s', error)
            errors.append(error)

    valid_sort_methods = frozenset({'NEWEST', 'TOP_RATED', 'TOP_RATED_NEW', 'FEATURED', 'MAXIS_MADE', 'RANDOM', 'CUTE_AND_CREEPY'})
    if 'sort_method' in crawler:
        sort_method = crawler['sort_method']
        if not isinstance(sort_method, list):
            log.warning('Config validation: sort_method must be a list')
            errors.append('sort_method must be a list')
        else:
            for sm in sort_method:
                if sm not in valid_sort_methods:
                    error = f"Invalid sort_method: '{sm}'. Must be one of: {valid_sort_methods}"
                    log.warning('Config validation: %s', error)
                    errors.append(error)

    valid_asset_types = frozenset({'CREATURE', 'BUILDING', 'VEHICLE', 'ADVENTURE', 'UFO'})
    if 'asset_types' in crawler:
        asset_types = crawler['asset_types']
        if not isinstance(asset_types, list):
            log.warning('Config validation: asset_types must be a list')
            errors.append('asset_types must be a list')
        else:
            for at in asset_types:
                if at not in valid_asset_types:
                    error = f"Invalid asset_type: '{at}'. Must be one of: {valid_asset_types}"
                    log.warning('Config validation: %s', error)
                    errors.append(error)

    valid_search_fields = frozenset({'title', 'author', 'tags', 'subtitle'})
    if 'search_fields' in crawler:
        search_fields = crawler['search_fields']
        if not isinstance(search_fields, list):
            log.warning('Config validation: search_fields must be a list')
            errors.append('search_fields must be a list')
        else:
            for sf in search_fields:
                if sf not in valid_search_fields:
                    error = f"Invalid search_field: '{sf}'. Must be one of: {valid_search_fields}"
                    log.warning('Config validation: %s', error)
                    errors.append(error)

    valid_subtypes = frozenset({
        'Animal', 'Tribal', 'Civ', 'Space', 'Captain',
        'City Hall', 'House', 'Factory', 'Entertainment',
        'Military Land', 'Military Water', 'Military Air',
        'Economic Land', 'Economic Water', 'Economic Air',
        'Religious Land', 'Religious Water', 'Religious Air',
        'Colony Land', 'Colony Water', 'Colony Air', 'Spaceships',
        'Attack', 'Collect', 'Defend', 'Explore', 'Puzzle',
        'Quest', 'Socialize', 'Story', 'Template', 'No Genre',
    })
    if 'subtypes' in crawler:
        subtypes = crawler['subtypes']
        if not isinstance(subtypes, list):
            log.warning('Config validation: subtypes must be a list')
            errors.append('subtypes must be a list')
        else:
            for st in subtypes:
                if st not in valid_subtypes:
                    error = f"Invalid subtype: '{st}'. Must be one of: {valid_subtypes}"
                    log.warning('Config validation: %s', error)
                    errors.append(error)

    logging_config = config.get('logging', {})
    if 'level' in logging_config:
        valid_levels = frozenset({'DEBUG', 'INFO', 'WARNING', 'ERROR', 'ALL'})
        if logging_config['level'].upper() not in valid_levels:
            error = f"Invalid logging level: '{logging_config['level']}'. Must be one of: {valid_levels}"
            log.warning('Config validation: %s', error)
            errors.append(error)

    output = config.get('output', {})
    if 'embed_metadata' in output:
        embed = output['embed_metadata']
        if not isinstance(embed, bool):
            error = f'Invalid embed_metadata: {embed}. Must be true or false'
            log.warning('Config validation: %s', error)
            errors.append(error)

    return errors


def get_config_presets() -> dict[str, dict]:
    """Get predefined config presets."""
    return {
        'quick': {
            'crawler': {
                'requests_per_second': 1.5,
                'request_timeout': 30,
                'max_retries': 3,
                'page_size': 500,
                'max_concurrent_downloads': 5,
                'sporecast_search_mode': 'batch',
                'sort_method': ['NEWEST'],
                'asset_types': ['CREATURE'],
                'subtypes': ['Animal', 'Tribal', 'Civ', 'Space', 'Captain'],
                'search_fields': ['title', 'author', 'tags', 'subtitle'],
            },
            'output': {
                'download_folder': './downloads',
                'organize_by_type': True,
                'embed_metadata': True,
            },
            'database': {
                'path': './sporepedia.db',
                'chunks_dir': './db_chunks',
                'auto_save_chunk': False,
                'auto_save_name': 'auto_backup',
            },
            'logging': {
                'enabled': True,
                'level': 'ALL',
                'file': './crawler.log',
            },
            'clean': {
                'databases': True,
                'downloads': True,
                'chunks': True,
                'config_yaml': False,
                'crawler_log': False,
                'credentials': False,
                'database_txt': False,
                'test_downloads': False,
            },
        },
        'full': {
            'crawler': {
                'requests_per_second': 2.0,
                'request_timeout': 30,
                'max_retries': 3,
                'page_size': 500,
                'max_concurrent_downloads': 5,
                'sporecast_search_mode': 'batch',
                'sort_method': ['NEWEST', 'TOP_RATED', 'TOP_RATED_NEW', 'FEATURED', 'MAXIS_MADE', 'RANDOM', 'CUTE_AND_CREEPY'],
                'asset_types': ['CREATURE', 'BUILDING', 'VEHICLE', 'ADVENTURE', 'UFO'],
                'subtypes': [
                    'Animal', 'Tribal', 'Civ', 'Space', 'Captain',
                    'City Hall', 'House', 'Factory', 'Entertainment',
                    'Military Land', 'Military Water', 'Military Air',
                    'Economic Land', 'Economic Water', 'Economic Air',
                    'Religious Land', 'Religious Water', 'Religious Air',
                    'Colony Land', 'Colony Water', 'Colony Air', 'Spaceships',
                    'Attack', 'Collect', 'Defend', 'Explore', 'Puzzle',
                    'Quest', 'Socialize', 'Story', 'Template', 'No Genre',
                ],
                'search_fields': ['title', 'author', 'tags', 'subtitle'],
            },
            'output': {
                'download_folder': './downloads',
                'organize_by_type': True,
                'embed_metadata': True,
            },
            'database': {
                'path': './sporepedia.db',
                'chunks_dir': './db_chunks',
                'auto_save_chunk': False,
                'auto_save_name': 'auto_backup',
            },
            'logging': {
                'enabled': True,
                'level': 'ALL',
                'file': './crawler.log',
            },
            'clean': {
                'databases': True,
                'downloads': True,
                'chunks': True,
                'config_yaml': False,
                'crawler_log': False,
                'credentials': False,
                'database_txt': False,
                'test_downloads': False,
            },
        },
        'safe': {
            'crawler': {
                'requests_per_second': 3.5,
                'request_timeout': 30,
                'max_retries': 3,
                'page_size': 500,
                'max_concurrent_downloads': 5,
                'sort_method': ['NEWEST', 'TOP_RATED', 'FEATURED'],
                'asset_types': ['CREATURE', 'BUILDING', 'VEHICLE', 'ADVENTURE', 'UFO'],
                'subtypes': [
                    'Animal', 'Tribal', 'Civ', 'Space', 'Captain',
                    'City Hall', 'House', 'Factory', 'Entertainment',
                    'Military Land', 'Military Water', 'Military Air',
                    'Economic Land', 'Economic Water', 'Economic Air',
                    'Religious Land', 'Religious Water', 'Religious Air',
                    'Colony Land', 'Colony Water', 'Colony Air', 'Spaceships',
                    'Attack', 'Collect', 'Defend', 'Explore', 'Puzzle',
                    'Quest', 'Socialize', 'Story', 'Template', 'No Genre',
                ],
                'search_fields': ['title', 'author', 'tags', 'subtitle'],
            },
            'output': {
                'download_folder': './downloads',
                'organize_by_type': True,
                'embed_metadata': True,
            },
            'database': {
                'path': './sporepedia.db',
                'chunks_dir': './db_chunks',
                'auto_save_chunk': False,
                'auto_save_name': 'auto_backup',
            },
            'logging': {
                'enabled': True,
                'level': 'INFO',
                'file': './crawler.log',
            },
            'clean': {
                'databases': True,
                'downloads': True,
                'chunks': True,
                'config_yaml': False,
                'crawler_log': False,
                'credentials': False,
                'database_txt': False,
                'test_downloads': False,
            },
        },
    }


def _setup_early_logging():
    """Read config.yaml early and set up logging so load_config() can log to file."""
    cfg_path = get_app_dir() / 'config.yaml'
    if not cfg_path.exists():
        return
    try:
        with open(cfg_path, encoding='utf-8') as f:
            raw = yaml.safe_load(f)
        log_cfg = raw.get('logging', {})
        if not log_cfg.get('enabled', True):
            return
        level_str = log_cfg.get('level', 'INFO').upper()
        if level_str == 'ALL':
            level = logging.NOTSET
        else:
            level = getattr(logging, level_str, logging.INFO)
        log_file = log_cfg.get('file', './crawler.log')
        handlers = [logging.FileHandler(log_file)]
        logging.basicConfig(
            level=level,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S',
            handlers=handlers,
            force=True,
        )
    except Exception:
        pass
