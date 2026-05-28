from PySide6.QtGui import QImage, QPainter

from desktop_sprite.models.geometry import Vec2
from desktop_sprite.models.state import Pet, PetState
from desktop_sprite.ui.pet_renderer import PetRenderer
from desktop_sprite.ui.render_pose import PoseBuilder


def make_pet(state: PetState) -> Pet:
    velocity = Vec2(120, 0)
    if state == PetState.FALL:
        velocity = Vec2(0, 800)
    return Pet(
        position=Vec2(0, 0),
        velocity=velocity,
        width=84,
        height=104,
        state=state,
    )


def has_visible_pixels(image: QImage) -> bool:
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 0:
                return True
    return False


def test_renderer_draws_non_empty_images_for_core_states():
    builder = PoseBuilder()
    renderer = PetRenderer()

    for state in [
        PetState.IDLE,
        PetState.WALK,
        PetState.JUMP,
        PetState.CLIMB,
        PetState.FALL,
        PetState.DRAGGED,
        PetState.OPEN_WINGS,
        PetState.FLY,
        PetState.HOVER,
        PetState.WING_LAND,
        PetState.CLOSE_WINGS,
    ]:
        image = QImage(84, 104, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        pose = builder.build(make_pet(state), phase=0.25, width=84, height=104)
        renderer.draw_pose(painter, pose, width=84, height=104)
        painter.end()

        assert has_visible_pixels(image), state
