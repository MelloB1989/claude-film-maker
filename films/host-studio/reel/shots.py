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

# PLAN v2 (the operator's review, 2026-11-01): no shot singles out one object. The studio is revealed area by area in
# unhurried glides (shelves -> credenza and records -> window and olive -> slats and the unlit sign), the light falling
# from day to blue hour across them, then the whole room in one wide (the payoff), the sign igniting on the drop and
# the same wide at night; a night glide over the breakdown, and only then the presenters, with four short lines.
# Shot ids: kept ones keep their v1 id (their frames and renders stay valid where nothing changed); new ones are Vxx
# (the reveal) and N01 (the night glide). S14 is gone (his line is two words now).
GLIDE = "nothing centred, held on or racked to: the details pass by and the eye finds them"
SHOTS = [
    # ---------------------------------------------------------------- A/B. the reveal, area by area (bars 1-12)
    Shot("V01", "The shelves", bar(1), bar(4), 40, 2.0,
         "a slow crane down the four shelves, top board to bottom, 100 cm, drifting 25 cm screen-right to left and "
         "a little oblique, so the boards and their things stream up through the frame in parallax",
         [[0, [-90, -178, 250], [-250, -132, 226]], [180, [-90, -153, 150], [-250, -128, 140]]],
         "the shelves as a whole, the full 150 cm width, two to three boards tall at a time: books, vases, frames, "
         "the maker's things, the trailing pothos at frame left, the LED strips under each board; " + GLIDE,
         "DAY", "the morning sun raking across the boards", into="cut on bar 4",
         focus=[[0, 178], [90, 192], [180, 180]], previs=0.5, vcrop=0.5,
         sound="room tone, birds outside, the felt-piano motif"),
    Shot("V02", "The credenza", bar(4), bar(7), 40, 2.0,
         "slow lateral dolly along the credenza top, screen-right to left (the opposite way to V01), low, "
         "looking slightly down across it, 125 cm",
         [[0, [-115, -215, 118], [-245, -175, 84]], [180, [-115, -90, 110], [-245, -50, 82]]],
         "the credenza's top as a whole: the record crate, the calendar, the walnut block, headphones, the "
         "turntable, the hoodie's sleeve at the start; the shelves' LED glow above the frame; " + GLIDE,
         "GOLDEN", "the light warms as the sun drops", into="cut on bar 7",
         focus=[[0, 140], [100, 125], [180, 138]], previs=0.5, vcrop=0.5,
         sound="the first kick lands mid-glide (bar 5), the room waking up"),
    Shot("V03", "The window and the olive", bar(7), bar(9), 35, 2.8,
         "a rising lateral crane past the olive tree from 2.6 m, its crown crossing the glowing sheers, 55 cm across and 37 cm up",
         [[0, [40, 118, 128], [-220, 200, 128]], [120, [40, 172, 165], [-220, 214, 150]]],
         "the window and the olive as a whole: the sheers lit gold by the low sun, the leaves in silhouette and "
         "translucent against them, the pot and the light on the floor at the start",
         "GOLDEN", "the sun low and long through the sheers; the window holds detail", into="cut on bar 9",
         focus=[[0, 255], [120, 262]], previs=0.5, vcrop=0.45,
         sound="birds thinning outside, the sheers breathe"),
    Shot("V04", "The slats and the sign", bar(9), bar(11), 35, 2.8,
         "a slow crane up the slat wall, drifting screen-right, to the unlit sign; the sign arrives at the top of "
         "the frame, never centred, still dark",
         [[0, [-60, 70, 115], [-260, 35, 140]], [120, [-60, 45, 165], [-260, 15, 192]]],
         "the walnut slats in the last light, their rhythm filling the frame, the black karma letters arriving "
         "unlit at the top; the pothos' vines and the shelves' first LEDs at frame right",
         "DUSK", "the window cooling; the shelf LEDs coming up", into="cut on bar 11",
         focus=[[0, 205], [120, 205]], previs=1.0, vcrop=0.5,
         sound="crickets begin, a far city; the riser starts (bar 11 is next)"),
    Shot("V05", "The room", bar(11), bar(13), 28, 5.6,
         "the payoff: the first and only view of the whole studio before the drop: S02's push and settle "
         "(crane 172 to 150 cm, dolly in 45 cm), settling into the frame S12 holds at night",
         [[0, [300, -35, 172], [-260, 15, 142]], [120, [255, -35, 150], [-260, 15, 140]]],
         "the whole set at blue hour: the window blue, the olive, the slat wall and the dark sign centre, the "
         "shelves and the credenza glowing on their LEDs, the stool",
         "BLUE", "empty room; the last of the light", into="smash cut on the drop (bar 13)", previs=1.0, vcrop=0.5,
         sound="the riser, then silence on bar 12 beat 4 (the breath)"),
    # ---------------------------------------------------------------- C. ignition (bars 13-14): the drop
    Shot("S11", "The sign lights", bar(13), bar(14), 40, 4.0,
         "slow push-in from below, 60 cm, as the halo ignites letter by letter (k a r m a on beats 1-4, + 'a' on 4&)",
         [[0, [-40, 14, 150], [-256, 22, 228]], [60, [-95, 30, 170], [-256, 22, 228]]],
         "the slat wall and the black Samarkan letters in near dark, the warm halo flaring behind each in turn",
         "IGNITION", into="cut on bar 14", previs=1.0, vcrop=0.5,
         sound="the drop: a sub hit, a relay clunk and electrical hum per letter, the full beat comes in"),
    Shot("S12", "The studio comes on", bar(14), bar(15), 28, 5.6,
         "the V05 frame at night (a match), a slow 30 cm push",
         [[0, [300, -35, 165], [-260, 15, 140]], [60, [270, -35, 155], [-260, 15, 140]]],
         "the whole room at night: the sign lit, downlights popping on the beats (credenza, slats, olive, shelves), "
         "the window blue-black",
         "NIGHT", into="cut on bar 15", previs=1.0, vcrop=0.5, sound="four relay clicks on the beats"),
    # ---------------------------------------------------------------- D. night (bars 15-16), then him (bars 17-18)
    Shot("N01", "The shelves at night", bar(15), bar(17), 50, 2.0,
         "a night glide: from the lit sign's edge along the shelves, screen-left to right, 115 cm, slightly oblique "
         "so the boards' LED lines converge; the halo's spill leaves frame left",
         [[0, [-110, 20, 184], [-252, -55, 180]], [120, [-110, -95, 178], [-252, -170, 176]]],
         "the shelves at night: warm LED lines under each board, the things on them half silhouette, half lit, "
         "the downlight's pool, the blue-black window reflected in a frame's glass; " + GLIDE,
         "NIGHT", "the room at rest", into="cut on bar 17", focus=[[0, 140], [60, 156], [120, 144]], previs=0.5,
         vcrop=0.5, sound="the score's drumless breakdown; the halo's hum, crickets"),
    Shot("S13", "Him", bar(17), bar(19), 35, 2.8,
         "slow push, 30 cm; his key light ramps up on bar 17 beat 3 (12 frames): a light reveal",
         [[0, [230, 70, 152], [30, 40, 160]], [120, [200, 62, 156], [30, 40, 162]]],
         "him on his mark, a silhouette against the halo-lit slats, then lit; shelves soft screen-right",
         "NIGHT+KEY", "head down; lifts his gaze to the lens with the key light (bar 17 beat 3); L1 on bar 18 beat 1, "
         "then a small smirk held to the cut", into="cut on bar 19", cast=("him",), previs=1.0, vcrop=0.42,
         sound="the groove returns (bar 17); the key light's soft 'thunk'; VO L1"),
    # ---------------------------------------------------------------- E. the hand-off and her (bars 19-22)
    Shot("S15", "The hand-off", bar(19), bar(21), 85, 2.0,
         "near locked-off (a 7 cm drift) on his shoulder line; the focus pulls from him (195 cm) to her (304 cm) in 18 frames on bar 20",
         [[0, [220, 85, 165], [-10, -10, 163]], [120, [214, 80, 165], [-10, -10, 162]]],
         "him sharp in the foreground frame-left, her soft in the background frame-right by the shelves",
         "NIGHT+KEY", "he says L2 and turns his head to her; she looks up from him to the lens: L3a, a half-smile",
         into="cut on bar 21", focus=[[0, 195], [60, 195], [78, 304]], cast=("him", "her"), previs=0.5, vcrop=0.62,
         sound="VO L2 then L3a"),
    Shot("S16", "Her line", bar(21), bar(23), 65, 2.0,
         "medium close-up, a slow 10 cm push, the shelf LEDs as bokeh behind her",
         [[0, [110, -40, 158], [-50, -55, 156]], [120, [100, -42, 158], [-50, -55, 156]]],
         "her, chest up, hoops and watch, the shelves and their things soft behind",
         "NIGHT+KEY", "L3b to the lens, unhurried, a small tilt of the head on 'yourself'", into="cut on bar 23",
         cast=("her",), previs=0.5, vcrop=0.5, sound="VO L3b; the lift (bar 21)"),
    # ---------------------------------------------------------------- F. together, and the title (bars 23-26)
    Shot("S17", "Together", bar(23), bar(25), 28, 4.0,
         "crane up and back 150 cm into the wide, keeping the sign centred",
         [[0, [170, -5, 150], [-20, -5, 165]], [120, [320, -10, 195], [-100, -5, 172]]],
         "both on their marks under the sign, the whole studio at night opening up around them",
         "NIGHT+KEY", "him: L4a / her: L4b; a glance between them on 'comes around', then both to the lens, a small smile",
         into="cut on bar 25", cast=("him", "her"), previs=1.0, vcrop=0.5, sound="VO L4a, L4b; the theme's last phrase"),
    Shot("S18", "Title", bar(25), bar(27), 28, 4.0,
         "locked off on the end of S17; the practicals ease down, the halo holds; title type fades in",
         [[0, [320, -10, 195], [-100, -5, 172]], [120, [320, -10, 195], [-100, -5, 172]]],
         "the wide with the lit sign; the title over it (the karma wordmark, then \"a studio by MelloB\"), then a fade to black on the halo",
         "NIGHT-DIM", "both hold, a natural idle", into="fade to black (last 24 frames)", cast=("him", "her"),
         vcrop=0.5, sound="the final chord and a sub tail; the halo's hum fades last"),
]

# The voice lines (PLAN.md section 2): [id, who, first frame of the voice, last frame of the window, text]. Under 10 s
# of speech in all; nothing explains, everything teases.
LINES = [
    ["L1", "him", bar(18), bar(18, 4), "Took you long enough."],
    ["L2", "him", bar(19, 2), bar(19, 4) + 8, "Ask her what's next."],
    ["L3a", "her", bar(20, 2) + 3, bar(20, 4), "Nice try."],
    ["L3b", "her", bar(21, 2), bar(22, 3), "Some things you have to see for yourself."],
    ["L4a", "him", bar(23, 3), bar(23, 4) + 12, "What goes around…"],
    ["L4b", "her", bar(24, 1) + 6, bar(24, 4) + 8, "…comes around. That's karma."],
]

assert sum(s.frames for s in SHOTS) == SHOTS[-1].end == 26 * BAR
assert all(a.end == b.start for a, b in zip(SHOTS, SHOTS[1:]))
