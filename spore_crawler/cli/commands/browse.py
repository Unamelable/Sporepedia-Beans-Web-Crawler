"""
browse.py - `browse` command: browse Sporepedia creations via REST API (no auth required).

Depends on: api/client, storage/database, models, ui/progress, cli/commands/_common,
            crawlers/hotkeys
Used by: cli/commands/__init__, cli/__init__

Side effects:
  - Opens Database (search_sporecast.db) -- must close
  - Starts HotkeyController -- must stop
  - Sets state['used_progress_bar'] = True
"""
import logging
from pathlib import Path

from spore_crawler.api.client import SporeAPI
from spore_crawler.storage.database import Database
from spore_crawler.models import AssetType, ViewType
from spore_crawler.ui.progress import print_hotkeys_hint, scroll_print, print_results
from spore_crawler.cli_ui import FG_GREEN, FG_RED, FG_YELLOW

from spore_crawler.cli.commands._common import get_browse_db_path, state

log = logging.getLogger(__name__)

# Map website filter names to ViewType values
FILTER_MAP = {
    'newest': 'NEWEST',
    'top_rated': 'TOP_RATED',
    'highly_rated': 'TOP_RATED',
    'recent_highly_rated': 'TOP_RATED_NEW',
    'featured': 'FEATURED',
    'all': 'RANDOM',
}

# Map website creation type names to AssetType values
TYPE_MAP = {
    'creature': 'CREATURE',
    'creatures': 'CREATURE',
    'building': 'BUILDING',
    'buildings': 'BUILDING',
    'vehicle': 'VEHICLE',
    'vehicles': 'VEHICLE',
    'adventure': 'ADVENTURE',
    'adventures': 'ADVENTURE',
}

# Subtypes by creation type (from website)
SUBTYPES = {
    'CREATURE': ['Animal', 'Tribal', 'Civ', 'Space', 'Captain'],
    'BUILDING': ['City Hall', 'House', 'Factory', 'Entertainment'],
    'VEHICLE': ['Military Land', 'Military Water', 'Military Air',
                'Economic Land', 'Economic Water', 'Economic Air',
                'Religious Land', 'Religious Water', 'Religious Air',
                'Colony Land', 'Colony Water', 'Colony Air', 'Spaceships'],
    'ADVENTURE': ['Attack', 'Collect', 'Defend', 'Explore', 'Puzzle',
                  'Quest', 'Socialize', 'Story', 'Template', 'No Genre'],
}


async def cmd_browse(config: dict, asset_types: list[str] = None,
                     filter_method: str = None, max_results: int = 0,
                     subtypes: list[str] = None, enumerate_all: bool = False):
    from spore_crawler.crawlers.hotkeys import HotkeyController

    output_dir = Path(config['output']['download_folder'])
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve filter method
    if filter_method:
        filter_key = filter_method.lower().replace('-', '_')
        view_type = FILTER_MAP.get(filter_key)
        if not view_type:
            print(f"Unknown filter: {filter_method}")
            print(f"Valid filters: {', '.join(FILTER_MAP.keys())}")
            return
    else:
        view_type = 'NEWEST'

    # Resolve asset types
    resolved_types = []
    if enumerate_all:
        resolved_types = ['CREATURE', 'BUILDING', 'VEHICLE', 'ADVENTURE']
    elif asset_types:
        for t in asset_types:
            type_key = t.lower()
            if type_key in TYPE_MAP:
                resolved_types.append(TYPE_MAP[type_key])
            else:
                print(f"Unknown creation type: {t}")
                print(f"Valid types: creature, building, vehicle, adventure")
                return
    else:
        resolved_types = ['CREATURE', 'BUILDING', 'VEHICLE', 'ADVENTURE']

    log.info('Command: browse')
    log.info('  Asset types: %s', resolved_types)
    log.info('  Filter/view: %s', view_type)
    log.info('  Max results: %d', max_results)
    log.info('  Subtypes: %s', subtypes)

    db_path = get_browse_db_path(config)
    db = Database(db_path)
    all_assets = []
    all_ids = set()
    skipped = 0

    log.info('Browse DB: %s (existing browsed: %d)', db_path,
             db.get_browsed_asset_count())

    hotkey = HotkeyController()
    hotkey.start()
    hotkey.progress.set_status(hotkey.progress.STATUS_RUNNING)
    hotkey.progress.render_progress()
    print_hotkeys_hint()

    cfg = config['crawler']

    try:
        async with SporeAPI(
            requests_per_second=cfg['requests_per_second'],
            timeout=cfg['request_timeout'],
            max_retries=cfg['max_retries'],
        ) as api:
            for asset_type in resolved_types:
                if hotkey.should_stop():
                    break

                log.info('Browsing type: %s, view: %s', asset_type, view_type)
                hotkey.progress.current_view = view_type
                hotkey.progress.current_type = asset_type
                hotkey.progress.category_bytes = 0
                hotkey.progress.render_progress()

                index = 0
                page_size = min(cfg.get('page_size', 500), 500)
                empty_streak = 0

                while True:
                    if hotkey.should_stop():
                        break
                    await hotkey.async_wait_if_paused()
                    if hotkey.should_stop():
                        break

                    assets = await api.search_assets(view_type, index, page_size, asset_type)
                    if not assets:
                        empty_streak += 1
                        if empty_streak >= 3:
                            break
                        index += page_size
                        continue

                    empty_streak = 0
                    new_count = 0

                    for asset in assets:
                        if hotkey.should_stop():
                            break

                        if asset.id in all_ids:
                            continue
                        if db.is_asset_browsed(asset.id):
                            skipped += 1
                            continue

                        # Filter by subtype if specified
                        if subtypes:
                            asset_subtype = asset.subtype or ''
                            if not any(s.lower() in asset_subtype.lower() for s in subtypes):
                                continue

                        all_ids.add(asset.id)
                        all_assets.append(asset)
                        new_count += 1

                        db.record_browsed_asset(
                            asset.id,
                            asset.name,
                            asset.type.value if hasattr(asset.type, 'value') else str(asset.type),
                            asset.author,
                            asset.subtype,
                            asset.description,
                            asset.tags,
                            asset.rating,
                        )

                        log.info('New asset: [%d] "%s" by %s (type=%s, subtype=%s)',
                                 asset.id, asset.name, asset.author,
                                 asset.type, asset.subtype)

                        hotkey.update_progress(
                            downloaded=len(all_assets),
                            skipped=skipped,
                            page=index // page_size,
                        )
                        hotkey.progress.render_progress()

                    log.info('Type %s page %d: got %d, new %d, total %d',
                             asset_type, index // page_size, len(assets), new_count, len(all_assets))

                    scroll_print(
                        f"[{asset_type}] Page {index // page_size + 1}: +{new_count} "
                        f"(total: {len(all_assets)}, skipped: {skipped})",
                        fg=FG_GREEN,
                    )

                    if max_results and len(all_assets) >= max_results:
                        log.info('Reached max_results limit (%d)', max_results)
                        break

                    if len(assets) < page_size:
                        break

                    index += page_size

                    # Rate limiting between pages
                    import asyncio
                    await asyncio.sleep(1)

    finally:
        hotkey.stop()

    if skipped > 0:
        log.info('Skipped %d already-browsed assets', skipped)

    if not all_assets:
        log.info('No new assets found')
        print_results([
            'No new assets found.',
            f"Database: {db.get_browsed_asset_count()} browsed assets",
        ])
        db.close()
        state['used_progress_bar'] = True
        return

    log.info('Browse complete: %d unique new assets found', len(all_assets))

    result_lines = [f"Total browsed: {len(all_assets)} new assets"]
    if skipped > 0:
        result_lines.append(f"Skipped (already in DB): {skipped}")
    result_lines.append(f"Database: {db.get_browsed_asset_count()} browsed assets")
    result_lines.append(f"Types: {', '.join(resolved_types)}")
    result_lines.append(f"Filter: {view_type}")
    print_results(result_lines)
    db.close()
    state['used_progress_bar'] = True
