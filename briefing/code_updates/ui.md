# ui/ changelog - progress.py, __init__.py, cli_ui.py
# Newest entries at the top.

2026-06-26 ui/progress.py
  REASON: print_results start_row overlapped with pause_for_exit hint area
  FIX:
  - Changed fallback start_row from height-4 to height-5 (1 row above hint)
  - Changed row guard from height-1 to height-3 (stop before progress bar area)

2026-06-26 cli_ui.py
  REASON: pause_for_exit hint position was off by 1 row from progress bar
  FIX:
  - Changed hint_row calculation for after_progress=True from Bottom-4 to height-4
  - This puts the hint exactly 1 row above the progress bar (at h-4 vs h-3)
  - Added height variable computation from csbi.srWindow bounds

2026-06-26 crawlers/hotkeys.py
  REASON: Hotkey X handler caused race condition by clearing progress from hotkey thread
  FIX:
  - Removed clear_progress_display() and scroll_print() calls from X handler
  - Added _on_stop callback mechanism (set via set_stop_callback())
  - X handler now only: sets stop_event, sets STATUS_STOPPED, disables rendering, calls callback
  - All screen refresh delegated to main thread

2026-06-26 ui/progress.py
  REASON: print_results cleared progress display - removed to keep last state visible
  FIX:
  - Removed clear_progress_display() call from print_results()
  - Progress bar last state now stays visible after results are shown
  - Continue/Exit prompt appears 1 row above the progress bar

2026-06-26 cli_ui.py
  REASON: setup_logging couldn't re-enable logging after it was disabled
  FIX:
  - Added logging.disable(logging.NOTSET) before basicConfig to reset disabled state
  - Allows config set logging.enabled true to work after previous disable

2026-06-25 cli_ui.py
  REASON: Login status checker thread breaks things - removed entirely
  FIX:
  - Removed _login_status_checker() background thread
  - Removed start/stop/reset_login_status() functions
  - Removed _login_status_thread and _login_status_stop globals
  - write_status_bar() remains available for future use

2026-06-25 cli_ui.py
  REASON: Status bar at row 0 for login state, background thread for session check
  FIX:
  - Added write_status_bar(): writes at row 0, saves/restores cursor position
  - Added _login_status_checker(): background thread with state machine
  - States: idle -> logging_in -> welcome / failure / reconnecting
  - Thread auto-starts if credentials exist, stops on --del or exit
  - Added start/stop/reset_login_status() thread control functions

2026-06-24 cli_ui.py
  REASON: get_resource_dir() had wrong path; _resize_monitor wasted Event objects
  FIX:
  - Removed get_resource_dir() (was buggy: Path(__file__).parent / "spore_crawler")
  - print_banner(): lazy imports get_resource_dir from cli.utilities
  - _resize_monitor(): replaced threading.Event().wait(0.3) with time.sleep(0.3)
  - Added `import time`
