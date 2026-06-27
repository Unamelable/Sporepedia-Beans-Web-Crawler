"""
list.py - `list` command: display user's sporecasts via DWR (requires login).

Depends on: api/auth
Used by: cli/commands/__init__, cli/__init__

Side effects:
  - SporeAuth opens/closes Playwright browser
"""
import logging

from spore_crawler.api.auth import (
    SporeAuth, get_credentials, get_credentials_interactive,
    save_credentials, load_credentials,
)

log = logging.getLogger(__name__)


async def cmd_list(config: dict, username: str, search_fields: list[str] | None = None):
    log.info("Command: list - listing sporecasts for user '%s'", username)
    log.info("  Search fields: %s", search_fields if search_fields else 'ALL')

    creds = get_credentials(config, prompt_if_missing=False)
    if creds:
        email, password = creds
    else:
        saved = load_credentials()
        if saved:
            email, password = saved
        else:
            print("Listing requires authentication (DWR).")
            try:
                email, password = get_credentials_interactive()
            except (ValueError, EOFError):
                print("Error: Credentials required.")
                return

    auth = SporeAuth(email=email, password=password)
    try:
        print("Logging in...", end=" ", flush=True)
        await auth.login()
        save_credentials(email, password)
        await auth.navigate_to_sporepedia()
        print("OK")
    except Exception as e:
        print(f"FAILED: {e}")
        await auth.close()
        return

    print(f"Searching sporecasts for '{username}'...")
    seen_ids = set()
    all_results = []
    index = 0
    try:
        while True:
            result = await auth.search_sporecasts(
                search_text=username,
                fields=search_fields if search_fields else ['author'],
                index=index,
                max_results=200,
            )
            if not result or 'results' not in result:
                break
            page = result['results']
            if not page:
                break
            new_items = 0
            for item in page:
                item_id = item.get('id')
                if item_id not in seen_ids:
                    seen_ids.add(item_id)
                    all_results.append(item)
                    new_items += 1
            total = result.get('resultSize', 0)
            if new_items == 0 or index + len(page) >= total:
                break
            index += len(page)
    except Exception as e:
        log.error("DWR search failed: %s", e)

    await auth.close()

    if all_results:
        print(f"Found {len(all_results)} sporecasts for '{username}':")
        for sc in all_results:
            author_data = sc.get('author', {})
            author_name = author_data.get('name', '?') if isinstance(author_data, dict) else str(author_data)
            assets = sc.get('count', 0)
            subs = sc.get('subscriptionCount', 0)
            print(f"  [{sc['id']}] {sc['title']} by {author_name} ({assets} assets, {subs} subs)")
    else:
        print(f"No sporecasts found for '{username}'")
