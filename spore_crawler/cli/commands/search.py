"""
search.py - `search` command: keyword search + --all THEME enumeration via DWR.

Depends on: api/client, api/auth, storage/database, ui/progress, cli_ui,
            cli/commands/_common, crawlers/hotkeys
Used by: cli/commands/__init__, cli/__init__

Side effects:
  - Opens Database (search_sporepedia.db) — must close
  - Starts HotkeyController — must stop
  - Writes sporecasts_temp.txt
  - Sets state['used_progress_bar'] = True
  - (--all) SporeAuth opens/closes Playwright browser
"""
import re
import asyncio
import logging
import threading
from pathlib import Path

from spore_crawler.api.auth import (
    SporeAuth, get_credentials, get_credentials_interactive,
    save_credentials, load_credentials,
)
from spore_crawler.storage.database import Database
from spore_crawler.ui.progress import print_hotkeys_hint, scroll_print, print_results
from spore_crawler.cli_ui import FG_GREEN, FG_YELLOW, FG_RED

from spore_crawler.cli.commands._common import (
    get_search_db_path, get_temp_file_path, state,
)

log = logging.getLogger(__name__)


def _parse_dwr_sporecast_list(text: str) -> list[dict]:
    """Parse DWR response from listSporecastInfosSubscribedToByUser or searchSporecastsDWR."""
    sporecasts = {}
    for m in re.finditer(r'(s\d+)\.id=(50\d{10})', text):
        var_name = m.group(1)
        sporecasts[var_name] = {"id": m.group(2)}
    for m in re.finditer(r'(s\d+)\.title="([^"]*)"', text):
        if m.group(1) in sporecasts:
            sporecasts[m.group(1)]["title"] = m.group(2)
    for m in re.finditer(r'(s\d+)\.count=(\d+)', text):
        if m.group(1) in sporecasts:
            sporecasts[m.group(1)]["asset_count"] = int(m.group(2))
    for m in re.finditer(r'(s\d+)\.subscriptionCount=(\d+)', text):
        if m.group(1) in sporecasts:
            sporecasts[m.group(1)]["subscribers"] = int(m.group(2))
    for m in re.finditer(r'(s\d+)\.author=s(\d+)', text):
        if m.group(1) in sporecasts:
            sporecasts[m.group(1)]["author_ref"] = m.group(2)
    # Extract author names
    for m in re.finditer(r's(\d+)\.name="([^"]*)"', text):
        for sc_var, sc in sporecasts.items():
            if sc.get("author_ref") == m.group(1):
                sc["author"] = m.group(2)
    return [sc for sc in sporecasts.values() if "id" in sc and "title" in sc]


def _parse_sporecast_dwr_response(text: str) -> list[dict]:
    """Parse DWR response from listSporecastInfos and extract sporecast objects."""
    sporecasts = []

    pattern = re.compile(
        r's(\d+)\.assetIds=[^;]*;'
        r's\1\.assets=[^;]*;'
        r's(\d+)\.author=s(\d+);'
        r's\1\.count=(\d+);'
        r's(\d+)\.description=([^;]*);'
        r's\1\.featured=[^;]*;'
        r's(\d+)\.id=(\d+);'
        r's(\d+)\.lastUpdated=([^;]*);'
        r's(\d+)\.locale=[^;]*;'
        r's(\d+)\.rating=([^;]*);'
        r's(\d+)\.sporecastId=s(\d+);'
        r's(\d+)\.subscribed=[^;]*;'
        r's(\d+)\.subscriptionCount=(\d+);'
        r's(\d+)\.tags=([^;]*);'
        r's(\d+)\.title=([^;]*);'
        r's(\d+)\.type=([^;]*);'
    )

    for m in pattern.finditer(text):
        var_name = m.group(1)
        author_ref = m.group(3)
        count = int(m.group(4))
        description = m.group(6).strip("'\"") if m.group(6) not in ('null', '') else None
        sporecast_id = int(m.group(8))
        last_updated = m.group(10).strip("'\"") if m.group(10) not in ('null', '') else None
        rating = m.group(12).strip("'\"") if m.group(12) not in ('null', '') else None
        subscription_count = int(m.group(15))
        tags = m.group(17).strip("'\"") if m.group(17) not in ('null', '') else None
        title = m.group(19).strip("'\"") if m.group(19) not in ('null', '') else None
        sporecast_type = m.group(21).strip("'\"") if m.group(21) not in ('null', '') else None

        author_match = re.search(
            rf's{author_ref}\.id=(\d+);'
            rf's{author_ref}\.[\'default\']=([^;]*);'
            rf's{author_ref}\.name="([^"]*)";'
            rf's{author_ref}\.screenName="([^"]*)";',
            text
        )

        author = ""
        if author_match:
            author = author_match.group(3)

        sporecasts.append({
            'id': sporecast_id,
            'title': title or '',
            'author': author,
            'asset_count': count,
            'subscribers': subscription_count,
            'description': description or '',
            'tags': tags or '',
            'rating': rating or '',
            'last_updated': last_updated or '',
        })

    return sporecasts


async def cmd_search(config: dict, search_terms: list[str], max_results: int = 0, enumerate_all: bool = False, search_fields: list[str] | None = None):
    from spore_crawler.crawlers.hotkeys import HotkeyController

    # Resolve search fields: CLI argument > config > all fields
    if search_fields is None:
        search_fields = config.get('crawler', {}).get('search_fields', [])

    output_dir = Path(config['output']['download_folder'])
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info('Command: search')
    log.info('  Search terms: %s', search_terms)
    log.info('  Max results per term: %d', max_results)
    log.info('  Enumerate all: %s', enumerate_all)
    log.info('  Search fields: %s', search_fields if search_fields else 'ALL')
    log.info('  Output dir: %s', output_dir.absolute())

    db = Database(get_search_db_path(config))
    temp_file = get_temp_file_path(config)
    all_sporecasts = []
    all_ids = set()
    skipped = 0

    log.info('Search DB: %s (existing scanned: %d)', get_search_db_path(config),
             db.get_scanned_sporecast_count())

    if not enumerate_all:
        for term in search_terms:
            if len(term) <= 1:
                print(f"Warning: Search term '{term}' is too short (single character). The server will return no results for single symbols.")
                print("Use at least 2 characters for meaningful search results.")

    hotkey = HotkeyController()

    # Resolve credentials upfront before starting hotkey/progress display
    email = None
    password = None
    creds = get_credentials(config, prompt_if_missing=False)
    if creds:
        email, password = creds
        log.info('Using saved credentials for: %s', email)
    else:
        saved = load_credentials()
        if saved:
            email, password = saved
            log.info('Using saved credentials for: %s', email)
        else:
            print("Search requires authentication (EA SSO login).")
            print()
            try:
                email, password = get_credentials_interactive()
            except (ValueError, EOFError):
                print("Error: Credentials required.")
                db.close()
                return
            save_credentials(email, password)

    auth = SporeAuth(email=email, password=password)

    async def ensure_auth():
        nonlocal auth
        if auth._logged_in and auth._page:
            valid = await auth.is_session_valid()
            if valid:
                return True
            scroll_print("Session expired, relogging in...", fg=FG_YELLOW)
            await auth.close()
            auth = SporeAuth(email=email, password=password)
        else:
            auth = SporeAuth(email=email, password=password)
        try:
            await auth.login()
            await auth.navigate_to_sporepedia()
            scroll_print("Logged in!", fg=FG_GREEN)
            return True
        except Exception as e:
            log.error('Login failed: %s', e)
            scroll_print(f"Login failed: {e}", fg=FG_RED)
            return False

    scroll_print("Logging in...", fg=FG_GREEN)
    if not await ensure_auth():
        db.close()
        return

    # Now start hotkey/progress display after login is done
    hotkey.start()

    _stopped_by_user = threading.Event()
    hotkey.set_stop_callback(lambda: _stopped_by_user.set())

    hotkey.progress.set_status(hotkey.progress.STATUS_RUNNING)
    hotkey.progress.render_progress()
    print_hotkeys_hint()

    if enumerate_all:
        PAGE_SIZE = 200
        batch_id = 100

        try:
            r = await auth.make_dwr_call("sporecastService", "countSporecastInfo",
                {"type": "THEME"}, batch_id)
            batch_id += 1
            body = r.get("body", "")
            count_match = re.search(r"_remoteHandleCallback\('(\d+)','(\d+)',(\d+)\);", body)
            total_count = int(count_match.group(3)) if count_match else None
        except Exception as e:
            log.error('Failed to get total count: %s', e)
            scroll_print(f"Failed to get total sporecast count: {e}", fg=FG_RED)
            hotkey.stop()
            db.close()
            return

        if total_count is None:
            scroll_print("Error: Could not retrieve total sporecast count.", fg=FG_RED)
            hotkey.stop()
            db.close()
            return

        scroll_print(f"Total THEME sporecasts on platform: {total_count}", fg=FG_GREEN)
        log.info('Total THEME sporecasts: %d', total_count)

        index = 0
        errors = 0
        empty_streak = 0

        while index < total_count:
            if hotkey.should_stop():
                break

            await hotkey.async_wait_if_paused()
            if hotkey.should_stop():
                break

            log.info('Fetching sporecast page index=%d (batch=%d)', index, batch_id)
            hotkey.progress.current_view = 'enumerate'
            hotkey.progress.current_type = f'{index}/{total_count}'
            hotkey.progress.downloaded = len(all_sporecasts)
            hotkey.progress.skipped = skipped
            hotkey.progress.page = index // PAGE_SIZE
            hotkey.progress.category_bytes = 0
            hotkey.progress.render_progress()

            try:
                r = await auth.make_dwr_call("sporecastService", "listSporecastInfos",
                    {"showEmpty": True, "count": PAGE_SIZE, "index": index}, batch_id)
                batch_id += 1

                if not r.get("ok"):
                    errors += 1
                    log.warning('DWR call failed: %s', r.get("error", "unknown"))
                    if errors >= 5:
                        scroll_print("Too many errors, stopping.", fg=FG_RED)
                        break
                    scroll_print("Session may have expired, re-authenticating...", fg=FG_YELLOW)
                    if not await ensure_auth():
                        scroll_print("Re-authentication failed, stopping.", fg=FG_RED)
                        break
                    index += PAGE_SIZE
                    await asyncio.sleep(2)
                    continue

                body = r.get("body", "")
                page_sporecasts = _parse_sporecast_dwr_response(body)

                if not page_sporecasts:
                    empty_streak += 1
                    log.info('Empty page at index=%d (streak=%d)', index, empty_streak)
                    if empty_streak >= 3:
                        scroll_print("Too many empty responses, stopping.", fg=FG_RED)
                        break
                    index += PAGE_SIZE
                    await asyncio.sleep(2)
                    continue

                empty_streak = 0
                errors = 0
                new_count = 0
                for sc in page_sporecasts:
                    if sc['id'] in all_ids:
                        continue
                    if db.is_sporecast_scanned(sc['id']):
                        skipped += 1
                        continue

                    all_ids.add(sc['id'])
                    all_sporecasts.append(sc)
                    new_count += 1

                    db.record_sporecast_scan(
                        sc['id'],
                        sc.get('title', ''),
                        sc.get('author', ''),
                        sc.get('asset_count', 0),
                        sc.get('subscribers', 0),
                    )

                    sc_title = sc.get('title', '?')
                    sc_author = sc.get('author', '?')
                    sc_assets = sc.get('asset_count', 0)
                    sc_subs = sc.get('subscribers', 0)
                    log.info('  [%s] %s by %s (%d assets, %d subs)', sc['id'], sc_title, sc_author, sc_assets, sc_subs)

                    hotkey.update_progress(
                        downloaded=len(all_sporecasts),
                        skipped=skipped,
                        page=index // PAGE_SIZE,
                    )
                    hotkey.progress.render_progress()

                log.info('Page index=%d: got %d, new %d, total %d', index, len(page_sporecasts), new_count, len(all_sporecasts))
                scroll_print(f"Page {index // PAGE_SIZE + 1}: +{new_count} new (total: {len(all_sporecasts)}/{total_count})", fg=FG_GREEN)
                hotkey.update_progress(downloaded=len(all_sporecasts), skipped=skipped, page=index // PAGE_SIZE)
                hotkey.progress.render_progress()

                index += PAGE_SIZE
                for countdown in range(3, 0, -1):
                    if hotkey.should_stop():
                        break
                    hotkey.progress.current_type = f'Next page in {countdown}s'
                    hotkey.progress.render_progress()
                    await asyncio.sleep(1)

            except Exception as e:
                errors += 1
                log.error('Error at index=%d: %s', index, e)
                if errors >= 5:
                    scroll_print(f"Too many errors ({errors}), stopping.", fg=FG_RED)
                    break
                scroll_print("Error, re-authenticating...", fg=FG_YELLOW)
                if not await ensure_auth():
                    scroll_print("Re-authentication failed, stopping.", fg=FG_RED)
                    break
                index += PAGE_SIZE
                await asyncio.sleep(2)

        try:
            await auth.close()
        except Exception:
            pass

    else:
        try:
            for term in search_terms:
                if hotkey.should_stop():
                    break

                await hotkey.async_wait_if_paused()

                if hotkey.should_stop():
                    break

                log.info('Searching term: "%s" via DWR searchSporecastsByAuthor', term)
                hotkey.progress.current_view = 'search'
                hotkey.progress.current_type = term[:20]
                hotkey.progress.category_bytes = 0
                hotkey.progress.render_progress()

                seen_ids = set()
                index = 0
                while True:
                    if hotkey.should_stop():
                        break
                    await hotkey.async_wait_if_paused()
                    if hotkey.should_stop():
                        break

                    result = await auth.search_sporecasts(
                        search_text=term,
                        fields=search_fields,
                        index=index,
                        max_results=200,
                    )
                    if not result or 'results' not in result:
                        break
                    page = result['results']
                    if not page:
                        break

                    new_count = 0
                    for item in page:
                        if hotkey.should_stop():
                            break
                        item_id = item.get('id')
                        if item_id in seen_ids or item_id in all_ids:
                            continue
                        if db.is_sporecast_scanned(item_id):
                            skipped += 1
                            continue

                        seen_ids.add(item_id)
                        all_ids.add(item_id)
                        author_data = item.get('author', {})
                        sc = {
                            'id': item_id,
                            'title': item.get('title', ''),
                            'author': author_data.get('name', '') if isinstance(author_data, dict) else str(author_data),
                            'asset_count': item.get('count', 0),
                            'subscribers': item.get('subscriptionCount', 0),
                        }
                        all_sporecasts.append(sc)
                        new_count += 1

                        db.record_sporecast_scan(
                            sc['id'],
                            sc.get('title', ''),
                            sc.get('author', ''),
                            sc.get('asset_count', 0),
                            sc.get('subscribers', 0),
                        )

                        log.info('New sporecast: [%s] "%s" by %s (%d assets, %d subs)',
                                 sc['id'], sc.get('title', ''), sc.get('author', ''),
                                 sc.get('asset_count', 0), sc.get('subscribers', 0))

                        hotkey.update_progress(
                            downloaded=len(all_sporecasts),
                            skipped=skipped,
                            page=(index // 200) + 1,
                        )
                        hotkey.progress.render_progress()

                    total = result.get('resultSize', 0)
                    log.info('Term "%s" page index=%d: got %d, new %d, total %d/%d',
                             term, index, len(page), new_count, len(all_sporecasts), total)

                    if index + len(page) >= total:
                        break
                    index += len(page)

        finally:
            try:
                await auth.close()
            except Exception:
                pass

    hotkey.stop()

    result_lines = []

    if _stopped_by_user.is_set():
        result_lines.append("Stopping...")
        result_lines.append("Progress has been saved.")

    if skipped > 0:
        log.info('Skipped %d already-scanned sporecasts', skipped)

    if not all_sporecasts:
        log.info('No new sporecasts found')
        print_results([
            'No new sporecasts found.',
            f"Database: {db.get_scanned_sporecast_count()} scanned sporecasts",
        ])
        db.close()
        state['used_progress_bar'] = True
        return

    all_sporecasts.sort(key=lambda sc: sc.get('subscribers', 0), reverse=True)

    log.info('Search complete: %d unique new sporecasts found', len(all_sporecasts))
    log.info('Top 5 by subscribers: %s',
             [(sc['id'], sc.get('title', ''), sc.get('subscribers', 0)) for sc in all_sporecasts[:5]])

    with open(temp_file, 'w', encoding='utf-8') as f:
        f.write('# Sporecast IDs discovered by search\n')
        f.write(f"# Total: {len(all_sporecasts)}\n")
        f.write('# Usage: sporecast --temp\n\n')
        for sc in all_sporecasts:
            sc_id = sc['id']
            title = sc.get('title', '')
            assets = sc.get('asset_count', 0)
            subs = sc.get('subscribers', 0)
            author = sc.get('author', '')
            description = sc.get('description', '')
            rating = sc.get('rating', '')
            tags = sc.get('tags', '')
            last_updated = sc.get('last_updated', '')
            f.write(f"{sc_id}\t{assets}\t{subs}\t{author}\t{title}\t{description}\t{rating}\t{tags}\t{last_updated}\n")

    log.info('Saved %d sporecasts to %s', len(all_sporecasts), temp_file)

    result_lines.append(f"Total discovered: {len(all_sporecasts)} new sporecasts")
    if skipped > 0:
        result_lines.append(f"Skipped (already in DB): {skipped}")
    result_lines.append(f"Database: {db.get_scanned_sporecast_count()} scanned sporecasts")
    if enumerate_all:
        result_lines.append(f"Enumeration: ALL THEME sporecasts")
    result_lines.append(f"Saved to: {temp_file}")
    print_results(result_lines)
    db.close()
    state['used_progress_bar'] = True
