import math

import pytest

from game.components import Collider, ControlVelocity, Grounded, Transform, Velocity
from game.physics import JUMP_SPEED, PLAYER_MOVE_SPEED, apply_impulse, move_aabb
from game.runtime import FIXED_STEP_SECONDS, FixedStepClock, create_runtime, step_runtime
from game.vectors import Aabb, Vec3
from game.world3d import World, create_test_arena


def step_many(runtime, seconds):
    for _ in range(math.ceil(seconds / FIXED_STEP_SECONDS)):
        step_runtime(runtime)


def test_player_falls_onto_ground_and_becomes_grounded():
    runtime = create_runtime()
    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    transform = player.require(Transform)
    transform.position = Vec3(2.5, 4.0, 2.5)

    step_many(runtime, 2)

    assert transform.position.y == pytest.approx(0.0, abs=1e-5)
    assert player.require(Grounded).value is True
    assert player.require(Velocity).value.y == 0


def test_player_cannot_move_through_arena_wall():
    runtime = create_runtime()
    runtime.world = create_test_arena()
    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    transform = player.require(Transform)
    transform.position = Vec3(8.5, 0.0, 0.5)
    session = runtime.require_session("local")
    session.apply_input(sequence=1, forward=0, strafe=1, yaw=0, pitch=0, jump=False)

    step_many(runtime, 1)

    assert transform.position.x == pytest.approx(9.7, abs=1e-5)
    assert player.require(Velocity).value.x == 0


def test_large_displacement_cannot_tunnel_through_one_block_wall():
    world = World()
    world.set_block(2, 0, 0, "stone")
    result = move_aabb(
        world,
        Vec3(0.5, 0, 0.5),
        Aabb(0.3, 1.8, 0.3),
        Vec3(8, 0, 0),
    )
    assert result.collided_x is True
    assert result.position.x == pytest.approx(1.7, abs=1e-5)


def test_floor_and_ceiling_block_vertical_motion():
    floor_world = World()
    floor_world.set_block(0, -1, 0, "stone")
    ceiling_world = World()
    ceiling_world.set_block(0, 2, 0, "stone")
    box = Aabb(0.3, 1.8, 0.3)

    falling = move_aabb(floor_world, Vec3(0.5, 0.5, 0.5), box, Vec3(0, -3, 0))
    rising = move_aabb(ceiling_world, Vec3(0.5, 0, 0.5), box, Vec3(0, 3, 0))

    assert falling.position.y == pytest.approx(0, abs=1e-5)
    assert falling.grounded is True
    assert rising.position.y == pytest.approx(0.2, abs=1e-5)
    assert rising.collided_y is True


def test_jump_is_consumed_and_only_applies_while_grounded():
    runtime = create_runtime()
    session = runtime.require_session("local")
    player = runtime.entities.require(session.player_entity_id)
    step_runtime(runtime)
    assert player.require(Grounded).value is True

    session.apply_input(sequence=1, forward=0, strafe=0, yaw=0, pitch=0, jump=True)
    step_runtime(runtime)
    first_jump_velocity = player.require(Velocity).value.y
    assert first_jump_velocity == pytest.approx(JUMP_SPEED - 24 * FIXED_STEP_SECONDS)
    assert session.command.jump_requested is False

    session.apply_input(sequence=2, forward=0, strafe=0, yaw=0, pitch=0, jump=True)
    step_runtime(runtime)
    assert player.require(Velocity).value.y < first_jump_velocity


def test_diagonal_input_is_normalized_and_relative_to_yaw():
    runtime = create_runtime()
    session = runtime.require_session("local")
    player = runtime.entities.require(session.player_entity_id)
    session.apply_input(sequence=1, forward=1, strafe=1, yaw=math.pi / 2, pitch=0, jump=False)

    step_runtime(runtime)

    velocity = player.require(ControlVelocity).value
    assert math.hypot(velocity.x, velocity.z) == pytest.approx(PLAYER_MOVE_SPEED)
    assert velocity.x < 0
    assert velocity.z < 0


def test_stale_input_sequence_is_ignored():
    runtime = create_runtime()
    session = runtime.require_session("local")
    assert session.apply_input(sequence=4, forward=1, strafe=0, yaw=0.5, pitch=0, jump=False)
    assert not session.apply_input(sequence=3, forward=-1, strafe=0, yaw=1, pitch=0, jump=True)
    assert session.command.sequence == 4
    assert session.command.forward == 1
    assert session.command.jump_requested is False


def test_fixed_step_clock_never_passes_variable_dt_to_simulation():
    clock = FixedStepClock()
    observed = []
    steps = clock.advance(0.1, observed.append)
    assert steps == 6
    assert observed == [FIXED_STEP_SECONDS] * 6


def test_horizontal_impulse_persists_decays_and_blends_with_input():
    runtime = create_runtime()
    session = runtime.require_session("local")
    player = runtime.entities.require(session.player_entity_id)
    step_runtime(runtime)
    start = player.require(Transform).position

    apply_impulse(player, Vec3(8, 0, 0))
    session.apply_input(sequence=1, forward=1, strafe=0, yaw=0, pitch=0, jump=False)
    step_runtime(runtime)
    blended = player.require(Transform).position

    assert blended.x > start.x
    assert blended.z < start.z
    assert 0 < player.require(Velocity).value.x < 8

    session.apply_input(sequence=2, forward=0, strafe=0, yaw=0, pitch=0, jump=False)
    for _ in range(180):
        step_runtime(runtime)
    assert player.require(Velocity).value.x == 0


def test_residual_axis_is_zeroed_when_impulse_hits_a_wall():
    runtime = create_runtime()
    runtime.world = create_test_arena()
    player = runtime.entities.require(runtime.require_session("local").player_entity_id)
    player.require(Transform).position = Vec3(9.6, 0, 0.5)
    apply_impulse(player, Vec3(20, 0, 0))

    step_runtime(runtime)

    assert player.require(Transform).position.x == pytest.approx(9.7, abs=1e-5)
    assert player.require(Velocity).value.x == 0
