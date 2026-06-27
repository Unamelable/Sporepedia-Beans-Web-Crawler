# cli/commands/ changelog - per command
# Newest entries at the top.

## sporecast.py, config.py
2026-06-27
  REASON: Missing cli_ui formatting, no login feedback, sporecast_search_mode config option
  FIX:
  - Replaced all raw print() calls with print_info/print_success/print_error from cli_ui
  - Added _auth_status helper for initial login messages (scroll_print fallback before hotkey exists)
  - Added sporecast_search_mode config: 'batch' (enumerate all then download) vs 'sequential' (search one download one)
  - Updated DEFAULT_CONFIG, quick preset, full preset, and config.yaml with sporecast_search_mode

## sporecast.py
2026-06-27
  REASON: X (stop) key hangs because crawl_sporecast doesn't check stop frequently
  FIX:
  - Added hotkey.should_stop() check inside asset loop (breaks current page)
  - Added hotkey.should_stop() check after asset loop (breaks page loop)
  - Stop now checkpoints current sporecast and returns immediately

## sporecast.py
2026-06-27
  REASON: FG_GREEN UnboundLocalError on "No sporecast source" screen; raw print() skips cli_ui formatting
  FIX:
  - Changed imports from spore_crawler.ui to spore_crawler.cli_ui (FG_YELLOW, FG_GREEN, FG_RED)
  - Added print_info, print_success, print_error imports from cli_ui
  - Replaced raw print(f'{FG_GREEN}...') with print_info() for themed output
  - Updated dependency header: ui -> cli_ui

## crawl.py, sporecast.py, search.py
2026-06-26
  REASON: Race condition on X stop - scroll_print messages overlap with results/hint
  FIX:
  - Removed scroll_print("Stopping...") and scroll_print("Progress has been saved.") from all three commands
  - These messages are now included in result_lines list instead
  - Result lines render above the hint area via print_results (no scroll area conflict)

## sporecast.py
2026-06-26
  REASON: Missing FG_RED import causes NameError in ensure_auth when login fails
  FIX:
  - Added FG_RED to imports from spore_crawler.ui (was: FG_YELLOW, FG_GREEN only)
  - Added "Logging in..." scroll_print message at start of ensure_auth for user feedback
  - Added else branch in ensure_auth to distinguish first login from relogin

## sporecast.py
2026-06-26
  REASON: --key path passes string subscriptionCount to crawl_sporecast causing TypeError on pause
  FIX:
  - Changed item.get('subscriptionCount', 0) to int(item.get('subscriptionCount', 0) or 0)
  - Ensures all numeric DWR response values are properly typed before processing

## sporecast.py
2026-06-26
  REASON: --all inline enumeration finds ALL sporecasts before downloading any
  FIX:
  - Rewrote --all inline enumeration to interleave search and download
  - Each sporecast is downloaded immediately after being found via DWR
  - Progress shows current sporecast name and download count in real-time
  - Returns early with results after enumeration completes

## crawl.py, search.py, sporecast.py
2026-06-26
  REASON: Hotkey X causes race condition - hotkey thread clears progress while main thread renders
  FIX:
  - Added _on_stop callback mechanism to HotkeyController
  - All three commands set callback via hotkey.set_stop_callback(lambda: _stopped_by_user.set())
  - After hotkey.stop(), commands check _stopped_by_user.is_set() and print "Stopping..." + "Progress has been saved."
  - All screen refresh now handled by main thread (no hotkey thread rendering)
  - crawl.py: added threading import, _stopped_by_user event, callback wiring (both --db and main paths)

## search.py
2026-06-26
  REASON: No feedback during login phase - user sees nothing while Playwright starts
  FIX:
  - Added scroll_print("Logging in...") before ensure_auth() call
  - Added FG_YELLOW to imports from cli_ui

## sporecast.py
2026-06-26
  REASON: Database naming labels were swapped in --db mode
  FIX:
  - Swapped db_label values: search_db now labeled 'search_sporepedia.db', browse_db labeled 'sporecast_search.db'
  - Updated log.info message to match corrected names

## crawl.py
2026-06-26
  REASON: Database references pointed to wrong filenames after naming fix
  FIX:
  - Updated print messages from 'search_sporepedia.db' to 'sporecast_search.db' (browse DB)

## clean.py, convert_sql.py, browse.py
2026-06-26
  REASON: Database filename references inconsistent after naming fix
  FIX:
  - Updated docstrings and export labels to match corrected database paths

## sporecast.py
2026-06-26
  REASON: NameError crash -- hotkey referenced before creation in use_temp branch
  FIX:
  - Moved auth setup (credentials, SporeAuth, ensure_auth) before mode branching
  - Moved HotkeyController creation before mode branching
  - Removed old duplicated hotkey creation after sporecast_ids processing
  - Cleaned up redundant nested `if keyword:` check in keyword branch

## bean.py
2026-06-26
  REASON: bean_test missing browsed_assets DB tests (browse command feature)
  FIX:
  - Added DB test: record_browsed_asset
  - Added DB test: is_asset_browsed
  - Added DB test: get_browsed_asset_count
  - Added DB test: get_all_browsed_assets

## browse.py
2026-06-26
  REASON: Browse ran immediately without limiting; no --all flag
  FIX:
  - Added enumerate_all parameter to cmd_browse()
  - When enumerate_all=True, browses all 4 types (creature/building/vehicle/adventure)
  - Dispatch guard: no types + no --all = show help

## crawl.py
2026-06-26
  REASON: No way to download from browse database
  FIX:
  - Added --db flag to download assets from search_sporepedia.db
  - Added use_browse_db parameter to cmd_crawl()
  - Reads browsed_assets table and downloads each asset
  - Applies metadata embedding when enabled
  - Added get_browse_db_path import

## clean.py
2026-06-26
  REASON: Missing search_sporepedia.db from cleanable databases
  FIX:
  - Added get_browse_db_path import
  - Added browse_db to databases list and database_txt list
  - Updated docstring to mention search_sporepedia.db

## convert_sql.py
2026-06-26
  REASON: Missing search_sporepedia.db from exportable databases
  FIX:
  - Added get_browse_db_path import
  - Added 'browse' type for exporting search_sporepedia.db
  - Added browse_db to 'all' type export
  - Updated error message to list 'browse' as valid type

## sporecast.py
2026-06-26
  REASON: --db only checked sporecast_search.db, not search_sporepedia.db
  FIX:
  - Added get_browse_db_path import
  - --db now falls back to search_sporepedia.db if sporecast_search.db is empty
  - Updated log and print messages to show which DB was loaded

## search.py
2026-06-26
  REASON: _sporecast_info.xml missing metadata; relogin prints 3 lines; temp file format lacks metadata
  FIX:
  - Updated _parse_sporecast_dwr_response to extract description, tags, rating, last_updated
  - Replaced print() relogin messages with scroll_print() (single-line, themed)
  - Updated temp file format to 9 fields: id, assets, subs, author, title, description, rating, tags, last_updated

## sporecast.py
2026-06-26
  REASON: _sporecast_info.xml missing tags/description/rating/updated/subscribers; relogin prints 3 lines
  FIX:
  - Expanded sporecast_ids tuple from 3 to 8 fields (added subtitle, rating, tags, updated, subscribers)
  - Updated all sporecast_ids creation sites (username, db, temp, keyword modes)
  - Passes all metadata fields to crawl_sporecast()
  - Replaced print() relogin messages with scroll_print() (single-line, themed)

## search.py
2026-06-25
  REASON: Single-char terms return nothing; progress only shows after each page; no re-auth on DWR fail
  FIX:
  - Added warning if any search term is <= 1 character before login
  - Added per-entry progress bar updates (downloaded/skipped/page) inside keyword and enumerate loops
  - Added auto re-auth attempt when DWR calls fail in enumerate_all loop

## sporecast.py
2026-06-25
  REASON: --key argument missing; temp file inline enumeration omits author; folder names wrong
  FIX:
  - Added --key <keyword> argument: searches DWR by keyword then downloads matching sporecasts
  - Inline enumeration temp file write now includes author in format: id assets subs author title
  - Updated no-source error message to mention --key

## list.py
2026-06-25
  REASON: list command only searched by author, no --fields support
  FIX:
  - Added --fields argument: title, author, tags, subtitle, or all
  - Uses search_sporecasts() instead of search_sporecasts_by_author()
  - Default search field is author (backwards compatible)

## convert_sql.py
2026-06-25
  REASON: References outdated spore_crawler.db name
  FIX:
  - Changed display labels from 'spore_crawler.db' to 'sporepedia.db'

## clean.py
2026-06-25
  REASON: Docstring referenced spore_crawler.db
  FIX:
  - Updated docstring to sporepedia.db

## clean.py
2026-06-25
  REASON: Clean command failed to delete crawler.log (WinError 32, file in use)
  FIX:
  - Added logging handler shutdown before deleting crawler.log
  - Closes all FileHandler instances pointing to the log path, then removes them

## search.py
2026-06-25
  REASON: Multiple issues: credential prompt after progress bar (ugly), pagination breaks early, skipped msg overwritten by pause prompt
  FIX:
  - Moved credential resolution + login BEFORE hotkey/progress startup
  - Added login feedback ("Logging in... OK/FAILED")
  - Fixed pagination: removed `new_count == 0` early break condition
  - Fixed progress bar: page number now tracks actual page (index//200+1)
  - Replaced final scroll_print() with print_results() to avoid pause prompt overlap
  - Updated temp file comment from "python -m spore_crawler" to direct command
  - Removed redundant scroll_print/login code paths (unified 2 branches into 1)

## sporecast.py
2026-06-25
  REASON: --all fails when temp file missing; dead config sporecast_users branch; no checkpoint resume
  FIX:
  - --all now runs inline enumeration when sporecasts_temp.txt is missing (generates it automatically)
  - Removed dead `else: log.info('Mode: config sporecast_users')` branch
  - Added checkpoint skip via download_db.is_sporecast_downloaded() before processing each sporecast

## clean.py
2026-06-25
  REASON: Clean command didn't clean test_downloads, no config control
  FIX:
  - Added test_downloads/ folder to cleanable items
  - Added config['clean'] section with bools for each category
  - Categories: databases, downloads, chunks, config_yaml, crawler_log, credentials, database_txt, test_downloads
  - Defaults: databases/downloads/chunks=true, rest=false

## convert_sql.py
2026-06-25
  REASON: convert-sql had "search / sporecast" abbreviation; output lacked color
  FIX:
  - Removed 'sporecast' as alias for 'search' type (search is now standalone)
  - Renamed 'sporecasts' type to 'sporecast' (singular)
  - Fixed unreachable elif branch for 'sporecast' type
  - Added colored output: green for database name + "Found X tables:", red for "DATABASE NOT FOUND:"
  - Updated help text and error messages

## search.py
2026-06-25
  REASON: Search end comment "To download this list, type: sporecast --temp" renders wrong
  FIX:
  - Removed the 3 scroll_print lines (empty line + hint text)
  - Final output is now just "Saved to: {path}" in green

## sporecast.py
2026-06-25
  REASON: sporecast --all argument fails with "No sporecast source specified"
  FIX:
  - --all now implies --temp (reads from sporecasts_temp.txt populated by search --all)
  - Updated error message to list all valid source options including --all

## bean.py
2026-06-25
  REASON: bean_test didn't test login; no way to test with credentials
  FIX:
  - bean_test now tests login first (EA SSO)
  - If no credentials saved, prompts for them interactively
  - If login fails, shows error and asks Continue/Exit before skipping API tests
  - Login test uses SporeAuth directly (not via API client)

## convert_sql.py
2026-06-25
  REASON: sporecasts.db was not included in export
  FIX:
  - Added 'sporecasts' type to export sporecasts.db separately
  - Updated 'all' type to export all 3 databases (was: only 2)
  - Updated help text and error messages

## config_cmd.py
2026-06-25
  REASON: Help text referenced "python -m spore_crawler" invocation
  FIX:
  - Replaced all "python -m spore_crawler config ..." with "config ..." in user-facing messages

## search.py
2026-06-25
  REASON: Output hint referenced old invocation style
  FIX:
  - Changed "python -m spore_crawler sporecast --temp" to "sporecast --temp"

## login.py
2026-06-25
  REASON: login command lacked credential management flags
  FIX:
  - Added --new flag: prompt for email/password, replace credentials.json on success
  - Added --del/--rem/--delete/--remove flags: delete credentials.json
  - Removed redundant get_credentials(config) path (config no longer stores email)
  - cmd_login() now accepts new_creds and delete parameters

## search.py
2026-06-25
  REASON: Help text referenced auth.email which was removed from config
  FIX:
  - Changed credential prompt text from "Set auth.email in config.yaml" to "Run 'login --new'"

## sporecast.py
2026-06-25
  REASON: Help text referenced auth.email which was removed from config
  FIX:
  - Changed credential prompt text from "Set auth.email in config.yaml" to "Run 'login --new'"

## list.py
2026-06-25
  REASON: REST API shows incomplete results with broken encoding for Asian chars
  FIX:
  - Removed REST API fallback entirely - always uses DWR (requires login)
  - Removed --all flag (was redundant since DWR is now the only method)
  - Updated help text to reflect new behavior

## search.py
2026-06-25
  REASON: search output overflows CMD screen, temp file format unreadable
  FIX:
  - Replaced all print() calls with scroll_print() to stay within scroll area
  - Temp file format changed to: id, assets, subs, title (was: id, title, assets, subs)
  - Removed unused print_results import (now imported at module level)

## auth.py
2026-06-25
  REASON: credentials.json stores plaintext passwords
  FIX:
  - Added XOR obfuscation with base64 encoding (v2 format)
  - Backwards compatible: still reads old v1 plaintext format
  - Key derived from program path constant

## search.py
2026-06-25
  REASON: search --all prints every sporecast to CMD, exits after page 1
  FIX:
  - Changed per-sporecast print() to log.info() - output goes to crawl.log only
  - Added 3-second countdown between pages with progress display
  - Page summary still prints to CMD for user visibility

## sporecast.py
2026-06-25
  REASON: --username creates fresh SporeAuth session per user (slow)
  FIX:
  - _get_user_sporecasts() now accepts optional auth= param to reuse session
  - cmd_sporecast creates auth early when --username or --all is used
  - Config user loop also reuses shared auth session
  - needs_auth now includes username mode (was: only --all)

## search.py
2026-06-24
  REASON: search --all crashes (asyncio not defined), theme mismatch, progress bar incomplete
  FIX:
  - Moved import asyncio from 4 scattered local imports to module level
  - Added cli_ui imports (set_colors, FG_*) for themed output
  - Applied themed colors to all print() calls in both search paths
  - Fixed progress: set hotkey.progress.downloaded/skipped/page before render_progress()
  - Fixed counter: non-enumerate uses len(all_sporecasts) not per-term new_count

## login.py
2026-06-24
  REASON: Login output lacked theme colors
  FIX:
  - Added cli_ui imports (set_colors, FG_*)
  - Applied themed colors to all print() calls

## sporecast.py
2026-06-24
  REASON: Added dependency header with Side effects section
  (No logic changes)

## crawl.py
2026-06-24
  REASON: Added dependency header with Side effects section
  (No logic changes)

## list.py, stats.py, config_cmd.py, convert_sql.py, bean.py
2026-06-24
  REASON: Added dependency header with Side effects section
  (No logic changes)
