# storage/ changelog — database.py, png_metadata.py
# Newest entries at the top.

2026-06-27 png_metadata.py
  REASON: TypeError 'str' object cannot be interpreted as an integer in _escape_xml
  FIX:
  - _escape_xml() now converts input to str() before calling .replace()
  - Fixes crash when DWR returns datetime objects for lastUpdated field
  - build_sporecast_xml updated parameter type hint removed (now accepts any type)

2026-06-26 database.py
  REASON: Export column order for downloaded_assets and scanned_sporecasts unreadable
  FIX:
  - Reordered downloaded_assets columns: asset_id, downloaded_at, file_size, file_path
  - Reordered scanned_sporecasts columns: sporecast_id, asset_count, subscribers, discovered_at, title, author

2026-06-25 database.py
  REASON: No sporecast checkpoint table for resume support
  FIX:
  - Added sporecast_downloaded table to _create_tables()
  - Added record_sporecast_downloaded() and is_sporecast_downloaded() methods
  - Used by crawl_sporecast to checkpoint each completed sporecast

2026-06-24 database.py
  REASON: Database not usable as context manager
  FIX:
  - Added __enter__ and __exit__ methods
  - close() docstring: "Safe to call multiple times. Idempotent."

2026-06-24 png_metadata.py
  REASON: Em dash in docstrings caused SyntaxError; leftover text from bad edit
  FIX:
  - Replaced em dashes with -- in docstrings
  - Cleaned up leftover docstring text
