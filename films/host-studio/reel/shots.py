"""The karma launch reel's shot table: the one source for PLAN.md's shot list, the previs (previs.py) and, later, the
build of the reel's sequence. Units cm and frames (24 fps); the studio's frame (unreal/studio.py): the back wall at
x = -260, the camera side towards +X, screen-left +Y, up +Z.

Music: 96 bpm in 4/4, so a beat is exactly 15 frames and a bar 60 frames (2.5 s); 26 bars = 1560 frames = 65 s.
Every shot starts on a bar line (a cut on the downbeat) unless its `cut` says otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass, field

FPS, BPM = 24, 96
BEAT = FPS * 60 // BPM  # 15 frames
BAR = 4 * BEAT          # 60 frames
FULL_FRAME = (36.0, 20.25)  # every reel camera: a full-frame 16:9 back (look.camera's default, not the Super 35 trap)

WALL, SLAT_Y, SH_L, CR_C = -260.0, 25.0, -60.0, -135.0
SIGN = (WALL + 4, SLAT_Y, 228.0)  # the sign's centre: 120 cm across, ~36 cm tall, 4 cm off the slats
# The presenters' reel marks (feet), staggered in depth so a focus pull can hand the shot from him to her.
# In the scene today both stand at the origin (her hidden): the reel's sequence moves them with transform keys.
MARK_HIM, MARK_HER = (30.0, 40.0, 0.0), (-50.0, -55.0, 0.0)
EYES_HIM, EYES_HER = 174.0, 158.0
COIN, PICK = [-249.0, -169.0, 172.0], [-251.0, -186.0, 178.0]  # S06's rack: the coin's face, the pickaxe's head


def bar(n: int, beat: int = 1) -> int:
    """The frame of bar n (1-based), beat (1-based)."""
    return (n - 1) * BAR + (beat - 1) * BEAT


@dataclass
class Shot:
    id: str
    title: str
    start: int                 # first frame (inclusive)
    end: int                   # last frame (exclusive)
    lens: float                # focal length, mm (full frame)
    stop: float                # aperture, T
    move: str                  # the camera move, in words
    keys: list                 # [frame offset in the shot, [x, y, z], [x, y, z] looked at]
    frame: str                 # what is in frame
    light: str                 # the lighting state (LIGHT below)
    action: str = ""           # the presenters (or the set's own motion)
    into: str = "cut"          # the transition into the next shot
    focus: list = field(default_factory=list)  # [frame offset, distance cm | [x, y, z] to focus on]: a pull; empty = on the look-at
    cast: tuple = ()           # who is visible: "him", "her"
    vcrop: float = 0.5         # 9:16 cut: the crop window's centre across the 16:9 frame (0 left .. 1 right)
    previs: float | None = None  # where in the move (0..1) the previs still is taken; None = no previs
    sound: str = ""

    @property
    def frames(self) -> int:
        return self.end - self.start

    def at(self, u: float):
        """Camera location and look-at at a fraction u of the shot (linear between keys; enough for previs)."""
        t = u * self.frames
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1], ks[0][2]
        for (f0, l0, a0), (f1, l1, a1) in zip(ks, ks[1:]):
            if t <= f1:
                s = (t - f0) / (f1 - f0)
                return ([p + (q - p) * s for p, q in zip(l0, l1)], [p + (q - p) * s for p, q in zip(a0, a1)])
        return ks[-1][1], ks[-1][2]


# The lighting states the timeline moves through (keyed on one shared light track: each shot samples it at its time).
LIGHT = {
    "DAY": "late-morning sun (studio.py day: sun 28 deg, 30 klx), bright sheers, sign OFF, shelf LEDs low (1.3)",
    "GOLDEN": "the sun low and warm (8 deg, 3200 K, ~8 klx), long raking light through the sheers, sign OFF",
    "DUSK": "the sun just down (-3 deg), window cooling to blue, shelf LEDs come up (1.5), exposure opening up",
    "BLUE": "blue hour: window blue (studio.py night), the room lit by the shelf LEDs and the candle only, sign OFF",
    "IGNITION": "BLUE, then the halo comes on letter by letter on the beats; downlights still off",
    "NIGHT": "studio.py night: downlights on the credenza, slats, olive and shelves; halo on; window blue-black",
    "NIGHT+KEY": "NIGHT plus the presenters' key, fill, hair and rims (channel 1), ramped up for the reveal",
    "NIGHT-DIM": "NIGHT with the practicals easing down 30%: the halo and the presenters' rims carry the frame",
}

SHOTS = [
    # ---------------------------------------------------------------- A. morning (bars 1-4): no drums
    Shot("S01", "Light through the olive", bar(1), bar(3), 85, 2.0,
         "slow lateral truck (screen-right to left) through the olive's crown, 25 cm over 5 s",
         [[0, [-130, 165, 160], [-215, 200, 152]], [120, [-130, 188, 160], [-215, 222, 152]]],
         "olive leaves backlit by the sheers, the window's glow blooming between them; focus on the nearest twigs (~60 cm), exposure 1.5 stops under DAY so the window holds detail (the previs is blown out)",
         "DAY", "the leaves are still (static mesh); a faint dust drift in the volumetric fog",
         into="cut on bar 3", previs=0.5, vcrop=0.55,
         sound="room tone, birds outside, a felt-piano motif enters"),
    Shot("S02", "The room", bar(3), bar(5), 28, 5.6,
         "slow push and settle down: crane from 170 to 150 cm, dolly in 45 cm",
         [[0, [300, -35, 172], [-260, 15, 142]], [120, [255, -35, 150], [-260, 15, 140]]],
         "the whole set: sheers and olive left, slat wall and the unlit sign centre, shelves and credenza right, stool",
         "DAY", "empty room; sun patches on the rug", into="cut on bar 5 (first kick)", previs=1.0, vcrop=0.5,
         sound="the curtain breathes (soft air), a clock-like tick doubles the tempo"),
    # ---------------------------------------------------------------- B. the things (bars 5-12): one bar each
    Shot("S03", "Seven spines", bar(5), bar(6), 85, 5.6,
         "macro slider parallel to the shelf, 44 cm screen-left to right along the green spines",
         [[0, [-181, -100, 212], [-236, -104, 211]], [60, [-181, -144, 212], [-236, -148, 211]]],
         "the seven dark-green spines, titles reading bottom to top: Socify, Noobsverse, Lyzn, Avidia, Respawn, "
         "Noobspaces, Noobs Learning; cloth texture, gilt titles", "GOLDEN", into="cut", previs=0.5, vcrop=0.5,
         sound="a finger along book cloth, a soft kick lands with the cut"),
    Shot("S04", "V and the heart", bar(6), bar(7), 85, 4.0,
         "slow push-in, 12 cm, with a rack from the vase behind to the polaroid",
         [[0, [-185, -140, 214], [-239, -163, 205]], [60, [-196, -147, 210], [-239, -163, 205]]],
         "the polaroid (the V and the heart) leaning on the books, the speckled vase soft behind it",
         "GOLDEN", into="cut", focus=[[0, 73], [36, 47]], previs=1.0, vcrop=0.5,
         sound="a polaroid's soft flick"),
    Shot("S05", "lyzn", bar(7), bar(8), 65, 4.0,
         "orbit around the acrylic block, 35 deg at 50 cm radius, the sun's glint crawling across its edge",
         [[0, [-196.7, -179.1, 208], [-245, -192, 205]], [30, [-195.4, -193.6, 208], [-245, -192, 205]],
          [60, [-198.0, -209.1, 208], [-245, -192, 205]]],
         "the frosted lyzn block, its engraved word catching the light, the shelf LED strip a line of bokeh above",
         "GOLDEN", into="cut", previs=0.5, vcrop=0.5, sound="a glassy tick on beat 3"),
    Shot("S06", "The coin and the pickaxe", bar(8), bar(9), 65, 4.0,
         "low push at shelf height, 11 cm, focus racks from the coin to the pickaxe on beat 3",
         [[0, [-190, -160, 170], [-250, -178, 174]], [60, [-200, -165, 170], [-250, -178, 174]]],
         "the coin on its walnut stand in front, the brass pickaxe behind; the candle's flame soft at frame left",
         "GOLDEN", into="cut", focus=[[0, COIN], [30, COIN], [42, PICK]], previs=0.6, vcrop=0.45,
         sound="a coin's ring (a single ping on beat 1), a mined 'tink' on the rack"),
    Shot("S07", "The drone", bar(9), bar(10), 50, 4.0,
         "crane down from a three-quarter top view to eye level with the gimbal, ending on its red LED",
         [[0, [-222, -124, 205], [-247.5, -124, 165]], [60, [-212, -116, 178], [-247.5, -124, 167]]],
         "the mini drone on the shelf, props folded, the gimbal lens and the red front LED",
         "DUSK", into="cut", previs=0.7, vcrop=0.5, sound="a gimbal servo whirr, an LED blip on beat 4"),
    Shot("S08", "hello, friend", bar(10), bar(11), 65, 4.0,
         "pedestal down and slight truck from the red print to the terminal's root prompt",
         [[0, [-195, -100, 150], [-254, -110, 140]], [60, [-200, -90, 133], [-248, -82, 129]]],
         "the framed red print, then the slim terminal display: root@mellob:~# and its cursor",
         "DUSK", "the terminal's cursor blinks on the beat (material param, new)", into="cut", previs=1.0,
         vcrop=0.5, sound="three keystrokes, a cursor tick per beat"),
    Shot("S09", "27 NOV", bar(11), bar(12), 50, 2.8,
         "a slow 8 cm drift, focus racking from the MelloB block (foreground) to the 27 NOV calendar",
         [[0, [-170, -95, 84], [-224, -143, 78]], [60, [-173, -99, 83], [-224, -143, 78]]],
         "the walnut MelloB nameplate soft in the foreground, the calendar's 27 NOV pulling sharp behind",
         "DUSK", into="cut", focus=[[0, 60], [24, 60], [40, 100]], previs=1.0, vcrop=0.6,
         sound="a calendar page settling"),
    Shot("S10", "The crate", bar(12), bar(13), 65, 4.0,
         "push-in 30 cm into the crate's front sleeve, ending on the name KARMA in its artist list",
         [[0, [-150, -150, 100], [-232, -157, 92]], [60, [-182, -154, 96], [-232, -157, 90]]],
         "the walnut crate of LPs: SEEDHE MAUT, KR$NA, RAFTAAR, KARMA, BELLA on the front sleeve",
         "BLUE", "the shelf LEDs carry the frame; the window goes blue behind", into="smash cut on the drop (bar 13)",
         previs=1.0, vcrop=0.5, sound="needle drop and vinyl crackle, a riser, then silence on beat 4 (+)"),
    # ---------------------------------------------------------------- C. ignition (bars 13-14): the drop
    Shot("S11", "The sign lights", bar(13), bar(14), 40, 4.0,
         "slow push-in from below, 60 cm, as the halo ignites letter by letter (k a r m a on beats 1-4, + 'a' on 4&)",
         [[0, [-40, 14, 150], [-256, 22, 228]], [60, [-95, 30, 170], [-256, 22, 228]]],
         "the slat wall and the black Samarkan letters in near dark, the warm halo flaring behind each in turn",
         "IGNITION", into="cut on bar 14", previs=1.0, vcrop=0.5,
         sound="the drop: a sub hit, a relay clunk and electrical hum per letter, the full beat comes in"),
    Shot("S12", "The studio comes on", bar(14), bar(15), 28, 5.6,
         "the S02 frame at night (a match), a slow 30 cm push",
         [[0, [300, -35, 165], [-260, 15, 140]], [60, [270, -35, 155], [-260, 15, 140]]],
         "the whole room at night: the sign lit, downlights popping on the beats (credenza, slats, olive, shelves)",
         "NIGHT", into="cut on bar 15", previs=1.0, vcrop=0.5, sound="four relay clicks on the beats"),
    # ---------------------------------------------------------------- D. him (bars 15-18)
    Shot("S13", "Him", bar(15), bar(17), 35, 2.8,
         "slow push, 30 cm; his key light ramps up on bar 16 beat 1 (12 frames): a light reveal",
         [[0, [230, 70, 152], [30, 40, 160]], [120, [200, 62, 156], [30, 40, 162]]],
         "him on his mark, a silhouette against the halo-lit slats, then lit; shelves soft screen-right",
         "NIGHT+KEY", "head down, lifts his gaze to the lens on bar 16 beat 1, starts line 1 on beat 3",
         into="cut on bar 17", cast=("him",), previs=1.0, vcrop=0.42, sound="the key light's soft 'thunk'; VO L1"),
    Shot("S14", "His line", bar(17), bar(19), 65, 2.0,
         "medium close-up, a 6 degree arc and a 10 cm push while he speaks",
         [[0, [175, 58, 172], [30, 40, 170]], [120, [165, 46, 172], [30, 40, 170]]],
         "him, chest up, the sign's halo behind his shoulder, eyes on the lens (gaze lock)",
         "NIGHT+KEY", "line 1 continues, one open-hand gesture", into="cut on bar 19", cast=("him",), previs=0.5,
         vcrop=0.5, sound="VO L1, music ducks 6-9 dB"),
    # ---------------------------------------------------------------- E. the hand-off and her (bars 19-22)
    Shot("S15", "The hand-off", bar(19), bar(21), 85, 2.0,
         "near locked-off (a 7 cm drift) on his shoulder line; the focus pulls from him (195 cm) to her (304 cm) in 18 frames on bar 20",
         [[0, [220, 85, 165], [-10, -10, 163]], [120, [214, 80, 165], [-10, -10, 162]]],
         "him sharp in the foreground frame-left, her soft in the background frame-right by the shelves",
         "NIGHT+KEY", "he says L2 and turns his head to her; she looks up from him to the lens and starts L3",
         into="cut on bar 21", focus=[[0, 195], [60, 195], [78, 304]], cast=("him", "her"), previs=0.5, vcrop=0.62,
         sound="VO L2 then L3"),
    Shot("S16", "Her line", bar(21), bar(23), 65, 2.0,
         "medium close-up, a slow 10 cm push, the shelf LEDs as bokeh behind her",
         [[0, [110, -40, 158], [-50, -55, 156]], [120, [100, -42, 158], [-50, -55, 156]]],
         "her, chest up, hoops and watch, the shelves and their things soft behind",
         "NIGHT+KEY", "line 3 continues; a small gesture with the watch hand", into="cut on bar 23", cast=("her",),
         previs=0.5, vcrop=0.5, sound="VO L3"),
    # ---------------------------------------------------------------- F. together, and the title (bars 23-26)
    Shot("S17", "Together", bar(23), bar(25), 28, 4.0,
         "crane up and back 150 cm into the wide, keeping the sign centred",
         [[0, [170, -5, 150], [-20, -5, 165]], [120, [320, -10, 195], [-100, -5, 172]]],
         "both on their marks under the sign, the whole studio opening up around them",
         "NIGHT+KEY", "him: 'Welcome' / her: 'to karma.'; both settle, a small smile to the lens",
         into="cut on bar 25", cast=("him", "her"), previs=1.0, vcrop=0.5, sound="VO L4, the theme's last phrase"),
    Shot("S18", "Title", bar(25), bar(27), 28, 4.0,
         "locked off on the end of S17; the practicals ease down, the halo holds; title type fades in",
         [[0, [320, -10, 195], [-100, -5, 172]], [120, [320, -10, 195], [-100, -5, 172]]],
         "the wide with the lit sign; the title over it (the karma wordmark, then \"a studio by MelloB\"), then a fade to black on the halo",
         "NIGHT-DIM", "both hold, a natural idle", into="fade to black (last 24 frames)", cast=("him", "her"),
         vcrop=0.5, sound="the final chord and a sub tail; the halo's hum fades last"),
]

assert sum(s.frames for s in SHOTS) == SHOTS[-1].end == 26 * BAR
assert all(a.end == b.start for a, b in zip(SHOTS, SHOTS[1:]))
