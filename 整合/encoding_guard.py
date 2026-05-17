# -*- coding: utf-8 -*-
"""Runtime output encoding guard for Windows consoles and subprocess readers."""

from __future__ import annotations

import os
import sys


def install_encoding_guard() -> None:
    """Prefer UTF-8 output and make text subprocess pipes decode safely."""
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    try:
        import subprocess
    except Exception:
        return

    if getattr(subprocess.Popen, "_utf8_guard_installed", False):
        return

    original_init = subprocess.Popen.__init__

    def guarded_init(self, *args, **kwargs):
        text_mode = kwargs.get("text") or kwargs.get("universal_newlines")
        if text_mode:
            kwargs.setdefault("encoding", "utf-8")
            kwargs.setdefault("errors", "replace")
        return original_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = guarded_init
    subprocess.Popen._utf8_guard_installed = True

