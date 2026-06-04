"""Tests for the atomic JSON write helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from desktop_sprite.utils.safe_io import SafeIOError, atomic_write, write_json_atomic


def test_write_json_atomic_creates_file_with_newline(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    write_json_atomic(path, {"k": "v"})

    text = path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text) == {"k": "v"}


def test_write_json_atomic_does_not_leave_tmp_on_success(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    write_json_atomic(path, {"x": 1})

    assert not (path.with_name(path.name + ".tmp")).exists()


def test_write_json_atomic_overwrites_existing(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    path.write_text('{"old": true}\n', encoding="utf-8")

    write_json_atomic(path, {"new": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}


def test_atomic_write_rolls_back_on_exception(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.json"
    spirit_marks = tmp_path / "spirit_marks.json"
    inventory.write_text('{"entries": []}\n', encoding="utf-8")
    spirit_marks.write_text('{"marks": []}\n', encoding="utf-8")
    original_inventory = inventory.read_bytes()
    original_marks = spirit_marks.read_bytes()

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with atomic_write([inventory, spirit_marks]):
            # Pretend the first write succeeds and the second fails
            # with something unrelated. The captured pre-state should
            # be restored before the exception escapes.
            write_json_atomic(inventory, {"entries": ["NEW"]})
            raise Boom

    assert inventory.read_bytes() == original_inventory
    assert spirit_marks.read_bytes() == original_marks


def test_atomic_write_rolls_back_partial_when_only_one_file_existed(
    tmp_path: Path,
) -> None:
    inventory = tmp_path / "inventory.json"
    spirit_marks = tmp_path / "spirit_marks.json"
    inventory.write_text('{"entries": []}\n', encoding="utf-8")
    # spirit_marks did not exist before
    assert not spirit_marks.exists()

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with atomic_write([inventory, spirit_marks]):
            write_json_atomic(spirit_marks, {"marks": ["NEW"]})
            raise Boom

    assert inventory.read_text(encoding="utf-8") == '{"entries": []}\n'
    assert not spirit_marks.exists()


def test_atomic_write_raises_safeio_error_when_rollback_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory = tmp_path / "inventory.json"
    inventory.write_text('{"entries": []}\n', encoding="utf-8")

    real_write_bytes = Path.write_bytes

    def fail_on_inventory(self, data):  # type: ignore[no-redef]
        if self.name == "inventory.json":
            raise OSError("disk on fire")
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", fail_on_inventory)

    with pytest.raises(SafeIOError):
        with atomic_write([inventory]):
            write_json_atomic(inventory, {"entries": ["NEW"]})
            raise RuntimeError("trigger rollback")
