import pytest

from desktop_sprite.core.pathfinding import PathFinder, Surface, SurfaceOrientation, TraversalAction
from desktop_sprite.environment.environment_snapshot import EnvironmentSnapshot
from desktop_sprite.models.geometry import Rect, Vec2
from desktop_sprite.models.platform import Platform, PlatformType
from desktop_sprite.models.state import Pet
from desktop_sprite.utils.config import load_config


def platform(id_: str, type_: PlatformType, rect: Rect, *, source_id: int | None = None) -> Platform:
    return Platform(
        id=id_,
        type=type_,
        rect=rect,
        walkable=type_ in {PlatformType.GROUND, PlatformType.TASKBAR, PlatformType.WINDOW_TOP},
        climbable=type_ in {PlatformType.WINDOW_LEFT, PlatformType.WINDOW_RIGHT},
        dynamic=source_id is not None,
        source_id=source_id,
    )


def window_platforms(hwnd: int, left: float, top: float, right: float, bottom: float) -> list[Platform]:
    return [
        platform(f"window:{hwnd}:top", PlatformType.WINDOW_TOP, Rect(left, top, right, top + 8), source_id=hwnd),
        platform(f"window:{hwnd}:left", PlatformType.WINDOW_LEFT, Rect(left - 8, top, left + 6, bottom), source_id=hwnd),
        platform(f"window:{hwnd}:right", PlatformType.WINDOW_RIGHT, Rect(right - 6, top, right + 8, bottom), source_id=hwnd),
    ]


def make_snapshot(platforms: list[Platform]) -> EnvironmentSnapshot:
    return EnvironmentSnapshot(
        screen_rect=Rect.from_xywh(0, 0, 900, 700),
        work_area_rect=Rect.from_xywh(0, 0, 900, 650),
        taskbar_rect=None,
        windows=[],
        platforms=platforms,
        timestamp=1.0,
    )


def make_pet() -> Pet:
    return Pet(
        position=Vec2(100, 546),
        velocity=Vec2(),
        width=84,
        height=104,
        support_platform_id="ground:work_area",
    )


def make_physics():
    return load_config().physics


def ground() -> Platform:
    return platform("ground:work_area", PlatformType.GROUND, Rect.from_xywh(0, 650, 900, 4))


def test_same_level_overlapping_platforms_generate_transform_not_jump():
    pet = make_pet()
    pet.support_platform_id = "taskbar:main"
    taskbar = platform("taskbar:main", PlatformType.TASKBAR, Rect.from_xywh(0, 650, 900, 4))
    snapshot = make_snapshot([ground(), taskbar])

    graph = PathFinder().build_surface_graph(pet, snapshot, make_physics())

    edge = next(
        edge
        for edge in graph.edges
        if graph.nodes[edge.from_node_id].surface_id == "taskbar:main"
        and graph.nodes[edge.to_node_id].surface_id == "ground:work_area"
    )
    assert edge.action == TraversalAction.TRANSFORM


def test_path_to_point_on_current_platform_generates_walk_edge():
    pet = make_pet()
    snapshot = make_snapshot([ground()])

    plan = PathFinder().find_path_to_surface_point(
        pet=pet,
        snapshot=snapshot,
        target_surface_id="ground:work_area",
        target_anchor_t=300,
        physics=make_physics(),
    )

    assert plan is not None
    assert plan.target_surface_id == "ground:work_area"
    assert plan.target_anchor_t == 300
    assert len(plan.steps) == 1
    assert plan.steps[0].action == TraversalAction.MOVE
    assert plan.steps[0].from_surface_id == "ground:work_area"
    assert plan.steps[0].to_surface_id == "ground:work_area"


def test_lower_platform_transfer_with_vertical_overlap_does_not_generate_jump():
    pet = make_pet()
    pet.support_platform_id = "window:1:top"
    source_top = platform("window:1:top", PlatformType.WINDOW_TOP, Rect(160, 430, 320, 438), source_id=1)
    lower_top = platform("window:2:top", PlatformType.WINDOW_TOP, Rect(170, 520, 310, 528), source_id=2)
    snapshot = make_snapshot([ground(), source_top, lower_top])

    graph = PathFinder().build_surface_graph(pet, snapshot, make_physics())

    edges = [
        edge
        for edge in graph.edges
        if graph.nodes[edge.from_node_id].surface_id == "window:1:top"
        and graph.nodes[edge.to_node_id].surface_id == "window:2:top"
    ]
    assert not any(edge.action == TraversalAction.JUMP for edge in edges)


def test_drop_edge_is_created_when_vertical_ray_hits_platform():
    pet = make_pet()
    pet.support_platform_id = "window:1:top"
    source_top = platform("window:1:top", PlatformType.WINDOW_TOP, Rect(160, 430, 320, 438), source_id=1)
    lower_top = platform("window:2:top", PlatformType.WINDOW_TOP, Rect(260, 520, 420, 528), source_id=2)
    snapshot = make_snapshot([ground(), source_top, lower_top])

    graph = PathFinder().build_surface_graph(pet, snapshot, make_physics())

    edges = [
        edge
        for edge in graph.edges
        if graph.nodes[edge.from_node_id].surface_id == "window:1:top"
        and graph.nodes[edge.to_node_id].surface_id == "window:2:top"
    ]
    assert edges
    assert any(edge.action == TraversalAction.FALL for edge in edges)
    assert any(graph.nodes[edge.from_node_id].anchor_t == source_top.rect.right for edge in edges)


def test_low_window_path_climbs_from_ground_to_window_top():
    pet = make_pet()
    snapshot = make_snapshot([ground(), *window_platforms(1, 160, 430, 320, 620)])

    plan = PathFinder().find_path(pet, snapshot, target_window_id=1, physics=make_physics())

    assert plan is not None
    assert any(step.action == TraversalAction.TRANSFORM for step in plan.steps)
    assert plan.steps[-1].to_surface_id == "window:1:top"


def test_high_window_can_be_reached_through_lower_window():
    pet = make_pet()
    snapshot = make_snapshot(
        [
            ground(),
            *window_platforms(1, 160, 430, 320, 620),
            *window_platforms(2, 340, 300, 520, 500),
        ]
    )

    plan = PathFinder().find_path(pet, snapshot, target_window_id=2, physics=make_physics())

    assert plan is not None
    assert len(plan.steps) >= 2
    assert any(step.to_surface_id == "window:1:top" for step in plan.steps)
    assert plan.steps[-1].to_surface_id == "window:2:top"


def test_gap_between_platforms_generates_jump_edge_when_in_range():
    pet = make_pet()
    target_top = platform("window:2:top", PlatformType.WINDOW_TOP, Rect(360, 430, 520, 438), source_id=2)
    snapshot = make_snapshot([ground(), *window_platforms(1, 160, 430, 320, 620), target_top])

    plan = PathFinder().find_path(pet, snapshot, target_window_id=2, physics=make_physics())

    assert plan is not None
    assert any(step.action == TraversalAction.JUMP for step in plan.steps)


def test_jump_to_platform_on_right_targets_near_edge():
    pet = make_pet()
    pet.support_platform_id = "window:1:top"
    source_top = platform("window:1:top", PlatformType.WINDOW_TOP, Rect(160, 430, 320, 438), source_id=1)
    target_top = platform("window:2:top", PlatformType.WINDOW_TOP, Rect(360, 430, 520, 438), source_id=2)
    snapshot = make_snapshot([ground(), source_top, target_top])

    plan = PathFinder().find_path(pet, snapshot, target_window_id=2, physics=make_physics())

    assert plan is not None
    jump = next(step for step in plan.steps if step.action == TraversalAction.JUMP)
    assert jump.land_point is not None
    assert jump.land_point[0] == target_top.rect.left - pet.width / 2


def test_gap_beyond_jump_distance_has_no_path():
    pet = make_pet()
    target_top = platform("window:2:top", PlatformType.WINDOW_TOP, Rect(760, 430, 880, 438), source_id=2)
    snapshot = make_snapshot([ground(), *window_platforms(1, 160, 430, 320, 620), target_top])

    plan = PathFinder().find_path(pet, snapshot, target_window_id=2, physics=make_physics())

    assert plan is None


def test_high_window_without_intermediate_path_is_unreachable():
    pet = make_pet()
    snapshot = make_snapshot([ground(), *window_platforms(1, 160, 100, 320, 280)])

    plan = PathFinder().find_path(pet, snapshot, target_window_id=1, physics=make_physics())

    assert plan is None


def test_platforms_are_adapted_to_surfaces():
    top = platform("window:1:top", PlatformType.WINDOW_TOP, Rect(160, 430, 320, 438), source_id=1)
    side = platform("window:1:left", PlatformType.WINDOW_LEFT, Rect(152, 430, 166, 620), source_id=1)

    top_surface = Surface.from_platform(top)
    side_surface = Surface.from_platform(side)

    assert top_surface.orientation == SurfaceOrientation.HORIZONTAL
    assert side_surface.orientation == SurfaceOrientation.VERTICAL


def test_surface_graph_uses_fall_edges_for_vertical_ray_hits():
    pet = make_pet()
    pet.support_platform_id = "window:1:top"
    source_top = platform("window:1:top", PlatformType.WINDOW_TOP, Rect(160, 430, 320, 438), source_id=1)
    lower_top = platform("window:2:top", PlatformType.WINDOW_TOP, Rect(260, 520, 420, 528), source_id=2)
    snapshot = make_snapshot([ground(), source_top, lower_top])

    graph = PathFinder().build_surface_graph(pet, snapshot, make_physics())

    fall_edges = [edge for edge in graph.edges if edge.action == TraversalAction.FALL]
    assert fall_edges
    assert any(graph.nodes[edge.from_node_id].anchor_t == source_top.rect.right for edge in fall_edges)


def test_vertical_surface_move_edges_use_climb_speed():
    pet = make_pet()
    snapshot = make_snapshot([ground(), *window_platforms(1, 160, 430, 320, 620)])
    physics = make_physics()

    graph = PathFinder().build_surface_graph(pet, snapshot, physics)

    edge = next(
        edge
        for edge in graph.edges
        if edge.action == TraversalAction.MOVE
        and graph.nodes[edge.from_node_id].surface_id == "window:1:left"
        and graph.nodes[edge.to_node_id].surface_id == "window:1:left"
    )
    source = graph.nodes[edge.from_node_id]
    target = graph.nodes[edge.to_node_id]
    assert edge.cost == pytest.approx(abs(target.anchor_t - source.anchor_t) / physics.climb_speed)


def test_transform_edges_only_connect_matching_window_side_and_top():
    pet = make_pet()
    snapshot = make_snapshot(
        [
            ground(),
            *window_platforms(1, 160, 430, 320, 620),
            *window_platforms(2, 360, 430, 520, 620),
        ]
    )

    graph = PathFinder().build_surface_graph(pet, snapshot, make_physics())

    transform_pairs = {
        (graph.nodes[edge.from_node_id].surface_id, graph.nodes[edge.to_node_id].surface_id)
        for edge in graph.edges
        if edge.action == TraversalAction.TRANSFORM
    }
    assert ("window:1:left", "window:1:top") in transform_pairs
    assert ("window:1:left", "window:2:top") not in transform_pairs


def test_intersecting_wall_and_platform_generate_transform_not_jump():
    pet = make_pet()
    platform_top = platform("window:1:top", PlatformType.WINDOW_TOP, Rect(160, 430, 320, 438), source_id=1)
    intersecting_side = platform("window:2:left", PlatformType.WINDOW_LEFT, Rect(220, 400, 232, 500), source_id=2)
    snapshot = make_snapshot([ground(), platform_top, intersecting_side])

    graph = PathFinder().build_surface_graph(pet, snapshot, make_physics())
    pairs_by_action = {
        action: {
            (graph.nodes[edge.from_node_id].surface_id, graph.nodes[edge.to_node_id].surface_id)
            for edge in graph.edges
            if edge.action == action
        }
        for action in (TraversalAction.TRANSFORM, TraversalAction.JUMP)
    }

    assert (platform_top.id, intersecting_side.id) in pairs_by_action[TraversalAction.TRANSFORM]
    assert (intersecting_side.id, platform_top.id) in pairs_by_action[TraversalAction.TRANSFORM]
    assert (platform_top.id, intersecting_side.id) not in pairs_by_action[TraversalAction.JUMP]


def test_surface_graph_generates_cross_surface_jumps_but_not_same_window_jumps():
    pet = make_pet()
    snapshot = make_snapshot(
        [
            ground(),
            *window_platforms(1, 160, 430, 320, 620),
            *window_platforms(2, 340, 300, 500, 500),
        ]
    )

    graph = PathFinder().build_surface_graph(pet, snapshot, make_physics())
    jump_pairs = {
        (graph.nodes[edge.from_node_id].surface_id, graph.nodes[edge.to_node_id].surface_id)
        for edge in graph.edges
        if edge.action == TraversalAction.JUMP
    }

    assert any(source == "ground:work_area" and target == "window:1:left" for source, target in jump_pairs)
    assert any(source == "window:1:top" and target.startswith("window:2:") for source, target in jump_pairs)
    assert not any(source.startswith("window:1:") and target.startswith("window:1:") for source, target in jump_pairs)
    assert not any(source.endswith(":left") or source.endswith(":right") for source, _target in jump_pairs)


def test_ground_jump_to_low_vertical_surface_keeps_wall_bottom_landing():
    pet = make_pet()
    snapshot = make_snapshot([ground(), *window_platforms(1, 160, 430, 320, 620)])

    plan = PathFinder().find_path(pet, snapshot, target_window_id=1, physics=make_physics())

    assert plan is not None
    jump = next(step for step in plan.steps if step.action == TraversalAction.JUMP and step.to_surface_id == "window:1:left")
    side = snapshot.platform_by_id("window:1:left")
    assert side is not None
    assert jump.land_t == side.rect.bottom
    assert jump.land_point is not None
    assert jump.land_point[0] == side.rect.center_x - pet.width / 2


def test_jump_to_vertical_surface_chooses_nearest_wall_contact():
    pet = make_pet()
    pet.support_platform_id = "window:1:top"
    source_top = platform("window:1:top", PlatformType.WINDOW_TOP, Rect(160, 430, 320, 438), source_id=1)
    target_side = platform("window:2:left", PlatformType.WINDOW_LEFT, Rect(360, 430, 374, 620), source_id=2)
    snapshot = make_snapshot([ground(), source_top, target_side])

    graph = PathFinder().build_surface_graph(pet, snapshot, make_physics())
    jump = next(
        edge
        for edge in graph.edges
        if edge.action == TraversalAction.JUMP
        and graph.nodes[edge.from_node_id].surface_id == source_top.id
        and graph.nodes[edge.to_node_id].surface_id == target_side.id
    )
    target_node = graph.nodes[jump.to_node_id]

    assert target_node.anchor_t == target_side.rect.top
    assert target_node.anchor_t != target_side.rect.bottom
    assert target_node.x == target_side.rect.center_x - pet.width / 2


def test_jump_reachability_uses_projectile_velocity_limits():
    pet = make_pet()
    source = platform("window:1:top", PlatformType.WINDOW_TOP, Rect(160, 430, 320, 438), source_id=1)
    reachable = platform("window:2:top", PlatformType.WINDOW_TOP, Rect(260, 520, 420, 528), source_id=2)
    too_high = platform("window:3:top", PlatformType.WINDOW_TOP, Rect(260, 20, 420, 28), source_id=3)
    physics = make_physics()
    pathfinder = PathFinder()

    assert pathfinder._jump_reachable(
        Surface.from_platform(source),
        240,
        Surface.from_platform(reachable),
        300,
        abs(physics.jump_speed_x),
        abs(physics.jump_speed_y),
        physics.gravity,
        physics.edge_snap_distance,
        pet,
    )
    assert not pathfinder._jump_reachable(
        Surface.from_platform(source),
        240,
        Surface.from_platform(too_high),
        300,
        abs(physics.jump_speed_x),
        abs(physics.jump_speed_y),
        physics.gravity,
        physics.edge_snap_distance,
        pet,
    )

