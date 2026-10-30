import json

import numpy as np
import pytest

from filmtools import ambience
from filmtools.wav import SR, read_wav

SCENES = [{"id": "a", "start": 0.0, "end": 4.0}, {"id": "b", "start": 4.0, "end": 9.0}]


def film_with(film, doc, duration=10.0):
    (film.data / "timeline.json").write_text(json.dumps({"fps": 30, "duration": duration, "scenes": SCENES}))
    (film.data / "ambience.json").write_text(json.dumps(doc))


def run(film, *args):
    ambience.main(list(args))
    return read_wav(film.audio / "sfx" / "sfx.wav", mono=False)


def test_cli_writes_a_stereo_stem_the_length_of_the_film(film):
    film_with(film, {"seed": 3, "beds": [{"sound": "wind", "start": 0, "end": 10}],
                     "hits": [{"sound": "bell", "at": 2}]})
    y, sr = run(film)
    assert sr == SR and y.shape == (round(10.0 * SR), 2)


def test_same_seed_same_samples_other_seed_differs(film):
    doc = {"seed": 5, "beds": [{"sound": "sea", "start": 0, "end": 3}], "hits": [{"sound": "gull", "at": 1}]}
    a = ambience.render(doc, SCENES, 4.0)
    assert np.array_equal(a, ambience.render(doc, SCENES, 4.0))
    assert not np.array_equal(a, ambience.render({**doc, "seed": 6}, SCENES, 4.0))


@pytest.mark.parametrize("sound", ambience.HITS)
def test_a_hit_lands_at_its_time(sound):
    t = 2.0
    y = ambience.render({"hits": [{"sound": sound, "at": t, "gain_db": -6}]}, SCENES, 8.0)
    m = np.abs(y).max(axis=1)
    assert m[:int(t * SR) - 5].max() == 0
    first = np.argmax(m > 0.05 * m.max())
    assert abs(first / SR - t) < 0.010, (sound, first / SR)


def test_scene_relative_placement_resolves():
    y = ambience.render({"hits": [{"sound": "cup", "scene": "b", "offset": 0.5}],
                         "beds": [{"sound": "room_tone", "scene": "a", "until": "b", "fade": 0.1}]}, SCENES, 10.0)
    assert np.abs(y[int(9.1 * SR):]).max() == 0  # the bed ends with scene b (9 s)
    only_hit = ambience.render({"hits": [{"sound": "cup", "scene": "b", "offset": 0.5}]}, SCENES, 10.0)
    first = np.argmax(np.abs(only_hit).max(axis=1) > 0.01)
    assert abs(first / SR - 4.5) < 0.010
    bed = ambience.render({"beds": [{"sound": "rain", "scene": "a"}]}, SCENES, 10.0)
    assert np.abs(bed[int(4.1 * SR):]).max() == 0 and np.abs(bed[:int(4 * SR)]).max() > 0


def test_unknown_sound_and_scene_are_errors(film):
    with pytest.raises(ValueError, match="unknown sound 'kazoo'"):
        ambience.render({"hits": [{"sound": "kazoo", "at": 1}]}, SCENES, 5.0)
    with pytest.raises(ValueError, match="unknown sound"):
        ambience.render({"beds": [{"sound": "lava", "start": 0, "end": 1}]}, SCENES, 5.0)
    with pytest.raises(ValueError, match="unknown scene"):
        ambience.render({"hits": [{"sound": "cup", "scene": "zz"}]}, SCENES, 5.0)
    film_with(film, {"hits": [{"sound": "kazoo", "at": 1}]})
    with pytest.raises(SystemExit, match="kazoo"):
        ambience.main([])


def test_no_clipping_with_everything_loud():
    doc = {"beds": [{"sound": s, "start": 0, "end": 6, "gain_db": 0, "intensity": 1} for s in ambience.BEDS],
           "hits": [{"sound": s, "at": 1 + 0.1 * i, "gain_db": 0} for i, s in enumerate(ambience.HITS)]}
    y = ambience.render(doc, SCENES, 8.0)
    assert 0 < np.abs(y).max() <= 10 ** (-1.0 / 20)


@pytest.mark.parametrize("sound", ambience.BEDS)
def test_every_bed_is_audible_stereo_and_fades(sound):
    y = ambience.render({"beds": [{"sound": sound, "start": 0, "end": 8, "gain_db": -12, "fade": 2}]}, SCENES, 8.0)
    assert np.abs(y[SR * 3:SR * 5]).max() > 0.05
    assert np.abs(y[:200]).max() < 0.01 and np.abs(y[-200:]).max() < 0.01
    assert not np.array_equal(y[:, 0], y[:, 1])
