"""User data directory for cabineteer.

Single source of truth for where projects, cutlists, and assembly docs
live on disk. The project was renamed from cabinet-mcp on 2026-07-29;
:func:`data_dir` migrates an existing ``~/.cabinet-mcp`` store to
``~/.cabineteer`` exactly once (an atomic same-volume rename — contents,
timestamps, and layout are untouched).
"""

from __future__ import annotations

from pathlib import Path

_LEGACY_DIR_NAME = ".cabinet-mcp"
_DIR_NAME = ".cabineteer"


def data_dir() -> Path:
    """Return ``~/.cabineteer``, migrating a legacy ``~/.cabinet-mcp`` store.

    Resolves ``Path.home()`` at call time (tests monkeypatch it). If only
    the legacy directory exists, it is renamed in place; if the rename is
    not possible (permissions, cross-device mount), the legacy path is
    returned so existing data keeps working.
    """
    new = Path.home() / _DIR_NAME
    old = Path.home() / _LEGACY_DIR_NAME
    if not new.exists() and old.exists():
        try:
            old.rename(new)
        except OSError:
            return old
    return new
