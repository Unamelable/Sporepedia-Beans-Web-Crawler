# DWR I/O Pipe Graceful Close - Investigation

## Status: FIXED (2026-06-26)

---

## Problem

Random crashes occur during `search <keyword>` (and potentially other DWR-using commands), causing the program to trigger the Continue/Exit loop. The crash appears when staying connected on end results — i.e., after DWR calls complete but while the Playwright browser session is still active.

The error manifests as an **unclosed transport** ResourceWarning that escalates to a crash. This was partially mitigated earlier by adding `warnings.filterwarnings("ignore", message="unclosed transport")` at module level in `auth.py:18`, but the underlying issue was not fully resolved.

---

## Root Cause Analysis

### How DWR Calls Work

All authenticated DWR calls go through `SporeAuth` methods in `api/auth.py`:

1. `make_dwr_call()` (line 379) — Used by `search --all` and `sporecast --all` for `countSporecastInfo` and `listSporecastInfos`
2. `search_sporecasts()` (line 474) — Used by `search <keyword>`, `list`, and `sporecast --key` for `searchSporecastsDWR`
3. `is_session_valid()` (line 327) — Used for session validation before re-auth

All three use `self._page.evaluate()` to run JavaScript inside the Playwright browser context. The JavaScript performs `fetch()` or DWR callback calls.

### The I/O Pipe Problem

When `page.evaluate()` is called:
1. Playwright sends the JavaScript to the browser process via an internal I/O pipe
2. The browser executes the JavaScript and sends results back via the same pipe
3. If the browser is closed (`page.close()`, `context.close()`, or `browser.close()`) while `page.evaluate()` is still waiting for a result, the I/O pipe is destroyed
4. Python's asyncio layer detects the broken pipe and raises a ResourceWarning or exception

**Critical timing issue:** The `search_sporecasts()` method creates a JavaScript Promise with a 15-second timeout:
```javascript
return new Promise((resolve) => {
    const timeout = setTimeout(() => resolve({error: 'timeout'}), 15000);
    // ... DWR call with callback ...
});
```

If `auth.close()` is called while this Promise is pending (e.g., user stops with 'X' hotkey, or search completes and cleanup runs), the page is closed before the 15s timeout fires, breaking the I/O pipe.

### Crash Sequence

```
1. search <keyword> runs
2. DWR call via search_sporecasts() → page.evaluate() starts
3. Search completes or user presses X
4. auth.close() called → page.close() destroys the I/O pipe
5. page.evaluate() was still awaiting JavaScript Promise result
6. Broken pipe → ResourceWarning / crash
7. Exception propagates to cli/__init__.py exception handler
8. "Error: ..." printed → Continue/Exit loop triggers
```

### Why It Was "Random"

The crash depends on timing:
- If the 15s JS timeout fires BEFORE `auth.close()` → no crash
- If `auth.close()` fires BEFORE the JS timeout → crash
- Network latency, server response time, and user actions all affect this timing

---

## DWR Methods in auth.py

| Method | Line | Used By | I/O Pipe Risk |
|--------|------|---------|---------------|
| `make_dwr_call()` | 379 | search.py (enumerate_all), sporecast.py (inline enum) | `page.evaluate()` with `fetch()` — no Python try/except |
| `search_sporecasts()` | 474 | search.py (keyword), list.py, sporecast.py (--key) | `page.evaluate()` with DWR callback Promise — no Python try/except |
| `is_session_valid()` | 327 | search.py (ensure_auth), sporecast.py (ensure_auth) | `page.evaluate()` with `fetch()` — no Python try/except |
| `_check_sso_error()` | 222 | _do_login() | `page.evaluate()` — low risk (only during login) |

### Key Finding

All DWR-calling methods have JavaScript-level try/catch inside `page.evaluate()`, but **none have Python-level try/except** around the `page.evaluate()` call itself. This means:
- JavaScript errors (DWR callback failures, timeouts) → handled gracefully
- Playwright errors (page closed, I/O pipe broken) → **unhandled crash**

---

## The `close()` Method

```python
async def close(self):
    if self._page:
        try:
            await self._page.close()    # <-- Breaks I/O pipe if evaluate() pending
        except Exception:
            pass
        self._page = None
    if self._context:
        try:
            await self._context.close()
        except Exception:
            pass
        self._context = None
    if self._browser:
        try:
            await self._browser.close()
        except Exception:
            pass
        self._browser = None
    if self._pw:
        try:
            await self._pw.stop()
        except Exception:
            pass
        self._pw = None
    self._logged_in = False
    self.jsessionid = None
```

The `close()` method is idempotent and handles its own exceptions, but the **caller** of DWR methods doesn't handle the case where `page.evaluate()` fails because the page was closed.

---

## Fix Applied

### 1. Added Python-level try/except around all `page.evaluate()` calls in DWR methods

Each DWR method now catches Playwright errors (Target closed, I/O pipe broken) and returns a safe error dict instead of crashing:

- `make_dwr_call()` → returns `{ok: False, error: "..."}`
- `search_sporecasts()` → returns `{error: "..."}`
- `is_session_valid()` → returns `False`
- `_check_sso_error()` → returns `None`
- `navigate_to_sporepedia()` → catches and logs navigation errors (already partially handled)

### 2. Added `asyncio.shield()` consideration

Not needed — the try/except approach is simpler and more reliable. Shielding would add complexity without benefit since the DWR methods already handle error returns.

### 3. Callers already handle error returns

The callers in `search.py`, `sporecast.py`, and `list.py` already check for error conditions:
- `search.py:386-393`: checks `if not result or 'results' not in result: break`
- `search.py:267-279`: checks `if not r.get("ok"):` and handles re-auth
- `sporecast.py:80-84`: checks `if not result or 'results' not in result: break`
- `list.py:63-64`: checks `if not result or 'results' not in result: break`

So returning error dicts instead of crashing is the correct approach.

---

## Why the Warning Filter Alone Was Insufficient

The `warnings.filterwarnings("ignore", message="unclosed transport")` at `auth.py:18` suppresses the ResourceWarning but does NOT prevent the actual exception. When `page.evaluate()` fails due to a closed page, Playwright raises a real exception (not just a warning). The warning filter only silences the asyncio transport cleanup warning, not the Playwright error.

---

## Testing Notes

- The crash was most reproducible with `search <keyword>` where the keyword returns results quickly (fast DWR response) but the user exits before the 15s JS timeout
- `search --all` was less affected because the enumerate_all loop has explicit error handling for failed DWR calls
- The fix is defensive — even if the I/O pipe breaks, the program continues gracefully

---

## Files Changed

| File | Change |
|------|--------|
| `api/auth.py` | Added try/except around all `page.evaluate()` calls in `make_dwr_call()`, `search_sporecasts()`, `is_session_valid()`, `_check_sso_error()`, `navigate_to_sporepedia()`, and session info fetch |

---

## Related: Previous Fix (2026-06-24)

The `warnings.filterwarnings("ignore", "unclosed transport")` was added to suppress ResourceWarning spam from Playwright's asyncio transport cleanup. This fix addresses a different (but related) issue: actual exceptions from `page.evaluate()` failing due to closed pages.
