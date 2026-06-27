"""
stats.py - `stats` command: fetch and display Sporepedia site statistics.

Depends on: api/client (SporeAPI)
Used by: cli/commands/__init__, cli/__init__

Side effects:
  - None (read-only API call, no state mutation)
"""
import logging

from spore_crawler.api.client import SporeAPI

log = logging.getLogger(__name__)


async def cmd_stats():
    """Command: stats - fetching site statistics"""
    log.info('Command: stats')
    async with SporeAPI() as api:
        stats = await api.get_stats()
    print(f"Total uploads: {stats.get('totalUploads', '?')}")
    print(f"Total users:   {stats.get('totalUsers', '?')}")
    print(f"Today uploads: {stats.get('dayUploads', '?')}")
    print(f"Today users:   {stats.get('dayUsers', '?')}")
