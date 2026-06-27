"""
full_crawler.py - Core download engine for assets and sporecasts with metadata embedding.

Depends on: api/client (SporeAPI), storage/database (Database), organizers/folders,
            models (Asset), storage/png_metadata
Used by: cli/commands/_common, cli/commands/crawl, cli/commands/sporecast,
         cli/commands/bean
"""
import asyncio
import aiohttp
import logging
from pathlib import Path
from typing import Optional
from spore_crawler.api.client import SporeAPI
from spore_crawler.storage.database import Database
from spore_crawler.organizers.folders import get_asset_path, get_asset_folder
from spore_crawler.models import Asset
from spore_crawler.storage.png_metadata import (
    embed_metadata_in_png, build_asset_xml, build_sporecast_xml,
    save_sporecast_metadata, embed_metadata_from_api_response,
)

log = logging.getLogger(__name__)


class Downloader:
    def __init__(self, api: SporeAPI, db: Database, output_dir: Path, max_concurrent: int = 5, embed_metadata: bool = True):
        self.api = api
        self.db = db
        self.output_dir = output_dir
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.embed_metadata = embed_metadata
        log.info("Downloader init: output=%s, max_concurrent=%d, embed_metadata=%s", output_dir, max_concurrent, embed_metadata)

    async def download_asset(self, asset: Asset, embed_api_xml: bool = None) -> bool:
        if self.db.is_downloaded(asset.id):
            log.debug("Skip (in DB): asset %d '%s' by %s", asset.id, asset.name, asset.author)
            return True

        dest = get_asset_path(asset, self.output_dir)
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            size = dest.stat().st_size
            self.db.record_download(asset.id, str(dest), size)
            log.debug("Skip (on disk): asset %d '%s' -> %s (%d bytes)", asset.id, asset.name, dest, size)
            return True

        url = asset.thumb_url
        if not url:
            s = str(asset.id)
            url = f"http://static.spore.com/static/thumb/{s[0:3]}/{s[3:6]}/{s[6:9]}/{asset.id}.png"

        log.info("Downloading: asset %d '%s' by %s (type=%s, folder=%s)", asset.id, asset.name, asset.author, asset.type, get_asset_folder(asset))
        async with self.semaphore:
            try:
                async with self.api.session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        dest.write_bytes(data)
                        self.db.record_download(asset.id, str(dest), len(data))
                        log.info("Downloaded: asset %d '%s' -> %s (%d bytes)", asset.id, asset.name, dest, len(data))

                        # Use parameter if provided, otherwise use instance setting
                        should_embed = embed_api_xml if embed_api_xml is not None else self.embed_metadata
                        if should_embed:
                            xml_str = build_asset_xml(
                                asset_id=asset.id,
                                name=asset.name,
                                author=asset.author,
                                created=asset.created,
                                description=asset.description,
                                tags=asset.tags,
                                asset_type=asset.type.value if hasattr(asset.type, 'value') else str(asset.type),
                                subtype=asset.subtype,
                                rating=asset.rating,
                                parent_id=asset.parent_id,
                            )
                            if not embed_metadata_in_png(dest, xml_str):
                                log.warning("Metadata embed failed for asset %d '%s'", asset.id, asset.name)

                        return True
                    else:
                        log.warning("Download HTTP %d for asset %d '%s' from %s", resp.status, asset.id, asset.name, url)
            except Exception as e:
                log.error("Download failed for asset %d '%s': %s (url=%s)", asset.id, asset.name, e, url)
        return False

    async def embed_metadata_for_asset(self, asset: Asset) -> bool:
        """Fetch fresh metadata from API and embed into existing PNG file."""
        dest = get_asset_path(asset, self.output_dir)
        if not dest.exists():
            log.warning("Cannot embed metadata: PNG not found for asset %d", asset.id)
            return False

        # Fetch full asset data from REST API (includes comments)
        full_asset = await self.api.get_asset(asset.id)
        if full_asset:
            xml_str = build_asset_xml(
                asset_id=full_asset.id,
                name=full_asset.name,
                author=full_asset.author,
                created=full_asset.created,
                description=full_asset.description,
                tags=full_asset.tags,
                asset_type=full_asset.type.value if hasattr(full_asset.type, 'value') else str(full_asset.type),
                subtype=full_asset.subtype,
                rating=full_asset.rating,
                parent_id=full_asset.parent_id,
            )
            return embed_metadata_in_png(dest, xml_str)
        return False


async def crawl_assets(
    api: SporeAPI,
    db: Database,
    output_dir: Path,
    view_type: str,
    asset_type: str,
    page_size: int = 500,
    max_pages: int = 0,
    max_amount: int = 0,
    max_size_mb: int = 0,
    max_concurrent_downloads: int = 5,
    embed_metadata: bool = True,
    hotkey=None,
):
    """Crawl assets by view type and asset type with resume support.
    Returns (downloaded_count, downloaded_bytes, limit_reached)."""
    crawl_id = f"search_{view_type}_{asset_type}"
    progress = db.get_progress(crawl_id)
    start = progress["last_start_index"] if progress else 0
    total = progress["total_processed"] if progress else 0

    downloader = Downloader(api, db, output_dir, max_concurrent_downloads, embed_metadata)

    max_size_bytes = max_size_mb * 1024 * 1024 if max_size_mb else 0
    limit_reached = False

    log.info("[%s] Starting crawl: view=%s, type=%s, start=%d, total_so_far=%d, page_size=%d, max_pages=%d, max_amount=%d, max_size_mb=%d",
             crawl_id, view_type, asset_type, start, total, page_size, max_pages, max_amount, max_size_mb)
    log.info("[%s] Resumed from previous progress: start=%d, total=%d", crawl_id, start, total)

    page = 0
    newly_downloaded = 0
    downloaded_bytes = 0
    category_bytes = 0
    skipped_count = 0
    
    # Initialize hotkey progress display
    if hotkey:
        hotkey.progress.current_view = view_type
        hotkey.progress.current_type = asset_type
        hotkey.progress.category_bytes = 0
    
    while True:
        # Check for user stop request
        if hotkey and hotkey.should_stop():
            log.info("[%s] Stopped by user", crawl_id)
            break
        
        # Wait if paused
        if hotkey:
            await hotkey.async_wait_if_paused()
            if hotkey.should_stop():
                break
        
        if max_pages and page >= max_pages:
            log.info("[%s] Reached max_pages limit (%d), stopping", crawl_id, max_pages)
            break

        log.info("[%s] Fetching page %d: start=%d, page_size=%d", crawl_id, page + 1, start, page_size)
        assets = await api.search_assets(view_type, start, page_size, asset_type)
        if not assets:
            log.info("[%s] No more assets returned at start=%d, stopping", crawl_id, start)
            break

        log.info("[%s] Page %d: got %d assets (first: id=%d '%s', last: id=%d '%s')",
                 crawl_id, page + 1, len(assets),
                 assets[0].id, assets[0].name if assets else "N/A",
                 assets[-1].id, assets[-1].name if assets else "N/A")

        downloaded = 0
        skipped_db = 0
        skipped_disk = 0
        failed = 0
        for asset in assets:
            # Check for user stop/pause request
            if hotkey and hotkey.should_stop():
                log.info("[%s] Stopped by user during download", crawl_id)
                break
            if hotkey:
                await hotkey.async_wait_if_paused()
                if hotkey.should_stop():
                    break
            
            was_new = not db.is_downloaded(asset.id)
            result = await downloader.download_asset(asset)
            if result:
                if was_new:
                    downloaded += 1
                    newly_downloaded += 1
                    dest = get_asset_path(asset, output_dir)
                    if dest.exists():
                        asset_size = dest.stat().st_size
                        downloaded_bytes += asset_size
                        category_bytes += asset_size
                else:
                    skipped_db += 1
            else:
                failed += 1

            # Update hotkey progress after each asset
            if hotkey:
                hotkey.update_progress(
                    downloaded=newly_downloaded,
                    skipped=skipped_db + skipped_disk,
                    failed=failed,
                    bytes=downloaded_bytes,
                    page=page,
                    category_bytes=category_bytes,
                )
                hotkey.render_progress()

            if max_amount and newly_downloaded >= max_amount:
                log.info("[%s] Reached max_amount limit (%d), stopping", crawl_id, max_amount)
                limit_reached = True
                break
            if max_size_bytes and downloaded_bytes >= max_size_bytes:
                log.info("[%s] Reached max_size limit (%d MB), stopping", crawl_id, max_size_mb)
                limit_reached = True
                break
        
        # Check if stopped during download loop
        if hotkey and hotkey.should_stop():
            break
        
        total += len(assets)
        start += len(assets)
        page += 1

        db.update_progress(crawl_id, start, total, "running")
        log.info("[%s] Page %d complete: got=%d, downloaded=%d, skipped_db=%d, failed=%d, total=%d, new_total=%d, size=%.2f MB",
                 crawl_id, page, len(assets), downloaded, skipped_db, failed, total, newly_downloaded, downloaded_bytes / 1024 / 1024)

        if len(assets) < page_size:
            log.info("[%s] Last page (got %d < page_size %d), stopping", crawl_id, len(assets), page_size)
            break

    db.update_progress(crawl_id, start, total, "completed")
    log.info("[%s] Crawl completed: total=%d, new_downloaded=%d, downloaded_bytes=%d (%.2f MB), limit_reached=%s",
             crawl_id, total, newly_downloaded, downloaded_bytes, downloaded_bytes / 1024 / 1024, limit_reached)
    return newly_downloaded, downloaded_bytes, limit_reached


async def crawl_sporecast(
    api: SporeAPI,
    db: Database,
    output_dir: Path,
    sporecast_id: int,
    sporecast_title: str,
    sporecast_author: str = "",
    sporecast_subtitle: str = "",
    sporecast_rating: str = "",
    sporecast_asset_count: int = 0,
    sporecast_tags: str = "",
    sporecast_updated: str = "",
    sporecast_subscribers: int = 0,
    page_size: int = 500,
    max_concurrent_downloads: int = 5,
    embed_metadata: bool = True,
    hotkey=None,
):
    """Download all assets in a sporecast"""
    from spore_crawler.organizers.folders import get_sporecast_path

    folder = get_sporecast_path(sporecast_title, output_dir, author=sporecast_author, sporecast_id=sporecast_id)
    folder.mkdir(parents=True, exist_ok=True)

    downloader = Downloader(api, db, output_dir, max_concurrent_downloads, embed_metadata)
    existing = db.get_sporecast_asset_ids(sporecast_id)

    log.info("Sporecast '%s' (ID: %d): folder=%s, existing_in_db=%d", sporecast_title, sporecast_id, folder, len(existing))

    start = 0
    total = 0
    new_count = 0
    skipped_existing = 0
    failed = 0
    downloaded_bytes = 0

    while True:
        log.info("Sporecast '%s': fetching page start=%d, page_size=%d", sporecast_title, start, page_size)
        assets = await api.get_sporecast_assets(sporecast_id, start, page_size)
        if not assets:
            log.info("Sporecast '%s': no more assets at start=%d", sporecast_title, start)
            break

        log.info("Sporecast '%s': got %d assets (first: id=%d '%s')",
                 sporecast_title, len(assets), assets[0].id, assets[0].name if assets else "N/A")

        for asset in assets:
            if hotkey and hotkey.should_stop():
                log.info("Sporecast '%s': stop requested, finishing current page", sporecast_title)
                break

            if asset.id not in existing:
                dest = folder / f"{asset.id}.png"
                if not dest.exists():
                    url = asset.thumb_url
                    if not url:
                        s = str(asset.id)
                        url = f"http://static.spore.com/static/thumb/{s[0:3]}/{s[3:6]}/{s[6:9]}/{asset.id}.png"
                    try:
                        log.info("Downloading asset %d '%s' from sporecast '%s' -> %s", asset.id, asset.name, sporecast_title, dest)
                        async with api.session.get(url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                dest.write_bytes(data)
                                db.record_download(asset.id, str(dest), len(data))
                                new_count += 1
                                downloaded_bytes += len(data)
                                log.info("Downloaded: asset %d '%s' (%d bytes) from sporecast '%s'", asset.id, asset.name, len(data), sporecast_title)

                                if embed_metadata:
                                    xml_str = build_asset_xml(
                                        asset_id=asset.id,
                                        name=asset.name,
                                        author=asset.author,
                                        created=asset.created,
                                        description=asset.description,
                                        tags=asset.tags,
                                        asset_type=asset.type.value if hasattr(asset.type, 'value') else str(asset.type),
                                        subtype=asset.subtype,
                                        rating=asset.rating,
                                        parent_id=asset.parent_id,
                                        sporecast_id=sporecast_id,
                                        sporecast_title=sporecast_title,
                                    )
                                    if not embed_metadata_in_png(dest, xml_str):
                                        log.warning("Metadata embed failed for asset %d '%s'", asset.id, asset.name)
                            else:
                                failed += 1
                                log.warning("Download HTTP %d for asset %d from sporecast '%s'", resp.status, asset.id, sporecast_title)
                    except Exception as e:
                        failed += 1
                        log.error("Download failed for asset %d from sporecast '%s': %s", asset.id, sporecast_title, e)
                else:
                    skipped_existing += 1
                    log.debug("Skip (on disk): asset %d from sporecast '%s'", asset.id, sporecast_title)
            else:
                skipped_existing += 1
                log.debug("Skip (in DB): asset %d from sporecast '%s'", asset.id, sporecast_title)
            db.record_sporecast_asset(sporecast_id, asset.id)

            # Update progress after each asset
            if hotkey:
                hotkey.update_progress(
                    downloaded=new_count,
                    skipped=skipped_existing,
                    failed=failed,
                    bytes=downloaded_bytes,
                    page=start // page_size,
                    category_bytes=downloaded_bytes,
                )
                hotkey.render_progress()

        total += len(assets)
        start += len(assets)

        if hotkey and hotkey.should_stop():
            log.info("Sporecast '%s': stop requested, checkpointing", sporecast_title)
            break

        if len(assets) < page_size:
            log.info("Sporecast '%s': last page (got %d < page_size %d)", sporecast_title, len(assets), page_size)
            break

    if sporecast_id:
        db.record_sporecast_downloaded(sporecast_id, sporecast_title)
        sporecast_xml = build_sporecast_xml(
            sporecast_id=sporecast_id,
            title=sporecast_title,
            author=sporecast_author,
            subtitle=sporecast_subtitle,
            rating=sporecast_rating,
            asset_count=total,
            tags=sporecast_tags,
            updated=sporecast_updated,
            subscribers=sporecast_subscribers,
        )
        save_sporecast_metadata(folder, sporecast_xml)

    log.info("Sporecast '%s' complete: total=%d, new_downloads=%d, skipped=%d, failed=%d",
             sporecast_title, total, new_count, skipped_existing, failed)
    return new_count, downloaded_bytes
