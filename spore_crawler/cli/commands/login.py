"""
login.py - `login` command: EA SSO authentication, loops on failure.

Depends on: api/auth (SporeAuth, get_credentials, etc.), cli_ui (set_colors, FG_*)
Used by: cli/commands/__init__, cli/__init__

Side effects:
  - SporeAuth opens/closes Playwright browser (per attempt)
  - Writes credentials.json on success
  - Deletes credentials.json with --del flag
"""
import logging

from spore_crawler.api.auth import (
    SporeAuth, get_credentials, get_credentials_interactive,
    save_credentials, load_credentials, delete_credentials,
)
from spore_crawler.cli_ui import set_colors, FG_YELLOW, FG_GREEN, FG_RED, FG_CYAN

log = logging.getLogger(__name__)


async def cmd_login(config: dict, new_creds: bool = False, delete: bool = False):
    """Command: login - Authenticate with Spore via EA SSO.

    Args:
        new_creds: If True, prompt for new email/password (--new).
        delete: If True, delete credentials.json (--del/--rem/--delete/--remove).
    """
    log.info('Command: login (new=%s, delete=%s)', new_creds, delete)

    if delete:
        deleted = delete_credentials()
        set_colors(fg=FG_YELLOW)
        if deleted:
            set_colors(fg=FG_GREEN)
            print("[ CREDENTIALS DELETED ]")
        else:
            set_colors(fg=FG_YELLOW)
            print("No credentials.json found.")
        set_colors(fg=FG_YELLOW)
        return

    if new_creds:
        while True:
            try:
                email, password = get_credentials_interactive()
            except (ValueError, EOFError):
                set_colors(fg=FG_RED)
                print("Error: Credentials cannot be empty.")
                set_colors(fg=FG_YELLOW)
                continue

            set_colors(fg=FG_YELLOW)
            print(f"Logging in as: {email}")
            print("Authenticating with EA SSO (headless)...")

            try:
                auth = SporeAuth(email=email, password=password)
                jsessionid = await auth.login()
                save_credentials(email, password)
                print("")
                set_colors(fg=FG_GREEN)
                print("[ LOGIN SUCCESSFUL! ]")
                set_colors(fg=FG_YELLOW)
                await auth.close()
                break
            except Exception as e:
                log.error('Login failed: %s', e)
                set_colors(fg=FG_RED)
                print(f"[ LOGIN FAILED ] : {e}")
                set_colors(fg=FG_YELLOW)
                print()
                print("Try again with different credentials.")
                print()
                continue

        print("")
        set_colors(fg=FG_GREEN)
        print(">>> Session is ready for sporecasts, and other advanced operations.")
        set_colors(fg=FG_YELLOW)
        return

    while True:
        email = None
        password = None

        creds = get_credentials(config, prompt_if_missing=False)
        if creds:
            email, password = creds
            set_colors(fg=FG_GREEN)
            print(f">>> Using saved credentials.")
            set_colors(fg=FG_YELLOW)
        else:
            saved = load_credentials()
            if saved:
                email, password = saved
                set_colors(fg=FG_YELLOW)
                print(f"Using saved credentials: {email}")
            else:
                try:
                    email, password = get_credentials_interactive()
                except (ValueError, EOFError):
                    set_colors(fg=FG_RED)
                    print("Error: Credentials cannot be empty.")
                    set_colors(fg=FG_YELLOW)
                    continue

        set_colors(fg=FG_YELLOW)
        print(f"Logging in as: {email}")
        print("Authenticating with EA SSO (headless)...")

        try:
            auth = SporeAuth(email=email, password=password)
            jsessionid = await auth.login()
            save_credentials(email, password)
            print("")
            set_colors(fg=FG_GREEN)
            print(f"[ LOGIN SUCCESSFUL! ]")
            set_colors(fg=FG_YELLOW)
            await auth.close()
            break
        except Exception as e:
            log.error('Login failed: %s', e)
            set_colors(fg=FG_RED)
            print(f"[ LOGIN FAILED ] : {e}")
            set_colors(fg=FG_YELLOW)
            print()
            print("Try again with different credentials.")
            print()
            continue

    print("")
    set_colors(fg=FG_GREEN)
    print(">>> Session is ready for sporecasts, and other advanced operations.")
    set_colors(fg=FG_YELLOW)
