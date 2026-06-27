"""
cli/__init__.py - Main CLI dispatcher: argv parsing, interactive mode, command routing.

Depends on: cli/config, cli/commands/*, cli/help_text, cli/commands/_common,
            storage/database, cli_ui
Used by: __main__ (entry point)
"""
import asyncio
import sys
import logging

from spore_crawler.cli.config import (
    load_config,
    _setup_early_logging,
)
from spore_crawler.cli.commands import (
    cmd_stats,
    cmd_crawl,
    cmd_sporecast,
    cmd_list,
    cmd_search,
    cmd_browse,
    cmd_login,
    cmd_convert_sql,
    cmd_config,
    cmd_bean,
    cmd_bean_test,
    cmd_clean,
)
from spore_crawler.cli.commands._common import state as _cmd_state
from spore_crawler.cli.help_text import (
    HELP_TEXT,
    COMMAND_HELP,
    COMMAND_ALIASES,
    ALL_COMMANDS,
    CRAWL_ARG_ALIASES,
    SPORECAST_ARG_ALIASES,
    SEARCH_ARG_ALIASES,
    BROWSE_ARG_ALIASES,
    CONVERT_SQL_ARG_ALIASES,
    CONFIG_ARG_ALIASES,
)
from spore_crawler.storage.database import Database
from spore_crawler.api.auth import load_credentials
from spore_crawler.cli_ui import FG_GREEN, print_info

log = logging.getLogger(__name__)


def _reload_config() -> dict:
    """Reload config from disk after config set/apply/reset."""
    from spore_crawler.cli_ui import setup_logging as cli_setup_logging
    config = load_config()
    cli_setup_logging(config)
    return config


def _normalize_command(cmd: str) -> str:
    """Normalize command: replace underscores with hyphens."""
    return cmd.replace('_', '-')


def _normalize_arg(arg: str, arg_aliases: dict) -> str:
    """Normalize argument: apply case-insensitive alias lookup.

    Supports single-dash args by converting -foo to --foo for lookup.
    """
    lower = arg.lower()
    if lower in arg_aliases:
        return arg_aliases[lower]
    if lower.startswith('-') and not lower.startswith('--'):
        double_dash = '--' + lower[1:]
        if double_dash in arg_aliases:
            return arg_aliases[double_dash]
    return arg


def _apply_arg_aliases(argv: list, arg_aliases: dict) -> list:
    """Apply argument aliases and case-insensitive matching to argv slice."""
    result = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith('-'):
            normalized = _normalize_arg(arg, arg_aliases)
            result.append(normalized)
        else:
            result.append(arg)
        i += 1
    return result


def _arg_name(arg: str) -> str:
    """Get the bare argument name by stripping all leading dashes."""
    return arg.lstrip('-')


def _suggest_command(cmd: str) -> str | None:
    """Suggest a command if user made a typo."""
    normalized = _normalize_command(cmd)
    for alias, target in COMMAND_ALIASES.items():
        if alias == normalized or target == normalized:
            return target
    candidates = list(ALL_COMMANDS) + list(COMMAND_ALIASES.keys())
    best = None
    best_dist = 999
    for c in candidates:
        d = _edit_distance(normalized, c)
        if d < best_dist:
            best_dist = d
            best = c
    if best_dist <= 3:
        return best
    return None


def _edit_distance(a: str, b: str) -> int:
    """Simple Levenshtein distance."""
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]


def _dispatch_from_argv(config: dict) -> bool:
    """Dispatch command from sys.argv.

    Returns True if command ran successfully, False on error.
    """
    if len(sys.argv) < 2 or sys.argv[1] in ('--help', '-h', '-help'):
        if len(sys.argv) > 2:
            subcmd = _normalize_command(sys.argv[2])
            if subcmd in COMMAND_ALIASES:
                subcmd = COMMAND_ALIASES[subcmd]
            if subcmd in COMMAND_HELP:
                log.info('Showing help for command: %s', subcmd)
                print(COMMAND_HELP[subcmd])
                return True
            log.warning('Unknown command in help: %s', sys.argv[2])
            print(f"Unknown command: {sys.argv[2]}")
        return True

    cmd = sys.argv[1]

    # Flag without command (e.g. "--search") -> error
    if cmd.startswith('--') and cmd not in ('--help', '-h', '-help'):
        print(f"Unknown command: {cmd}")
        return False

    # Case-insensitive command matching
    cmd_lower = cmd.lower()
    cmd = _normalize_command(cmd_lower)

    if cmd in COMMAND_ALIASES:
        cmd = COMMAND_ALIASES[cmd]

    if len(sys.argv) > 2 and sys.argv[2] in ('--help', '-h', '-help'):
        if cmd in COMMAND_HELP:
            log.info('Showing help for command: %s', cmd)
            print(COMMAND_HELP[cmd])
            return True
        else:
            log.warning('Unknown command: %s', cmd)
            print(f"Unknown command: {cmd}")
            return False

    if cmd not in ALL_COMMANDS:
        suggestion = _suggest_command(cmd)
        log.warning('Unknown command: %s (suggestion: %s)', cmd, suggestion)
        print(f"Unknown command: {cmd}")
        if suggestion:
            print(f"  Did you mean: '{suggestion}'?")
        return False

    log.info('Dispatching command: %s', cmd)

    if cmd == 'stats':
        asyncio.run(cmd_stats())

    elif cmd == 'crawl':
        sort_method = None
        asset_types = None
        subtypes = None
        max_pages = 0
        max_amount = 0
        max_size_mb = 0
        forcestop = False
        save_chunk = None
        load_chunk = None
        skipcheck = False
        list_chunks = False
        use_config_subtypes = False
        use_browse_db = False

        # Apply argument aliases and case normalization
        raw_args = sys.argv[2:]
        args = _apply_arg_aliases(raw_args, CRAWL_ARG_ALIASES)

        for i, arg in enumerate(args):
            an = _arg_name(arg)
            if an == 'sort' and i + 1 < len(args):
                sort_method = args[i + 1].split(',')
            if an == 'views' and i + 1 < len(args):
                sort_method = args[i + 1].split(',')
            if an == 'types' and i + 1 < len(args):
                asset_types = args[i + 1].split(',')
            if an == 'subtypes' and i + 1 < len(args):
                subtypes = args[i + 1].split(',')
            if an == 'max-pages' and i + 1 < len(args):
                try:
                    max_pages = int(args[i + 1])
                except ValueError:
                    print(f"Error: Invalid max-pages value: '{args[i + 1]}'")
                    print('Max-pages must be a number.')
                    return False
            if an == 'amount' and i + 1 < len(args):
                try:
                    max_amount = int(args[i + 1])
                except ValueError:
                    print(f"Error: Invalid amount value: '{args[i + 1]}'")
                    print('Amount must be a number (PNG count).')
                    return False
            if an == 'size' and i + 1 < len(args):
                try:
                    max_size_mb = int(args[i + 1])
                except ValueError:
                    print(f"Error: Invalid size value: '{args[i + 1]}'")
                    print('Size must be a number (megabytes).')
                    return False
            if an == 'forcestop':
                forcestop = True
            if an == 'save-chunk' and i + 1 < len(args):
                save_chunk = args[i + 1]
            if an == 'load-chunk' and i + 1 < len(args):
                load_chunk = args[i + 1]
            if an == 'skipcheck':
                skipcheck = True
            if an == 'list-chunks':
                list_chunks = True
            if an == 'db':
                use_browse_db = True

        if list_chunks:
            db = Database(config['database']['path'])
            chunks_dir = config['database'].get('chunks_dir')
            chunks = db.list_chunks(chunks_dir)
            if not chunks:
                print('No database chunks found.')
                print(f"Chunks directory: {db.get_chunk_dir(chunks_dir)}")
            else:
                print(f"Found {len(chunks)} database chunk(s):")
                print()
                for chunk in chunks:
                    size_mb = chunk['size'] / 1048576
                    print(f"  {chunk['name']}")
                    print(f"    Path: {chunk['path']}")
                    print(f"    Size: {size_mb:.2f} MB")
                    print(f"    Created: {chunk['created']}")
                    print(f"    Assets: {chunk['assets']}")
                    print()
            db.close()
            return True

        limits = sum(1 for x in (max_pages, max_amount, max_size_mb) if x > 0)
        limit_flags = frozenset({'max-pages', 'amount', 'size'})
        any_limit_flag = any(_arg_name(arg).lower() in limit_flags for arg in args)

        if limits > 1:
            print('Error: --max-pages, --amount, and --size cannot be combined.')
            print('Use only one limit at a time.')
            return False

        if not any_limit_flag and not list_chunks and not save_chunk and not load_chunk:
            print('Error: No download limit specified.')
            print('To prevent infinite crawling, please specify at least one limit:')
            print('  --max-pages <n>   Stop after N pages (use 0 for unlimited)')
            print('  --amount <n>      Stop after downloading N PNGs (use 0 for unlimited)')
            print('  --size <n>        Stop after downloading N megabytes (use 0 for unlimited)')
            print()
            print('Examples:')
            print('  crawl --size 1024      # Download 1 GB')
            print('  crawl --amount 1000    # Download 1000 PNGs')
            print('  crawl --max-pages 50   # Crawl 50 pages')
            print('  crawl --amount 0       # Unlimited download')
            print()
            print_info('Type "crawl --help" to see full help section with all options.')
            return False

        if subtypes is None:
            subtypes = config.get('crawler', {}).get('subtypes')

        asyncio.run(cmd_crawl(config, sort_method, asset_types, subtypes, max_pages, max_amount, max_size_mb, forcestop, save_chunk, load_chunk, skipcheck, use_browse_db))

    elif cmd == 'sporecast':
        username = None
        sporecast_id = None
        use_db = False
        use_temp = False
        use_all = False
        keyword = None
        max_size_mb = 0
        max_amount = 0
        max_pages = 0
        sort_method = None
        forcestop = False
        save_chunk = None
        load_chunk = None

        # Apply argument aliases and case normalization
        raw_args = sys.argv[2:]
        args = _apply_arg_aliases(raw_args, SPORECAST_ARG_ALIASES)

        for i, arg in enumerate(args):
            an = _arg_name(arg)
            if an == 'username' and i + 1 < len(args):
                username = args[i + 1]
            if an == 'id' and i + 1 < len(args):
                try:
                    sporecast_id = int(args[i + 1])
                except ValueError:
                    print(f"Error: Invalid sporecast ID: '{args[i + 1]}'")
                    print('Sporecast ID must be a number.')
                    return False
                if sporecast_id > 9223372036854775807:
                    print(f"Error: Sporecast ID too large: '{args[i + 1]}'")
                    print('Sporecast ID must fit in SQLite INTEGER (max 9223372036854775807).')
                    return False
            if an == 'db':
                use_db = True
            if an == 'temp':
                use_temp = True
            if an == 'all':
                use_all = True
                use_temp = True
            if an in ('key', 'k') and i + 1 < len(args):
                keyword = args[i + 1]
            if an == 'size' and i + 1 < len(args):
                try:
                    max_size_mb = int(args[i + 1])
                except ValueError:
                    print(f"Error: Invalid size value: '{args[i + 1]}'")
                    print('Size must be a number (megabytes).')
                    return False
            if an == 'amount' and i + 1 < len(args):
                try:
                    max_amount = int(args[i + 1])
                except ValueError:
                    print(f"Error: Invalid amount value: '{args[i + 1]}'")
                    print('Amount must be a number (PNG count).')
                    return False
            if an == 'max-pages' and i + 1 < len(args):
                try:
                    max_pages = int(args[i + 1])
                except ValueError:
                    print(f"Error: Invalid max-pages value: '{args[i + 1]}'")
                    print('Max-pages must be a number.')
                    return False
            if an == 'sort' and i + 1 < len(args):
                sort_method = args[i + 1].split(',')
            if an == 'forcestop':
                forcestop = True
            if an == 'save-chunk' and i + 1 < len(args):
                save_chunk = args[i + 1]
            if an == 'load-chunk' and i + 1 < len(args):
                load_chunk = args[i + 1]

        limits = sum(1 for x in (max_pages, max_amount, max_size_mb) if x > 0)
        limit_flags = frozenset({'max-pages', 'amount', 'size'})
        any_limit_flag = any(_arg_name(arg).lower() in limit_flags for arg in args)

        if limits > 1:
            print('Error: --max-pages, --amount, and --size cannot be combined.')
            print('Use only one limit at a time.')
            return False

        if not any_limit_flag and not save_chunk and not load_chunk:
            print('Error: No download limit specified.')
            print('To prevent infinite downloading, please specify at least one limit:')
            print('  --max-pages <n>   Stop after N sporecasts (use 0 for unlimited)')
            print('  --amount <n>      Stop after downloading N PNGs (use 0 for unlimited)')
            print('  --size <n>        Stop after downloading N megabytes (use 0 for unlimited)')
            print()
            print('Examples:')
            print('  sporecast --temp --size 4')
            print('  sporecast --temp --amount 100')
            print('  sporecast --temp --max-pages 10')
            print('  sporecast --temp --amount 0  # Unlimited')
            print()
            print_info('Type "sporecast --help" to see full help section with all options.')
            return False

        asyncio.run(cmd_sporecast(config, username, sporecast_id, use_db, use_temp, use_all, keyword, max_size_mb, max_amount, max_pages, sort_method, forcestop, save_chunk, load_chunk))

    elif cmd == 'list':
        username = ''
        search_fields = None
        args_iter = iter(sys.argv[2:])
        for arg in args_iter:
            an = _arg_name(arg)
            if an == 'fields' and username:
                fields_str = next(args_iter, '')
                if fields_str.lower() == 'all':
                    search_fields = []
                else:
                    search_fields = [f.strip() for f in fields_str.split(',') if f.strip()]
            elif not arg.startswith('-'):
                username = arg
        if not username:
            print(COMMAND_HELP['list'])
            return False
        asyncio.run(cmd_list(config, username, search_fields))

    elif cmd == 'login':
        new_creds = False
        delete = False
        for arg in sys.argv[2:]:
            an = _arg_name(arg)
            if an == 'new':
                new_creds = True
            elif an in ('del', 'rem', 'delete', 'remove'):
                delete = True
        asyncio.run(cmd_login(config, new_creds=new_creds, delete=delete))

    elif cmd == 'search':
        search_terms = []
        max_results = 0
        enumerate_all = False
        search_fields = None

        # Apply argument aliases and case normalization
        raw_args = sys.argv[2:]
        args = _apply_arg_aliases(raw_args, SEARCH_ARG_ALIASES)

        i = 0
        while i < len(args):
            arg = args[i]
            an = _arg_name(arg)
            if an == 'max' and i + 1 < len(args):
                try:
                    max_results = int(args[i + 1])
                except ValueError:
                    print(f"Error: Invalid max value: '{args[i + 1]}'")
                    print('Max must be a number.')
                    return False
                i += 2
            elif an == 'all':
                enumerate_all = True
                i += 1
            elif an == 'fields' and i + 1 < len(args):
                fields_str = args[i + 1]
                if fields_str.lower() == 'all':
                    search_fields = []
                else:
                    search_fields = [f.strip() for f in fields_str.split(',') if f.strip()]
                i += 2
            elif not arg.startswith('-'):
                search_terms.append(arg)
                i += 1
            else:
                i += 1

        if not search_terms and not enumerate_all:
            print(COMMAND_HELP['search'])
            return False

        asyncio.run(cmd_search(config, search_terms, max_results, enumerate_all, search_fields))

    elif cmd == 'browse':
        browse_types = []
        filter_method = None
        max_results = 0
        browse_subtypes = None
        enumerate_all = False

        raw_args = sys.argv[2:]
        args = _apply_arg_aliases(raw_args, BROWSE_ARG_ALIASES)

        i = 0
        while i < len(args):
            arg = args[i]
            an = _arg_name(arg)
            if an == 'max' and i + 1 < len(args):
                try:
                    max_results = int(args[i + 1])
                except ValueError:
                    print(f"Error: Invalid max value: '{args[i + 1]}'")
                    print('Max must be a number.')
                    return False
                i += 2
            elif an == 'all':
                enumerate_all = True
                i += 1
            elif an == 'filter' and i + 1 < len(args):
                filter_method = args[i + 1]
                i += 2
            elif an == 'type' and i + 1 < len(args):
                browse_types = [t.strip() for t in args[i + 1].split(',') if t.strip()]
                i += 2
            elif an == 'subtypes' and i + 1 < len(args):
                browse_subtypes = [s.strip() for s in args[i + 1].split(',') if s.strip()]
                i += 2
            elif not arg.startswith('-'):
                browse_types.append(arg)
                i += 1
            else:
                i += 1

        if not browse_types and not enumerate_all:
            print(COMMAND_HELP['browse'])
            return False

        asyncio.run(cmd_browse(config, browse_types or None, filter_method, max_results, browse_subtypes, enumerate_all))

    elif cmd == 'convert-sql':
        if len(sys.argv) < 3:
            print(COMMAND_HELP['convert-sql'])
            return False
        db_type = sys.argv[2].lower()
        # Apply convert-sql argument aliases
        if db_type in CONVERT_SQL_ARG_ALIASES:
            db_type = CONVERT_SQL_ARG_ALIASES[db_type]
        asyncio.run(cmd_convert_sql(config, db_type))

    elif cmd == 'config':
        if len(sys.argv) < 3:
            print(COMMAND_HELP['config'])
            return False
        action = sys.argv[2].lower()
        # Apply config argument aliases
        if action in CONFIG_ARG_ALIASES:
            action = CONFIG_ARG_ALIASES[action]
        args = sys.argv[3:] if len(sys.argv) > 3 else []
        asyncio.run(cmd_config(config, action, args))

    elif cmd == 'clean':
        asyncio.run(cmd_clean(config))

    elif cmd == 'bean_test':
        asyncio.run(cmd_bean_test(config))
        _cmd_state['skip_pause'] = True

    elif cmd == 'bean':
        asyncio.run(cmd_bean())
        _cmd_state['skip_pause'] = True

    return True


def _show_help(config: dict):
    """Print help section to console."""
    if not config.get('bean_test', False):
        help_text = HELP_TEXT.replace('  bean_test             BEAN\n', '')
        print(help_text)
    else:
        print(HELP_TEXT)


def _is_valid_command(user_input: str) -> bool:
    """Check if user input is a known command (before dispatch)."""
    parts = user_input.split()
    if not parts:
        return False
    cmd = parts[0].lower().replace('_', '-')
    if cmd in COMMAND_ALIASES:
        cmd = COMMAND_ALIASES[cmd]
    return cmd in ALL_COMMANDS


def _run_interactive(config: dict, saved_argv: list):
    """Interactive loop: banner + help + @> prompt. Returns False to exit."""
    from spore_crawler.cli_ui import init_cli, pause_for_exit, set_colors, FG_YELLOW, exit_program
    import shlex

    while True:
        set_colors(fg=FG_YELLOW)
        try:
            user_input = input("@> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            exit_program()
            return False

        if user_input.lower() in ('exit', 'quit', 'q'):
            exit_program()
            return False

        # Empty input -> refresh screen
        if not user_input:
            init_cli(config)
            _show_help(config)
            continue

        if 'spore_crawler' in user_input and 'python' in user_input.lower():
            init_cli(config)
            _show_help(config)
            print("Don't run 'python -m spore_crawler' inside the loop.")
            print("Type the command directly, e.g.: stats, crawl --help, config")
            if not pause_for_exit():
                exit_program()
                return False
            init_cli(config)
            _show_help(config)
            continue

        try:
            sys.argv = ['spore_crawler'] + shlex.split(user_input)
        except Exception:
            continue

        # Valid command -> refresh window before execution, show input
        # Wrong command -> skip refresh, show error directly
        if _is_valid_command(user_input):
            init_cli(config)
            print(f"@> {user_input}")

        _cmd_state['used_progress_bar'] = False
        try:
            _dispatch_from_argv(config)
        except SystemExit:
            pass
        except Exception as e:
            import traceback
            log.error('Command error: %s', e)
            log.error('Command traceback:\n%s', traceback.format_exc())
            print(f"Error: {e}")

        sys.argv = saved_argv[:]

        if not pause_for_exit(after_progress=_cmd_state['used_progress_bar']):
            exit_program()
            return False

        # Reload config (may have changed via config set/apply/reset)
        config = _reload_config()

        # Refresh to banner + help for next command
        init_cli(config)
        _show_help(config)


def main():
    from spore_crawler.cli_ui import (
        init_cli, setup_logging as cli_setup_logging, pause_for_exit, exit_program,
    )

    _setup_early_logging()

    config = load_config()

    cli_setup_logging(config)

    log.info("=== Sporepedia Bean's Web Crawler started ===")
    log.info('Args: %s', sys.argv)

    saved_argv = sys.argv[:]

    # No args -> interactive mode: banner + help + @> prompt
    if len(sys.argv) < 2:
        init_cli(config)
        _show_help(config)
        _run_interactive(config, saved_argv)
        return

    # Has args -> run single command, then pause (Enter=Continue, X=Exit)
    init_cli(config)

    _cmd_state['used_progress_bar'] = False

    try:
        _dispatch_from_argv(config)
    except SystemExit:
        pass
    except Exception as e:
        import traceback
        log.error('Command error: %s', e)
        log.error('Command traceback:\n%s', traceback.format_exc())
        print(f"Error: {e}")
    finally:
        sys.argv = saved_argv

    if _cmd_state.get('skip_pause'):
        _cmd_state['skip_pause'] = False
        return

    if not pause_for_exit(after_progress=_cmd_state['used_progress_bar']):
        exit_program()
        return

    # Enter continues -> reload config (may have changed via config set/apply/reset)
    config = _reload_config()
    init_cli(config)
    _show_help(config)
    _run_interactive(config, saved_argv)


__all__ = ["main"]
