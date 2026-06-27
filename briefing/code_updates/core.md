# core/ changelog - cli/__init__.py, models.py, organizers/, config.py, utilities.py, _common.py
# Newest entries at the top.

## config.py
2026-06-27
  REASON: No config option for sporecast search behavior (batch vs sequential)
  FIX:
  - Added sporecast_search_mode: 'batch' (enumerate all then download) vs 'sequential' (search one download one)
  - Added to DEFAULT_CONFIG, quick preset, full preset
  - Default is 'batch' (current behavior)

## cli/__init__.py
2026-06-27
  REASON: Exception handlers only logged error message, no traceback for debugging
  FIX:
  - Added import traceback to both interactive and single-command exception handlers
  - Both handlers now log full traceback via log.error('Command traceback:\n%s', traceback.format_exc())
  - Critical for diagnosing TypeError in _escape_xml (datetime passed to str.replace)

## cli/__init__.py
2026-06-27
  REASON: FG_GREEN raw print crashes; int() calls lack ValueError handling in all dispatchers
  FIX:
  - Added print_info import from cli_ui
  - Replaced raw print(f'{FG_GREEN}...') with print_info() in crawl/sporecast no-limit screens
  - Wrapped int() calls in try/except for crawl, sporecast, search, browse dispatchers
  - Invalid values now show clear error messages instead of crashing

2026-06-26 cli/utilities.py
  REASON: Database filenames didn't match action names
  FIX:
  - get_search_db_path() returns 'search_sporepedia.db' (search command - DWR)
  - get_browse_db_path() returns 'search_sporecast.db' (browse command - REST, was 'sporecast_search.db')
  - Updated docstrings to match corrected paths

2026-06-26 cli/help_text.py
  REASON: Database filenames in help text didn't match action names
  FIX:
  - crawl --db: references search_sporecast.db (was: sporecast_search.db)
  - sporecast --db: search_sporepedia.db or search_sporecast.db
  - browse: results saved to search_sporecast.db (was: sporecast_search.db)
  - convert-sql: export labels updated to search_sporecast.db
  - clean: databases list updated to search_sporecast.db

2026-06-26 cli/config.py
  REASON: Clean section comment referenced wrong database name
  FIX:
  - Updated databases comment to list search_sporepedia.db (was: sporecast_search.db)

2026-06-26 cli/__init__.py
  REASON: config set/apply/reset didn't take effect until program restart
  FIX:
  - Added _reload_config() helper: reloads config from disk + reconfigures logging
  - main(): reloads config after pause_for_exit Continue before re-entering interactive loop
  - _run_interactive(): reloads config after each command's pause_for_exit
  - Config changes now take effect on next command without restart

2026-06-26 cli_ui.py
  REASON: setup_logging couldn't re-enable logging after it was disabled
  FIX:
  - Added logging.disable(logging.NOTSET) before basicConfig to reset disabled state
  - Allows config set logging.enabled true to work after previous disable

2026-06-26 cli/help_text.py
  REASON: Browse help missing --type/-t option; bean_test description inaccurate
  FIX:
  - Added OPTIONS section to browse help: --type/-t, --filter/-fi, --max/-m, --subtypes/-sub
  - Updated bean_test description from "Tests every command combination" to
    "Tests database, API, crawl, and metadata functionality"

2026-06-26 cli/__init__.py
  REASON: Browse had no limiting; ran scrape immediately on bare 'browse'
  FIX:
  - Added --all / -all flag to browse dispatch (mirrors search's --all)
  - Added guard: no types + no --all = show help (same as search)
  - Added -help to global and per-command help checks (alongside --help, -h)
  - Browse dispatch now passes enumerate_all to cmd_browse
  - Added BROWSE_ARG_ALIASES '--a' -> '--all'

2026-06-26 cli/commands/browse.py
  REASON: Browse needs --all flag to browse all types without specifying each
  FIX:
  - Added enumerate_all parameter to cmd_browse()
  - When enumerate_all=True, resolves all 4 types regardless of asset_types

2026-06-26 cli/help_text.py
  REASON: Browse help was missing --all, -help, and had wrong defaults
  FIX:
  - Rewrote browse help: added --all, -help to docs, removed "default: all types"
  - Updated examples to show --all usage
  - Added '--a': '--all' to BROWSE_ARG_ALIASES

2026-06-26 cli/__init__.py
  REASON: Browse dispatch missing arg aliases; browse filters not matching website
  FIX:
  - Added BROWSE_ARG_ALIASES import from help_text
  - Browse dispatch now uses _apply_arg_aliases(BROWSE_ARG_ALIASES)
  - Added --db flag parsing for crawl command

2026-06-26 cli/__init__.py
  REASON: New 'browse' command added, needs dispatch and import
  FIX:
  - Added cmd_browse import from cli.commands
  - Added browse command dispatch block with --max, --filter, --type, --subtypes parsing

2026-06-26 cli/commands/_common.py
  REASON: browse command needs get_browse_db_path
  FIX:
  - Added get_browse_db_path to imports from cli.utilities

2026-06-26 cli/utilities.py
  REASON: browse command needs search_sporepedia.db path helper
  FIX:
  - Added get_browse_db_path() returning main_db parent + '/search_sporepedia.db'

2026-06-26 cli/help_text.py
  REASON: New 'browse' command needs help text, aliases, arg aliases
  FIX:
  - Added 'browse' to HELP_TEXT command list
  - Added browse COMMAND_HELP with usage, options, fields, examples
  - Added browse aliases: explore, b, br
  - Added BROWSE_ARG_ALIASES (--m, --f, --fl)
  - Updated convert-sql help: added 'browse' type, "all four databases"
  - Updated sporecast help: --db now checks both search and browse DBs
  - Updated clean help: databases section mentions search_sporepedia.db

2026-06-26 cli/commands/__init__.py
  REASON: browse command needs re-export
  FIX:
  - Added 'from .browse import cmd_browse'

2026-06-26 cli/__init__.py
  REASON: Arguments require double-dash prefix (e.g. --sort) in interactive mode
  FIX:
  - Added _arg_name() helper to strip leading dashes from args
  - Updated _normalize_arg() to convert single-dash to double-dash for alias lookup
  - Updated all arg comparison loops in crawl/sporecast/search/list/login dispatchers to use _arg_name()

2026-06-26 cli/utilities.py
  REASON: Database export column order unreadable; temp file format lacks metadata
  FIX:
  - Added _EXPORT_COLUMN_ORDER mapping for scanned_sporecasts and downloaded_assets tables
  - Updated _export_database() to use explicit column ordering for known tables
  - Updated _read_temp_file() to parse new 9-field format (with backward compat)

2026-06-26 cli/help_text.py
  REASON: Help text missing shorthand/abbreviation info
  FIX:
  - Added single-dash arg info to all command help texts (e.g. -sort, -mp, -a, -s, -f)
  - Updated env override comment from spore_crawler.db to sporepedia.db

2026-06-26 cli/config.py
  REASON: Env override comment references old spore_crawler.db name
  FIX:
  - Changed SPORE_CRAWLER_DATABASE_PATH example from spore_crawler.db to sporepedia.db

2026-06-25 cli/config.py
  REASON: Rename spore_crawler.db to sporepedia.db; presets missing clean section
  FIX:
  - Changed DEFAULT_CONFIG['database']['path'] from './spore_crawler.db' to './sporepedia.db'
  - Updated DEFAULT_CONFIG_YAML path, clean section comment
  - Updated all presets (quick, full, safe) database path references
  - Added 'clean' section to all presets (was missing)

2026-06-25 cli/__init__.py
  REASON: No-limit error confusing; list and sporecast missing --fields/--key args
  FIX:
  - Added green "Type crawl/sporecast --help to see full help" after no-limit errors
  - Added --fields parsing for list command
  - Added --key (and -k alias) parsing for sporecast command
  - Imported FG_GREEN from cli_ui

2026-06-25 cli/utilities.py
  REASON: _read_temp_file parsed wrong column as title; no author support
  FIX:
  - Rewrote _read_temp_file to handle new 5-part format (id, assets, subs, author, title)
  - Added backward compatibility for old 4-part format (id, assets, subs, title)
  - Added author extraction from parts[3]

2026-06-25 cli/help_text.py
  REASON: list and sporecast help text missing new --fields/--key arguments
  FIX:
  - Updated list help with --fields documentation and SEARCH FIELDS section
  - Updated sporecast help with --key documentation and example

2026-06-25 organizers/folders.py
  REASON: Sporecast folders named "X_assets" instead of "username_title" due to wrong column parsing
  FIX:
  - Changed get_sporecast_path to use {author}_{title} format instead of {author}_{id}
  - Improved sanitization with rstrip("_") for cleaner folder names

2026-06-25 cli/config.py
  REASON: Deprecated SPORE_CRAWLER_DOWNLOAD_MODE env override referenced in comments
  FIX:
  - Removed SPORE_CRAWLER_DOWNLOAD_MODE=sporepedia from env override documentation comments

2026-06-25 cli/help_text.py
  REASON: sporecast help text outdated, config help referenced download_mode
  FIX:
  - Updated sporecast help with authentication info, inline enumeration for --all, DWR vs REST flow
  - Changed `config get download_mode` example to `config get crawler.requests_per_second`
  - Removed SIZE HINT section (unnecessary clutter)

2026-06-25 cli/commands/config_cmd.py
  REASON: Example referenced removed download_mode config key
  FIX:
  - Changed `config set download_mode sporepedia` to `config set output.download_folder ./downloads`

2026-06-25 cli/config.py
  REASON: Config lacked subtypes list and clean section
  FIX:
  - Added 'subtypes' list to DEFAULT_CONFIG (all 32 subtypes by default)
  - Added 'clean' section with bools: databases, downloads, chunks, config_yaml, crawler_log, credentials, database_txt, test_downloads
  - Added subtypes to DEFAULT_CONFIG_YAML with comments listing all valid values
  - Added subtypes validation to validate_config()
  - Updated all presets (quick, full, safe) to include subtypes

2026-06-25 cli/__init__.py
  REASON: --subtypes didn't default to config; --all didn't work for sporecast
  FIX:
  - Crawl dispatcher now reads subtypes from config['crawler']['subtypes'] when not provided via CLI
  - Sporecast --all now sets use_temp=True to read from sporecasts_temp.txt

2026-06-25 cli/help_text.py
  REASON: Hints didn't reflect current code structures
  FIX:
  - Removed convert-sql from HOTKEYS hint (convert-sql doesn't use hotkeys)
  - Removed HOTKEYS section from convert-sql help text
  - Updated crawl --subtypes help with actual subtype names (was: "e.g. FLYING, AQUATIC")
  - Renamed convert-sql "sporecasts" type to "sporecast" (singular)
  - Removed 'sporecast' as alias for 'search' in convert-sql types

2026-06-25 cli/utilities.py
  REASON: _export_database output lacked color for database name
  FIX:
  - Added green color for "{label} : Found X tables:" line
  - Added yellow color reset for table list output

2026-06-25 cli/__init__.py
  REASON: Removed login status checker thread - was breaking things
  FIX:
  - Removed start_login_status_checker/stop_login_status_checker/reset_login_status imports
  - Removed all stop_login_status_checker() calls from interactive loop and exit paths
  - Removed load_credentials() check and thread startup from main()
  - Login command no longer calls stop/reset_login_status

2026-06-25 cli/__init__.py
  REASON: Major CLI dispatcher rewrite: case-insensitive, argument aliases, clean command
  FIX:
  - Added case-insensitive command matching (StATs = stats, Crawl = crawl)
  - Added argument alias system: --mp/--p for --max-pages, --a for --amount, --s for --size, etc.
  - Added _normalize_arg() and _apply_arg_aliases() helper functions
  - Added clean command import and dispatch
  - Rewrote arg parsing loops to use normalized args list instead of raw sys.argv
  - All command arg parsing now uses .lower() for case-insensitive matching

2026-06-25 cli/help_text.py
  REASON: Help text rewrite, argument aliases, case-insensitive support
  FIX:
  - All help text now uses direct command names (crawl ...) instead of "python -m spore_crawler crawl ..."
  - Added CRAWL_ARG_ALIASES, SPORECAST_ARG_ALIASES, SEARCH_ARG_ALIASES, CONVERT_SQL_ARG_ALIASES, CONFIG_ARG_ALIASES
  - Added clean command help text
  - Updated bean_test help text to document login-first behavior
  - Added cast/dw to sporecast/crawl command aliases
  - Added lookup/look/analyze to search aliases
  - Added ls/lst to list aliases
  - Added auth/signin to login aliases
  - Added sp/sql/cv to convert-sql aliases
  - Added setup to config aliases
  - Added clear/purge to clean aliases
  - Updated COMMAND_ALIASES with all new command aliases from command_aliases.txt

2026-06-25 cli/config.py
  REASON: Config template referenced old invocation style
  FIX:
  - Replaced all "python -m spore_crawler" references with direct command names
  - Updated preset examples, validate references, bean_test references

2026-06-25 cli/__init__.py
  REASON: Status bar auto-login on startup, login command wiring
  FIX:
  - Imports load_credentials to check on startup
  - Starts login_status_checker thread if credentials exist
  - Login command stops/resets checker after execution
  - All exit paths call stop_login_status_checker()

2026-06-25 cli/config.py
  REASON: Credentials stored in credentials.json, not config.yaml
  FIX:
  - Removed 'auth' section from DEFAULT_CONFIG (email field)
  - Removed auth.email from YAML template
  - Updated YAML comments to reference credentials.json

2026-06-25 cli/help_text.py
  REASON: login help text didn't document new --new/--del flags
  FIX:
  - Updated login help to document --new, --del/--rem/--delete/--remove options
  - Removed references to auth.email in config.yaml

2026-06-24 cli/__init__.py
  REASON: Off-by-one IndexError in arg parsing; _dispatch_from_argv returned mixed types
  FIX:
  - crawl/sporecast arg loops: guard changed from `i + 1 < len(sys.argv)` to `i + 3 < len(sys.argv)`
  - bean/bean_test: set _cmd_state['skip_pause'] = True instead of returning string
  - caller: checks _cmd_state.get('skip_pause') instead of result string

2026-06-24 cli/commands/_common.py
  REASON: State dict needed skip_pause flag
  FIX:
  - state dict: added 'skip_pause': False

2026-06-24 cli/config.py
  REASON: Duplicate get_app_dir() removed
  FIX:
  - Removed local get_app_dir(); imports from cli.utilities

2026-06-24 cli/utilities.py
  REASON: Now single source of truth for get_app_dir() and get_resource_dir()
  (No logic changes, just consolidation)
