"""
auth.py - EA SSO authentication via Playwright headless browser.

Depends on: None (leaf module, no internal imports)
Used by: cli/commands/_common, cli/commands/login, cli/commands/search,
         cli/commands/sporecast, cli/commands/list
"""
import os
import sys
import json
import base64
import asyncio
import logging
import warnings
from pathlib import Path
from typing import Optional

warnings.filterwarnings("ignore", message="unclosed transport", category=ResourceWarning)

log = logging.getLogger(__name__)

# Playwright error types for I/O pipe / target closed handling
try:
    from playwright.async_api import Error as PlaywrightError
except ImportError:
    PlaywrightError = Exception

# Save credentials inside program folder (works with PyInstaller)
if getattr(sys, 'frozen', False):
    _PROGRAM_DIR = Path(os.path.dirname(sys.executable))
else:
    _PROGRAM_DIR = Path(__file__).parent.parent.parent

CREDENTIALS_FILE = _PROGRAM_DIR / "credentials.json"

# Simple obfuscation key derived from program path (not real encryption)
_OBFUSCATION_KEY = b"SporeBeanCrawler2026"


def _obfuscate(data: str) -> str:
    """XOR obfuscate string and return as base64."""
    raw = data.encode("utf-8")
    key = _OBFUSCATION_KEY
    encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
    return base64.b64encode(encrypted).decode("ascii")


def _deobfuscate(data: str) -> str:
    """Decode base64 and XOR deobfuscate string."""
    try:
        raw = base64.b64decode(data.encode("ascii"))
        key = _OBFUSCATION_KEY
        decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
        return decrypted.decode("utf-8")
    except Exception:
        return ""


def save_credentials(email: str, password: str):
    """Save credentials to program folder with obfuscation."""
    try:
        CREDENTIALS_FILE.write_text(json.dumps({
            "email": _obfuscate(email),
            "password": _obfuscate(password),
            "v": 2,
        }, indent=2), encoding="utf-8")
        log.info("Credentials saved to %s", CREDENTIALS_FILE)
    except Exception as e:
        log.warning("Failed to save credentials: %s", e)


def delete_credentials() -> bool:
    """Delete credentials.json. Returns True if deleted, False if not found."""
    if CREDENTIALS_FILE.exists():
        try:
            CREDENTIALS_FILE.unlink()
            log.info("Credentials deleted: %s", CREDENTIALS_FILE)
            return True
        except Exception as e:
            log.warning("Failed to delete credentials: %s", e)
    return False


def load_credentials() -> Optional[tuple[str, str]]:
    """Load saved credentials. Returns (email, password) or None."""
    if not CREDENTIALS_FILE.exists():
        return None
    try:
        data = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        if "email" in data and "password" in data:
            if data.get("v") == 2:
                email = _deobfuscate(data["email"])
                password = _deobfuscate(data["password"])
            else:
                email = data["email"]
                password = data["password"]
            if email and password:
                return email, password
    except Exception as e:
        log.warning("Failed to load credentials: %s", e)
    return None


class SporeAuth:
    """Authenticate with Spore via EA SSO using Playwright (headless)."""

    def __init__(self, email: str = None, password: str = None):
        self.email = email
        self.password = password
        self.jsessionid: Optional[str] = None
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False

    async def login(self) -> str:
        """Login and return JSESSIONID cookie."""
        from playwright.async_api import async_playwright

        if not self.email or not self.password:
            raise ValueError("Email and password are required for login")

        log.info("SporeAuth: starting login for %s", self.email)
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )
        self._page = await self._context.new_page()

        await self._do_login()
        self._logged_in = True

        return self.jsessionid

    async def _find_and_click_next(self, page, screenshot_dir: Path = None):
        """Find and click the 'Next' button after entering email. Tries multiple strategies."""
        selectors = [
            ("button[type=submit]", "main page button[type=submit]"),
            ("input[type=submit]", "main page input[type=submit]"),
            ("text=ДАЛЕЕ", "text ДАЛЕЕ (Russian)"),
            ("text=Next", "text Next (English)"),
            ("text=Continue", "text Continue"),
            ("text=Submit", "text Submit"),
            ("[type=submit]", "any [type=submit]"),
            ("role=button", "any role=button"),
            ("button:visible", "first visible button"),
        ]

        iframe_selectors = [
            "iframe",
            "iframe[src*='ea.com']",
            "iframe[src*='signin']",
            "#iaFrame",
            "iframe#iaFrame",
        ]

        for sel, desc in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=1000):
                    log.info("SporeAuth: found button via %s", desc)
                    await loc.click(timeout=5000)
                    return True
            except Exception:
                continue

        try:
            btn = page.get_by_role("button", name="ДАЛЕЕ")
            if await btn.is_visible(timeout=1000):
                log.info("SporeAuth: found button via get_by_role ДАЛЕЕ")
                await btn.click(timeout=5000)
                return True
        except Exception:
            pass
        try:
            btn = page.get_by_role("button", name="Next")
            if await btn.is_visible(timeout=1000):
                log.info("SporeAuth: found button via get_by_role Next")
                await btn.click(timeout=5000)
                return True
        except Exception:
            pass

        for iframe_sel in iframe_selectors:
            try:
                frame = page.frame_locator(iframe_sel)
                for sel, desc in selectors:
                    try:
                        loc = frame.locator(sel).first
                        if await loc.is_visible(timeout=1000):
                            log.info("SporeAuth: found button via %s inside %s", desc, iframe_sel)
                            await loc.click(timeout=5000)
                            return True
                    except Exception:
                        continue
                try:
                    btn = frame.get_by_role("button", name="ДАЛЕЕ")
                    if await btn.is_visible(timeout=1000):
                        log.info("SporeAuth: found button via get_by_role ДАЛЕЕ inside %s", iframe_sel)
                        await btn.click(timeout=5000)
                        return True
                except Exception:
                    pass
                try:
                    btn = frame.get_by_role("button", name="Next")
                    if await btn.is_visible(timeout=1000):
                        log.info("SporeAuth: found button via get_by_role Next inside %s", iframe_sel)
                        await btn.click(timeout=5000)
                        return True
                except Exception:
                    pass
            except Exception:
                continue

        log.error("SporeAuth: could not find Next button with any selector")
        if screenshot_dir:
            try:
                screenshot_dir.mkdir(parents=True, exist_ok=True)
                await page.screenshot(path=str(screenshot_dir / "login_next_button_not_found.png"))
                log.info("SporeAuth: saved debug screenshot to %s", screenshot_dir)
            except Exception as e:
                log.warning("SporeAuth: screenshot failed: %s", e)
        return False

    async def _check_sso_error(self, page) -> str:
        """Check EA SSO page for error messages after login attempt. Returns error text or None."""
        try:
            result = await page.evaluate("""() => {
                const selectors = [
                    '.otkinput-errormsg',
                    '.otkform-group-haserror',
                    '[class*="error-message"]',
                    '[class*="error_msg"]',
                    '.field-error',
                    '#errorMessage',
                ];
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const text = el.textContent.trim();
                        if (text && text.length > 5 && text.length < 500) {
                            return text;
                        }
                    }
                }
                return null;
            }""")
            return result
        except Exception:
            return None

    async def _do_login(self):
        """Perform the EA SSO login flow."""
        page = self._page
        debug_dir = _PROGRAM_DIR / ".auth" / "debug"

        log.info("SporeAuth: navigating to login page")
        await page.goto("https://www.spore.com/login.jsp", wait_until="networkidle", timeout=60000)
        await page.wait_for_selector("#email", state="visible", timeout=10000)
        await page.fill("#email", self.email)

        clicked = await self._find_and_click_next(page, debug_dir)
        if not clicked:
            raise RuntimeError(
                "could not find the 'Next' button after email. "
                "Check .auth/debug/ for screenshot."
            )

        await page.wait_for_load_state("networkidle", timeout=10000)
        await page.wait_for_timeout(1000)

        try:
            await page.wait_for_selector("#password", state="visible", timeout=10000)
        except Exception:
            sso_error = await self._check_sso_error(page)
            if sso_error:
                raise RuntimeError(f"Login failed: {sso_error}")
            url = page.url
            if "signin.ea.com" in url:
                raise RuntimeError(
                    "invalid email or account does not exist. "
                    "EA SSO did not show the password page."
                )
            raise RuntimeError(
                "password field not found. "
                "Check .auth/debug/ for screenshot."
            )

        await page.fill("#password", self.password)
        await page.click("#logInBtn", timeout=5000)

        # Poll for SSO errors instead of fixed wait (faster on success, catches errors)
        for _ in range(6):
            await page.wait_for_timeout(500)
            sso_error = await self._check_sso_error(page)
            if sso_error:
                log.warning("SporeAuth: SSO error detected: %s", sso_error)
                raise RuntimeError(f"Login failed: {sso_error}")

        # Wait for redirect loop to settle
        for _ in range(15):
            await page.wait_for_timeout(1000)
            url = page.url
            if "chrome-error" in url or (url.startswith("https://www.spore.com/") and "signin" not in url):
                break

        cookies = await self._context.cookies()
        for c in cookies:
            if c["name"] == "JSESSIONID" and "spore.com" in c.get("domain", ""):
                self.jsessionid = c["value"]
                break

        if not self.jsessionid:
            raise RuntimeError("Login failed: no JSESSIONID cookie obtained")

        log.info("SporeAuth: login successful, JSESSIONID=%s...", self.jsessionid[:20])

    async def navigate_to_sporepedia(self):
        """Navigate to sporepedia page and wait for DWR to load."""
        if not self._page:
            raise RuntimeError("Not logged in")

        log.info("SporeAuth: navigating to sporepedia")
        try:
            await self._page.goto("https://www.spore.com/sporepedia", timeout=30000)
        except PlaywrightError as e:
            log.warning("SporeAuth: navigation page evaluate failed (I/O pipe broken?): %s", e)
            return
        except Exception as e:
            log.warning("SporeAuth: navigation error (non-fatal): %s", e)
        await self._page.wait_for_timeout(5000)

    async def is_session_valid(self) -> bool:
        """Check if current session is still valid by testing a DWR call."""
        if not self._page:
            return False

        try:
            result = await self._page.evaluate("""async () => {
                try {
                    const resp = await fetch('/jsserv/call/plaincall/loginService.getLoggedInUser.dwr', {
                        method: 'POST',
                        headers: {'Content-Type': 'text/plain'},
                        body: 'callCount=1\\npage=/sporepedia\\nscriptSessionId=test\\nc0-scriptName=loginService\\nc0-methodName=getLoggedInUser\\nc0-id=0\\nbatchId=999',
                        credentials: 'same-origin',
                    });
                    const text = await resp.text();
                    return {ok: resp.ok, body: text.substring(0, 500)};
                } catch(e) {
                    return {ok: false, error: e.toString()};
                }
            }""")

            if result.get("ok") and result.get("body"):
                body = result["body"]
                if "_remoteHandleCallback" in body and "null" not in body.split("_remoteHandleCallback")[1][:50]:
                    log.info("SporeAuth: session is valid")
                    return True
                if "error" in body.lower() or "exception" in body.lower():
                    log.warning("SporeAuth: session invalid (server error)")
                    return False
            log.warning("SporeAuth: session check inconclusive")
            return False
        except PlaywrightError as e:
            log.warning("SporeAuth: page evaluate failed in is_session_valid (I/O pipe broken?): %s", e)
            return False
        except Exception as e:
            log.error("SporeAuth: session check failed: %s", e)
            return False

    async def ensure_valid_session(self) -> bool:
        """Ensure session is valid, relogin if needed. Returns True if session is ready."""
        if self._page and self._logged_in:
            if await self.is_session_valid():
                return True
            log.info("SporeAuth: session expired, relogin needed")

        await self.close()

        try:
            await self.login()
            await self.navigate_to_sporepedia()
            return True
        except Exception as e:
            log.error("SporeAuth: relogin failed: %s", e)
            return False

    async def make_dwr_call(self, script_name: str, method_name: str, params_obj: dict, batch_id: int) -> dict:
        """Make a DWR call through the browser page context."""
        if not self._page:
            raise RuntimeError("Not logged in - call login() first")

        try:
            session = await self._page.evaluate("""() => {
                return {
                    scriptSessionId: dwr.engine._getScriptSessionId(),
                    jsessionid: dwr.engine._getJSessionId(),
                };
            }""")
        except PlaywrightError as e:
            log.warning("SporeAuth: failed to get DWR session info (I/O pipe broken?): %s", e)
            return {"ok": False, "error": f"page evaluate failed: {e}"}
        except Exception as e:
            log.error("SporeAuth: unexpected error getting DWR session info: %s", e)
            return {"ok": False, "error": str(e)}

        lines = [
            "callCount=1",
            "page=/sporepedia",
            f"httpSessionId={session['jsessionid']}",
            f"scriptSessionId={session['scriptSessionId']}",
            f"c0-scriptName={script_name}",
            f"c0-methodName={method_name}",
            "c0-id=0",
        ]

        if params_obj:
            ref_id = 1
            for key, value in params_obj.items():
                if isinstance(value, str):
                    lines.append(f"c0-e{ref_id}=string:{value}")
                elif isinstance(value, bool):
                    lines.append(f"c0-e{ref_id}=boolean:{str(value).lower()}")
                elif isinstance(value, (int, float)):
                    lines.append(f"c0-e{ref_id}=number:{value}")
                elif value is None:
                    lines.append(f"c0-e{ref_id}=null:null")
                ref_id += 1

            if len(params_obj) == 1:
                first_value = next(iter(params_obj.values()))
                if isinstance(first_value, str):
                    lines.append(f"c0-param0=string:{first_value}")
                elif isinstance(first_value, bool):
                    lines.append(f"c0-param0=boolean:{str(first_value).lower()}")
                elif isinstance(first_value, (int, float)):
                    lines.append(f"c0-param0=number:{first_value}")
                elif first_value is None:
                    lines.append("c0-param0=null:null")
            else:
                param_parts = []
                ref_id = 1
                for key, value in params_obj.items():
                    if isinstance(value, str):
                        param_parts.append(f"{key}:reference:c0-e{ref_id}")
                    elif isinstance(value, bool):
                        param_parts.append(f"{key}:reference:c0-e{ref_id}")
                    elif isinstance(value, (int, float)):
                        param_parts.append(f"{key}:reference:c0-e{ref_id}")
                    elif value is None:
                        param_parts.append(f"{key}:reference:c0-e{ref_id}")
                    ref_id += 1
                lines.append(f"c0-param0=Object_Object:{{{','.join(param_parts)}}}")

        lines.append(f"batchId={batch_id}")
        body = "\n".join(lines)

        url = f"/jsserv/call/plaincall/{script_name}.{method_name}.dwr"
        try:
            result = await self._page.evaluate("""async ({body, url}) => {
                try {
                    const resp = await fetch(url, {
                        method: 'POST',
                        headers: {'Content-Type': 'text/plain'},
                        body: body,
                        credentials: 'same-origin',
                    });
                    const text = await resp.text();
                    return {ok: resp.ok, status: resp.status, body: text};
                } catch(e) {
                    return {ok: false, error: e.toString()};
                }
            }""", {"body": body, "url": url})
        except PlaywrightError as e:
            log.warning("SporeAuth: DWR call page evaluate failed (I/O pipe broken?): %s", e)
            return {"ok": False, "error": f"page evaluate failed: {e}"}
        except Exception as e:
            log.error("SporeAuth: unexpected error in DWR call: %s", e)
            return {"ok": False, "error": str(e)}

        return result

    async def search_sporecasts_by_author(self, username: str, index: int = 0, max_results: int = 200) -> dict:
        """Search sporecasts by author username via DWR searchSporecastsDWR.

        Returns dict with 'resultSize' (int) and 'results' (list of sporecast dicts).
        Each sporecast has: id, title, type, count, description, tags,
        subscriptionCount, rating, author (dict with id, name, screenName).
        """
        return await self.search_sporecasts(
            search_text=username,
            fields=['author'],
            index=index,
            max_results=max_results,
        )

    async def search_sporecasts(
        self,
        search_text: str,
        fields: list[str] | None = None,
        index: int = 0,
        max_results: int = 200,
    ) -> dict:
        """Search sporecasts via DWR searchSporecastsDWR with configurable fields.

        Args:
            search_text: The search query string.
            fields: Which fields to search. Valid values for sporecasts:
                    'title' (Sporecast Name), 'author' (Creator Name),
                    'tags' (Tags), 'subtitle' (Description).
                    None or empty list = search ALL fields (default behavior).
            index: Pagination offset (0, 12, 24, ...).
            max_results: Max results per page (default 200, server caps ~16).

        Returns dict with 'resultSize' (int) and 'results' (list of sporecast dicts).
        Each sporecast has: id, title, type, count, description, tags,
        subscriptionCount, rating, author (dict with id, name, screenName).
        """
        if not self._page:
            raise RuntimeError("Not logged in - call login() first")

        if fields is None:
            fields = []

        try:
            result = await self._page.evaluate("""async (params) => {
                return new Promise((resolve) => {
                    const timeout = setTimeout(() => resolve({error: 'timeout'}), 15000);
                    try {
                        var query = {
                            adv: 1,
                            searchText: params.searchText,
                            maxResults: params.maxResults,
                            index: params.index
                        };
                        if (params.fields && params.fields.length > 0) {
                            query.fields = params.fields;
                        }
                        searchService.searchSporecastsDWR(
                            query,
                            function(data) {
                                clearTimeout(timeout);
                                resolve(data);
                            }
                        );
                    } catch(e) {
                        clearTimeout(timeout);
                        resolve({error: e.toString()});
                    }
                });
            }""", {"searchText": search_text, "maxResults": max_results, "index": index, "fields": fields})
        except PlaywrightError as e:
            log.warning("SporeAuth: search_sporecasts page evaluate failed (I/O pipe broken?): %s", e)
            return {"error": f"page evaluate failed: {e}"}
        except Exception as e:
            log.error("SporeAuth: unexpected error in search_sporecasts: %s", e)
            return {"error": str(e)}

        return result

    async def get_page(self):
        """Get Playwright page for manual DWR calls."""
        return self._page

    async def close(self):
        """Close Playwright browser and context. Safe to call multiple times. Idempotent."""
        if self._page:
            try:
                await self._page.close()
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


def _input_password_asterisks(prompt: str = "Password: ") -> str:
    """Read password with asterisks displayed (Windows-compatible)."""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    password = []
    if sys.platform == "win32":
        import msvcrt
        while True:
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                break
            elif ch == "\b" or ch == "\x7f":
                if password:
                    password.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif ch == "\x03":
                raise KeyboardInterrupt
            else:
                password.append(ch)
                sys.stdout.write("*")
                sys.stdout.flush()
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while True:
                ch = sys.stdin.read(1)
                if ch in ("\r", "\n"):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    break
                elif ch == "\x7f" or ch == "\b":
                    if password:
                        password.pop()
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                elif ch == "\x03":
                    raise KeyboardInterrupt
                else:
                    password.append(ch)
                    sys.stdout.write("*")
                    sys.stdout.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return "".join(password)


def get_credentials_interactive() -> tuple[str, str]:
    """Prompt user for email and password interactively."""
    print("Spore EA SSO Login")
    print("==================")
    email = input("Email: ").strip()
    if not email:
        raise ValueError("Email cannot be empty")
    password = _input_password_asterisks("Password: ")
    if not password:
        raise ValueError("Password cannot be empty")
    return email, password


def get_credentials(config: dict, prompt_if_missing: bool = True) -> Optional[tuple[str, str]]:
    """Get credentials from saved file or interactive prompt.

    Priority:
    1. Saved credentials file (email + password)
    2. Interactive prompt (if prompt_if_missing=True)

    Returns None when can't provide both email AND password (non-interactive).
    """
    saved = load_credentials()

    if saved:
        email, password = saved
        log.info("Using saved credentials: %s", email)
        return email, password

    if prompt_if_missing:
        log.info("No credentials found, prompting user")
        email = input("Email: ").strip()
        if not email:
            raise ValueError("Email cannot be empty")
        password = _input_password_asterisks("Password: ")
        if not password:
            raise ValueError("Password cannot be empty")
        return email, password

    return None
