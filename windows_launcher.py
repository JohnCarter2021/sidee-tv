#!/usr/bin/env python3
"""Frozen Windows entry point for Sidee (PyInstaller, console=True).

Why a wrapper instead of running sidee.py directly: a frozen console
app that exits on error closes its window, hiding the cause. This
launcher tees stdout/stderr to a log file next to the executable
(``Sidee.log`` in the portable folder, when frozen), prints the
traceback on failure, and waits for Enter before closing -- unless
running under CI, where waiting would hang the build.

Normal exit (including Ctrl+C, and the "dashboard already running"
reopen path) does not prompt. Safe mode is a separate entry:
``Sidee-SafeMode.bat`` runs this same executable with ``--headless``,
so the dashboard runs without auto-opening a browser.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


class _Tee:
    """Write to the console and to a log file at the same time."""

    def __init__(self, stream, log_file):
        self._stream = stream
        self._log = log_file

    def write(self, text):
        self._stream.write(text)
        try:
            self._log.write(text)
            self._log.flush()
        except (OSError, ValueError):
            pass
        return len(text)

    def flush(self):
        self._stream.flush()
        try:
            self._log.flush()
        except (OSError, ValueError):
            pass

    def __getattr__(self, name):
        # Let code that inspects stdout/stderr (encoding, isatty, ...)
        # see the real stream, not this wrapper.
        return getattr(self.__dict__["_stream"], name)


def _log_path() -> Path | None:
    override = os.environ.get("SIDEE_LOG_DIR", "").strip()
    if override:
        return Path(override).expanduser() / "Sidee.log"
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "Sidee.log"
    # Source runs: do not litter the checkout with a log file.
    return None


def _prompt_to_close() -> None:
    if os.environ.get("SIDEE_CI") == "1":
        return
    try:
        input("Press Enter to close Sidee...")
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    log_file = None
    path = _log_path()
    if path is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            log_file = open(path, "a", encoding="utf-8")
            log_file.write(f"\n--- Sidee started ---\n")
            log_file.flush()
        except OSError:
            log_file = None
    original_stdout, original_stderr = sys.stdout, sys.stderr
    if log_file is not None:
        sys.stdout = _Tee(sys.stdout, log_file)
        sys.stderr = _Tee(sys.stderr, log_file)
    try:
        import sidee

        return sidee.main()
    except KeyboardInterrupt:
        return 0
    except SystemExit as error:
        code = error.code
        if code:
            _prompt_to_close()
        return code if isinstance(code, int) else 1
    except Exception:
        traceback.print_exc()
        _prompt_to_close()
        return 1
    finally:
        if log_file is not None:
            # Restore the real streams before closing the log, or
            # interpreter shutdown would flush a tee over a closed file.
            sys.stdout, sys.stderr = original_stdout, original_stderr
            try:
                log_file.close()
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
