"""Crash-safe filesystem IO helpers.

Two reusable primitives:

* :func:`write_json_atomic` — write JSON to ``path`` by first writing
  to a sibling ``.tmp`` file, then atomically renaming via
  :func:`os.replace`. A crash before, during, or after the rename
  leaves the destination either fully written or fully untouched.

* :func:`atomic_write` — context manager for **multi-file** writes
  that must all succeed or all roll back. Captures each file's
  previous contents (or its absence), lets the caller write each
  file, and on exit-with-exception restores every captured state
  before re-raising. On normal exit, the renames are committed.

These are the building blocks the spirit-mark grant service uses to
guarantee that ``inventory.json`` and ``spirit_marks.json`` never end
up half-written (e.g. one updated, the other not).
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class SafeIOError(OSError):
    """Raised when a safe IO operation cannot complete and has been rolled back."""


def write_json_atomic(path: Path, data: Any, *, ensure_ascii: bool = False, indent: int = 2) -> None:
    """Atomically write ``data`` as JSON to ``path``.

    Writes to ``path + ".tmp"`` first, then ``os.replace``-s it into
    place. The replace is atomic on every platform the project
    supports (POSIX, Windows with same-volume rename).

    Raises whatever ``open`` / ``json.dump`` / ``os.replace`` raises.
    The ``.tmp`` file is removed on failure.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=ensure_ascii, indent=indent)
            file.write("\n")
        os.replace(tmp, path)
    except BaseException:
        # Best-effort cleanup of the half-written tmp file.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


def merge_dict(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Deep-merge ``source`` into ``target`` in place.

    Only nested ``dict`` values are merged recursively; every other
    type (lists, scalars) is overwritten by ``source``. The same rule
    applies for top-level keys, so this is the right shape for the
    JSON config merge in :func:`desktop_sprite.utils.config.load_config`
    and the user-overlay merge in
    :class:`desktop_sprite.ui.config_editor.ConfigEditorWidget`.
    """

    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_dict(target[key], value)
        else:
            target[key] = value


@dataclass
class _Captured:
    path: Path
    existed: bool
    contents: bytes | None = field(default=None)


@contextlib.contextmanager
def atomic_write(paths: list[Path]) -> Iterator[None]:
    """Context manager: commit a set of file writes atomically.

    Usage::

        with atomic_write([inventory_file, spirit_mark_file]):
            write_json_atomic(inventory_file, inventory_data)
            write_json_atomic(spirit_mark_file, marks_data)

    Captures the pre-block contents (or absence) of every file on
    enter. If any exception escapes the block, every file is restored
    to its pre-block state before the exception re-raises — even if
    only one of the writes had completed, the partial state on the
    others is also overwritten with their original bytes.

    On normal exit the manager is a no-op: the caller is responsible
    for the writes (typically via :func:`write_json_atomic`, which is
    internally atomic on its own).
    """

    captured: list[_Captured] = []
    for path in paths:
        if path.exists():
            captured.append(
                _Captured(
                    path=path,
                    existed=True,
                    contents=path.read_bytes(),
                )
            )
        else:
            captured.append(_Captured(path=path, existed=False))

    try:
        yield
    except BaseException as exc:
        rollback_errors: list[str] = []
        for record in captured:
            try:
                if record.existed and record.contents is not None:
                    record.path.write_bytes(record.contents)
                else:
                    # Either it didn't exist before, or we never
                    # captured it (shouldn't happen). Remove whatever
                    # is there now.
                    try:
                        record.path.unlink()
                    except FileNotFoundError:
                        pass
            except OSError as rollback_exc:
                rollback_errors.append(f"{record.path}: {rollback_exc}")
        if rollback_errors:
            raise SafeIOError(
                "Atomic write rolled back partially: " + "; ".join(rollback_errors)
            ) from exc
        raise
