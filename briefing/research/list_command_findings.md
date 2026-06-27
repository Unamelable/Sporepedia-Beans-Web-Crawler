# List Command - Investigation Findings

## Status: WORKING (2026-06-24)

---

## Problem

`list <username>` returns incomplete results:
- **LansRu**: REST API returns only 1 sporecast (Captain's League by Miikka64), missing Vanilla+ Creatures/Buildings/Space
- **DecayedGuard**: REST API returns 0 sporecasts, but user has "dragons only" sporecast

---

## Root Cause

REST API `/rest/sporecasts/{username}` only returns sporecasts **created** by the user, not sporecasts they are **subscribed to** or associated with. The profile page "RECENT SPORECASTS" section is loaded via DWR, not REST.

---

## Solution: DWR searchSporecastsDWR

### Working Method

The correct approach is `searchService.searchSporecastsDWR` with the `fields:['author']` parameter to search by creator name.

### Query Object Structure

```javascript
{
    adv: 1,                                    // Required: enables advanced search
    searchText: "username",                    // The username to search
    maxResults: 200,                           // Max results per page
    index: 0,                                  // Pagination offset (0, 10, 20...)
    fields: ['author']                         // Search by creator name
}
```

### Available Fields

| Field | Checkbox Label | Description |
|-------|---------------|-------------|
| `name` | Sporecast Name | Search by sporecast title |
| `author` | Creator Name | Search by author username |
| `tags` | Tags | Search by tags |
| `description` | Description | Search by description text |

### Response Format (JSON, not DWR JS)

```json
{
    "resultSize": 22,
    "results": [
        {
            "id": 501116030789,
            "title": "Vanilla+ Creatures",
            "type": "THEME",
            "count": 551,
            "description": "Adds creations...",
            "tags": "vanilla+, sporecast",
            "subscriptionCount": 300,
            "rating": 4,
            "author": {
                "id": 501088287156,
                "name": "LansRu",
                "screenName": "LansRu"
            }
        }
    ]
}
```

### Sporecast Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | number | Sporecast ID |
| `title` | string | Sporecast name |
| `type` | string | Usually "THEME" |
| `count` | number | Number of assets in sporecast |
| `description` | string | Sporecast description |
| `tags` | string | Comma-separated tags |
| `subscriptionCount` | number | Number of subscribers |
| `rating` | number | Average rating (0-10) |
| `author.id` | number | Author's user ID |
| `author.name` | string | Author's username |

### Pagination

- Server caps results at ~16 per request (even with maxResults=500)
- Use `index` parameter for pagination: index=0, index=10, index=20...
- Continue until results array is empty or index exceeds total

### Implementation

```python
# In auth.py - new method
async def search_sporecasts_by_author(self, username: str) -> list[dict]:
    """Search sporecasts by author username via DWR."""
    result = await self._page.evaluate("""async (username) => {
        return new Promise((resolve) => {
            const timeout = setTimeout(() => resolve({error: 'timeout'}), 15000);
            searchService.searchSporecastsDWR(
                {adv: 1, searchText: username, maxResults: 200, index: 0, fields: ['author']},
                function(data) {
                    clearTimeout(timeout);
                    resolve(data);
                }
            );
        });
    }""", username)
    return result

# In commands.py - rewritten _get_user_sporecasts
async def _get_user_sporecasts(auth, username):
    """Get all sporecasts created by a user."""
    all_sporecasts = []
    index = 0
    while True:
        result = await auth.search_sporecasts_by_author(username, index=index)
        if not result or 'results' not in result:
            break
        sporecasts = result['results']
        if not sporecasts:
            break
        all_sporecasts.extend(sporecasts)
        index += len(sporecasts)
        if index >= result.get('resultSize', 0):
            break
    return all_sporecasts
```

---

## Other DWR Methods Tested

| Method | Parameters | Result |
|--------|-----------|--------|
| `listSporecastInfosSubscribedToByUser` | `{userId: id}` | Returns empty [] for both users |
| `listSporecastInfos` | `{authorId: id}` | Oracle DB error (server-side bug) |
| `searchSporecastsDWR` | `{searchText: 'username'}` | Returns 0 (without fields) |
| `searchSporecastsDWR` | `{searchText: 'username', fields:['author']}` | **Works!** |

---

## Profile Page URLs

| URL | Status |
|-----|--------|
| `https://www.spore.com/sporepedia/user/{username}` | 200 (correct) |
| `https://www.spore.com/person/{username}` | 404 |
| `https://www.spore.com/rest/user/{username}` | 200 (returns user ID XML) |

## Known User IDs

| Username | User ID |
|----------|---------|
| LansRu | 501088287156 |
| DecayedGuard | 501096472394 |
