# crawlers/ changelog — full_crawler.py, hotkeys.py
# Newest entries at the top.

2026-06-27 full_crawler.py
  REASON: X (stop) key hangs because crawl_sporecast doesn't check stop frequently
  FIX:
  - Added hotkey.should_stop() check inside asset loop (breaks current page)
  - Added hotkey.should_stop() check after asset loop (breaks page loop)
  - Stop now checkpoints current sporecast and returns immediately

2026-06-26 hotkeys.py
  REASON: 'ProgressDisplay' object has no attribute 'clear_progress_display' crash on X hotkey
  FIX:
  - Changed self.progress.clear_progress_display() to clear_progress_display() (standalone function)

2026-06-25 hotkeys.py
  REASON: No checkpoint warning when exiting via X hotkey
  FIX:
  - Added scroll_print "Progress has been saved. You can resume later." after "Stopping..."
  - Updated log message to mention checkpoint saved

2026-06-25 full_crawler.py
  REASON: Downloaded count == Failed count bug; hotkey breaks mid-sporecast
  FIX:
  - Moved `failed += 1` from inside successful-download block to the `else:` (HTTP non-200) branch
  - Removed hotkey.should_stop() checks from inner asset loop so current sporecast always finishes
  - Added db.record_sporecast_downloaded() checkpoint after each completed sporecast

2026-06-24 full_crawler.py
  REASON: embed_metadata_in_png return value ignored; indentation bug
  FIX:
  - Both call sites: added "if not embed_metadata_in_png(...): log.warning"
  - crawl_sporecast(): fixed indentation of embed call (was outside if embed_metadata block)

2026-06-24 hotkeys.py
  REASON: Cleanup method lacked documentation
  FIX:
  - stop() docstring: "Safe to call multiple times. Idempotent."
