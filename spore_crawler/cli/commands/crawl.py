"""
crawl.py - `crawl` command: bulk asset downloading with limits.

Depends on: api/client, storage/database, crawlers/full_crawler,
            organizers/folders, ui, ui/progress, cli/commands/_common,
            crawlers/hotkeys
Used by: cli/commands/__init__, cli/__init__

Side effects:
  - Opens Database (sporepedia.db) -- must close
  - Starts HotkeyController -- must stop
  - Downloads PNG files to disk
  - Sets state['used_progress_bar'] = True
"""
import logging
import threading
from pathlib import Path

from spore_crawler.api.client import SporeAPI
from spore_crawler.storage.database import Database
from spore_crawler.crawlers.full_crawler import crawl_assets
from spore_crawler.organizers.folders import ensure_directories
from spore_crawler.ui import FG_YELLOW
from spore_crawler.ui.progress import print_hotkeys_hint, scroll_print

from spore_crawler.cli.commands._common import get_browse_db_path, state

log = logging.getLogger(__name__)


async def cmd_crawl(config, sort_method=None, asset_types=None, subtypes=None,
                    max_pages=0, max_amount=0, max_size_mb=0, forcestop=False,
                    save_chunk=None, load_chunk=None, skipcheck=False,
                    use_browse_db=False):
    from spore_crawler.crawlers.hotkeys import HotkeyController

    cfg = config['crawler']
    output_dir = Path(config['output']['download_folder'])
    output_dir.mkdir(parents=True, exist_ok=True)
    ensure_directories(output_dir)

    sm = sort_method or cfg['sort_method']
    at = asset_types or cfg['asset_types']

    db = Database(config['database']['path'])

    log.info('Command: crawl')
    log.info('  Output dir: %s', output_dir.absolute())
    log.info('  Sort method: %s', sm)
    log.info('  Asset types: %s', at)
    log.info('  Subtypes: %s', subtypes)
    log.info('  Max pages: %d', max_pages)
    log.info('  Max amount: %d', max_amount)
    log.info('  Max size: %d MB', max_size_mb)
    log.info('  Forcestop: %s', forcestop)
    log.info('  Page size: %d', cfg['page_size'])
    log.info('  Rate limit: %.1f req/s', cfg['requests_per_second'])
    log.info('  Concurrent downloads: %d', cfg.get('max_concurrent_downloads', 5))
    log.info('  Timeout: %ds, Retries: %d', cfg['request_timeout'], cfg['max_retries'])
    log.info('  DB path: %s', config['database']['path'])
    log.info('  Save chunk: %s', save_chunk)
    log.info('  Load chunk: %s', load_chunk)
    log.info('  Skip check: %s', skipcheck)
    log.info('  Use browse DB: %s', use_browse_db)

    _stopped_by_user = threading.Event()

    # Handle --db mode: download assets from browse database
    if use_browse_db:
        browse_db_path = get_browse_db_path(config)
        browse_db = Database(browse_db_path)
        browsed = browse_db.get_all_browsed_assets()
        browse_db.close()

        if not browsed:
            print("No browsed assets found in search_sporecast.db.")
            print("Run 'browse' first to discover assets.")
            db.close()
            return

        print(f"Loaded {len(browsed)} browsed assets from search_sporecast.db")

        from spore_crawler.models import Asset, AssetType
        from spore_crawler.organizers.folders import get_asset_path

        hotkey = HotkeyController()
        hotkey.start()
        hotkey.set_stop_callback(lambda: _stopped_by_user.set())
        hotkey.progress.set_status(hotkey.progress.STATUS_RUNNING)
        hotkey.progress.render_progress()
        print_hotkeys_hint()

        total_downloaded = 0
        total_bytes = 0
        skipped = 0

        try:
            async with SporeAPI(
                requests_per_second=cfg['requests_per_second'],
                timeout=cfg['request_timeout'],
                max_retries=cfg['max_retries'],
            ) as api:
                for idx, brow in enumerate(browsed):
                    if hotkey.should_stop():
                        break
                    await hotkey.async_wait_if_paused()
                    if hotkey.should_stop():
                        break

                    asset_id = brow['asset_id']
                    if db.is_downloaded(asset_id):
                        skipped += 1
                        continue

                    # Create Asset object from browsed data
                    try:
                        asset_type_enum = AssetType(brow.get('type', 'CREATURE'))
                    except ValueError:
                        asset_type_enum = AssetType.CREATURE

                    asset = Asset(
                        id=asset_id,
                        name=brow.get('name', ''),
                        type=asset_type_enum,
                        author=brow.get('author', ''),
                        subtype=brow.get('subtype', ''),
                        description=brow.get('description', ''),
                        tags=brow.get('tags', ''),
                        rating=brow.get('rating', '-1'),
                    )

                    dest = get_asset_path(asset, output_dir)
                    dest.parent.mkdir(parents=True, exist_ok=True)

                    if dest.exists():
                        size = dest.stat().st_size
                        db.record_download(asset_id, str(dest), size)
                        skipped += 1
                        continue

                    s = str(asset_id)
                    url = f"http://static.spore.com/static/thumb/{s[0:3]}/{s[3:6]}/{s[6:9]}/{asset_id}.png"

                    try:
                        async with api.session.get(url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                dest.write_bytes(data)
                                db.record_download(asset_id, str(dest), len(data))
                                total_downloaded += 1
                                total_bytes += len(data)
                                log.info('Downloaded: [%d] "%s" (%d bytes)', asset_id, asset.name, len(data))

                                if config['output'].get('embed_metadata', True):
                                    from spore_crawler.storage.png_metadata import build_asset_xml, embed_metadata_in_png
                                    xml_str = build_asset_xml(
                                        asset_id=asset_id,
                                        name=asset.name,
                                        author=asset.author,
                                        subtype=asset.subtype,
                                        description=asset.description,
                                        tags=asset.tags,
                                        asset_type=asset.type.value,
                                        rating=asset.rating,
                                    )
                                    embed_metadata_in_png(dest, xml_str)
                    except Exception as e:
                        log.error('Download failed for asset %d: %s', asset_id, e)

                    hotkey.update_progress(
                        downloaded=total_downloaded,
                        skipped=skipped,
                        page=idx // cfg.get('page_size', 500),
                    )
                    hotkey.progress.render_progress()

                    if max_amount and total_downloaded >= max_amount:
                        break
                    if max_size_mb and total_bytes >= max_size_mb * 1024 * 1024:
                        break

        finally:
            hotkey.stop()

        from spore_crawler.ui.progress import print_results

        result_lines = []
        if _stopped_by_user.is_set():
            result_lines.append("Stopping...")
            result_lines.append("Progress has been saved.")

        result_lines.extend([
            f"Done! Downloaded: {total_downloaded} PNGs ({total_bytes / 1024 / 1024:.2f} MB)",
            f"Skipped: {skipped} (already downloaded or on disk)",
            f"Database: {db.get_total_downloaded()} assets tracked",
        ])
        print_results(result_lines)
        db.close()
        state['used_progress_bar'] = True
        return

    if load_chunk:
        load_path = Path(load_chunk)
        if not load_path.exists():
            print(f"Error: Chunk file not found: {load_path}")
            db.close()
            return

        print(f"Loading database chunk: {load_path}")
        log.info('Loading chunk: %s (verify=%s)', load_path, not skipcheck)

        result = db.load_chunk(str(load_path), verify=not skipcheck, download_dir=str(output_dir))

        print('Chunk loaded successfully!')
        print(f"  Assets loaded: {result['loaded']}")
        if not skipcheck:
            print(f"  Assets verified on disk: {result['verified']}")
            print(f"  Assets missing from disk: {result['missing']}")
            if result['missing'] > 0:
                print(f"\n  Warning: {result['missing']} assets are missing from disk.")
                print('  These assets were tracked in the database but the PNG files were not found.')
                print("  They will be skipped during download if they don't exist.")
        print()

    print(f"Output: {output_dir.absolute()}")
    print(f"Sort: {sm}")
    print(f"Types: {at}")
    if subtypes:
        print(f"Subtypes: {subtypes}")
    if max_amount:
        print(f"Amount limit: {max_amount} PNGs")
    if max_size_mb:
        print(f"Size limit: {max_size_mb} MB")
    if max_pages:
        print(f"Max pages: {max_pages}")
    if forcestop:
        print("Forcestop: ON (stop all categories when limit hit)")

    hotkey = HotkeyController()
    hotkey.start()

    hotkey.set_stop_callback(lambda: _stopped_by_user.set())
    hotkey.progress.set_status(hotkey.progress.STATUS_RUNNING)
    hotkey.progress.render_progress()
    print_hotkeys_hint()

    async with SporeAPI(
        requests_per_second=cfg['requests_per_second'],
        timeout=cfg['request_timeout'],
        max_retries=cfg['max_retries'],
    ) as api:
        total = 0
        total_bytes = 0
        stop_all = False

        for view in sm:
            if stop_all or hotkey.should_stop():
                break
            for asset_type in at:
                if stop_all or hotkey.should_stop():
                    break

                hotkey.wait_if_paused()
                if hotkey.should_stop():
                    break

                log.info('Starting crawl: view=%s, type=%s', view, asset_type)
                count, bytes_downloaded, limit_reached = await crawl_assets(
                    api, db, output_dir, view, asset_type,
                    cfg['page_size'], max_pages, max_amount, max_size_mb,
                    cfg.get('max_concurrent_downloads', 5),
                    config['output'].get('embed_metadata', True),
                    hotkey,
                )
                total += count
                total_bytes += bytes_downloaded
                log.info('Finished crawl: view=%s, type=%s, downloaded=%d (%.2f MB), limit_reached=%s',
                         view, asset_type, count, bytes_downloaded / 1024 / 1024, limit_reached)
                if forcestop and limit_reached:
                    log.info('Forcestop triggered: stopping all categories')
                    scroll_print('Forcestop: limit reached, stopping all categories.', fg=FG_YELLOW)
                    stop_all = True

    hotkey.stop()

    from spore_crawler.ui.progress import print_results

    result_lines = []

    if _stopped_by_user.is_set():
        result_lines.append("Stopping...")
        result_lines.append("Progress has been saved.")

    if save_chunk:
        result_lines.append(f"Saving database chunk: {save_chunk}")
        log.info('Saving chunk: %s', save_chunk)
        chunks_dir = config['database'].get('chunks_dir')
        chunk_path = db.save_chunk(save_chunk, chunks_dir)
        result_lines.append(f"Chunk saved to: {chunk_path}")
        result_lines.append(f"  Assets in database: {db.get_total_downloaded()}")

    log.info('Command: crawl completed. Total downloaded: %d (%.2f MB), DB tracked: %d',
             total, total_bytes / 1024 / 1024, db.get_total_downloaded())
    result_lines.append(f"Done! Total downloaded: {total} PNGs ({total_bytes / 1024 / 1024:.2f} MB)")
    result_lines.append(f"Database: {db.get_total_downloaded()} assets tracked")
    print_results(result_lines)
    db.close()
    state['used_progress_bar'] = True
