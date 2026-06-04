import time
from desktop_sprite.ai.channel import AIText, Channel


class RecordingChannel(Channel):
    def __init__(self, name: str = "test") -> None:
        super().__init__(name=name)
        self.dispatched: list[AIText] = []

    def dispatch(self, message: AIText) -> None:
        self.dispatched.append(message)


def test_aitext_is_immutable_and_slotted():
    msg = AIText(text="hi", source="ai", use_case_id="x", timestamp=1.0)
    assert msg.text == "hi"
    assert msg.source == "ai"
    with __import__("pytest").raises(AttributeError):
        msg.text = "no"  # type: ignore[misc]


def test_channel_abstract_dispatch_must_be_overridden():
    class Broken(Channel):
        pass
    import pytest
    with pytest.raises(TypeError):
        Broken(name="x")  # 未实现 dispatch


def test_recording_channel_dispatch_appends():
    ch = RecordingChannel()
    msg = AIText(text="t", source="ai", use_case_id="u", timestamp=time.time())
    ch.dispatch(msg)
    ch.dispatch(msg)
    assert len(ch.dispatched) == 2
    assert ch.dispatched[0] is msg


def test_channel_name_stored():
    ch = RecordingChannel(name="pet_bubble")
    assert ch.name == "pet_bubble"
