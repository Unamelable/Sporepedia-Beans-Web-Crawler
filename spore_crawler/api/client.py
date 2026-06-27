"""
client.py - Async HTTP client for Spore REST/DWR APIs with rate limiting.

Depends on: models (Asset, Sporecast)
Used by: cli/commands/_common, cli/commands/search, cli/commands/sporecast,
         cli/commands/crawl, cli/commands/stats, cli/commands/bean,
         crawlers/full_crawler
"""
import asyncio
import time
import random
import re
import logging
import xmltodict
import aiohttp
from typing import Optional
from spore_crawler.models import Asset, Sporecast

log = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised when the server signs off the user (403/401)."""
    pass


BASE_URL = "https://www.spore.com"
USER_AGENT = "Sporepedia Bean's Web Crawler/0.6 (github.com/spore-bean-crawler)"
USER_AGENT_TEST = "Sporepedia Bean's Web Crawler TEST MODE/0.6 (github.com/spore-bean-crawler)"


class RateLimiter:
    def __init__(self, requests_per_second: float = 1.5):
        self.min_interval = 1.0 / requests_per_second
        self.last_request = 0.0
        self._lock = asyncio.Lock()
        log.info("RateLimiter: %.1f req/s, min_interval=%.3fs", requests_per_second, self.min_interval)

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            base_wait = self.min_interval
            jitter = base_wait * random.uniform(-0.2, 0.2)
            wait = base_wait + jitter - (now - self.last_request)
            if wait > 0:
                log.debug("RateLimiter: sleeping %.3fs (jitter=%.3fs)", wait, jitter)
                await asyncio.sleep(wait)
            self.last_request = time.monotonic()


class SporeAPI:
    def __init__(self, requests_per_second: float = 1.5, timeout: int = 30, max_retries: int = 3, user_agent: str = None):
        self.rate_limiter = RateLimiter(requests_per_second)
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.user_agent = user_agent or USER_AGENT
        self.session: Optional[aiohttp.ClientSession] = None
        self._batch_id = 0
        log.info("SporeAPI init: rate=%.1f, timeout=%ds, retries=%d, UA=%s", requests_per_second, timeout, max_retries, self.user_agent)

    async def __aenter__(self):
        log.info("SporeAPI: opening session (UA=%s)", self.user_agent)
        self.session = aiohttp.ClientSession(
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
        )
        return self

    async def __aexit__(self, *args):
        if self.session:
            log.info("SporeAPI: closing session")
            await self.session.close()

    async def _request(self, url: str) -> dict:
        for attempt in range(self.max_retries):
            await self.rate_limiter.acquire()
            try:
                log.debug("REST request [%d/%d]: %s", attempt + 1, self.max_retries, url)
                async with self.session.get(url) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        log.debug("REST response 200: %s (%d bytes)", url, len(text))
                        return xmltodict.parse(text)
                    elif resp.status in (401, 403):
                        log.warning("REST auth error %d for %s - server signed off", resp.status, url)
                        raise AuthError(f"Server signed off (HTTP {resp.status})")
                    elif resp.status == 429:
                        wait = 2 ** attempt
                        log.warning("Rate limited on %s, waiting %ds (attempt %d/%d)", url, wait, attempt + 1, self.max_retries)
                        print(f"  Rate limited, waiting {wait}s...")
                        await asyncio.sleep(wait)
                    else:
                        log.warning("REST HTTP %d for %s (attempt %d/%d)", resp.status, url, attempt + 1, self.max_retries)
                        print(f"  HTTP {resp.status} for {url}")
                        return {}
            except Exception as e:
                if attempt < self.max_retries - 1:
                    log.error("REST error on %s: %s (attempt %d/%d, retrying)", url, e, attempt + 1, self.max_retries)
                    await asyncio.sleep(1)
                else:
                    log.error("REST error on %s: %s (attempt %d/%d, giving up)", url, e, attempt + 1, self.max_retries)
                    print(f"  Error: {e}")
                    return {}
        log.warning("REST request exhausted retries for %s", url)
        return {}

    def _build_dwr_body(self, service: str, method: str, params: list) -> str:
        self._batch_id += 1
        lines = [
            f"callCount=1",
            f"scriptSessionId=B46A8740BB941667AB32B719F1B7115A19",
            f"c0-scriptName={service}",
            f"c0-methodName={method}",
            f"c0-id=0",
        ]
        for i, param in enumerate(params):
            if isinstance(param, str):
                lines.append(f"c0-param{i}=string:{param}")
            elif isinstance(param, int):
                lines.append(f"c0-param{i}=number:{param}")
            else:
                lines.append(f"c0-param{i}={param}")
        lines.append(f"batchId={self._batch_id}")
        return "\n".join(lines)

    def _parse_dwr_response(self, text: str) -> list:
        match = re.search(r'_remoteHandleCallback\([^,]+,\s*[^,]+,\s*(\[.*?\]|\{.*?\})\)', text, re.DOTALL)
        if match:
            try:
                import json
                return json.loads(match.group(1))
            except:
                pass
        return []

    async def _dwr_request(self, service: str, method: str, params: list) -> list:
        url = f"{BASE_URL}/jsserv/call/plaincall/{service}.{method}.dwr"
        body = self._build_dwr_body(service, method, params)
        log.debug("DWR request [%s.%s]: %s (batch=%d)", service, method, url, self._batch_id)

        for attempt in range(self.max_retries):
            await self.rate_limiter.acquire()
            try:
                async with self.session.post(url, data=body, headers={"Content-Type": "text/plain"}) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        result = self._parse_dwr_response(text)
                        log.debug("DWR response 200: %s.%s -> %d items", service, method, len(result))
                        return result
                    elif resp.status in (401, 403):
                        log.warning("DWR auth error %d for %s.%s - server signed off", resp.status, service, method)
                        raise AuthError(f"DWR server signed off (HTTP {resp.status})")
                    elif resp.status == 429:
                        wait = 2 ** attempt
                        log.warning("DWR rate limited on %s.%s, waiting %ds (attempt %d/%d)", service, method, wait, attempt + 1, self.max_retries)
                        print(f"  Rate limited, waiting {wait}s...")
                        await asyncio.sleep(wait)
                    else:
                        log.warning("DWR HTTP %d for %s.%s (attempt %d/%d)", resp.status, service, method, attempt + 1, self.max_retries)
                        print(f"  DWR HTTP {resp.status}")
                        return []
            except Exception as e:
                if attempt < self.max_retries - 1:
                    log.error("DWR error on %s.%s: %s (attempt %d/%d, retrying)", service, method, e, attempt + 1, self.max_retries)
                    await asyncio.sleep(1)
                else:
                    log.error("DWR error on %s.%s: %s (attempt %d/%d, giving up)", service, method, e, attempt + 1, self.max_retries)
                    print(f"  DWR Error: {e}")
                    return []
        log.warning("DWR request exhausted retries for %s.%s", service, method)
        return []

    async def get_buddies(self, username: str) -> list[str]:
        log.info("REST: get_buddies(%s)", username)
        data = await self._request(f"{BASE_URL}/rest/users/buddies/{username}/0/100")
        buddies_data = data.get("users", {}).get("buddy", [])
        if isinstance(buddies_data, dict):
            buddies_data = [buddies_data]
        result = [b.get("name", "") for b in buddies_data if isinstance(b, dict)]
        log.info("Buddies for '%s': %d found - %s", username, len(result), result)
        return result

    async def get_stats(self) -> dict:
        log.info("REST: get_stats()")
        data = await self._request(f"{BASE_URL}/rest/stats")
        stats = data.get("stats", {})
        log.info("Stats: %s", stats)
        return stats

    async def search_assets(
        self, view: str, start: int, length: int, asset_type: str = None
    ) -> list[Asset]:
        url = f"{BASE_URL}/rest/assets/search/{view}/{start}/{length}"
        if asset_type:
            url += f"/{asset_type}"
        log.info("REST: search_assets(view=%s, start=%d, length=%d, type=%s)", view, start, length, asset_type)

        data = await self._request(url)
        assets_data = data.get("assets", {}).get("asset", [])
        if isinstance(assets_data, dict):
            assets_data = [assets_data]

        result = [Asset.from_api(a) for a in assets_data]
        log.info("search_assets: %d assets returned (view=%s, start=%d)", len(result), view, start)
        return result

    async def get_asset(self, asset_id: int) -> Optional[Asset]:
        log.info("REST: get_asset(%d)", asset_id)
        data = await self._request(f"{BASE_URL}/rest/asset/{asset_id}")
        asset_data = data.get("asset")
        if asset_data:
            result = Asset.from_api(asset_data)
            log.info("Asset %d: '%s' by %s (type=%s)", result.id, result.name, result.author, result.type)
            return result
        log.info("Asset %d: not found", asset_id)
        return None

    async def get_user_assets(self, username: str, start: int, length: int) -> list[Asset]:
        log.info("REST: get_user_assets(%s, start=%d, length=%d)", username, start, length)
        data = await self._request(f"{BASE_URL}/rest/assets/user/{username}/{start}/{length}")
        assets_data = data.get("assets", {}).get("asset", [])
        if isinstance(assets_data, dict):
            assets_data = [assets_data]
        result = [Asset.from_api(a) for a in assets_data]
        log.info("User '%s' assets: %d returned", username, len(result))
        return result

    async def get_user_sporecasts(self, username: str) -> list[Sporecast]:
        log.info("REST: get_user_sporecasts(%s)", username)
        data = await self._request(f"{BASE_URL}/rest/sporecasts/{username}")
        sporecasts_data = data.get("sporecasts", {}).get("sporecast", [])
        if isinstance(sporecasts_data, dict):
            sporecasts_data = [sporecasts_data]
        result = [Sporecast.from_api(s) for s in sporecasts_data]
        log.info("User '%s' sporecasts: %d found - %s", username, len(result), [(s.id, s.title) for s in result])
        return result

    async def get_sporecast_assets(self, sporecast_id: int, start: int, length: int) -> list[Asset]:
        log.info("REST: get_sporecast_assets(id=%d, start=%d, length=%d)", sporecast_id, start, length)
        data = await self._request(f"{BASE_URL}/rest/assets/sporecast/{sporecast_id}/{start}/{length}")
        assets_data = data.get("assets", {}).get("asset", [])
        if isinstance(assets_data, dict):
            assets_data = [assets_data]
        result = [Asset.from_api(a) for a in assets_data]
        log.info("Sporecast %d assets: %d returned", sporecast_id, len(result))
        return result

    async def search_sporecasts(self, search_text: str, max_results: int = 100) -> list[dict]:
        url = f"{BASE_URL}/jsserv/call/plaincall/searchService.searchSporecastsDWR.dwr"
        self._batch_id += 1
        body = (
            f"callCount=1\n"
            f"scriptSessionId=B46A8740BB941667AB32B719F1B7115A19\n"
            f"c0-scriptName=searchService\n"
            f"c0-methodName=searchSporecastsDWR\n"
            f"c0-id=0\n"
            f"c0-searchText={search_text}\n"
            f"c0-maxResults={max_results}\n"
            f"c0-filter=MOST_POPULAR\n"
            f"c0-param0=Object_Object:{{searchText:reference:c0-searchText,maxResults:reference:c0-maxResults,filter:reference:c0-filter}}\n"
            f"batchId={self._batch_id}"
        )
        log.info("DWR: searchSporecastsDWR(text='%s', max=%d, batch=%d)", search_text, max_results, self._batch_id)

        for attempt in range(self.max_retries):
            await self.rate_limiter.acquire()
            try:
                async with self.session.post(url, data=body, headers={"Content-Type": "text/plain"}) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        result = self._parse_sporecast_search(text)
                        log.info("DWR searchSporecastsDWR: %d results for '%s'", len(result), search_text)
                        return result
                    elif resp.status in (401, 403):
                        log.warning("DWR auth error %d for searchSporecastsDWR - server signed off", resp.status)
                        raise AuthError(f"searchSporecastsDWR server signed off (HTTP {resp.status})")
                    elif resp.status == 429:
                        wait = 2 ** attempt
                        log.warning("DWR rate limited on searchSporecastsDWR, waiting %ds (attempt %d/%d)", wait, attempt + 1, self.max_retries)
                        print(f"  Rate limited, waiting {wait}s...")
                        await asyncio.sleep(wait)
                    else:
                        log.warning("DWR HTTP %d for searchSporecastsDWR (attempt %d/%d)", resp.status, attempt + 1, self.max_retries)
                        print(f"  DWR HTTP {resp.status}")
                        return []
            except Exception as e:
                if attempt < self.max_retries - 1:
                    log.error("DWR error on searchSporecastsDWR: %s (attempt %d/%d, retrying)", e, attempt + 1, self.max_retries)
                    await asyncio.sleep(1)
                else:
                    log.error("DWR error on searchSporecastsDWR: %s (attempt %d/%d, giving up)", e, attempt + 1, self.max_retries)
                    print(f"  DWR Error: {e}")
                    return []
        log.warning("DWR request exhausted retries for searchSporecastsDWR")
        return []

    def _parse_sporecast_search(self, text: str) -> list[dict]:
        sporecasts = {}
        for m in re.finditer(r'(s\d+)\.id=(500\d{9})', text):
            var_name = m.group(1)
            sporecast_id = m.group(2)
            if var_name not in sporecasts:
                sporecasts[var_name] = {"id": sporecast_id}
        for m in re.finditer(r'(s\d+)\.title="([^"]*)"', text):
            var_name = m.group(1)
            if var_name in sporecasts:
                sporecasts[var_name]["title"] = m.group(2)
        for m in re.finditer(r'(s\d+)\.count=(\d+)', text):
            var_name = m.group(1)
            if var_name in sporecasts:
                sporecasts[var_name]["asset_count"] = int(m.group(2))
        for m in re.finditer(r'(s\d+)\.subscriptionCount=(\d+)', text):
            var_name = m.group(1)
            if var_name in sporecasts:
                sporecasts[var_name]["subscribers"] = int(m.group(2))
        return [sc for sc in sporecasts.values() if "id" in sc and "title" in sc]
