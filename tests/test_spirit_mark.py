import random
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from desktop_sprite.models.spirit_mark import (
    SpiritMarkError,
    SpiritMarkGrantRequest,
    SpiritMarkInventory,
    generate_spirit_mark,
    load_spirit_mark_inventory,
    save_spirit_mark_inventory,
)


def test_generate_spirit_mark_uses_request_source_and_safe_pet_stats():
    request = SpiritMarkGrantRequest(
        entry_id="spirit-entry-001",
        source_type="focus",
        source_id="focus-001",
        source_description="这道灵痕来自一次 45 分钟的专注，任务是修改论文摘要。",
        quality_hint="completed",
        style_hint="trail",
        record_tags=("deep_work", "night"),
    )

    mark = generate_spirit_mark(
        request,
        rng=random.Random(7),
        now=datetime(2026, 6, 3, tzinfo=timezone.utc),
    )

    assert mark.source_type == "focus"
    assert mark.entry_id == "spirit-entry-001"
    assert mark.source_id == "focus-001"
    assert mark.source_description == request.source_description
    assert mark.set_id == "stardust_echo"
    assert mark.rarity >= 3
    assert mark.main_stat.name in {"机动", "稳定", "柔韧", "爆发", "辉光", "余韵", "凝聚", "感知", "亲和", "威仪", "灵巧", "回响"}
    assert "专注收益" not in {mark.main_stat.name, *(stat.name for stat in mark.sub_stats)}


def test_equipping_marks_is_exclusive_per_slot_and_stat_totals_include_two_piece_bonus():
    first = generate_spirit_mark(
        SpiritMarkGrantRequest(set_hint="silent_guardian", rarity_hint=3),
        rng=random.Random(1),
    )
    same_slot = replace(first, entry_id="same-slot", main_stat=replace(first.main_stat, value=first.main_stat.value + 1))
    other_slot_id = "core" if first.slot_id != "core" else "echo"
    other_slot = replace(first, entry_id="other-slot", slot_id=other_slot_id)
    inventory = SpiritMarkInventory((first, same_slot, other_slot)).equip(first.entry_id).equip(other_slot.entry_id).equip(same_slot.entry_id)

    equipped = inventory.equipped_marks()

    assert same_slot.entry_id in {mark.entry_id for mark in equipped}
    assert first.entry_id not in {mark.entry_id for mark in equipped}
    assert len({mark.slot_id for mark in equipped}) == len(equipped)
    assert inventory.stat_totals()["亲和"] >= 2


def test_favorite_marks_are_protected_from_decompose_and_enhance_increases_level():
    mark = generate_spirit_mark(SpiritMarkGrantRequest(rarity_hint=2), rng=random.Random(3))
    inventory = SpiritMarkInventory((mark,)).set_favorite(mark.entry_id)

    with pytest.raises(SpiritMarkError):
        inventory.decompose(mark.entry_id)

    updated = inventory.set_favorite(mark.entry_id, False).enhance(mark.entry_id, rng=random.Random(0))

    assert updated.mark_by_entry_id(mark.entry_id).level == 1
    assert updated.mark_by_entry_id(mark.entry_id).main_stat.value > mark.main_stat.value


def test_spirit_mark_inventory_round_trips_json(tmp_path):
    mark = generate_spirit_mark(SpiritMarkGrantRequest(rarity_hint=4), rng=random.Random(4))
    path = tmp_path / "spirit_marks.json"

    save_spirit_mark_inventory(path, SpiritMarkInventory((mark,)))
    loaded = load_spirit_mark_inventory(path)

    assert loaded.marks == (mark,)
