# api/ changelog — auth.py, client.py
# Newest entries at the top.

2026-06-26 auth.py
  REASON: DWR methods crash with I/O pipe broken error when page closed during evaluate()
  FIX:
  - Added PlaywrightError import for specific error handling
  - Wrapped page.evaluate() calls in make_dwr_call() with try/except, returns {ok: False, error} on failure
  - Wrapped page.evaluate() calls in search_sporecasts() with try/except, returns {error} on failure
  - Wrapped page.evaluate() calls in is_session_valid() with try/except, returns False on failure
  - Added PlaywrightError handling in navigate_to_sporepedia() for navigation failures
  - Research saved in briefing/research/dwr_io_pipe_graceful_close.md

2026-06-25 auth.py
  REASON: Config no longer stores email; login command needs delete support
  FIX:
  - Removed get_credentials_from_config() (auth.email removed from config)
  - Simplified get_credentials() to only check saved file + interactive prompt
  - Added delete_credentials(): removes credentials.json, returns bool

2026-06-25 auth.py
  REASON: credentials.json stores plaintext passwords (security risk)
  FIX:
  - Added XOR obfuscation with base64 encoding (v2 format)
  - _obfuscate(): XOR with key + base64 encode
  - _deobfuscate(): base64 decode + XOR reverse
  - Backwards compatible: reads old v1 plaintext if "v" key missing

2026-06-24 auth.py
  REASON: Login crashes with invalid username (raw Playwright timeout)
  FIX:
  - warnings.filterwarnings("ignore", "unclosed transport") at module level
  - _do_login(): try/except on wait_for_selector("#password"); checks SSO errors + signin.ea.com; raises clean RuntimeError
  - close(): removed asyncio.wait_for timeout, simplified to direct await
  - ensure_valid_session(): delegates to close() instead of manual cleanup
  - close() docstring: "Safe to call multiple times. Idempotent."
