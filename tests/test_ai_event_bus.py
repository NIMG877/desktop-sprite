from desktop_sprite.ai.event_bus import EventBus


def test_publish_calls_handler_with_payload():
    bus = EventBus()
    received = []
    bus.subscribe("topic.a", lambda payload: received.append(payload))
    bus.publish("topic.a", "hello")
    assert received == ["hello"]


def test_publish_to_unsubscribed_topic_is_noop():
    bus = EventBus()
    received = []
    bus.subscribe("topic.a", lambda payload: received.append(payload))
    bus.publish("topic.b", "hello")
    assert received == []


def test_subscribe_returns_unsubscribe_callable():
    bus = EventBus()
    received = []
    unsubscribe = bus.subscribe("topic.a", lambda p: received.append(p))
    unsubscribe()
    bus.publish("topic.a", "x")
    assert received == []


def test_multiple_subscribers_called_in_subscription_order():
    bus = EventBus()
    order = []
    bus.subscribe("t", lambda _: order.append("a"))
    bus.subscribe("t", lambda _: order.append("b"))
    bus.publish("t", None)
    assert order == ["a", "b"]


def test_handler_exception_does_not_break_other_handlers():
    bus = EventBus()
    order = []
    def bad(_):
        raise RuntimeError("boom")
    bus.subscribe("t", bad)
    bus.subscribe("t", lambda _: order.append("ok"))
    bus.publish("t", None)  # 不应抛
    assert order == ["ok"]


def test_unsubscribe_is_idempotent():
    bus = EventBus()
    received = []
    unsubscribe = bus.subscribe("t", lambda p: received.append(p))
    unsubscribe()
    unsubscribe()  # 不应抛
    bus.publish("t", "x")
    assert received == []
