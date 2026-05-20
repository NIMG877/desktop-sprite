from desktop_sprite.core.stamina_system import StaminaSystem
from desktop_sprite.models.geometry import Vec2
from desktop_sprite.models.state import Pet, PetState
from desktop_sprite.utils.config import load_config


def make_system_and_pet(stamina: float = 100) -> tuple[StaminaSystem, Pet]:
    config = load_config()
    pet = Pet(
        position=Vec2(0, 0),
        velocity=Vec2(),
        width=84,
        height=104,
        stamina=stamina,
    )
    return StaminaSystem(config.stamina, config.physics), pet


def test_lower_stamina_reduces_capability_and_effective_speeds():
    system, full = make_system_and_pet(100)
    _, tired = make_system_and_pet(25)

    assert system.capability(tired) < system.capability(full)
    assert system.effective_walk_speed(tired) < system.effective_walk_speed(full)
    assert system.effective_climb_speed(tired) < system.effective_climb_speed(full)
    assert system.max_jump_height(tired) < system.max_jump_height(full)
    assert system.max_jump_distance(tired) < system.max_jump_distance(full)


def test_capability_has_minimum_floor():
    system, pet = make_system_and_pet(0)

    assert system.capability(pet) == system.config.min_capability_factor


def test_walk_climb_jump_consume_stamina():
    system, pet = make_system_and_pet(100)

    pet.state = PetState.WALK
    pet.position.x = 20
    system.apply_motion_cost(pet, Vec2(0, 0), PetState.WALK)
    walk_stamina = pet.stamina

    pet.position.y = -20
    system.apply_motion_cost(pet, Vec2(pet.position.x, 0), PetState.CLIMB)
    climb_stamina = pet.stamina

    system.consume_jump(pet)

    assert walk_stamina < 100
    assert climb_stamina < walk_stamina
    assert pet.stamina < climb_stamina


def test_idle_recovery_caps_at_max_stamina():
    system, pet = make_system_and_pet(95)

    system.recover(pet, dt=10, resting=True)

    assert pet.stamina == system.config.max_stamina
