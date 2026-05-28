from desktop_sprite.core.behavior_orchestrator import BehaviorOrchestrator, BehaviorPhaseName
from desktop_sprite.core.pet_mode import ModeController, PetMode


def test_mode_controller_defaults_to_idle():
    controller = ModeController()

    assert controller.is_idle()
    assert not controller.is_go_to_target()


def test_mode_controller_switches_to_go_to_target():
    controller = ModeController()

    controller.set_mode(PetMode.GO_TO_TARGET)

    assert controller.is_go_to_target()
    assert not controller.is_idle()


def test_mode_controller_locked_show_blocks_normal_mode_switch():
    controller = ModeController()

    assert controller.set_mode(PetMode.SHOW, force=True, lock=True)
    assert not controller.set_mode(PetMode.IDLE)

    assert controller.mode == PetMode.SHOW

    controller.unlock()
    assert controller.set_mode(PetMode.IDLE)
    assert controller.mode == PetMode.IDLE


def test_orchestrator_tracks_phase_elapsed_and_reset():
    orchestrator = BehaviorOrchestrator()

    orchestrator.tick(0.25)
    orchestrator.advance(BehaviorPhaseName.PATH_EXECUTING)
    orchestrator.tick(0.5)

    assert orchestrator.phase.name == BehaviorPhaseName.PATH_EXECUTING
    assert orchestrator.phase.elapsed == 0.5

    orchestrator.reset()

    assert orchestrator.phase.name == BehaviorPhaseName.IDLE_WAIT
    assert orchestrator.phase.elapsed == 0.0


def test_orchestrator_runs_show_sequence_by_phase_duration():
    orchestrator = BehaviorOrchestrator()

    orchestrator.begin_show()
    assert orchestrator.phase.name == BehaviorPhaseName.SHOW_OPEN_WINGS

    orchestrator.tick(0.71)
    assert orchestrator.phase.name == BehaviorPhaseName.SHOW_FLY
    assert not orchestrator.is_sequence_complete()

    for seconds in [1.21, 1.01, 5.01, 1.81, 0.71]:
        orchestrator.tick(seconds)

    assert orchestrator.phase.name == BehaviorPhaseName.SHOW_CLOSE_WINGS
    assert orchestrator.is_sequence_complete()
