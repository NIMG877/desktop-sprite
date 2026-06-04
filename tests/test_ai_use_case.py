import pytest
from desktop_sprite.ai.use_case import UseCase, UseCaseRegistry


def test_use_case_stores_fields():
    uc = UseCase(
        use_case_id="x",
        event_topic="topic.a",
        prompt_template="hi {name}",
        target_channels=("pet_bubble", "chat_panel"),
        throttle_ms=500,
        fallback_text="oops",
    )
    assert uc.use_case_id == "x"
    assert uc.target_channels == ("pet_bubble", "chat_panel")
    assert uc.throttle_ms == 500
    assert uc.fallback_text == "oops"


def test_use_case_defaults():
    uc = UseCase(
        use_case_id="x",
        event_topic="t",
        prompt_template="p",
        target_channels=("a",),
    )
    assert uc.throttle_ms == 0
    assert uc.fallback_text is None


def test_registry_register_and_get():
    reg = UseCaseRegistry()
    uc = UseCase(
        use_case_id="a", event_topic="t.a", prompt_template="p",
        target_channels=("c",),
    )
    reg.register(uc)
    assert reg.get("a") is uc
    assert reg.get("missing") is None


def test_registry_for_topic_returns_matching_use_cases():
    reg = UseCaseRegistry()
    a = UseCase(use_case_id="a", event_topic="t.x", prompt_template="p", target_channels=("c",))
    b = UseCase(use_case_id="b", event_topic="t.x", prompt_template="p", target_channels=("c",))
    c = UseCase(use_case_id="c", event_topic="t.y", prompt_template="p", target_channels=("c",))
    reg.register(a)
    reg.register(b)
    reg.register(c)
    matches = reg.for_topic("t.x")
    assert matches == [a, b]
    assert reg.for_topic("t.y") == [c]
    assert reg.for_topic("missing") == []


def test_registry_register_idempotent_overwrites():
    reg = UseCaseRegistry()
    a1 = UseCase(use_case_id="a", event_topic="t", prompt_template="p1", target_channels=("c",))
    a2 = UseCase(use_case_id="a", event_topic="t", prompt_template="p2", target_channels=("c",))
    reg.register(a1)
    reg.register(a2)
    assert reg.get("a") is a2
