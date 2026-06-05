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


def test_channel_default_dispatch_stream_methods_are_noop():
    """基类三个钩子默认 no-op；不抛错、不写任何状态。"""
    class _Empty(Channel):
        def dispatch(self, message: AIText) -> None:
            pass

    ch = _Empty(name="x")
    ch.dispatch_stream_start("s1", "uc1")
    ch.dispatch_stream_delta("s1", "hi", "uc1")
    ch.dispatch_stream_end("s1", "hi", "ai", "uc1")
    # 不抛错即过


def test_channel_subclass_can_override_only_delta():
    class _Partial(Channel):
        def __init__(self):
            super().__init__(name="p")
            self.deltas: list[str] = []
        def dispatch(self, message: AIText) -> None:
            pass
        def dispatch_stream_delta(self, stream_id, delta, use_case_id):
            self.deltas.append(delta)

    p = _Partial()
    p.dispatch_stream_start("s", "u")
    p.dispatch_stream_delta("s", "a", "u")
    p.dispatch_stream_delta("s", "b", "u")
    p.dispatch_stream_end("s", "ab", "ai", "u")
    assert p.deltas == ["a", "b"]
