# Search Command - Investigation Findings

## Status: IMPLEMENTED (2026-06-25)

---

## Problem

`search <keyword>` (e.g., `search pop`) returns far fewer results than expected. The Spore website's advanced search for "pop" shows hundreds of sporecasts, but the crawler only finds a handful.

---

## Root Cause

**`search_sporecasts_by_author()` in `api/auth.py:460-494` hardcodes `fields: ['author']`.**

This means the search ONLY matches against the **Creator Name** field. When searching for "pop", it only finds sporecasts where the author's name contains "pop" — not sporecasts with "pop" in the title, tags, or description.

### Current Code (auth.py:470-492)

```javascript
searchService.searchSporecastsDWR(
    {
        adv: 1,
        searchText: params.username,
        maxResults: params.maxResults,
        index: params.index,
        fields: ['author']    // <-- HARDCODED: only searches creator name
    },
    function(data) { ... }
);
```

### What the Website Does

The Spore website's advanced search form has **4 checkboxes** under "SEARCH BY":

| Checkbox | Field Name | ID |
|----------|-----------|-----|
| Sporecast Name | `title` | `js-spc-name` |
| Creator Name | `author` | `js-spc-auth` |
| Tags | `tags` | `js-spc-tags` |
| Description | `subtitle` | `js-spc-desc` |

**Critical:** For sporecasts, the description field is called `subtitle`, NOT `description`. (For assets/creations, it IS `description`.)

### Website Behavior

- When **all checkboxes are checked** (default): `fields: ['title', 'author', 'tags', 'subtitle']`
- When **no checkboxes are checked** or `fields` is empty: searches **ALL fields**
- URL format: `#qry=advssrch-pop` (no `:fi-` segment = all fields)
- URL format with fields: `#qry=advssrch-pop:fi-title,author,tags,subtitle`

---

## Available DWR Search Parameters

The `searchSporecastsDWR` method accepts a query object:

```javascript
{
    adv: 1,                              // Required: enables advanced search
    searchText: "search term",           // The search query
    maxResults: 12,                      // Results per page (default: 12, max safe: 200)
    index: 0,                            // Pagination offset
    fields: ['title', 'author', 'tags', 'subtitle'],  // Which fields to search
}
```

### Field Names (SPORECASTS only)

| Internal Name | Checkbox Label | Description |
|---------------|---------------|-------------|
| `title` | Sporecast Name | Search by sporecast title |
| `author` | Creator Name | Search by author username |
| `tags` | Tags | Search by tags |
| `subtitle` | Description | Search by description text |

**Note:** These are DIFFERENT from asset/creation field names (`name`, `author`, `tags`, `description`).

---

## Proposed Solution

### 1. New Search Method in `auth.py`

Create a general-purpose `search_sporecasts()` method that accepts a `fields` parameter:

```python
async def search_sporecasts(
    self,
    search_text: str,
    fields: list[str] = None,  # None = all fields, [] = all fields
    index: int = 0,
    max_results: int = 200,
) -> dict:
```

### 2. Config Option for Default Search Fields

Add to `config.yaml`:

```yaml
crawler:
  search_fields:
    - title
    - author
    - tags
    - subtitle
```

### 3. CLI Arguments for Search Fields

Add `--fields` argument to the `search` command:

```
search <terms...> --fields title,author,tags,subtitle
search <terms...> --fields name        # Only search by name
search <terms...> --fields all         # All fields (default)
```

### 4. Update Presets

Add `search_fields` to all presets (quick, full, safe).

---

## Files to Modify

| File | Change |
|------|--------|
| `api/auth.py` | Add `search_sporecasts()` method with configurable fields |
| `cli/commands/search.py` | Use `search_sporecasts()` instead of `search_sporecasts_by_author()`, pass fields |
| `cli/config.py` | Add `search_fields` to DEFAULT_CONFIG, presets, DEFAULT_CONFIG_YAML |
| `cli/__init__.py` | Parse `--fields` argument for search command |
| `cli/help_text.py` | Update search help text, add field aliases |

---

## Testing Plan

1. **Test default search** (all fields): `search pop` should find hundreds of results
2. **Test specific field**: `search pop --fields title` should only find title matches
3. **Test multiple fields**: `search pop --fields title,tags` should find title + tags matches
4. **Test author-only** (old behavior): `search pop --fields author` should match old behavior
5. **Compare with website**: Results should match `https://www.spore.com/sporepedia#qry=advssrch-pop`
6. **Pagination test**: Verify multi-page results work correctly

---

## Key Code References

- Current search method: `api/auth.py:460-494`
- Search command: `cli/commands/search.py:408-491` (keyword branch)
- Config defaults: `cli/config.py:17-66`
- Config presets: `cli/config.py:458-566`
- CLI dispatcher: `cli/__init__.py:373-402`
- Help text: `cli/help_text.py:188-222`

---

## Implementation Summary (2026-06-25)

### Changes Made

| File | Change |
|------|--------|
| `api/auth.py` | Added `search_sporecasts()` method with configurable `fields` parameter. Updated `search_sporecasts_by_author()` to delegate to it. |
| `cli/config.py` | Added `search_fields` to DEFAULT_CONFIG, DEFAULT_CONFIG_YAML, all presets (quick/full/safe), validation, and env overrides. |
| `cli/__init__.py` | Added `--fields` argument parsing for search command. |
| `cli/commands/search.py` | Updated `cmd_search()` to accept `search_fields` parameter, use config defaults, and call `search_sporecasts()`. |
| `cli/help_text.py` | Updated search help text with --fields documentation and field aliases. |

### New CLI Arguments

```
search <terms...> --fields <list>
```

- `--fields title` - Search only Sporecast Name
- `--fields author` - Search only Creator Name
- `--fields tags` - Search only Tags
- `--fields subtitle` - Search only Description
- `--fields title,author,tags,subtitle` - Search all fields (explicit)
- `--fields all` - Search all fields (alias)
- No --fields argument - Uses config default (all fields)

### Config Option

```yaml
crawler:
  search_fields:
    - title
    - author
    - tags
    - subtitle
```

### Environment Variable Override

```bash
SPORE_CRAWLER_CRAWLER_SEARCH_FIELDS=title,author,tags,subtitle
```
