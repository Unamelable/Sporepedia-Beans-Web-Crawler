# Sporepedia Browse API - REST DWR Search (No Auth Required)

## Status: IMPLEMENTED (2026-06-26)

---

## Overview

The Sporepedia website allows browsing sporecasts through two mechanisms:

1. **Authenticated DWR** (via Playwright) - Used by `search`, `list`, `sporecast --key` commands
   - Requires EA SSO login (JSESSIONID cookie)
   - Methods: `searchSporecastsDWR`, `listSporecastInfos`, `countSporecastInfo`
   - Full access to all sporecast data

2. **REST DWR** (via HTTP POST) - Used by `browse` command (new)
   - **No authentication required**
   - Same `searchSporecastsDWR` method, but called through REST endpoint
   - Returns same data structure as authenticated version
   - Limited to keyword search (no enumeration of all sporecasts)

---

## REST DWR Endpoint

### URL
```
POST https://www.spore.com/jsserv/call/plaincall/searchService.searchSporecastsDWR.dwr
```

### Headers
```
Content-Type: text/plain
```

### Body Format
```
callCount=1
scriptSessionId=B46A8740BB941667AB32B719F1B7115A19
c0-scriptName=searchService
c0-methodName=searchSporecastsDWR
c0-id=0
c0-searchText={search_text}
c0-maxResults={max_results}
c0-filter=MOST_POPULAR
c0-param0=Object_Object:{searchText:reference:c0-searchText,maxResults:reference:c0-maxResults,filter:reference:c0-filter}
batchId={incrementing_int}
```

### Key Differences from Authenticated DWR

| Aspect | Authenticated (Playwright) | REST (HTTP POST) |
|--------|---------------------------|-------------------|
| Authentication | JSESSIONID cookie required | None |
| scriptSessionId | From `dwr.engine._getScriptSessionId()` | Hardcoded value |
| Session | Must navigate to /sporepedia first | Direct POST |
| Methods available | All (search, list, count, find) | searchSporecastsDWR only |
| Page context | Browser page.evaluate() | aiohttp session.post() |

---

## Response Format

### DWR JavaScript Response (from REST endpoint)

The REST DWR endpoint returns JavaScript, not JSON:

```javascript
throw 'allowScriptTagRemoting is false.';
//#DWR-INSERT
//#DWR-REPLY
var s0=[];var s1={};...
s0[0]=s1;s0[1]=s2;...
s1.assetIds=null;s1.assets=null;s1.author=s21;s1.count=551;...
s1.id=501116030789;s1.lastUpdated=new Date(1782199826079);...
s1.title="Vanilla+ Creatures ";s1.type='THEME';
s21.id=501088287156;s21.name="LansRu";s21.screenName="LansRu";...
dwr.engine._remoteHandleCallback('5','0',s0);
```

### Parsed Sporecast Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | number | Sporecast ID (e.g., 501116030789) |
| `title` | string | Sporecast name |
| `count` | number | Number of assets in sporecast |
| `subscriptionCount` | number | Number of subscribers |
| `type` | string | Usually "THEME" |
| `description` | string | Sporecast description |
| `tags` | string | Comma-separated tags |
| `rating` | number | Average rating (0-10) |
| `lastUpdated` | string | Last update timestamp |
| `author` | object | Author info: `{id, name, screenName}` |

---

## Pagination

- **Parameter:** `index` (start position), `maxResults` (page size)
- **Server caps results** at ~16 per request (even with maxResults=200)
- **Pagination loop:** index += len(page) until empty page or index >= resultSize

```python
# Pagination loop
index = 0
while True:
    result = await api.search_sporecasts(search_text, max_results=200)
    page = result['results']
    if not page:
        break
    # process page...
    index += len(page)
    if index >= result.get('resultSize', 0):
        break
```

---

## Search Fields

The `searchSporecastsDWR` method accepts a `fields` parameter:

| Field | Checkbox Label | Description |
|-------|---------------|-------------|
| `title` | Sporecast Name | Search by sporecast title |
| `author` | Creator Name | Search by author username |
| `tags` | Tags | Search by tags |
| `subtitle` | Description | Search by description text |

**Default behavior:** When `fields` is empty/missing, searches ALL fields.

---

## Implementation: browse.py

### Database: search_sporepedia.db

New table `browsed_sporecasts`:
```sql
CREATE TABLE IF NOT EXISTS browsed_sporecasts (
    sporecast_id INTEGER PRIMARY KEY,
    title TEXT,
    author TEXT,
    asset_count INTEGER DEFAULT 0,
    subscribers INTEGER DEFAULT 0,
    description TEXT,
    tags TEXT,
    rating TEXT,
    discovered_at TEXT
);
```

### Command Usage

```
browse <terms...> [options]

OPTIONS:
  -a / --all            Browse all popular sporecasts (no auth needed)
  -m / --max <n>        Max results per term (default: unlimited)
  -f / --fields <list>  Comma-separated fields to search

EXAMPLES:
  browse creature              # Search for "creature" sporecasts
  browse pop -f title          # Search by title only
  browse --all                 # Browse all popular sporecasts
  browse creature building     # Multiple search terms
```

### Integration with Other Commands

1. **convert-sql browse** - Export search_sporepedia.db to text
2. **crawl --db** - Download assets from sporecasts in search_sporepedia.db
3. **clean** - Delete search_sporepedia.db when cleaning databases

---

## Key Code References

| File | Method | Description |
|------|--------|-------------|
| `api/client.py:248` | `search_sporecasts()` | REST DWR call (no auth) |
| `api/client.py:297` | `_parse_sporecast_search()` | Parse DWR JavaScript response |
| `api/auth.py:500` | `search_sporecasts()` | Auth DWR call (with auth) |
| `cli/commands/search.py` | `cmd_search()` | Existing search command |
| `cli/commands/browse.py` | `cmd_browse()` | New browse command |
