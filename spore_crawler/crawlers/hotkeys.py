"""
hotkeys.py - Keyboard hotkey controller (P/R/X) for pause/resume/stop during crawl.

Depends on: ui/progress (ProgressDisplay, clear_progress_display, scroll_print),
            ui (FG_RED, FG_YELLOW)
Used by: cli/commands/search, cli/commands/sporecast, cli/commands/crawl
"""
import threading
import time
import logging
import msvcrt
from typing import Optional
from spore_crawler.ui.progress import ProgressDisplay, clear_progress_display, scroll_print
from spore_crawler.ui import FG_RED, FG_YELLOW

log = logging.getLogger(__name__)


class HotkeyController:
    """
    Handle keyboard input for pause/resume/stop during crawl.

    Usage:
        hotkey = HotkeyController()
        hotkey.start()

        # In crawl loop:
        if hotkey.should_stop():
            break
        hotkey.wait_if_paused()

        # Cleanup:
        hotkey.stop()
    """

    def __init__(self):
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.progress = ProgressDisplay()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._on_stop = None  # Callback set by main thread for clean refresh

    def start(self):
        """Start hotkey listener daemon thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._listener, daemon=True)
        self._thread.start()
        log.info("Hotkey controller started (P=Pause, R=Resume, X=Stop)")

    def stop(self):
        """Stop hotkey listener thread. Safe to call multiple times. Idempotent."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        log.info("Hotkey controller stopped")

    def set_stop_callback(self, callback):
        """Set callback for when X is pressed. Called from hotkey thread."""
        self._on_stop = callback

    def _listener(self):
        """Background thread: listen for keyboard input."""
        while self._running:
            try:
                if msvcrt.kbhit():
                    key = msvcrt.getch()

                    # Handle single character keys
                    if key in (b'p', b'P'):
                        if not self.pause_event.is_set():
                            self.pause_event.set()
                            self.progress.set_status(self.progress.STATUS_PAUSED)
                            self.progress.render_progress()
                            log.info("Crawl paused by user")

                    elif key in (b'r', b'R'):
                        if self.pause_event.is_set():
                            self.pause_event.clear()
                            self.progress.set_status(self.progress.STATUS_RUNNING)
                            self.progress.render_progress()
                            log.info("Crawl resumed by user")

                    elif key in (b'x', b'X'):
                        self.stop_event.set()
                        self.progress.set_status(self.progress.STATUS_STOPPED)
                        self._running = False
                        self.progress.disable_rendering()
                        log.info("Crawl stopped by user (checkpoint saved)")
                        # Notify main thread -- it handles screen refresh
                        if self._on_stop:
                            try:
                                self._on_stop()
                            except Exception:
                                pass

                time.sleep(0.05)  # 50ms polling interval

            except Exception as e:
                log.error("Hotkey listener error: %s", e)
                time.sleep(0.1)

    def should_stop(self) -> bool:
        """Check if stop was requested."""
        return self.stop_event.is_set()

    def wait_if_paused(self):
        """Block until resumed or stopped. Call this in sync code."""
        while self.pause_event.is_set():
            if self.stop_event.is_set():
                break
            time.sleep(0.1)

    async def async_wait_if_paused(self):
        """Async-compatible wait. Call this in async code."""
        import asyncio
        while self.pause_event.is_set():
            if self.stop_event.is_set():
                break
            await asyncio.sleep(0.1)

    def update_progress(self, **kwargs):
        """Update progress display (thread-safe)."""
        self.progress.update_progress(**kwargs)

    def render_progress(self):
        """Render current progress line."""
        self.progress.render_progress()
