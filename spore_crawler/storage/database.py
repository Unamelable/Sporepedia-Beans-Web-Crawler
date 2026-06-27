"""
database.py - SQLite persistence for downloads, progress, sporecast tracking, chunks.

Depends on: None (leaf module, no internal imports)
Used by: cli/commands/_common, cli/commands/search, cli/commands/sporecast,
         cli/commands/crawl, cli/commands/browse, cli/commands/bean,
         cli/__init__, crawlers/full_crawler
"""
import sqlite3
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        log.info("Database: opening %s (exists=%s)", self.db_path, self.db_path.exists())
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        log.debug("Database: creating tables if not exist")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS downloaded_assets (
                asset_id INTEGER PRIMARY KEY,
                downloaded_at TEXT,
                file_size INTEGER,
                file_path TEXT
            );

            CREATE TABLE IF NOT EXISTS crawl_progress (
                crawl_id TEXT PRIMARY KEY,
                last_start_index INTEGER DEFAULT 0,
                total_processed INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                last_updated TEXT
            );

            CREATE TABLE IF NOT EXISTS sporecast_assets (
                sporecast_id INTEGER,
                asset_id INTEGER,
                PRIMARY KEY (sporecast_id, asset_id)
            );

            CREATE TABLE IF NOT EXISTS scanned_sporecasts (
                sporecast_id INTEGER PRIMARY KEY,
                asset_count INTEGER DEFAULT 0,
                subscribers INTEGER DEFAULT 0,
                discovered_at TEXT,
                title TEXT,
                author TEXT
            );

            CREATE TABLE IF NOT EXISTS sporecast_downloaded (
                sporecast_id INTEGER PRIMARY KEY,
                title TEXT,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS browsed_assets (
                asset_id INTEGER PRIMARY KEY,
                name TEXT,
                type TEXT,
                author TEXT,
                subtype TEXT,
                description TEXT,
                tags TEXT,
                rating TEXT,
                discovered_at TEXT
            );
        """)
        self.conn.commit()

    def is_downloaded(self, asset_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM downloaded_assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        return row is not None

    def record_download(self, asset_id: int, file_path: str, file_size: int):
        log.debug("DB record_download: asset_id=%d, path=%s, size=%d", asset_id, file_path, file_size)
        self.conn.execute(
            "INSERT OR REPLACE INTO downloaded_assets (asset_id, file_path, downloaded_at, file_size) VALUES (?, ?, ?, ?)",
            (asset_id, file_path, datetime.utcnow().isoformat(), file_size),
        )
        self.conn.commit()

    def get_progress(self, crawl_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM crawl_progress WHERE crawl_id = ?", (crawl_id,)
        ).fetchone()
        result = dict(row) if row else None
        log.debug("DB get_progress(%s): %s", crawl_id, result)
        return result

    def update_progress(self, crawl_id: str, last_start: int, total: int, status: str = "running"):
        log.debug("DB update_progress(%s): start=%d, total=%d, status=%s", crawl_id, last_start, total, status)
        self.conn.execute(
            """INSERT OR REPLACE INTO crawl_progress
               (crawl_id, last_start_index, total_processed, status, last_updated)
               VALUES (?, ?, ?, ?, ?)""",
            (crawl_id, last_start, total, status, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_total_downloaded(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM downloaded_assets").fetchone()
        count = row[0]
        log.debug("DB get_total_downloaded: %d", count)
        return count

    def get_downloaded_ids(self) -> set:
        rows = self.conn.execute("SELECT asset_id FROM downloaded_assets").fetchall()
        result = {row[0] for row in rows}
        log.debug("DB get_downloaded_ids: %d IDs", len(result))
        return result

    def record_sporecast_asset(self, sporecast_id: int, asset_id: int):
        log.debug("DB record_sporecast_asset: sc=%d, asset=%d", sporecast_id, asset_id)
        self.conn.execute(
            "INSERT OR IGNORE INTO sporecast_assets (sporecast_id, asset_id) VALUES (?, ?)",
            (sporecast_id, asset_id),
        )
        self.conn.commit()

    def get_sporecast_asset_ids(self, sporecast_id: int) -> set:
        rows = self.conn.execute(
            "SELECT asset_id FROM sporecast_assets WHERE sporecast_id = ?", (sporecast_id,)
        ).fetchall()
        result = {row[0] for row in rows}
        log.debug("DB get_sporecast_asset_ids(%d): %d assets", sporecast_id, len(result))
        return result

    def is_sporecast_scanned(self, sporecast_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM scanned_sporecasts WHERE sporecast_id = ?", (sporecast_id,)
        ).fetchone()
        return row is not None

    def record_sporecast_scan(self, sporecast_id: int, title: str, author: str, asset_count: int, subscribers: int):
        log.debug("DB record_sporecast_scan: [%d] '%s' by %s (%d assets, %d subs)", sporecast_id, title, author, asset_count, subscribers)
        self.conn.execute(
            "INSERT OR IGNORE INTO scanned_sporecasts (sporecast_id, title, author, asset_count, subscribers, discovered_at) VALUES (?, ?, ?, ?, ?, ?)",
            (sporecast_id, title, author, asset_count, subscribers, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_scanned_sporecast_ids(self) -> set:
        rows = self.conn.execute("SELECT sporecast_id FROM scanned_sporecasts").fetchall()
        result = {row[0] for row in rows}
        log.debug("DB get_scanned_sporecast_ids: %d IDs", len(result))
        return result

    def get_scanned_sporecast_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM scanned_sporecasts").fetchone()
        return row[0]

    def get_all_scanned_sporecasts(self) -> list[dict]:
        rows = self.conn.execute("SELECT sporecast_id, title, author, asset_count, subscribers FROM scanned_sporecasts").fetchall()
        result = [dict(row) for row in rows]
        log.debug("DB get_all_scanned_sporecasts: %d rows", len(result))
        return result

    def get_unscanned_sporecasts(self, sporecast_ids: list[int]) -> list[int]:
        if not sporecast_ids:
            return []
        placeholders = ",".join("?" * len(sporecast_ids))
        rows = self.conn.execute(
            f"SELECT sporecast_id FROM scanned_sporecasts WHERE sporecast_id IN ({placeholders})",
            sporecast_ids,
        ).fetchall()
        scanned = {row[0] for row in rows}
        result = [sid for sid in sporecast_ids if sid not in scanned]
        log.debug("DB get_unscanned_sporecasts: %d input, %d unscanned", len(sporecast_ids), len(result))
        return result

    def record_sporecast_downloaded(self, sporecast_id: int, title: str):
        """Mark a sporecast as fully downloaded. Used for checkpoint/resume."""
        log.debug("DB record_sporecast_downloaded: [%d] '%s'", sporecast_id, title)
        self.conn.execute(
            "INSERT OR IGNORE INTO sporecast_downloaded (sporecast_id, title, completed_at) VALUES (?, ?, ?)",
            (sporecast_id, title, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def is_sporecast_downloaded(self, sporecast_id: int) -> bool:
        """Check if a sporecast was fully downloaded."""
        row = self.conn.execute(
            "SELECT 1 FROM sporecast_downloaded WHERE sporecast_id = ?", (sporecast_id,)
        ).fetchone()
        return row is not None

    def is_asset_browsed(self, asset_id: int) -> bool:
        """Check if an asset was already browsed."""
        row = self.conn.execute(
            "SELECT 1 FROM browsed_assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        return row is not None

    def record_browsed_asset(self, asset_id: int, name: str, asset_type: str,
                             author: str, subtype: str = "", description: str = "",
                             tags: str = "", rating: str = ""):
        """Record a browsed asset."""
        log.debug("DB record_browsed_asset: [%d] '%s' by %s (type=%s)", asset_id, name, author, asset_type)
        self.conn.execute(
            """INSERT OR IGNORE INTO browsed_assets
               (asset_id, name, type, author, subtype, description, tags, rating, discovered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (asset_id, name, asset_type, author, subtype, description, tags, rating,
             datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_browsed_asset_count(self) -> int:
        """Get count of browsed assets."""
        row = self.conn.execute("SELECT COUNT(*) FROM browsed_assets").fetchone()
        return row[0]

    def get_all_browsed_assets(self) -> list[dict]:
        """Get all browsed assets."""
        rows = self.conn.execute(
            "SELECT asset_id, name, type, author, subtype, description, tags, rating FROM browsed_assets"
        ).fetchall()
        result = [dict(row) for row in rows]
        log.debug("DB get_all_browsed_assets: %d rows", len(result))
        return result

    def get_chunk_dir(self, chunks_dir: str = None) -> Path:
        """Get the directory for storing database chunks.
        
        Args:
            chunks_dir: Custom directory path. If None, uses default location.
        """
        if chunks_dir:
            chunk_dir = Path(chunks_dir)
        else:
            chunk_dir = self.db_path.parent / "db_chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        return chunk_dir

    def save_chunk(self, chunk_name: str, chunks_dir: str = None) -> Path:
        """Save current database state to a chunk file.
        
        Args:
            chunk_name: Name for the chunk (e.g., 'backup_20260620')
            chunks_dir: Custom directory path. If None, uses default location.
            
        Returns:
            Path to the saved chunk file
        """
        chunk_dir = self.get_chunk_dir(chunks_dir)
        chunk_path = chunk_dir / f"{chunk_name}.db"
        
        log.info("Database: saving chunk '%s' to %s", chunk_name, chunk_path)
        
        # Create a backup using SQLite's backup API
        target_conn = sqlite3.connect(str(chunk_path))
        self.conn.backup(target_conn)
        target_conn.close()
        
        log.info("Database: chunk saved successfully (%s)", chunk_path)
        return chunk_path

    def load_chunk(self, chunk_path: str, verify: bool = True, download_dir: str = None) -> dict:
        """Load a database chunk and merge/verify it.
        
        Args:
            chunk_path: Path to the chunk file to load
            verify: Whether to verify that assets exist on disk
            download_dir: Directory to check for downloaded files (if verify=True)
            
        Returns:
            Dict with verification results:
            {
                'loaded': int,      # Assets loaded from chunk
                'verified': int,    # Assets verified on disk
                'missing': int,     # Assets missing from disk
                'missing_ids': list # List of missing asset IDs
            }
        """
        chunk_path = Path(chunk_path)
        if not chunk_path.exists():
            log.error("Database: chunk file not found: %s", chunk_path)
            raise FileNotFoundError(f"Chunk file not found: {chunk_path}")
        
        log.info("Database: loading chunk from %s (verify=%s)", chunk_path, verify)
        
        # Open the chunk database
        chunk_conn = sqlite3.connect(str(chunk_path))
        chunk_conn.row_factory = sqlite3.Row
        
        # Get all assets from chunk
        chunk_assets = chunk_conn.execute(
            "SELECT asset_id, file_path, downloaded_at, file_size FROM downloaded_assets"
        ).fetchall()
        
        log.info("Database: chunk contains %d assets", len(chunk_assets))
        
        loaded = 0
        verified = 0
        missing = 0
        missing_ids = []
        
        for asset in chunk_assets:
            asset_id = asset[0]
            file_path = asset[1]
            
            # Insert or replace into main database
            self.conn.execute(
                "INSERT OR REPLACE INTO downloaded_assets (asset_id, file_path, downloaded_at, file_size) VALUES (?, ?, ?, ?)",
                (asset_id, file_path, asset[2], asset[3])
            )
            loaded += 1
            
            # Verify if requested
            if verify and download_dir:
                full_path = Path(download_dir) / file_path
                if full_path.exists():
                    verified += 1
                else:
                    missing += 1
                    missing_ids.append(asset_id)
                    log.warning("Database: asset %d missing from disk: %s", asset_id, full_path)
        
        # Also load sporecast assets
        chunk_sporecast_assets = chunk_conn.execute(
            "SELECT sporecast_id, asset_id FROM sporecast_assets"
        ).fetchall()
        
        for sc_id, asset_id in chunk_sporecast_assets:
            self.conn.execute(
                "INSERT OR IGNORE INTO sporecast_assets (sporecast_id, asset_id) VALUES (?, ?)",
                (sc_id, asset_id)
            )
        
        # Load scanned sporecasts
        chunk_scanned = chunk_conn.execute(
            "SELECT sporecast_id, title, author, asset_count, subscribers, discovered_at FROM scanned_sporecasts"
        ).fetchall()
        
        for sc in chunk_scanned:
            self.conn.execute(
                "INSERT OR IGNORE INTO scanned_sporecasts (sporecast_id, title, author, asset_count, subscribers, discovered_at) VALUES (?, ?, ?, ?, ?, ?)",
                (sc[0], sc[1], sc[2], sc[3], sc[4], sc[5])
            )
        
        # Load crawl progress
        chunk_progress = chunk_conn.execute(
            "SELECT crawl_id, last_start_index, total_processed, status, last_updated FROM crawl_progress"
        ).fetchall()
        
        for prog in chunk_progress:
            self.conn.execute(
                "INSERT OR REPLACE INTO crawl_progress (crawl_id, last_start_index, total_processed, status, last_updated) VALUES (?, ?, ?, ?, ?)",
                (prog[0], prog[1], prog[2], prog[3], prog[4])
            )
        
        self.conn.commit()
        chunk_conn.close()
        
        result = {
            'loaded': loaded,
            'verified': verified,
            'missing': missing,
            'missing_ids': missing_ids
        }
        
        log.info("Database: chunk loaded - %d assets loaded, %d verified, %d missing", 
                 loaded, verified, missing)
        
        return result

    def list_chunks(self, chunks_dir: str = None) -> list[dict]:
        """List available database chunks.
        
        Args:
            chunks_dir: Custom directory path. If None, uses default location.
        
        Returns:
            List of dicts with chunk info:
            [
                {
                    'name': str,           # Chunk name
                    'path': str,           # Full path
                    'size': int,           # File size in bytes
                    'created': str,        # Creation timestamp
                    'assets': int          # Number of assets in chunk
                }
            ]
        """
        chunk_dir = self.get_chunk_dir(chunks_dir)
        chunks = []
        
        for chunk_file in chunk_dir.glob("*.db"):
            try:
                # Get file stats
                stat = chunk_file.stat()
                
                # Count assets in chunk
                conn = sqlite3.connect(str(chunk_file))
                asset_count = conn.execute("SELECT COUNT(*) FROM downloaded_assets").fetchone()[0]
                conn.close()
                
                chunks.append({
                    'name': chunk_file.stem,
                    'path': str(chunk_file),
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'assets': asset_count
                })
            except Exception as e:
                log.warning("Database: failed to read chunk %s: %s", chunk_file, e)
        
        # Sort by creation time, newest first
        chunks.sort(key=lambda x: x['created'], reverse=True)
        
        log.info("Database: found %d chunks", len(chunks))
        return chunks

    def verify_chunk(self, chunk_path: str, download_dir: str) -> dict:
        """Verify that all assets in a chunk exist on disk.
        
        Args:
            chunk_path: Path to the chunk file
            download_dir: Directory to check for downloaded files
            
        Returns:
            Dict with verification results
        """
        chunk_path = Path(chunk_path)
        if not chunk_path.exists():
            raise FileNotFoundError(f"Chunk file not found: {chunk_path}")
        
        log.info("Database: verifying chunk %s against %s", chunk_path, download_dir)
        
        conn = sqlite3.connect(str(chunk_path))
        assets = conn.execute(
            "SELECT asset_id, file_path FROM downloaded_assets"
        ).fetchall()
        
        verified = 0
        missing = 0
        missing_ids = []
        
        for asset_id, file_path in assets:
            full_path = Path(download_dir) / file_path
            if full_path.exists():
                verified += 1
            else:
                missing += 1
                missing_ids.append(asset_id)
        
        conn.close()
        
        result = {
            'total': len(assets),
            'verified': verified,
            'missing': missing,
            'missing_ids': missing_ids
        }
        
        log.info("Database: verification complete - %d total, %d verified, %d missing",
                 len(assets), verified, missing)
        
        return result

    def close(self):
        """Close SQLite connection. Safe to call multiple times. Idempotent."""
        log.info("Database: closing %s", self.db_path)
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
