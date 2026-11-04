"""Moving the open level sequence's playhead without the deprecated call.

LevelSequenceEditorBlueprintLibrary.SetCurrentTime(int) is deprecated since 5.4 and warns on every call
(LevelSequenceEditorBlueprintLibrary.h:88-90); the replacement is SetGlobalPosition (Python set_global_position,
:107-108) with an FMovieSceneSequencePlaybackParams (MovieSceneSequencePlayer.h: Frame, PositionType Frame,
UpdateMethod Scrub). Older engines without it fall back to set_current_time.
"""
from __future__ import annotations

import unreal


def set_frame(frame: int) -> None:
    """Put the open sequence's playhead on a display-rate frame (a scrub: no events fired in between)."""
    LSE = unreal.LevelSequenceEditorBlueprintLibrary
    fn = getattr(LSE, "set_global_position", None)
    if fn is None:
        LSE.set_current_time(int(frame))
        return
    params = unreal.MovieSceneSequencePlaybackParams(
        frame=unreal.FrameTime(unreal.FrameNumber(int(frame))), position_type=unreal.MovieScenePositionType.FRAME,
        update_method=unreal.UpdatePositionMethod.SCRUB)
    fn(params, unreal.MovieSceneTimeUnit.DISPLAY_RATE)
