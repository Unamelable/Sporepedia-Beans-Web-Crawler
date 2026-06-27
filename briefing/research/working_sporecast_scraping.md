# Authenticated Sporecast Scraping - Implementation Guide

## Status: WORKING (2026-06-23)

All research and proof-of-concept scripts are in the project root (`temp_*.py`).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Playwright (headless=False for debug)                      │
│  1. Launch Chromium                                         │
│  2. Login via EA SSO (spore.com → signin.ea.com → callback)│
│  3. Navigate to /sporepedia (DWR scripts load)              │
│  4. Make manual DWR fetch calls from page.evaluate()        │
│  5. Parse DWR JavaScript responses in Python                │
└─────────────────────────────────────────────────────────────┘
```

**Why Playwright?** EA SSO requires browser automation. The DWR servlet needs a valid `JSESSIONID` cookie, which is set by the browser during the EA SSO redirect chain. Pure `aiohttp` cannot complete the SSO flow.

---

## Login Flow

```
spore.com/login.jsp
  → redirects to signin.ea.com/p/juno/login
  → Step 1: fill #email, click "ДАЛЕЕ" (Next)
  → Step 2: fill #password, click #logInBtn
  → Redirect chain (hits ERR_TOO_MANY_REDIRECTS - this is OK)
  → Cookies set: JSESSIONID, AWSALB, AWSALBCORS on spore.com
```

**Important:** The redirect loop error is expected and non-blocking. Cookies are set even though the page shows an error. Just navigate to `/sporepedia` after login.

---

## DWR Authentication Mechanism

### What We Discovered

The DWR `scriptSessionId` is **generated client-side** in `engine.js`:

```javascript
dwr.engine._origScriptSessionId = "AC660F2021240B98A2E6D4C22477D969"; // hardcoded in served JS
dwr.engine._getScriptSessionId = function() {
    if (dwr.engine._scriptSessionId == null) {
        dwr.engine._scriptSessionId = dwr.engine._origScriptSessionId + Math.floor(Math.random() * 1000);
    }
    return dwr.engine._scriptSessionId;
};
```

**Key finding:** The server does NOT validate `scriptSessionId`. Any value works as long as the `JSESSIONID` cookie is valid. The `_origScriptSessionId` changes on every page load (different each session).

### The Real Auth: JSESSIONID Cookie

The only authentication that matters is the `JSESSIONID` cookie set by the EA SSO redirect chain. All DWR calls must be made from the same browser context (or use the same cookie).

---

## DWR Request Body Format (Confirmed Working)

```
callCount=1
page=/sporepedia
httpSessionId={JSESSIONID_COOKIE}
scriptSessionId={ANY_VALUE}
c0-scriptName={serviceName}
c0-methodName={methodName}
c0-id=0
c0-e1=string:{value}
c0-e2=number:{value}
c0-e3=boolean:{true|false}
c0-param0=Object_Object:{key1:reference:c0-e1,key2:reference:c0-e2}
batchId={incrementing_int}
```

### Parameter Serialization Rules

| Type | Format | Example |
|------|--------|---------|
| String | `string:{value}` | `string:creature` |
| Number | `number:{value}` | `number:501116668587` |
| Boolean | `boolean:{true\|false}` | `boolean:true` |
| Null | `null:null` | `null:null` |
| Object | `Object_Object:{key:reference:c0-eN,...}` | See below |
| Array | `Array:[reference:c0-eN,...]` | `Array:[reference:c0-e1]` |

### Example: listSporecastInfos Call

```
callCount=1
page=/sporepedia
httpSessionId=D53A9BD0ABE5CD76B6AFB670A112E917
scriptSessionId=B69189A98E7A054FE2238FF818782DF8966
c0-scriptName=sporecastService
c0-methodName=listSporecastInfos
c0-id=0
c0-e1=string:THEME
c0-e2=number:501116668587
c0-e3=boolean:true
c0-e4=number:100
c0-param0=Object_Object:{type:reference:c0-e1,authorId:reference:c0-e2,showEmpty:reference:c0-e3,count:reference:c0-e4}
batchId=5
```

---

## Available DWR Methods (Authenticated)

### Sporecast Methods (sporecastService)

| Method | Parameters | Returns |
|--------|-----------|---------|
| `listSporecastInfos` | `{showEmpty: bool, count: int, index: int, type: string}` | Array of sporecast objects |
| `listSporecastInfosSubscribedToByUser` | `{number: userId}` | User's subscribed sporecasts |
| `countSporecastInfo` | `{type: string}` | Total count (e.g., 512983 for THEME) |
| `findSporecastAssets` | `{number: sporecastId, number: start, number: count}` | Assets in a sporecast |
| `searchSporecastsDWR` | `{searchText: string}` | Matching sporecasts |

### User Methods (loginService, sporeUserService)

| Method | Parameters | Returns |
|--------|-----------|---------|
| `loginService.getLoggedInUser` | (none) | Current user info |
| `sporeUserService.isCurrentUserEntitledToComment` | (none) | boolean |

### Asset Methods (assetService)

| Method | Parameters | Returns |
|--------|-----------|---------|
| `assetService.countAssets` | (none) | User's asset count |
| `assetService.countTotalAssets` | (none) | Total platform assets (~191M) |

---

## Pagination

- **Parameter:** `index` (start position), `count` (page size)
- **Max safe count:** 200 (500+ causes 504 Gateway Timeout)
- **Total THEME sporecasts:** 512,983
- **Estimated pages:** ~2,565 at count=200

```python
# Pagination loop
index = 0
PAGE_SIZE = 200
while index < total_count:
    sporecasts = dwr_call("sporecastService", "listSporecastInfos",
        {"showEmpty": True, "count": PAGE_SIZE, "index": index})
    index += PAGE_SIZE
```

---

## DWR Response Format

DWR responses are JavaScript, not JSON. Example:

```javascript
throw 'allowScriptTagRemoting is false.';
//#DWR-INSERT
//#DWR-REPLY
var s0=[];var s1={};var s2={};...
s0[0]=s1;s0[1]=s2;...
s1.assetIds=null;s1.assets=null;s1.author=s21;s1.count=551;...
s1.id=501116030789;s1.lastUpdated=new Date(1782199826079);...
s1.title="Vanilla+ Creatures ";s1.type='THEME';
s21.id=501088287156;s21.name="LansRu";s21.screenName="LansRu";...
dwr.engine._remoteHandleCallback('5','0',s0);
```

### Parsing Strategy

Use regex to extract fields from the DWR response. Each sporecast object has a consistent field order:

```python
pattern = re.compile(
    r's(\d+)\.assetIds=[^;]*;'
    r's\1\.assets=[^;]*;'
    r's(\d+)\.author=s(\d+);'
    r's\1\.count=(\d+);'
    r's(\d+)\.description=([^;]*);'
    r's\1\.featured=[^;]*;'
    r's(\d+)\.id=(\d+);'
    r's\1\.lastUpdated=[^;]*;'
    r's(\d+)\.locale=[^;]*;'
    r's(\d+)\.rating=[^;]*;'
    r's(\d+)\.sporecastId=s(\d+);'
    r's(\d+)\.subscribed=[^;]*;'
    r's(\d+)\.subscriptionCount=(\d+);'
    r's(\d+)\.tags=([^;]*);'
    r's(\d+)\.title=([^;]*);'
    r's(\d+)\.type=([^;]*);'
)
```

### Sporecast Object Fields

| Field | Type | Example |
|-------|------|---------|
| `id` | number | `501116030789` |
| `title` | string | `"Vanilla+ Creatures"` |
| `type` | string | `"THEME"` |
| `count` | number | `551` (assets in sporecast) |
| `description` | string | `"Adds creations..."` |
| `tags` | string | `"template, mod, original..."` |
| `subscriptionCount` | number | `297` |
| `author.id` | number | `501088287156` |
| `author.name` | string | `"LansRu"` |
| `author.screenName` | string | `"LansRu"` |

---

## Integration Into Existing Crawler

### Current State (`spore_crawler/api/client.py`)

The existing `SporeAPI` class uses `aiohttp` for REST calls and has a `_dwr_request` method with a **hardcoded** `scriptSessionId`. This works for unauthenticated DWR (search, count) but not for authenticated methods (`listSporecastInfos`).

### Required Changes

1. **Add Playwright login step** — Run before `SporeAPI` is used
2. **Pass JSESSIONID cookie** to `aiohttp` session after login
3. **Fix DWR body format** — Use proper `c0-eN=type:value` + `c0-param0=Object_Object:{...}` format
4. **Add authenticated DWR methods** — `listSporecastInfos`, `countSporecastInfo`, `findSporecastAssets`
5. **Add DWR response parser** — Parse JavaScript responses (not JSON)

### Proposed Architecture

```
┌──────────────────────────┐     ┌─────────────────────────────┐
│  SporeAuth (new)         │     │  SporeAPI (existing)        │
│  - Playwright login      │────>│  - aiohttp REST calls       │
│  - Get JSESSIONID        │     │  - DWR calls with cookie    │
│  - Async context manager │     │  - Rate limiting            │
└──────────────────────────┘     └─────────────────────────────┘
```

### Credentials Handling

**DO NOT hardcode credentials.** Use one of:

1. **Environment variables** (recommended):
   ```python
   import os
   SPORE_EMAIL = os.environ["SPORE_EMAIL"]
   SPORE_PASSWORD = os.environ["SPORE_PASSWORD"]
   ```

2. **Config file** (`config.yaml`):
   ```yaml
   auth:
     email: ""      # or use env var SPORE_EMAIL
     password: ""   # or use env var SPORE_PASSWORD
   ```

3. **Prompt at runtime**:
   ```python
   import getpass
   email = input("Spore email: ")
   password = getpass.getpass("Spore password: ")
   ```

### Example Integration Code

```python
# spore_crawler/api/auth.py (NEW FILE)
import os
import asyncio
import logging
from playwright.async_api import async_playwright

log = logging.getLogger(__name__)

class SporeAuth:
    """Authenticate with Spore via EA SSO using Playwright."""
    
    def __init__(self, email: str = None, password: str = None):
        self.email = email or os.environ.get("SPORE_EMAIL")
        self.password = password or os.environ.get("SPORE_PASSWORD")
        self.jsessionid = None
        self._browser = None
        self._context = None
        self._page = None
    
    async def login(self):
        """Login and return JSESSIONID cookie."""
        if not self.email or not self.password:
            raise ValueError("Set SPORE_EMAIL and SPORE_PASSWORD env vars")
        
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent="Mozilla/5.0 ...",
        )
        self._page = await self._context.new_page()
        
        # EA SSO login flow
        await self._page.goto("https://www.spore.com/login.jsp",
                              wait_until="networkidle", timeout=60000)
        await self._page.wait_for_selector("#email", state="visible")
        await self._page.fill("#email", self.email)
        await self._page.click("text=ДАЛЕЕ")
        await self._page.wait_for_load_state("networkidle")
        await self._page.wait_for_timeout(2000)
        await self._page.wait_for_selector("#password", state="visible")
        await self._page.fill("#password", self.password)
        await self._page.click("#logInBtn")
        
        # Wait for redirect loop to finish
        for _ in range(20):
            await self._page.wait_for_timeout(1000)
            url = self._page.url
            if "chrome-error" in url or (
                url.startswith("https://www.spore.com/") and "signin" not in url
            ):
                break
        
        # Extract JSESSIONID from cookies
        cookies = await self._context.cookies()
        for c in cookies:
            if c["name"] == "JSESSIONID" and "spore.com" in c.get("domain", ""):
                self.jsessionid = c["value"]
                break
        
        if not self.jsessionid:
            raise RuntimeError("Login failed: no JSESSIONID cookie")
        
        log.info("SporeAuth: logged in, JSESSIONID=%s", self.jsessionid[:20])
        return self.jsessionid
    
    async def get_page(self):
        """Get Playwright page for DWR calls."""
        return self._page
    
    async def close(self):
        """Clean up browser."""
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
```

### Usage in Crawler

```python
# In the crawl command or main entry point
async with SporeAuth() as auth:
    jsessionid = await auth.login()
    page = await auth.get_page()
    
    async with SporeAPI(jsessionid=jsessionid) as api:
        # Now api can make authenticated DWR calls
        total = await api.count_sporecasts(type="THEME")
        sporecasts = await api.list_sporecasts(index=0, count=200, type="THEME")
```

---

## Key Differences From Current Code

### Current `_build_dwr_body` (client.py:91)

```python
def _build_dwr_body(self, service, method, params):
    lines = [
        f"callCount=1",
        f"scriptSessionId=B46A8740BB941667AB32B719F1B7115A19",  # hardcoded
        f"c0-scriptName={service}",
        f"c0-methodName={method}",
        f"c0-id=0",
    ]
    for i, param in enumerate(params):
        if isinstance(param, str):
            lines.append(f"c0-param{i}=string:{param}")  # WRONG FORMAT
```

### Correct Format (from intercepted requests)

```python
def _build_dwr_body(self, service, method, params_obj, session):
    lines = [
        "callCount=1",
        "page=/sporepedia",
        f"httpSessionId={session['jsessionid']}",
        f"scriptSessionId={session['scriptSessionId']}",  # any value works
        f"c0-scriptName={service}",
        f"c0-methodName={method}",
        "c0-id=0",
    ]
    # Serialize params as referenced objects
    param_parts = []
    ref_id = 1
    for key, value in params_obj.items():
        if isinstance(value, str):
            lines.append(f"c0-e{ref_id}=string:{value}")
        elif isinstance(value, (int, float)):
            lines.append(f"c0-e{ref_id}=number:{value}")
        elif isinstance(value, bool):
            lines.append(f"c0-e{ref_id}=boolean:{str(value).lower()}")
        param_parts.append(f"{key}:reference:c0-e{ref_id}")
        ref_id += 1
    lines.append(f"c0-param0=Object_Object:{{{','.join(param_parts)}}}")
    lines.append(f"batchId={self._batch_id}")
```

### Current `_parse_dwr_response` (client.py:110)

```python
def _parse_dwr_response(self, text):
    match = re.search(r'_remoteHandleCallback\([^,]+,\s*[^,]+,\s*(\[.*?\]|\{.*?\})\)', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))  # WRONG: DWR responses are not JSON
        except:
            pass
    return []
```

### Correct Parser

Use regex to extract fields directly from the JavaScript response. See the `parse_sporecast_dwr_response` function in `temp_sporecast_enum.py`.

---

## Running the Enumeration Script

```bash
cd C:\Projects\SPORE_WebCrawler

# Set credentials (choose one method)
export SPORE_EMAIL="your@email.com"
export SPORE_PASSWORD="yourpassword"

# Or edit config.yaml with auth section

# Run the enumeration
python temp_sporecast_enum.py
```

### Output

- `sporecasts_all.json` — All discovered sporecasts
- `sporecast_progress.json` — Resume checkpoint (resumable)

### Expected Runtime

- 512,983 sporecasts at 200/page = ~2,565 requests
- At 1 request/second = ~43 minutes
- At 2 requests/second = ~21 minutes

---

## Testing Checklist

- [ ] Login works with Playwright
- [ ] JSESSIONID cookie is extracted correctly
- [ ] DWR calls return valid responses
- [ ] `countSporecastInfo` returns 512983
- [ ] `listSporecastInfos` pagination works (index + count)
- [ ] Response parser extracts all sporecast fields
- [ ] Resumable progress saving works
- [ ] Integration with existing `SporeAPI` class

---

## Next Steps

1. **Create `SporeAuth` class** in `spore_crawler/api/auth.py`
2. **Update `SporeAPI`** to accept JSESSIONID and use correct DWR format
3. **Add `list_sporecasts` method** to `SporeAPI`
4. **Add `find_sporecast_assets` method** to `SporeAPI`
5. **Update crawl command** to use authenticated DWR for sporecast discovery
6. **Run full enumeration** and verify output
