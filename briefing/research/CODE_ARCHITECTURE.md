# SPORE Web Crawler — Architecture

## Entry flow
```
__main__.py  →  cli/__init__.py::main()
                    ├── No args → interactive mode (@> prompt)
                    └── Has args → _dispatch_from_argv() → cmd_*() → pause_for_exit()
```

## Layer map

| Layer | Package | Responsibility |
|-------|---------|----------------|
| **api** | `api/auth.py` | EA SSO login via Playwright headless browser. Returns JSESSIONID cookie. Manages browser lifecycle. |
| | `api/client.py` | Async HTTP client for Spore REST + DWR APIs. Rate limiting, retries, XML parsing. |
| **cli** | `cli/__init__.py` | Main dispatcher. Arg parsing, interactive mode, command routing. |
| | `cli/commands/*` | Individual command implementations (login, search, browse, crawl, sporecast, list, stats, config, convert-sql, clean, bean). |
| | `cli/commands/_common.py` | Shared imports hub + mutable `state` dict (used_progress_bar, skip_pause). |
| | `cli/config.py` | YAML config loading, validation, presets, env overrides. |
| | `cli/utilities.py` | Path resolution, temp file reading, DB export helpers. |
| | `cli/help_text.py` | All help text, command aliases, usage strings. |
| **crawlers** | `crawlers/full_crawler.py` | Core download engine. Downloader class, crawl_assets(), crawl_sporecast(). |
| | `crawlers/hotkeys.py` | Keyboard hotkey controller (P/R/X) in daemon thread. |
| **storage** | `storage/database.py` | SQLite persistence. Downloads, progress, sporecast tracking, chunks. Context manager. |
| | `storage/png_metadata.py` | Embed XML metadata as zTXt chunks in PNG files. |
| **ui** | `ui/__init__.py` | RGB color constants, basic print helpers. |
| | `ui/progress.py` | ProgressDisplay, Spinner, scroll area, fixed-bottom rendering. |
| | `cli_ui.py` | Win32 console API theming, palette remapping, banner, exit cleanup. |
| **organizers** | `organizers/folders.py` | Asset subtype → folder mapping, path helpers. |
| **models** | `models.py` | Data classes: Asset, Sporecast, CrawlProgress, enums. |

## Data flow: crawl command
```
cli/__init__ → cmd_crawl()
  → SporeAPI (REST) → pages of assets
  → Downloader → aiohttp downloads PNGs
  → Database.record_download() (SQLite)
  → png_metadata.embed_metadata_in_png()
  → organizers/folders.get_asset_path() (file placement)
```

## Data flow: search --all
```
cli/__init__ → cmd_search(enumerate_all=True)
  → SporeAuth.login() (Playwright → EA SSO → JSESSIONID)
  → SporeAuth.navigate_to_sporepedia()
  → SporeAuth.make_dwr_call(sporecastService.listSporecastInfos)
  → _parse_sporecast_dwr_response() (regex parse DWR JS response)
  → Database.record_sporecast_scan()
  → save to sporecasts_temp.txt
```

## Data flow: sporecast command
```
cli/__init__ → cmd_sporecast()
  → Sources: --username / --id / --db / --temp / --all
  → --all implies --temp (reads sporecasts_temp.txt from search --all)
  → --db checks search_sporepedia.db then search_sporecast.db
  → SporeAPI.get_sporecast_assets() or SporeAuth DWR
  → crawl_sporecast() → aiohttp downloads
  → Database + png_metadata
```

## Data flow: browse command
```
cli/__init__ → cmd_browse()
  → SporeAPI.search_sporecasts() (REST DWR, no auth needed)
  → _parse_sporecast_search() (regex parse DWR JS response)
  → Database.record_sporecast_scan() → search_sporepedia.db
```

## Key patterns

### Shared state
`cli/commands/_common.py` exports `state = {'used_progress_bar': False, 'skip_pause': False}`.
Commands mutate this; `cli/__init__.py` reads/resets it after each command.

### Hotkey lifecycle
Every crawl/search/sporecast command must:
1. Create `HotkeyController()` and call `.start()`
2. Check `.should_stop()` and `.async_wait_if_paused()` in loops
3. Call `.stop()` in finally block (or after loop)

### Database lifecycle
`Database(db_path)` opens SQLite. Must be closed.
Supports context manager: `with Database(path) as db:`
Four separate DB files:
- `sporepedia.db` — main crawl tracking
- `search_sporecast.db` — search enumeration (authenticated DWR)
- `sporecasts.db` — sporecast downloads
- `search_sporepedia.db` — browse results (REST DWR, no auth)

### Auth lifecycle
`SporeAuth(email, password)` → `.login()` → `.navigate_to_sporepedia()` → DWR calls → `.close()`
Session expires; re-auth via `ensure_valid_session()` or manual `.close()` + new instance.

### Progress bar
`ProgressDisplay` renders at console bottom (rows h-3, h-2).
`scroll_print()` prints in the area above (row h-6).
`print_results()` clears progress and writes final output.
Hotkeys hint at row h-2.

## Cleanup obligations (must be done on every code path)

| Resource | Cleanup | Enforced by |
|----------|---------|-------------|
| `Database` | `.close()` | Context manager (`with`) or try/finally |
| `HotkeyController` | `.stop()` | try/finally |
| `SporeAuth` | `.close()` | try/finally |
| `SporeAPI` | `__aexit__` | `async with SporeAPI(...) as api:` |
| Console palette | `_exit_cleanup()` | atexit handler (auto) |

## File dependency hints

Every `.py` file in `spore_crawler/` has a docstring header:
```
"""
<module>.py - <purpose>

Depends on: <internal modules this file imports from>
Used by: <internal modules that import from this file>
"""
```
Use these to quickly understand what a file touches without reading all its code.
