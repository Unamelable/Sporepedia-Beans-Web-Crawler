"""
sporecast.py - `sporecast` command: download sporecast assets with limits.

Depends on: api/client, api/auth, storage/database, crawlers/full_crawler,
            models, cli_ui, ui/progress, cli/commands/_common, crawlers/hotkeys
Used by: cli/commands/__init__, cli/__init__

Side effects:
  - Opens Database (sporecasts.db) — must close
  - Starts HotkeyController — must stop
  - Downloads PNG files to disk
  - Sets state['used_progress_bar'] = True
  - (--all) SporeAuth opens/closes Playwright browser
"""
import logging
import threading
from pathlib import Path

from spore_crawler.api.client import SporeAPI
from spore_crawler.api.auth import (
    SporeAuth, get_credentials, get_credentials_interactive,
    save_credentials, load_credentials,
)
from spore_crawler.storage.database import Database
from spore_crawler.crawlers.full_crawler import crawl_sporecast
from spore_crawler.models import Sporecast
from spore_crawler.cli_ui import FG_YELLOW, FG_GREEN, FG_RED, print_info, print_success, print_error
from spore_crawler.ui.progress import print_hotkeys_hint, scroll_print

from spore_crawler.cli.commands._common import (
    get_sporecast_db_path, get_search_db_path, get_browse_db_path, get_temp_file_path,
    _read_temp_file, state,
)

log = logging.getLogger(__name__)


async def _get_user_sporecasts(config: dict, username: str, auth: SporeAuth = None):
    """Fetch sporecasts created by a user via DWR searchSporecastsDWR (requires auth).

    If auth is provided, reuses the existing session (no re-login).
    Otherwise creates and closes its own session.
    """
    log.info("Fetching sporecasts for user '%s' via DWR search", username)

    own_auth = auth is None
    if own_auth:
        creds = get_credentials(config, prompt_if_missing=False)
        if creds:
            email, password = creds
        else:
            saved = load_credentials()
            if saved:
                email, password = saved
            else:
                print_info(f"DWR lookup for '{username}' requires authentication.")
                try:
                    email, password = get_credentials_interactive()
                except (ValueError, EOFError):
                    print_error("Error: Credentials required.")
                    return []

        auth = SporeAuth(email=email, password=password)
        try:
            await auth.login()
            save_credentials(email, password)
            await auth.navigate_to_sporepedia()
        except Exception as e:
            log.error("Login failed: %s", e)
            print_error(f"Login failed: {e}")
            await auth.close()
            return []

    # Search sporecasts by author name via DWR searchSporecastsDWR
    seen_ids = set()
    all_results = []
    index = 0
    try:
        while True:
            result = await auth.search_sporecasts_by_author(username, index=index, max_results=200)
            if not result or 'results' not in result:
                break
            page = result['results']
            if not page:
                break
            new_items = 0
            for item in page:
                item_id = item.get('id')
                if item_id not in seen_ids:
                    seen_ids.add(item_id)
                    all_results.append(item)
                    new_items += 1
            total = result.get('resultSize', 0)
            if new_items == 0 or index + len(page) >= total:
                break
            index += len(page)
    except Exception as e:
        log.error("DWR search failed: %s", e)

    if own_auth:
        await auth.close()

    sporecasts = []
    for r in all_results:
        author_data = r.get('author', {})
        sporecasts.append(Sporecast(
            id=int(r.get('id', 0)),
            title=r.get('title', 'Untitled'),
            author=author_data.get('name', username),
            subtitle=r.get('description', ''),
            rating=str(r.get('rating', 0)),
            asset_count=int(r.get('count', 0)),
            tags=r.get('tags', ''),
            updated=r.get('lastUpdated', ''),
        ))

    log.info("User '%s' sporecasts: %d found", username, len(sporecasts))
    return sporecasts


async def cmd_sporecast(config, username=None, sporecast_id=None, use_db=False, use_temp=False, use_all=False, keyword=None, max_size_mb=0, max_amount=0, max_pages=0, sort_method=None, forcestop=False, save_chunk=None, load_chunk=None):
    from spore_crawler.crawlers.hotkeys import HotkeyController

    cfg = config['crawler']
    output_dir = Path(config['output']['download_folder'])
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info('Command: sporecast')
    log.info('  username=%s, sporecast_id=%s, use_db=%s, use_temp=%s, use_all=%s', username, sporecast_id, use_db, use_temp, use_all)
    log.info('  max_size_mb=%d, max_amount=%d, max_pages=%d', max_size_mb, max_amount, max_pages)
    log.info('  sort_method=%s, forcestop=%s', sort_method, forcestop)
    log.info('  save_chunk=%s, load_chunk=%s', save_chunk, load_chunk)
    log.info('  Output dir: %s', output_dir.absolute())

    sporecast_db_path = get_sporecast_db_path(config)
    download_db = Database(sporecast_db_path)
    sporecast_ids = []

    # Resolve auth early -- needed by --username, --all, --key, and inline enumeration
    needs_auth = use_all or bool(username) or bool(keyword)

    email = None
    password = None
    auth = None

    if needs_auth:
        creds = get_credentials(config, prompt_if_missing=False)
        if creds:
            email, password = creds
            log.info('Using config credentials for: %s', email)
        else:
            print_info("No credentials found for sporecast authentication.")
            print_info("Spore requires EA SSO login to access sporecast data.")
            print()
            print_info("Options:")
            print_info("  1. Run 'login --new' to save credentials")
            print_info("  2. Enter credentials now")
            print()
            try:
                email, password = get_credentials_interactive()
            except (ValueError, EOFError):
                print_error("Error: Credentials required for sporecast operations.")
                download_db.close()
                return

        auth = SporeAuth(email=email, password=password)

        def _auth_status(msg, fg=FG_YELLOW):
            """Show auth status via progress bar (if available) or scroll_print."""
            if 'hotkey' in dir() and hotkey is not None:
                hotkey.progress.current_view = 'Auth'
                hotkey.progress.current_type = msg
                hotkey.progress.render_progress()
            else:
                scroll_print(msg, fg=fg)

        async def ensure_auth():
            """Login and navigate to sporepedia, or relogin if session expired."""
            nonlocal auth
            if auth._logged_in and auth._page:
                valid = await auth.is_session_valid()
                if valid:
                    return True
                log.info("SporeAuth: session expired, relogging in...")
                _auth_status('Relogging in...')
                try:
                    await auth.close()
                except Exception:
                    pass
                auth = SporeAuth(email=email, password=password)
            else:
                log.info("SporeAuth: logging in...")
                _auth_status('Logging in...')
            try:
                await auth.login()
                await auth.navigate_to_sporepedia()
                _auth_status('Logged in', fg=FG_GREEN)
                return True
            except Exception as e:
                log.error('Login failed: %s', e)
                _auth_status(f'Login FAILED: {e}', fg=FG_RED)
                return False

        if not await ensure_auth():
            download_db.close()
            return

    hotkey = HotkeyController()
    hotkey.start()

    _stopped_by_user = threading.Event()
    hotkey.set_stop_callback(lambda: _stopped_by_user.set())

    if sporecast_id:
        log.info('Mode: single sporecast ID=%d', sporecast_id)
        sporecast_ids = [(sporecast_id, f'sporecast_{sporecast_id}', '', '', '', '', '', 0)]
    elif username:
        log.info("Mode: user sporecasts for '%s'", username)
        sporecasts = await _get_user_sporecasts(config, username, auth=auth)
        if not sporecasts:
            log.info('No sporecasts found for user: %s', username)
            print_error(f"No sporecasts found for user: {username}")
            download_db.close()
            return
        log.info('Found %d sporecasts for %s: %s', len(sporecasts), username,
                 [(sc.id, sc.title) for sc in sporecasts])
        print_success(f"Found {len(sporecasts)} sporecasts for {username}:")
        sporecast_ids = [(sc.id, sc.title, sc.author, sc.subtitle, sc.rating, sc.tags, sc.updated, 0) for sc in sporecasts]
    elif use_db:
        log.info('Mode: from search_sporepedia.db or search_sporecast.db')
        search_db = Database(get_search_db_path(config))
        all_scanned = search_db.get_all_scanned_sporecasts()
        if not all_scanned:
            search_db.close()
            browse_db = Database(get_browse_db_path(config))
            all_scanned = browse_db.get_all_scanned_sporecasts()
            db_label = 'search_sporecast.db'
            if not all_scanned:
                browse_db.close()
                log.info('No sporecasts in search or browse database')
                print_error("No sporecasts in search database. Run 'search' or 'browse' first.")
                download_db.close()
                return
        else:
            db_label = 'search_sporepedia.db'
        sporecast_ids = [(s['sporecast_id'], s['title'], s.get('author', ''), '', '', '', '', s.get('subscribers', 0)) for s in all_scanned]
        log.info('Loaded %d sporecasts from %s: %s', len(sporecast_ids), db_label,
                 [(s[0], s[1]) for s in sporecast_ids[:10]])
        print_info(f"Loaded {len(sporecast_ids)} sporecasts from {db_label}")
        search_db.close()
    elif use_temp:
        log.info('Mode: from sporecasts_temp.txt')
        temp_file = get_temp_file_path(config)
        if not temp_file.exists():
            if use_all:
                log.info('Temp file missing, running inline enumeration + download for --all')
                import asyncio, re as _re
                from spore_crawler.cli.commands.search import _parse_sporecast_dwr_response

                search_db = Database(get_search_db_path(config))
                scroll_print("No sporecasts_temp.txt found. Running enumeration for --all...", fg=FG_YELLOW)

                enum_index = 0
                batch_id = 100
                all_ids = set()
                all_sporecasts = []
                processed = 0
                total_downloaded = 0
                total_bytes = 0

                try:
                    r = await auth.make_dwr_call("sporecastService", "countSporecastInfo",
                        {"type": "THEME"}, batch_id)
                    batch_id += 1
                    body = r.get("body", "")
                    count_match = _re.search(r"_remoteHandleCallback\('(\d+)','(\d+)',(\d+)\);", body)
                    total_count = int(count_match.group(3)) if count_match else None
                except Exception as e:
                    log.error('Failed to get total count: %s', e)
                    scroll_print(f"Failed to get total sporecast count: {e}", fg=FG_RED)
                    download_db.close()
                    search_db.close()
                    return

                if total_count is None:
                    scroll_print("Error: Could not retrieve total sporecast count.", fg=FG_RED)
                    download_db.close()
                    search_db.close()
                    return

                scroll_print(f"Total THEME sporecasts on platform: {total_count}", fg=FG_GREEN)

                hotkey.progress.current_view = 'enumerate'
                hotkey.progress.current_type = f'0/{total_count}'
                hotkey.progress.render_progress()

                errors = 0
                empty_streak = 0
                async with SporeAPI(
                    requests_per_second=cfg['requests_per_second'],
                    timeout=cfg['request_timeout'],
                    max_retries=cfg['max_retries'],
                ) as api:
                    while enum_index < total_count:
                        if hotkey.should_stop():
                            break
                        await hotkey.async_wait_if_paused()
                        if hotkey.should_stop():
                            break

                        hotkey.progress.current_type = f'{enum_index}/{total_count}'
                        hotkey.progress.render_progress()

                        try:
                            r = await auth.make_dwr_call("sporecastService", "listSporecastInfos",
                                {"showEmpty": True, "count": 200, "index": enum_index}, batch_id)
                            batch_id += 1
                            if not r.get("ok"):
                                errors += 1
                                if errors >= 5:
                                    scroll_print("Too many errors, stopping.", fg=FG_RED)
                                    break
                                enum_index += 200
                                await asyncio.sleep(2)
                                continue
                            body = r.get("body", "")
                            page_sporecasts = _parse_sporecast_dwr_response(body)
                            if not page_sporecasts:
                                empty_streak += 1
                                if empty_streak >= 3:
                                    scroll_print("Too many empty responses, stopping.", fg=FG_RED)
                                    break
                                enum_index += 200
                                await asyncio.sleep(2)
                                continue
                            empty_streak = 0
                            errors = 0
                            for sc in page_sporecasts:
                                if hotkey.should_stop():
                                    break
                                if sc['id'] in all_ids or download_db.is_sporecast_downloaded(sc['id']):
                                    continue
                                if search_db.is_sporecast_scanned(sc['id']):
                                    continue
                                all_ids.add(sc['id'])
                                all_sporecasts.append(sc)
                                search_db.record_sporecast_scan(
                                    sc['id'], sc.get('title', ''),
                                    sc.get('author', ''), sc.get('asset_count', 0),
                                    sc.get('subscribers', 0),
                                )

                                sc_id = sc['id']
                                sc_title = sc.get('title', 'Untitled')
                                sc_author = sc.get('author', '')
                                sc_desc = sc.get('description', '')
                                sc_rating = str(sc.get('rating', ''))
                                sc_tags = sc.get('tags', '')
                                sc_updated = sc.get('last_updated', '')
                                sc_subs = int(sc.get('subscribers', 0) or 0)

                                log.info("Downloading sporecast [%d] '%s' (%d/%d)", sc_id, sc_title, processed + 1, total_count)
                                hotkey.progress.current_view = 'sporecast'
                                hotkey.progress.current_type = sc_title[:30]
                                hotkey.progress.render_progress()

                                count, bytes_downloaded = await crawl_sporecast(
                                    api, download_db, output_dir, sc_id, sc_title,
                                    sporecast_author=sc_author,
                                    sporecast_subtitle=sc_desc,
                                    sporecast_rating=sc_rating,
                                    sporecast_tags=sc_tags,
                                    sporecast_updated=sc_updated,
                                    sporecast_subscribers=sc_subs,
                                    page_size=cfg['page_size'],
                                    max_concurrent_downloads=cfg.get('max_concurrent_downloads', 5),
                                    embed_metadata=config['output'].get('embed_metadata', True),
                                    hotkey=hotkey,
                                )
                                processed += 1
                                total_downloaded += count
                                total_bytes += bytes_downloaded

                                hotkey.progress.downloaded = total_downloaded
                                hotkey.progress.page = processed
                                hotkey.progress.render_progress()

                            log.info('Page index=%d: got %d, new %d, total %d', enum_index, len(page_sporecasts), len(all_sporecasts), len(all_ids))
                            enum_index += 200
                            await asyncio.sleep(2)
                        except Exception as e:
                            errors += 1
                            log.error('Error at index=%d: %s', enum_index, e)
                            if errors >= 5:
                                scroll_print(f"Too many errors ({errors}), stopping.", fg=FG_RED)
                                break
                            enum_index += 200
                            await asyncio.sleep(2)

                all_sporecasts.sort(key=lambda sc: sc.get('subscribers', 0), reverse=True)
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write('# Sporecast IDs discovered by --all enumeration\n')
                    f.write(f"# Total: {len(all_sporecasts)}\n\n")
                    for sc in all_sporecasts:
                        f.write(f"{sc['id']}\t{sc.get('asset_count', 0)}\t{sc.get('subscribers', 0)}\t{sc.get('author', '')}\t{sc.get('title', '')}\t{sc.get('description', '')}\t{sc.get('rating', '')}\t{sc.get('tags', '')}\t{sc.get('last_updated', '')}\n")
                log.info('Saved %d sporecasts to %s', len(all_sporecasts), temp_file)
                scroll_print(f"Saved {len(all_sporecasts)} sporecasts to {temp_file}", fg=FG_GREEN)
                search_db.close()

                result_lines = [f"Processed: {processed} sporecasts"]
                result_lines.append(f"Downloaded: {total_downloaded} PNGs ({total_bytes / 1024 / 1024:.2f} MB)")
                result_lines.append(f"Database: {download_db.get_total_downloaded()} assets tracked")
                hotkey.stop()
                print_results(result_lines)
                download_db.close()
                state['used_progress_bar'] = True
                return
            else:
                log.warning('Temp file not found: %s', temp_file)
                print_error(f"File not found: {temp_file}")
                print_info("Run 'search' command first to generate sporecasts_temp.txt")
                download_db.close()
                return
        else:
            sporecast_ids = _read_temp_file(temp_file)
            if not sporecast_ids:
                log.info('No sporecast IDs found in %s', temp_file)
                print_error(f"No sporecast IDs found in {temp_file}")
                download_db.close()
                return
            log.info('Loaded %d sporecasts from temp file: %s', len(sporecast_ids),
                     [(s[0], s[1]) for s in sporecast_ids[:10]])
            print_info(f"Loaded {len(sporecast_ids)} sporecasts from sporecasts_temp.txt")

    elif keyword:
        log.info('Mode: keyword search for "%s"', keyword)
        search_mode = cfg.get('sporecast_search_mode', 'batch')
        log.info('Search mode: %s', search_mode)

        if search_mode == 'sequential':
            # Sequential mode: search one, download next, repeat
            log.info('Using sequential mode: search one sporecast, download, repeat')
            scroll_print(f"Sequential mode: searching sporecasts for '{keyword}'...")
            search_cfg = config.get('crawler', {}).get('search_fields', [])
            seen_ids = set()
            search_index = 0
            sporecast_ids = []
            sequential_done = False
        else:
            # Batch mode: enumerate all first, then download
            log.info('Using batch mode: enumerate all sporecasts, then download')
            scroll_print(f"Searching sporecasts for keyword '{keyword}'...")
            search_cfg = config.get('crawler', {}).get('search_fields', [])
            seen_ids = set()
            search_index = 0
            sporecast_ids = []
            sequential_done = True  # Will be set after search completes
        try:
            while True:
                result = await auth.search_sporecasts(
                    search_text=keyword,
                    fields=search_cfg if search_cfg else None,
                    index=search_index,
                    max_results=200,
                )
                if not result or 'results' not in result:
                    break
                page = result['results']
                if not page:
                    break
                for item in page:
                    item_id = item.get('id')
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)
                    author_data = item.get('author', {})
                    author_name = author_data.get('name', '') if isinstance(author_data, dict) else str(author_data)
                    sporecast_ids.append((
                        item_id,
                        item.get('title', ''),
                        author_name,
                        item.get('description', ''),
                        str(item.get('rating', '')),
                        item.get('tags', ''),
                        item.get('lastUpdated', ''),
                        int(item.get('subscriptionCount', 0) or 0),
                    ))
                total = result.get('resultSize', 0)
                if search_index + len(page) >= total:
                    break
                search_index += len(page)
            log.info('Keyword search found %d sporecasts for "%s"', len(sporecast_ids), keyword)
            if not sequential_done:
                print_success(f"Found {len(sporecast_ids)} sporecasts for keyword '{keyword}'")
        except Exception as e:
            log.error("Keyword search failed: %s", e)
            print_error(f"Keyword search failed: {e}")

    if not sporecast_ids:
        download_db.close()
        print_error('No sporecast source specified.')
        print_info('Use --username <user>, --id <id>, --db, --temp, --all, or --key <keyword>')
        print_info('(--all requires running search --all first to populate sporecasts_temp.txt)')
        print_info('Use --key <keyword> to search and download sporecasts by keyword.')
        return

    if not sporecast_ids:
        log.info('No sporecasts to process')
        print_info('No sporecasts to process.')
        download_db.close()
        return

    log.info('Processing %d sporecasts: %s', len(sporecast_ids),
             sporecast_ids[:20])
    print_info(f"Processing {len(sporecast_ids)} sporecasts...")

    if max_size_mb:
        print_info(f"Size limit: {max_size_mb} MB (will finish current sporecast on limit)")
    if max_amount:
        print_info(f"Amount limit: {max_amount} PNGs (will finish current sporecast on limit)")
    if max_pages:
        print_info(f"Max pages: {max_pages}")
    if forcestop:
        print_info("Forcestop: ON (stop all when limit hit)")

    hotkey.progress.set_status(hotkey.progress.STATUS_RUNNING)
    hotkey.progress.render_progress()
    print_hotkeys_hint()

    try:
        async with SporeAPI(
            requests_per_second=cfg['requests_per_second'],
            timeout=cfg['request_timeout'],
            max_retries=cfg['max_retries'],
        ) as api:
            processed = 0
            total_downloaded = 0
            total_bytes = 0
            total_pages = 0
            limit_reached = False
            stop_all = False

            idx = 0
            while idx < len(sporecast_ids) or (keyword and search_mode == 'sequential' and not sequential_done):
                if hotkey.should_stop() or stop_all:
                    break

                if limit_reached:
                    log.info('Limit reached, skipping remaining sporecasts')
                    break

                # Sequential mode: search for next sporecast on each iteration
                if keyword and search_mode == 'sequential' and idx >= len(sporecast_ids):
                    # Search for next sporecast
                    next_sporecast = None
                    while not next_sporecast and not sequential_done:
                        try:
                            result = await auth.search_sporecasts(
                                search_text=keyword,
                                fields=search_cfg if search_cfg else None,
                                index=search_index,
                                max_results=200,
                            )
                            if not result or 'results' not in result:
                                sequential_done = True
                                break
                            page = result['results']
                            if not page:
                                sequential_done = True
                                break
                            for item in page:
                                item_id = item.get('id')
                                if item_id in seen_ids:
                                    continue
                                seen_ids.add(item_id)
                                author_data = item.get('author', {})
                                author_name = author_data.get('name', '') if isinstance(author_data, dict) else str(author_data)
                                next_sporecast = (
                                    item_id,
                                    item.get('title', ''),
                                    author_name,
                                    item.get('description', ''),
                                    str(item.get('rating', '')),
                                    item.get('tags', ''),
                                    item.get('lastUpdated', ''),
                                    int(item.get('subscriptionCount', 0) or 0),
                                )
                                break
                            total = result.get('resultSize', 0)
                            if search_index + len(page) >= total:
                                sequential_done = True
                            else:
                                search_index += len(page)
                        except Exception as e:
                            log.error("Sequential search failed: %s", e)
                            sequential_done = True
                            break

                    if not next_sporecast:
                        log.info('Sequential search: no more sporecasts found')
                        break

                    # Add to processing list
                    sporecast_ids.append(next_sporecast)
                    sc_id, sc_title, sc_author, sc_subtitle, sc_rating, sc_tags, sc_updated, sc_subscribers = next_sporecast
                    log.info("Sequential: found sporecast [%d] '%s'", sc_id, sc_title)
                else:
                    # Batch mode: use pre-populated list
                    sc_id, sc_title, sc_author, sc_subtitle, sc_rating, sc_tags, sc_updated, sc_subscribers = sporecast_ids[idx]

                if download_db.is_sporecast_downloaded(sc_id):
                    log.info("Sporecast [%d] '%s' already fully downloaded (checkpoint), skipping", sc_id, sc_title)
                    processed += 1
                    idx += 1
                    continue

                log.info("Processing sporecast [%d] '%s' (%d/%d)", sc_id, sc_title, idx + 1, len(sporecast_ids))

                count, bytes_downloaded = await crawl_sporecast(
                    api, download_db, output_dir, sc_id, sc_title,
                    sporecast_author=sc_author,
                    sporecast_subtitle=sc_subtitle,
                    sporecast_rating=sc_rating,
                    sporecast_tags=sc_tags,
                    sporecast_updated=sc_updated,
                    sporecast_subscribers=sc_subscribers,
                    page_size=cfg['page_size'],
                    max_concurrent_downloads=cfg.get('max_concurrent_downloads', 5),
                    embed_metadata=config['output'].get('embed_metadata', True),
                    hotkey=hotkey,
                )
                processed += 1
                total_downloaded += count
                total_bytes += bytes_downloaded
                total_pages += 1
                idx += 1

                if hotkey.pause_event.is_set():
                    log.info('Pause active after sporecast %d, waiting for resume', processed)
                    await hotkey.async_wait_if_paused()
                    if hotkey.should_stop():
                        break

                if max_amount and total_downloaded >= max_amount:
                    log.info('Amount limit reached (%d >= %d), finishing', total_downloaded, max_amount)
                    limit_reached = True
                if max_size_mb and total_bytes >= max_size_mb * 1024 * 1024:
                    log.info('Size limit reached (%.2f MB >= %d MB), finishing', total_bytes / 1024 / 1024, max_size_mb)
                    limit_reached = True
                if max_pages and total_pages >= max_pages:
                    log.info('Max pages reached (%d >= %d), finishing', total_pages, max_pages)
                    limit_reached = True

                if forcestop and limit_reached:
                    log.info('Forcestop triggered: stopping all sporecasts')
                    scroll_print('Forcestop: limit reached, stopping all sporecasts.', fg=FG_YELLOW)
                    stop_all = True

    finally:
        if needs_auth and auth:
            try:
                await auth.close()
            except Exception:
                pass

    hotkey.stop()

    from spore_crawler.ui.progress import print_results

    result_lines = []

    if _stopped_by_user.is_set():
        result_lines.append("Stopping...")
        result_lines.append("Progress has been saved.")

    result_lines.append(f"Processed: {processed} sporecasts")
    if max_size_mb or max_amount or max_pages:
        result_lines.append(f"Downloaded: {total_downloaded} PNGs ({total_bytes / 1024 / 1024:.2f} MB)")
    if limit_reached:
        result_lines.append("Limit reached - stopped after finishing current sporecast")

    if save_chunk:
        result_lines.append(f"Saving database chunk: {save_chunk}")
        log.info('Saving chunk: %s', save_chunk)
        chunks_dir = config['database'].get('chunks_dir')
        chunk_path = download_db.save_chunk(save_chunk, chunks_dir)
        result_lines.append(f"Chunk saved to: {chunk_path}")
        result_lines.append(f"  Sporecasts in database: {download_db.get_total_downloaded()}")

    log.info('Command: sporecast completed. Processed: %d, downloaded: %d (%.2f MB), limit_reached=%s',
             processed, total_downloaded, total_bytes / 1024 / 1024, limit_reached)
    print_results(result_lines)
    download_db.close()
    state['used_progress_bar'] = True
