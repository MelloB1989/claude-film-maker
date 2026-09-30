"""A frame-change handler that raises fails its frame (lib/handlers.py), bpy-free.

Blender calls bpy.app.handlers from C: an exception in one is printed and cleared, and frame_set() and render() carry
on as if nothing happened (bpy_app_handlers.cc). FakeBlender does the same with plain lists.
"""
from types import SimpleNamespace

import pytest

from lib import handlers


class FakeBlender:
    """The handler lists and a frame_set that calls them the way Blender does: each with (scene, depsgraph), and an
    exception printed and swallowed, so frame_set itself never raises."""

    def __init__(self):
        self.frame_change_pre, self.frame_change_post = [], []
        self.scene = SimpleNamespace(frame_current=0, frame_subframe=0.0)
        self.printed = []

    def frame_set(self, frame, subframe=0.0):
        self.scene.frame_current, self.scene.frame_subframe = frame, subframe
        for fns in (self.frame_change_pre, self.frame_change_post):
            for fn in fns:
                try:
                    fn(self.scene, None)
                except Exception as e:  # noqa: BLE001 - what Blender does
                    self.printed.append(repr(e))

    def guard(self):
        g = handlers.HandlerGuard()
        g.install(frame_change_pre=self.frame_change_pre, frame_change_post=self.frame_change_post)
        return g


def pose_failing_on(bad_frame):
    posed = []

    def pose(scene, _depsgraph):
        if scene.frame_current + scene.frame_subframe == bad_frame:
            raise IndexError("list index out of range")
        posed.append(scene.frame_current + scene.frame_subframe)

    return pose, posed


def test_a_handler_error_fails_the_frame():
    bl = FakeBlender()
    pose, posed = pose_failing_on(168)
    bl.frame_change_pre.append(pose)
    guard = bl.guard()
    guard.reset()
    bl.frame_set(167)
    guard.check("[b01_thread] film frame 167")  # a frame whose handlers ran clean passes
    guard.reset()
    bl.frame_set(168)
    with pytest.raises(handlers.HandlerError) as err:
        guard.check("[b01_thread] film frame 168")
    msg = str(err.value)
    for part in ("[b01_thread] film frame 168", "frame_change_pre", "pose", "IndexError", "list index out of range"):
        assert part in msg
    assert posed == [167]
    assert bl.printed == ["IndexError('list index out of range')"]  # raised on to Blender, which still prints it


def test_an_error_on_a_motion_blur_step_fails_the_frame_and_names_the_step():
    bl = FakeBlender()
    pose, posed = pose_failing_on(168.25)
    bl.frame_change_post.append(pose)
    guard = bl.guard()
    guard.reset()
    bl.frame_set(168)
    guard.check("[b01_thread] film frame 168")
    for frame, sub in ((167, 0.75), (168, 0.0), (168, 0.25)):  # the render's motion-blur steps: frame_set at sub-frames
        bl.frame_set(frame, sub)
    with pytest.raises(handlers.HandlerError, match=r"frame_change_post.*168\.25"):
        guard.check("[b01_thread] film frame 168, while rendering")
    assert posed == [168, 167.75, 168]


def test_an_error_before_the_reset_does_not_fail_the_next_frame():
    bl = FakeBlender()
    pose, _ = pose_failing_on(10)
    bl.frame_change_pre.append(pose)
    guard = bl.guard()
    bl.frame_set(10)  # say, the shot's own build() setting a frame before any check
    guard.reset()
    bl.frame_set(11)
    guard.check("[shot] film frame 11")


def test_a_failure_is_reported_once():
    bl = FakeBlender()
    pose, _ = pose_failing_on(5)
    bl.frame_change_pre.append(pose)
    guard = bl.guard()
    guard.reset()
    bl.frame_set(5)
    with pytest.raises(handlers.HandlerError):
        guard.check("[shot] film frame 5")
    guard.check("[shot] film frame 5, again")  # the check hands the failure over and forgets it


def test_installing_twice_wraps_each_handler_once_and_it_still_runs_once_a_frame():
    bl = FakeBlender()
    pose, posed = pose_failing_on(None)
    bl.frame_change_pre.append(pose)
    guard = handlers.HandlerGuard()
    assert guard.install(frame_change_pre=bl.frame_change_pre, frame_change_post=bl.frame_change_post) == 1
    assert guard.install(frame_change_pre=bl.frame_change_pre, frame_change_post=bl.frame_change_post) == 0
    bl.frame_set(3)
    assert posed == [3]
    assert bl.frame_change_pre[0] is not pose and bl.frame_change_pre[0].__name__ == "pose"
