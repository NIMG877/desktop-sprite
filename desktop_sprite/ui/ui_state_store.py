"""Read/mutate/write helper for the management window's ``ui_state.json``.

Both :class:`desktop_sprite.ui.main_window.MainWindow` and
:class:`desktop_sprite.ui.config_editor.ConfigEditorWidget` keep a small
JSON file at the same path (``config/user/ui_state.json``) and follow
the same pattern: load the dict, mutate one or two keys, write it
back. The pattern was previously open-coded in two places, with subtly
different error handling (one logged, one silently swallowed; one
validated the top-level type, the other didn't).

The :class:`UiStateStore` makes the contract explicit:

* :meth:`read` returns a fresh dict on every call (so a stale in-memory
  copy never shadows a recent change from a different widget).
* :meth:`update` loads, hands the dict to the caller's mutator, then
  writes it back. The mutator is free to mutate or replace the dict;
  :meth:`update` always writes what the mutator returned.

Errors are logged but never re-raised — losing a window geometry
preference is not worth killing the process.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class UiStateStore:
    """Thin wrapper around the ``ui_state.json`` file on disk."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, Any]:
        """Read the file, returning ``{}`` on any error or non-dict content."""

        if not self.path.is_file():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as file:
                state = json.load(file)
        except (OSError, json.JSONDecodeError):
            logger.exception("Failed to read ui state from %s", self.path)
            return {}
        return state if isinstance(state, dict) else {}

    def write(self, state: dict[str, Any]) -> None:
        """Atomically write `state` to disk.

        Uses :func:`desktop_sprite.utils.safe_io.write_json_atomic` so a
        crash mid-write leaves either the old file or the new one in
        place — never a half-written file.
        """

        from desktop_sprite.utils.safe_io import write_json_atomic

        try:
            write_json_atomic(self.path, state, ensure_ascii=False, indent=2)
        except OSError:
            logger.exception("Failed to write ui state to %s", self.path)

    def update(self, mutator: Callable[[dict[str, Any]], dict[str, Any] | None]) -> None:
        """Read, mutate, and write back the state.

        `mutator` receives the current dict and may either mutate it in
        place and return ``None``, or return a fresh dict to replace it.
        Both styles are supported because the two call sites have
        different needs (MainWindow mutates, ConfigEditorWidget
        replaces).
        """

        state = self.read()
        updated = mutator(state)
        self.write(updated if updated is not None else state)
