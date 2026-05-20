from desktop_sprite.models.geometry import Rect


def test_rect_overlap_and_intersection():
    first = Rect.from_xywh(0, 0, 10, 10)
    second = Rect.from_xywh(8, 8, 10, 10)
    third = Rect.from_xywh(20, 20, 5, 5)

    assert first.intersects(second)
    assert not first.intersects(third)
    assert first.overlaps_x(second)
    assert first.overlaps_y(second)
