"""Console output helpers.

Why this exists
---------------
Windows consoles default to the cp1252 code page, which cannot encode the
box-drawing characters, ellipses, and arrows our CLI scripts print. The result is
a `UnicodeEncodeError` that kills a script *after* it has done all its work --
including the eval scripts, which would lose a completed run at the print step.

An evaluator cloning this repo on Windows would hit the same wall, so the fix
belongs in the code rather than in a "set PYTHONIOENCODING first" instruction.

Usage: call `ensure_utf8_stdout()` at the top of `main()` in any script that
prints non-ASCII.
"""

from __future__ import annotations

import contextlib
import sys


def ensure_utf8_stdout() -> None:
    """Force UTF-8 on stdout/stderr, replacing anything unencodable.

    `errors="replace"` rather than `"strict"`: a mangled glyph in a progress line
    is a cosmetic problem, while a crash loses the run. Safe to call repeatedly,
    and a no-op on streams that do not support reconfigure (e.g. when stdout has
    been replaced by a test fixture).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        # Detached or non-reconfigurable stream -- nothing we can do about it, and
        # nothing worth failing over.
        with contextlib.suppress(ValueError, OSError):
            reconfigure(encoding="utf-8", errors="replace")
