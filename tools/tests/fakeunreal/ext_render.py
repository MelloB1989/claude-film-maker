"""WP9's fakes: Movie Render Queue (queue subsystem, queue, job, legacy preset config and its settings, PIE and
new-process executors) and level sequences with a playback range, display rate and camera cuts.

A started render writes one frame per tick (a minimal valid PNG/JPG/EXR/BMP for every image output and every pass)
into the output setting's directory, following file_name_format, for frames [custom_start_frame, custom_end_frame);
the WAV output writes one WAV per job. Tests steer it with `fake.mrq`:

    fake.mrq.fail_at = 1203        # stop (as a crash would) before writing this frame
    fake.mrq.never_start = True    # the queue is accepted, nothing renders, MRQ stops (the unsaved-map case)
    fake.mrq.hang = True           # the queue is accepted, MRQ says it renders, nothing is written (a modal)
    fake.mrq.frames_per_tick = 4
    fake.mrq.jobs                  # every job started: {"config": {...}, "executor": name, "map", "sequence"}
"""
from __future__ import annotations

import os
import struct
import wave

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16 + b"\x00\x00\x00\x00IEND\xaeB`\x82"
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 16 + b"\xff\xd9"
EXR = b"\x76\x2f\x31\x01" + b"\x00" * 400
BMP_BODY = b"\x00" * 50


def _bmp() -> bytes:
    size = 2 + 4 + len(BMP_BODY)
    return b"BM" + struct.pack("<I", size) + BMP_BODY


DATA = {"png": PNG, "jpg": JPG, "exr": EXR, "bmp": _bmp()}
OUT_CLASSES = {"MoviePipelineImageSequenceOutput_PNG": "png", "MoviePipelineImageSequenceOutput_JPG": "jpg",
               "MoviePipelineImageSequenceOutput_EXR": "exr", "MoviePipelineImageSequenceOutput_BMP": "bmp"}
PASS_NAMES = {"MoviePipelineDeferredPass_Unlit": "Unlit", "MoviePipelineDeferredPass_LightingOnly": "LightingOnly",
              "MoviePipelineDeferredPass_DetailLighting": "DetailLighting",
              "MoviePipelineDeferredPass_ReflectionsOnly": "ReflectionsOnly",
              "MoviePipelineObjectIdRenderPass": "ObjectId"}


class MrqState:
    def __init__(self):
        self.fail_at = None
        self.never_start = False
        self.hang = False
        self.frames_per_tick = 1
        self.jobs: list = []
        self.active = None  # [job record, next frame, end, ext list, executor]


def install(fake):
    O = fake.Object
    state = MrqState()
    fake.mrq = state

    class Setting(O):
        pass

    class ConsoleVariableSetting(Setting):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            object.__setattr__(self, "cvars", {})

        def add_or_update_console_variable(self, name, value):
            self.cvars[name] = value
            return True

    class PostProcessPass(O):
        pass

    class DeferredPassBase(Setting):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            passes = []
            for m in ("/MovieRenderPipeline/Materials/MovieRenderQueue_WorldDepth.MovieRenderQueue_WorldDepth",
                      "/MovieRenderPipeline/Materials/MovieRenderQueue_MotionVectors.MovieRenderQueue_MotionVectors"):
                p = PostProcessPass()
                p.set_editor_property("material", fake.SoftObjectPath(m))
                p.set_editor_property("enabled", False)
                passes.append(p)
            self.set_editor_property("additional_post_process_materials", passes)

    class PathTracer(DeferredPassBase):
        pass

    for cls, n in ((ConsoleVariableSetting, "MoviePipelineConsoleVariableSetting"),
                   (PostProcessPass, "MoviePipelinePostProcessPass"), (DeferredPassBase, "MoviePipelineDeferredPassBase"),
                   (PathTracer, "MoviePipelineDeferredPass_PathTracer")):
        cls.__name__ = cls.__qualname__ = n
        setattr(fake, n, cls)
    for n in ("MoviePipelineOutputSetting", "MoviePipelineAntiAliasingSetting", "MoviePipelineWaveOutput",
              *OUT_CLASSES, *PASS_NAMES):
        setattr(fake, n, type(n, (Setting,), {}))

    class Config(O):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            object.__setattr__(self, "settings", [])

        def find_setting_by_class(self, cls, include_disabled=False, exact_match=False):
            for s in self.settings:
                if (type(s) is cls) if exact_match else isinstance(s, cls):
                    return s
            return None

        def find_or_add_setting_by_class(self, cls, include_disabled=False, exact_match=False):
            s = self.find_setting_by_class(cls, include_disabled, exact_match)
            if s is None:
                s = cls()
                self.settings.append(s)
            return s

        def get_user_settings(self):
            return list(self.settings)

    class Job(O):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            object.__setattr__(self, "_config", Config())

        def get_configuration(self):
            return self._config

        def set_config_mode(self, mode):
            return True

    class Queue(O):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            object.__setattr__(self, "jobs", [])

        def allocate_new_job(self, cls):
            j = Job()
            self.jobs.append(j)
            return j

        def delete_all_jobs(self):
            self.jobs.clear()

        def get_jobs(self):
            return list(self.jobs)

    class Delegate:
        def __init__(self):
            self.fns = []

        def add_callable(self, fn):
            self.fns.append(fn)

    class Executor(O):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            object.__setattr__(self, "on_executor_errored_delegate", Delegate())
            object.__setattr__(self, "on_executor_finished_delegate", Delegate())
            object.__setattr__(self, "cancelled", False)

        def cancel_all_jobs(self):
            object.__setattr__(self, "cancelled", True)
            state.active = None

    fake.MoviePipelinePIEExecutor = type("MoviePipelinePIEExecutor", (Executor,), {})
    fake.MoviePipelineNewProcessExecutor = type("MoviePipelineNewProcessExecutor", (Executor,), {})
    fake.MoviePipelineExecutorJob = Job
    fake.MoviePipelineQueue = Queue

    class QueueSubsystem(O):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            object.__setattr__(self, "_queue", Queue())
            object.__setattr__(self, "_exe", None)

        def get_queue(self):
            return self._queue

        def get_active_executor(self):
            return self._exe

        def is_rendering(self):
            return state.active is not None

        def render_queue_with_executor(self, cls):
            exe = cls()
            object.__setattr__(self, "_exe", exe)
            job = self._queue.jobs[0]
            cfg = job.get_configuration()
            o = cfg.find_setting_by_class(fake.MoviePipelineOutputSetting)
            rec = {"executor": cls.__name__, "sequence": str(job.get_editor_property("sequence")),
                   "map": str(job.get_editor_property("map")), "name": job.get_editor_property("job_name"),
                   "settings": {type(s).__name__: s for s in cfg.settings}, "cfg": cfg}
            state.jobs.append(rec)
            if state.never_start:
                return exe
            if state.hang:
                state.active = "hang"
                return exe
            exts = [e for c, e in OUT_CLASSES.items() if cfg.find_setting_by_class(getattr(fake, c), exact_match=True)]
            start, end = o.get_editor_property("custom_start_frame"), o.get_editor_property("custom_end_frame")
            state.active = [rec, start, end, exts, exe]
            wav = cfg.find_setting_by_class(fake.MoviePipelineWaveOutput)
            if wav is not None:
                name = wav.get_editor_property("file_name_format_override")
                path = os.path.join(str(o.get_editor_property("output_directory").path), *str(name).split("/")) + ".wav"
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with wave.open(path, "wb") as w:
                    w.setnchannels(2)
                    w.setsampwidth(2)
                    w.setframerate(48000)
                    w.writeframes(b"\x01\x00\x02\x00" * int(48000 * (end - start) / 24))
            return exe

    fake.MoviePipelineQueueSubsystem = QueueSubsystem
    fake.get_default_object(fake.MoviePipelineInProcessExecutorSettings).set_editor_property(
        "additional_command_line_arguments", "")

    class DirectoryPath:
        def __init__(self, path=""):
            self.path = path

        def __str__(self):
            return self.path

    fake.DirectoryPath = DirectoryPath

    def _passes(cfg) -> list:
        names = ["FinalImage"]
        main = cfg.find_setting_by_class(DeferredPassBase)
        for p in main.get_editor_property("additional_post_process_materials") or []:
            if p.get_editor_property("enabled"):
                names.append(str(p.get_editor_property("material")).rsplit(".", 1)[-1])
        for c, n in PASS_NAMES.items():
            if cfg.find_setting_by_class(getattr(fake, c), exact_match=True):
                names.append(n)
        return names

    def tick(_dt):
        a = state.active
        if not isinstance(a, list):
            return
        rec, f, end, exts, exe = a
        cfg = rec["cfg"]
        o = cfg.find_setting_by_class(fake.MoviePipelineOutputSetting)
        root = str(o.get_editor_property("output_directory").path)
        fmt = o.get_editor_property("file_name_format")
        pad = o.get_editor_property("zero_pad_frame_numbers")
        for _ in range(state.frames_per_tick):
            if f >= end:
                break
            if state.fail_at is not None and f == state.fail_at:
                for fn in exe.on_executor_errored_delegate.fns:
                    fn(exe, None, True, "fake crash")
                state.active = None
                return
            for rp in _passes(cfg):
                name = fmt.replace("{render_pass}", rp).replace("{frame_number}", f"{f:0{pad}d}")
                for ext in exts:
                    path = os.path.join(root, *name.split("/")) + "." + ext
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "wb") as fh:
                        fh.write(DATA[ext])
            f += 1
        a[1] = f
        if f >= end:
            state.active = None

    fake.register_slate_post_tick_callback(tick)

    class LevelSequence(O):
        """A sequence with a playback range [start, end), a display rate and camera cuts [[label, start, end]]."""

        def __init__(self, name=None, outer=None, start=0, end=120, fps=24, cuts=None, **props):
            super().__init__(name, outer, **props)
            object.__setattr__(self, "_range", [start, end])
            object.__setattr__(self, "_fps", fps)
            object.__setattr__(self, "cuts", [list(c) for c in (cuts or [])])

        def get_playback_start(self):
            return self._range[0]

        def get_playback_end(self):
            return self._range[1]

        def get_display_rate(self):
            return fake.FrameRate(self._fps, 1)

    fake.LevelSequence = LevelSequence

    def add_sequence(path, start=0, end=120, fps=24, cuts=None):
        return fake.add_asset(path, LevelSequence, start=start, end=end, fps=fps, cuts=cuts)

    fake.add_sequence = add_sequence
